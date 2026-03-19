import os
import time
import MetaTrader5 as mt5
import pandas as pd
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

# นำเข้าเครื่องมือทั้งหมดที่เราสร้างไว้ (🌟 เพิ่ม update_symbol_config เข้ามาด้วย)
from database.db import save_new_trade, get_bot_settings_db, get_symbol_config, update_symbol_config
from mt5_engine.connect import connect_mt5, get_account_info
from mt5_engine.data_feed import get_candles
from mt5_engine.trade_executor import send_order
from ai_engine.market_structure import detect_trend
from ai_engine.strategy_selector import choose_strategy
from ai_engine.liquidity_ai import liquidity_filter
from ai_engine.prediction_ai import predict_probability, update_brain_daily
from risk_manager.risk_control import calculate_lot_size
from risk_manager.trailing_stop import manage_dynamic_trailing_stop
from utils.telegram_notifier import send_telegram_message

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

def apply_break_even(position, df, break_even_mult=1.5):
    """เลื่อนเส้น Stop Loss มาบังหน้าทุน (ทุนปลอดภัย 100%) ตามค่าที่ตั้งไว้"""
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    
    current_close = df['close'].iloc[-1]
    entry = position.price_open
    sl = position.sl
    
    profit_distance = break_even_mult * atr
    request = None
    
    if position.type == mt5.ORDER_TYPE_BUY:
        if current_close > entry + profit_distance and sl < entry:
            request = {"action": mt5.TRADE_ACTION_SLTP, "position": position.ticket, "symbol": position.symbol, "sl": entry, "tp": position.tp}
    elif position.type == mt5.ORDER_TYPE_SELL:
        if current_close < entry - profit_distance and (sl > entry or sl == 0.0):
            request = {"action": mt5.TRADE_ACTION_SLTP, "position": position.ticket, "symbol": position.symbol, "sl": entry, "tp": position.tp}
            
    if request:
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"🛡️ [Break-Even] ตลาดเป็นใจ! เลื่อน SL บังหน้าทุนให้ {position.symbol} ทุนปลอดภัย 100% แล้ว!")

def sync_manual_order_to_db(pos):
    """ฟังก์ชันจดบันทึกออเดอร์เปิดมือ (ใช้วันเวลาที่บันทึกลงระบบ)"""
    try:
        conn = sqlite3.connect("quantum_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT ticket_id FROM trade_history WHERE ticket_id = ?", (pos.ticket,))
        if not cursor.fetchone():
            trade_type = "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell"
            record_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                INSERT INTO trade_history (ticket_id, symbol, trade_type, entry_price, status, timestamp)
                VALUES (?, ?, ?, ?, 'OPEN', ?)
            ''', (pos.ticket, pos.symbol, trade_type, pos.price_open, record_time))
            conn.commit()
            print(f"📥 [DB Sync] ตรวจพบออเดอร์เปิดมือ (Ticket: {pos.ticket}) แสตมป์เวลาบันทึก: {record_time} เรียบร้อย!")
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
        
        for symbol in active_symbols:
            df_today = get_candles(symbol, TIMEFRAME, bars=500)
            if df_today is not None: update_brain_daily(df_today, symbol)

def check_and_notify_closed_trades():
    """ฟังก์ชันดักจับออเดอร์ที่ชน TP, ชน SL หรือปิดมือ แล้วส่งแจ้งเตือน"""
    try:
        conn = sqlite3.connect("quantum_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT ticket_id, symbol, trade_type, entry_price FROM trade_history WHERE status = 'OPEN'")
        open_trades = cursor.fetchall()
        
        for trade in open_trades:
            ticket_id, symbol, trade_type, entry_price = trade
            pos = mt5.positions_get(ticket=ticket_id)
            
            if pos is None or len(pos) == 0:
                deals = mt5.history_deals_get(position=ticket_id)
                if deals and len(deals) > 0:
                    net_profit = sum(d.profit + d.swap + d.commission for d in deals)
                    cursor.execute("UPDATE trade_history SET status = 'CLOSED', profit = ? WHERE ticket_id = ?", (net_profit, ticket_id))
                    conn.commit()
                    
                    emoji = "🟢" if net_profit >= 0 else "🔴"
                    profit_sign = "+" if net_profit >= 0 else ""
                    close_type = "TAKE PROFIT (TP) 🏆" if net_profit > 0 else "STOP LOSS (SL) 🛡️"
                    
                    msg = (
                        f"🏁 <b>TRADE CLOSED ({close_type})</b> 🏁\n\n"
                        f"💱 <b>Symbol:</b> {symbol} (Ticket: #{ticket_id})\n"
                        f"📦 <b>Type:</b> {trade_type.upper()}\n"
                        f"📥 <b>Entry Price:</b> {entry_price:.5f}\n"
                        f"💰 <b>Net Profit:</b> {emoji} <b>{profit_sign}${net_profit:.2f}</b>\n"
                        f"⏱️ <b>Time:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    send_telegram_message(msg)
                    print(f"🏁 [Trade Closed] {symbol} (Ticket: #{ticket_id}) ปิดออเดอร์แล้ว | PnL: {profit_sign}${net_profit:.2f}")
        conn.close()
    except Exception as e:
        print(f"⚠️ [Check Closed Trades Error]: {e}")


# ==========================================
# 🧠 วัฏจักรการทำงานหลัก (Main Loop) - V4.1 (Defense + Add-On)
# ==========================================
def run_bot_cycle(active_symbols: list):
    send_daily_summary(active_symbols)
    check_and_notify_closed_trades()

    global_settings = get_bot_settings_db()
    now_time = datetime.now().time()
    start_time = datetime.strptime(global_settings.trade_start_time, "%H:%M").time()
    end_time = datetime.strptime(global_settings.trade_end_time, "%H:%M").time()
    
    is_trading_time = False
    if start_time <= end_time:
        is_trading_time = start_time <= now_time <= end_time
    else:
        is_trading_time = now_time >= start_time or now_time <= end_time
        
    # 🌟🌟🌟 ตั้งค่าโควต้า Add-On 🌟🌟🌟
    MAX_TOTAL_POSITIONS = 2 # จำนวนออเดอร์สูงสุดต่อ 1 เหรียญ (ไม้หลัก 1 + ไม้ Add-on 1)
    
    for symbol in active_symbols:
        sym_config = get_symbol_config(symbol)

        # ดึงกราฟมาก่อน
        df = get_candles(symbol, TIMEFRAME, bars=200)
        if df is None or df.empty:
            continue

        regime_text = "SCANNING..."

        # คำนวณ TR (True Range) 
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # 🤖🤖🤖 ระบบสมองกลปรับค่าอัตโนมัติ (Dynamic Auto-Tune) 🤖🤖🤖
        atr_14 = tr.rolling(14).mean().iloc[-1]
        atr_50 = tr.rolling(50).mean().iloc[-1]
        ema_20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema_50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        
        is_high_vol = atr_14 > (atr_50 * 1.2)
        trend_dist = abs(ema_20 - ema_50) / ema_50
        is_strong_trend = trend_dist > 0.002
        
        # 🌟 สร้างคำอธิบายสภาวะตลาด
        t_str = "🔥 STRONG TREND" if is_strong_trend else "💤 SIDEWAY"
        v_str = "🌊 HIGH VOL" if is_high_vol else "🧊 LOW VOL"
        regime_text = f"{t_str} | {v_str}"
        
        if sym_config.get('auto_tune', False):
            # 🌟 ดึงค่าจาก Database ของใครของมัน
            if is_strong_trend:
                sym_config['confidence'] = sym_config['at_trend_strong_conf']
                sym_config['rr_ratio'] = sym_config['at_trend_strong_rr']
            else:
                sym_config['confidence'] = sym_config['at_trend_weak_conf']
                sym_config['rr_ratio'] = sym_config['at_trend_weak_rr']
                
            if is_high_vol:
                sym_config['atr_sl'] = sym_config['at_vol_high_atr_sl']
                sym_config['break_even'] = sym_config['at_vol_high_be']
            else:
                sym_config['atr_sl'] = sym_config['at_vol_low_atr_sl']
                sym_config['break_even'] = sym_config['at_vol_low_be']
                
            # อัปเดตค่าลง Database
            from database.db import update_symbol_config
            update_symbol_config(symbol, sym_config)
        # 🤖🤖🤖 จบระบบ Auto-Tune 🤖🤖🤖

        # ดึงตัวแปรมาใช้งาน
        target_confidence_percent = sym_config["confidence"]
        risk_percent = sym_config["risk_percent"]
        atr_mult = sym_config["atr_sl"]
        rr_ratio = sym_config["rr_ratio"]
        break_even_mult = sym_config["break_even"]

        # โยน atr_mult ไปให้ Trailing Stop
        manage_dynamic_trailing_stop(symbol, timeframe=TIMEFRAME, atr_multiplier=atr_mult)

        # AI ประมวลผลสถานการณ์ปัจจุบัน
        trend = detect_trend(df)
        raw_signal = choose_strategy(trend)
        liq_signal = liquidity_filter(df, raw_signal)
        
        prob = 0.5
        if liq_signal != "hold":
            prob = predict_probability(df, symbol)
            
        buy_prob = prob * 100
        sell_prob = (1 - prob) * 100

        # โชว์สถานะ SLEEP ถ้านอกเวลาเทรด
        display_signal = liq_signal.upper() if liq_signal != "hold" else "HOLD"
        if not is_trading_time:
            display_signal = "SLEEP 💤"
            regime_text = "MARKET CLOSED"

        # ส่งค่าขึ้นไปโชว์ที่ Dashboard
        live_signals[symbol] = {
            "signal": display_signal,
            "buy_prob": buy_prob,
            "sell_prob": sell_prob,
            "regime": regime_text
        }

        # โชว์ใน Console (Terminal)
        mode_str = "🤖 [AUTO]" if sym_config.get('auto_tune', False) else "⚙️ [MANUAL]"
        print(f"[{time.strftime('%H:%M:%S')}] 🔍 {symbol} {mode_str} | SMC: {liq_signal.upper()} | B: {buy_prob:.1f}% S: {sell_prob:.1f}% | 🎯 {target_confidence_percent:.1f}% | {regime_text}")

        # ==========================================
        # 🛡️ โซนจัดการออเดอร์ (บีบโล่ + เติมกระสุน Add-on)
        # ==========================================
        positions = mt5.positions_get(symbol=symbol)
        
        if positions is not None and len(positions) > 0:
            main_position = None
            addon_count = 0
            
            for pos in positions:
                sync_manual_order_to_db(pos)
                apply_break_even(pos, df, break_even_mult)

                # ⚡ ท่าไม้ตายใหม่: เก็บสั้นรับเงินสด (Quick Scalp Cash Out) ⚡
                QUICK_PROFIT_TARGET = 5.0  # 🎯 ลูกพี่เปลี่ยนตัวเลขตรงนี้ได้เลย (เช่น กำไร $5 ปิดทันที)
                
                if pos.profit >= QUICK_PROFIT_TARGET:
                    # ถ้าฟังก์ชันปิดออเดอร์ในระบบลูกพี่ใช้ชื่อ close_mt5_position ก็ใช้ตามนี้ได้เลย
                    if close_mt5_position(pos, comment="AI Quick Scalp"):
                        msg = (
                            f"⚡ <b>AI QUICK SCALP (สับไกเก็บสั้น)</b> ⚡\n\n"
                            f"💱 <b>Symbol:</b> {symbol} (Ticket: {pos.ticket})\n"
                            f"💰 <b>Net Profit:</b> 🟢 <b>+${pos.profit:.2f}</b>\n"
                            f"🚨 <b>Reason:</b> ถึงเป้ากำไรเงินสด สับไกปิดออเดอร์หนีเข้ากระเป๋า!"
                        )
                        send_telegram_message(msg)
                        print(f"⚡ [Quick Scalp] ปิดทำกำไรสั้น {symbol} รับเงิน +${pos.profit:.2f} ทันที!")
                    continue # ปิดออเดอร์เสร็จแล้ว ข้ามไปดูไม้อื่นต่อเลยไม่ต้องทำคำสั่งด้านล่าง

                # 🛡️ ท่าแก้เกม: ล็อคกำไรทันทีเมื่อถึงเป้าครึ่งทาง (Trailing Profit)
                LOCK_PROFIT_TRIGGER = 3.0  # พอกำไรถึง $3
                if pos.profit >= LOCK_PROFIT_TRIGGER and not pos.be_applied:
                    tick = mt5.symbol_info_tick(symbol)
                    sym_info = mt5.symbol_info(symbol)
                    if tick and sym_info:
                        # new_sl = pos.price_open # ขยับ SL มาบังทุนเป๊ะๆ
                        
                        # หรือถ้าอยากบังทุน + เอากำไรนิดนึงค่าธรรมเนียม
                        new_sl = pos.price_open + 0.5 # (สำหรับ BUY)
                        
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP, "symbol": symbol,
                            "sl": new_sl, "tp": pos.tp, "position": pos.ticket
                        }
                        if mt5.order_send(request).retcode == mt5.TRADE_RETCODE_DONE:
                            pos.be_applied = True
                            print(f"🔒 [Lock Profit] กำไรถึง ${LOCK_PROFIT_TRIGGER} เลื่อน SL บังทุนให้ {symbol}")
                                
                # จำแนกประเภทไม้
                if pos.comment == "AI Addon":
                    addon_count += 1
                else:
                    main_position = pos # ถือเป็นไม้หลัก
                
                # 🛡️ ท่าไม้ตาย: ตั้งป้อมบีบโล่ (Aggressive Defense Mode)
                defense_mode = False
                if pos.type == mt5.ORDER_TYPE_BUY and liq_signal in ["sell", "strong_sell"] and sell_prob >= target_confidence_percent:
                    defense_mode = True
                elif pos.type == mt5.ORDER_TYPE_SELL and liq_signal in ["buy", "strong_buy"] and buy_prob >= target_confidence_percent:
                    defense_mode = True
                    
                if defense_mode:
                    tick = mt5.symbol_info_tick(symbol)
                    sym_info = mt5.symbol_info(symbol)
                    
                    if tick and sym_info:
                        # ⚔️ บีบระยะโล่ให้เหลือแค่ 0.5 ATR (แคบมากๆ จ่อตูดราคาเลย)
                        aggressive_dist = atr_14 * 0.5 
                        new_sl = 0.0
                        
                        if pos.type == mt5.ORDER_TYPE_BUY:
                            new_sl = tick.bid - aggressive_dist
                            if pos.sl == 0.0 or new_sl > pos.sl:
                                new_sl = round(new_sl, sym_info.digits)
                                request = {
                                    "action": mt5.TRADE_ACTION_SLTP, "symbol": symbol,
                                    "sl": new_sl, "tp": pos.tp, "position": pos.ticket
                                }
                                res = mt5.order_send(request)
                                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                    msg = (f"🛡️ <b>AI DEFENSE MODE (ตั้งป้อมบีบโล่)</b> 🛡️\n\n"
                                           f"💱 <b>Symbol:</b> {symbol}\n📦 <b>Type:</b> BUY (Ticket: {pos.ticket})\n"
                                           f"🚨 <b>Reason:</b> AI ตรวจพบแรงเทขาย กราฟอาจจะทุบ!\n🎯 <b>Action:</b> ร่น SL มาที่ <b>{new_sl}</b>")
                                    send_telegram_message(msg)
                                    print(f"🛡️ [Defense Mode] เลื่อน SL ฝั่ง BUY {symbol} บีบแคบสุดๆ ที่ {new_sl}")

                        elif pos.type == mt5.ORDER_TYPE_SELL:
                            new_sl = tick.ask + aggressive_dist
                            if pos.sl == 0.0 or new_sl < pos.sl:
                                new_sl = round(new_sl, sym_info.digits)
                                request = {
                                    "action": mt5.TRADE_ACTION_SLTP, "symbol": symbol,
                                    "sl": new_sl, "tp": pos.tp, "position": pos.ticket
                                }
                                res = mt5.order_send(request)
                                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                    msg = (f"🛡️ <b>AI DEFENSE MODE (ตั้งป้อมบีบโล่)</b> 🛡️\n\n"
                                           f"💱 <b>Symbol:</b> {symbol}\n📦 <b>Type:</b> SELL (Ticket: {pos.ticket})\n"
                                           f"🚨 <b>Reason:</b> AI ตรวจพบแรงซื้อ กราฟอาจจะพุ่งสวน!\n🎯 <b>Action:</b> ร่น SL มาที่ <b>{new_sl}</b>")
                                    send_telegram_message(msg)
                                    print(f"🛡️ [Defense Mode] เลื่อน SL ฝั่ง SELL {symbol} บีบแคบสุดๆ ที่ {new_sl}")
            
            # 🚀 ท่าไม้ตาย: ยิงไม้เพิ่ม (Pyramiding Add-On)
            # ทำงานเมื่อ: อยู่ในเวลาเทรด + เปิด Auto-Tune + มีไม้หลัก + โควต้ายังเหลือ + กราฟเป็น STRONG TREND
            if is_trading_time and sym_config.get('auto_tune', False) and main_position and addon_count < (MAX_TOTAL_POSITIONS - 1) and is_strong_trend:
                
                # เช็คก่อนว่าไม้หลัก "ไร้ความเสี่ยง (Secured)" หรือยัง?
                main_secured = False
                if main_position.type == mt5.ORDER_TYPE_BUY and main_position.sl >= main_position.price_open:
                    main_secured = True
                elif main_position.type == mt5.ORDER_TYPE_SELL and main_position.sl <= main_position.price_open and main_position.sl != 0.0:
                    main_secured = True
                
                # ถ้าไม้หลักปลอดภัยแล้ว ให้หาจังหวะ Add-On
                if main_secured:
                    final_addon_signal = None
                    if main_position.type == mt5.ORDER_TYPE_BUY and buy_prob >= target_confidence_percent:
                        final_addon_signal = "strong_buy"
                    elif main_position.type == mt5.ORDER_TYPE_SELL and sell_prob >= target_confidence_percent:
                        final_addon_signal = "strong_sell"
                        
                    if final_addon_signal:
                        tick = mt5.symbol_info_tick(symbol)
                        sym_info = mt5.symbol_info(symbol)
                        
                        if tick and sym_info:
                            lot = main_position.volume # ใช้ Lot เท่าไม้หลัก
                            sl_dist = atr_14 * atr_mult
                            tp_dist = sl_dist * rr_ratio
                            
                            if main_position.type == mt5.ORDER_TYPE_BUY:
                                sl_price = round(tick.ask - sl_dist, sym_info.digits)
                                tp_price = round(tick.ask + tp_dist, sym_info.digits)
                            else:
                                sl_price = round(tick.bid + sl_dist, sym_info.digits)
                                tp_price = round(tick.bid - tp_dist, sym_info.digits)
                                
                            result = send_order(symbol, final_addon_signal, lot, sl=sl_price, tp=tp_price, comment="AI Addon")
                            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                                # ถ้าฟังก์ชัน save_new_trade ของลูกพี่มีพารามิเตอร์ comment ก็ใส่ได้เลย แต่ถ้าไม่มี เอาไว้เท่านี้ก่อนได้ครับ
                                save_new_trade(result.order, symbol, final_addon_signal, result.price)
                                msg = (
                                    f"🔥 <b>AI ADD-ON EXECUTED (ยิงไม้เร่งกำไร)</b> 🔥\n\n"
                                    f"🎯 <b>Signal:</b> {final_addon_signal.upper()}\n"
                                    f"💱 <b>Symbol:</b> {symbol}\n"
                                    f"💰 <b>Add Entry:</b> {result.price}\n"
                                    f"📦 <b>Lot:</b> {lot}\n"
                                    f"🚨 <b>Reason:</b> เทรนด์แกร่ง + ไม้หลักปลอดภัย สบจังหวะอัดไม้เพิ่ม!"
                                )
                                send_telegram_message(msg)
                                print(f"🔥 [Add-On] ยิงไม้เพิ่มเหรียญ {symbol} (Ticket: {result.order}) ล็อคเป้าเร่งกำไร!")

            # 🛑 หยุดลูปการเข้าเทรดไม้หลัก ถ้ามีของอยู่ในมือแล้ว (จะไม้หลักหรือไม้ Add-on ก็ตาม)
            continue

        # ==========================================
        # 🚀 โซนยิงออเดอร์ใหม่ (ไม้หลัก - เมื่อมือว่างสนิท)
        # ==========================================
        if not is_trading_time:
            continue
        
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
            
            # คำนวณระยะด้วย ATR
            sl_distance = atr_14 * atr_mult
            tp_distance = sl_distance * rr_ratio
            
            tick = mt5.symbol_info_tick(symbol)
            if tick is None: 
                continue 
                
            sl_price = 0.0
            tp_price = 0.0
            
            if final_signal in ["buy", "strong_buy"]:
                sl_price = tick.ask - sl_distance
                tp_price = tick.ask + tp_distance
            elif final_signal in ["sell", "strong_sell"]:
                sl_price = tick.bid + sl_distance
                tp_price = tick.bid - tp_distance
                
            sl_price = round(sl_price, symbol_info.digits)
            tp_price = round(tp_price, symbol_info.digits)

            # 🛡️ 🌟 ท่าแก้เกม: ระบบเบรกฉุกเฉิน (Max Dollar Risk Cap) 🌟 🛡️
            MAX_ALLOWED_LOSS_USD = 25.0  # 💵 ลิมิตยอมขาดทุนสูงสุดต่อไม้
            
            # ดึง Contract Size ของเหรียญนั้นๆ จาก Exness โดยตรง (XAU=100, BTC=1, ETH=...)
            contract_size = symbol_info.trade_contract_size
            
            # คำนวณความเสี่ยงที่แม่นยำ 100%
            if final_signal in ["buy", "strong_buy"]:
                estimated_loss_usd = abs(tick.ask - sl_price) * lot * contract_size
            else:
                estimated_loss_usd = abs(sl_price - tick.bid) * lot * contract_size
            
            if estimated_loss_usd > MAX_ALLOWED_LOSS_USD:
                print(f"🚫 [Risk Control] กราฟผันผวนหนัก! ระยะ SL กว้างเกินไป เสี่ยงติดลบ ${estimated_loss_usd:.2f} (เกินลิมิต ${MAX_ALLOWED_LOSS_USD}) -> ยกเลิกการยิงออเดอร์หนีตาย!")
                continue # ข้ามการเทรดไม้นี้ไปเลย ไม่ต้องส่งคำสั่งไป MT5!
            # 🛡️ 🌟 สิ้นสุดระบบเบรกฉุกเฉิน 🌟 🛡️
            
            # 🌟 ประทับตรา comment="AI Main" ให้ไม้หลัก เพื่อให้ระบบ Add-on จำแนกได้
            result = send_order(symbol, final_signal, lot, sl=sl_price, tp=tp_price, comment="AI Main")
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                save_new_trade(result.order, symbol, final_signal, result.price)
                msg = (
                    f"🚨 <b>QUANTUM AI EXECUTED (ไม้หลัก)</b> 🚨\n\n"
                    f"🎯 <b>Signal:</b> {final_signal.upper()}\n"
                    f"💱 <b>Symbol:</b> {symbol}\n"
                    f"💰 <b>Entry:</b> {result.price}\n"
                    f"🛡️ <b>Stop Loss:</b> {sl_price} (ATR x{atr_mult})\n"
                    f"🚀 <b>Take Profit:</b> {tp_price} (R:R 1:{rr_ratio})\n"
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
                
                run_bot_cycle(active_symbols) 
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n🛑 หยุดการทำงานของบอทด้วยผู้ใช้")
            mt5.shutdown()