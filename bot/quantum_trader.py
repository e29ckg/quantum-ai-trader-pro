import os
import time
import MetaTrader5 as mt5
import pandas as pd
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

# นำเข้าเครื่องมือทั้งหมดที่เราสร้างไว้
from mt5_engine.connect import connect_mt5, get_account_info
from mt5_engine.data_feed import get_candles
from mt5_engine.trade_executor import send_order
from ai_engine.market_structure import detect_trend
from ai_engine.strategy_selector import choose_strategy
from ai_engine.liquidity_ai import liquidity_filter
from ai_engine.prediction_ai import predict_probability, update_brain_daily
from risk_manager.risk_control import calculate_lot_size
from risk_manager.trailing_stop import manage_dynamic_trailing_stop
from database.db import save_new_trade
from utils.telegram_notifier import send_telegram_message

# นำเข้าฟังก์ชันดึงค่าจาก DB
from database.db import get_bot_settings_db

# โหลดค่าจากไฟล์ .env
load_dotenv()

# ==========================================
# ⚙️ ตั้งค่าพื้นฐานเริ่มต้น
# ==========================================
tf_map = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1
}
env_timeframe = os.getenv("TRADE_TIMEFRAME", "M15").upper()
TIMEFRAME = tf_map.get(env_timeframe, mt5.TIMEFRAME_M15)

live_signals = {}
last_summary_date = None

# ==========================================
# 🥷 3 ท่าไม้ตาย: ระบบปิดออเดอร์ (Golden Exit)
# ==========================================
def close_mt5_position(position, comment="AI Reversal"):
    """ปิดออเดอร์แบบฉุกเฉิน ทิ้งของทันที (Market Close)"""
    tick = mt5.symbol_info_tick(position.symbol)
    if not tick: return False
    
    # สลับคำสั่งเพื่อปิด (BUY ให้ SELL ทิ้ง, SELL ให้ BUY คืน)
    action_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if action_type == mt5.ORDER_TYPE_SELL else tick.ask
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": position.ticket,
        "symbol": position.symbol,
        "volume": position.volume,
        "type": action_type,
        "price": price,
        "deviation": 20,
        "magic": 100,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

def apply_break_even(position, df):
    """เลื่อนเส้น Stop Loss มาบังหน้าทุน (ทุนปลอดภัย 100%) เมื่อกำไรเกิน 1.5 ATR"""
    # คำนวณความผันผวน (ATR)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    
    current_close = df['close'].iloc[-1]
    entry = position.price_open
    sl = position.sl
    
    profit_distance = 1.5 * atr
    request = None
    
    # เลื่อนบังทุนฝั่ง BUY
    if position.type == mt5.ORDER_TYPE_BUY:
        if current_close > entry + profit_distance and sl < entry:
            request = {"action": mt5.TRADE_ACTION_SLTP, "position": position.ticket, "symbol": position.symbol, "sl": entry, "tp": position.tp}
    # เลื่อนบังทุนฝั่ง SELL
    elif position.type == mt5.ORDER_TYPE_SELL:
        if current_close < entry - profit_distance and (sl > entry or sl == 0.0):
            request = {"action": mt5.TRADE_ACTION_SLTP, "position": position.ticket, "symbol": position.symbol, "sl": entry, "tp": position.tp}
            
    if request:
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"🛡️ [Break-Even] ตลาดเป็นใจ! เลื่อน SL บังหน้าทุนให้ {position.symbol} ทุนปลอดภัย 100% แล้ว!")

def sync_manual_order_to_db(pos):
    """ฟังก์ชันจดบันทึกออเดอร์เปิดมือ พร้อมระบบ Auto-Patch Database"""
    try:
        conn = sqlite3.connect("quantum_bot.db")
        cursor = conn.cursor()
        
        # 🛠️ [Auto-Patch] สั่งให้มันลองสร้างคอลัมน์ time ดู ถ้ายังไม่มีมันจะสร้างให้ทันที!
        try:
            cursor.execute("ALTER TABLE trade_history ADD COLUMN time TEXT")
            conn.commit()
            print("🛠️ [DB Upgrade] สร้างคอลัมน์ 'time' ในฐานข้อมูลสำเร็จแล้ว!")
        except:
            pass # ถ้ามีคอลัมน์อยู่แล้ว คำสั่งนี้จะ error เงียบๆ แล้วทำงานต่อได้เลย
            
        # เช็คว่าเลข Ticket นี้มีในฐานข้อมูลหรือยัง?
        cursor.execute("SELECT ticket_id FROM trade_history WHERE ticket_id = ?", (pos.ticket,))
        if not cursor.fetchone():
            # ถ้ายังไม่มี แปลว่าเพิ่งเปิดมือ!
            trade_type = "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell"
            
            # แปลงเวลาจาก MT5
            trade_time = datetime.fromtimestamp(pos.time).strftime('%Y-%m-%d %H:%M:%S')
            
            # บันทึกข้อมูลลงฐานข้อมูล
            cursor.execute('''
                INSERT INTO trade_history (ticket_id, symbol, trade_type, entry_price, status, time)
                VALUES (?, ?, ?, ?, 'OPEN', ?)
            ''', (pos.ticket, pos.symbol, trade_type, pos.price_open, trade_time))
            
            conn.commit()
            print(f"📥 [DB Sync] ตรวจพบออเดอร์เปิดมือ (Ticket: {pos.ticket}) ดึงเข้า Dashboard เรียบร้อย!")
            
        conn.close()
    except Exception as e:
        print(f"⚠️ [DB Sync Error]: {e}")

# ==========================================
# 📊 ระบบส่งรายงานสรุปยอดประจำวัน
# ==========================================
def send_daily_summary(active_symbols: list):
    global last_summary_date
    now = datetime.now()
    if now.hour == 23 and last_summary_date != now.date():
        start_of_day = datetime(now.year, now.month, now.day)
        end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59)
        deals = mt5.history_deals_get(start_of_day, end_of_day)
        total_profit = 0.0
        total_trades = 0
        win_trades = 0
        if deals:
            for deal in deals:
                if deal.entry == 1: 
                    net_profit = deal.profit + deal.swap + deal.commission
                    total_profit += net_profit
                    total_trades += 1
                    if net_profit > 0: win_trades += 1
                        
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
        emoji = "🟢" if total_profit >= 0 else "🔴"
        msg = (
            f"📊 <b>สรุปผลประกอบการ (Daily Report)</b>\n"
            f"📈 <b>ออเดอร์:</b> {total_trades} ไม้\n"
            f"🏆 <b>Win Rate:</b> {win_rate:.1f}%\n"
            f"💰 <b>Net Profit:</b> {emoji} <b>${total_profit:.2f}</b>"
        )
        send_telegram_message(msg)
        last_summary_date = now.date()
        
        # Night School (เรียนเสริมรอบดึก)
        for symbol in active_symbols:
            df_today = get_candles(symbol, TIMEFRAME, bars=500)
            if df_today is not None: update_brain_daily(df_today, symbol)

# ==========================================
# 🧠 วัฏจักรการทำงานหลัก (Main Loop)
# ==========================================
def run_bot_cycle(ai_confidence: float, risk_percent: float, active_symbols: list):
    send_daily_summary(active_symbols)
    target_confidence_percent = ai_confidence * 100 
    
    for symbol in active_symbols:
        if symbol not in live_signals:
            live_signals[symbol] = {"signal": "WAIT", "buy_prob": 0.0, "sell_prob": 0.0}

        # 1. ระบบรักษาความปลอดภัย: เลื่อน Trailing Stop (ทำตลอดเวลา)
        manage_dynamic_trailing_stop(symbol, timeframe=TIMEFRAME, atr_multiplier=2.0)

        # 2. ดึงกราฟมาวิเคราะห์ "ทุกรอบ" (แก้ปัญหา WAIT 0.0% หน้าเว็บ)
        df = get_candles(symbol, TIMEFRAME, bars=200)
        if df is None:
            continue

        # 3. AI ประมวลผลสถานการณ์ปัจจุบัน
        trend = detect_trend(df)
        raw_signal = choose_strategy(trend)
        liq_signal = liquidity_filter(df, raw_signal)
        
        prob = 0.5
        if liq_signal != "hold":
            prob = predict_probability(df, symbol)
            
        buy_prob = prob * 100
        sell_prob = (1 - prob) * 100

        # ส่งค่าขึ้นไปโชว์ที่ Dashboard
        live_signals[symbol] = {
            "signal": liq_signal.upper() if liq_signal != "hold" else "HOLD",
            "buy_prob": buy_prob,
            "sell_prob": sell_prob
        }

        print(f"[{time.strftime('%H:%M:%S')}] 🔍 {symbol} | SMC: {liq_signal.upper()} | AI BUY: {buy_prob:.1f}% | AI SELL: {sell_prob:.1f}% | 🎯 เป้า: {target_confidence_percent:.1f}%")

        # ==========================================
        # 🛡️ โซนจัดการออเดอร์ (เมื่อมีของอยู่ในมือ)
        # ==========================================
        positions = mt5.positions_get(symbol=symbol)
        if positions is not None and len(positions) > 0:
            
            # 🌟 [แก้ไขใหม่] วนลูปดูแลทุกออเดอร์ที่ค้างอยู่ (ทั้งบอทเปิด และลูกพี่เปิดมือ)
            for pos in positions:
                # 🌟 [เพิ่มใหม่] สั่งให้บอทจดบันทึกออเดอร์มือลงฐานข้อมูลก่อน!
                sync_manual_order_to_db(pos)
                # ท่าไม้ตายที่ 1: เลื่อน SL บังทุน (Break-Even)
                apply_break_even(pos, df)
                
                # ท่าไม้ตายที่ 2: ชิงเผ่นหนีตาย (AI Reversal Exit)
                close_trade = False
                if pos.type == mt5.ORDER_TYPE_BUY and liq_signal in ["sell", "strong_sell"] and sell_prob >= target_confidence_percent:
                    close_trade = True
                elif pos.type == mt5.ORDER_TYPE_SELL and liq_signal in ["buy", "strong_buy"] and buy_prob >= target_confidence_percent:
                    close_trade = True
                    
                if close_trade:
                    if close_mt5_position(pos, comment="AI Reversal"):
                        msg = (
                            f"🥷 <b>AI REVERSAL EXIT (หนีตาย)</b> 🥷\n\n"
                            f"💱 <b>Symbol:</b> {symbol} (Ticket: {pos.ticket})\n"
                            f"🚨 <b>Reason:</b> กราฟเปลี่ยนทิศ บอทชิงปิดไม้หนีตาย!\n"
                            f"⏱️ <b>Time:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        send_telegram_message(msg)
                        print(f"🚨 [AI Reversal] สั่งปิด {symbol} (Ticket: {pos.ticket}) หนีตายเรียบร้อย!")
            
            # เมื่อจัดการออเดอร์เก่าเสร็จ ก็ให้ข้ามการเปิดออเดอร์ใหม่ไปก่อน (ไม่เปิดซ้อน)
            continue

        # ==========================================
        # 🚀 โซนยิงออเดอร์ใหม่ (เมื่อมือว่าง)
        # ==========================================
        final_signal = None
        if liq_signal in ["buy", "strong_buy"] and buy_prob >= target_confidence_percent:
            final_signal = liq_signal
        elif liq_signal in ["sell", "strong_sell"] and sell_prob >= target_confidence_percent:
            final_signal = liq_signal

        if final_signal:
            account = get_account_info()
            if not account: continue
                
            raw_lot = calculate_lot_size(account["balance"], risk_percentage=risk_percent)
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None: continue
                
            min_lot, step_lot = symbol_info.volume_min, symbol_info.volume_step
            lot = round(max(raw_lot, min_lot) / step_lot) * step_lot
            
            result = send_order(symbol, final_signal, lot)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                save_new_trade(result.order, symbol, final_signal, result.price)
                msg = (
                    f"🚨 <b>QUANTUM AI EXECUTED</b> 🚨\n\n"
                    f"🎯 <b>Signal:</b> {final_signal.upper()}\n"
                    f"💱 <b>Symbol:</b> {symbol}\n"
                    f"💰 <b>Entry:</b> {result.price}\n"
                    f"📦 <b>Lot:</b> {lot} (Risk: {risk_percent}%)\n"
                    f"⏱️ <b>Time:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                send_telegram_message(msg)


if __name__ == "__main__":
    print("🤖 กำลังปลุก Quantum AI Trader PRO...")
    if connect_mt5():
        try:
            while True:
                settings = get_bot_settings_db()
                active_symbols = [s.strip() for s in settings.symbols.split(",") if s.strip()]
                run_bot_cycle(settings.confidence, settings.risk_percent, active_symbols) 
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n🛑 หยุดการทำงานของบอทด้วยผู้ใช้")
            mt5.shutdown()