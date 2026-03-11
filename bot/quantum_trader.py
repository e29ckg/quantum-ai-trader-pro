import os
import time
import MetaTrader5 as mt5
from datetime import datetime
from dotenv import load_dotenv # 👇 เพิ่มตัวโหลด .env

# นำเข้าเครื่องมือทั้งหมดที่เราสร้างไว้
from mt5_engine.connect import connect_mt5, get_account_info
from mt5_engine.data_feed import get_candles
from mt5_engine.trade_executor import send_order
from ai_engine.market_structure import detect_trend
from ai_engine.strategy_selector import choose_strategy
from ai_engine.liquidity_ai import liquidity_filter
from ai_engine.prediction_ai import predict_probability
from risk_manager.risk_control import calculate_lot_size
from risk_manager.trailing_stop import manage_trailing_stop
from database.db import save_new_trade
from utils.telegram_notifier import send_telegram_message

# โหลดค่าจากไฟล์ .env
load_dotenv()

# ==========================================
# ⚙️ ตั้งค่าพื้นฐานของบอท (ดึงจากไฟล์ .env)
# ==========================================

# 1. คู่เงินที่ต้องการเทรด (ดึงมาแล้วแยกด้วยลูกน้ำ)
env_symbols = os.getenv("TRADE_SYMBOLS", "BTCUSDm,XAUUSDm,EURUSDm")
SYMBOLS = [s.strip() for s in env_symbols.split(",") if s.strip()]

# 2. สมุดจดจำสัญญาณของแต่ละเหรียญ
live_signals = {sym: {"signal": "WAIT", "buy_prob": 0.0, "sell_prob": 0.0} for sym in SYMBOLS}

# 3. กรอบเวลา (แปลงข้อความ M15 ให้เป็นคำสั่งของ MT5)
tf_map = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1
}
env_timeframe = os.getenv("TRADE_TIMEFRAME", "M15").upper()
TIMEFRAME = tf_map.get(env_timeframe, mt5.TIMEFRAME_M15) # ถ้าใส่ผิด จะกลับไปใช้ M15 อัตโนมัติ

# 4. การจัดการความเสี่ยง
RISK_PERCENT = float(os.getenv("RISK_PERCENT", "1.0"))
AI_CONFIDENCE = float(os.getenv("AI_CONFIDENCE", "70.0"))

# ตัวแปรจำว่าวันนี้ส่งสรุปไปหรือยัง (กันบอทส่งสแปมซ้ำๆ)
last_summary_date = None


def send_daily_summary():
    global last_summary_date
    now = datetime.now()
    
    # 🕒 เช็คเวลา 23:00 น. (5 ทุ่ม) และเช็คว่าวันนี้ยังไม่ได้ส่ง
    if now.hour == 23 and last_summary_date != now.date():
        
        # 1. กำหนดช่วงเวลาดึงประวัติเทรด (ตั้งแต่เที่ยงคืน ถึง 5 ทุ่ม 59)
        start_of_day = datetime(now.year, now.month, now.day)
        end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59)
        
        # 2. ดึงประวัติจาก MT5
        deals = mt5.history_deals_get(start_of_day, end_of_day)
        
        total_profit = 0.0
        total_trades = 0
        win_trades = 0
        
        if deals:
            for deal in deals:
                # เช็คเฉพาะออเดอร์ที่ปิดไปแล้ว (DEAL_ENTRY_OUT = 1)
                if deal.entry == 1: 
                    # รวมกำไรสุทธิ (หักค่าธรรมเนียมและดอกเบี้ยข้ามคืนแล้ว)
                    net_profit = deal.profit + deal.swap + deal.commission
                    total_profit += net_profit
                    total_trades += 1
                    if net_profit > 0:
                        win_trades += 1
                        
        # 3. คำนวณอัตราชนะ (Win Rate)
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
        emoji = "🟢" if total_profit >= 0 else "🔴"
        
        # 4. สร้างข้อความรายงานลูกพี่
        msg = (
            f"📊 <b>สรุปผลประกอบการรายวัน (Daily Report)</b>\n"
            f"📅 <b>วันที่:</b> {now.strftime('%d/%m/%Y')}\n\n"
            f"📈 <b>ออเดอร์ที่ปิดแล้ว:</b> {total_trades} ไม้\n"
            f"🏆 <b>Win Rate:</b> {win_rate:.1f}%\n"
            f"💰 <b>Net Profit:</b> {emoji} <b>${total_profit:.2f}</b>\n\n"
            f"💤 พักผ่อนได้เลยครับลูกพี่ บอทจะเฝ้ากราฟต่อให้เอง!"
        )
        
        # 5. ส่งเข้า Telegram ทันที
        send_telegram_message(msg)
        last_summary_date = now.date()
        print("✅ [Telegram] ส่งสรุปยอดกำไรรายวัน 23:00 น. เรียบร้อยแล้ว!")

def run_bot_cycle():
    """
    วัฏจักรการทำงานของบอท 1 รอบ (จะวนสแกนทุกคู่เงินใน SYMBOLS)
    """
    send_daily_summary()
    
    for symbol in SYMBOLS:
        # 1. 🛡️ เลื่อน Stop Loss ล็อกกำไรให้ออเดอร์ของคู่เงินนี้ก่อน
        manage_trailing_stop(symbol, trailing_points=500)

        # เช็คว่ามีออเดอร์ของคู่เงินนี้เปิดค้างอยู่ไหม
        positions = mt5.positions_get(symbol=symbol)
        if positions is not None and len(positions) > 0:
            continue # ถ้าคู่นี้มีออเดอร์วิ่งอยู่แล้ว ให้ข้ามไปสแกนคู่ถัดไปเลย!

        # 2. 📊 ดึงข้อมูลกราฟแท่งเทียนล่าสุด
        df = get_candles(symbol, TIMEFRAME, bars=200)
        if df is None:
            continue

        # 3. 🧠 กระบวนการคิดของ AI
        trend = detect_trend(df)
        raw_signal = choose_strategy(trend)
        liq_signal = liquidity_filter(df, raw_signal)
        
        if liq_signal == "hold":
            continue # ถ้าราคาไซด์เวย์ ข้ามไปคู่ถัดไปเลย

        # prob = predict_probability(df)
        prob = predict_probability(df, symbol) # 👈 โยนชื่อเหรียญให้มันไปหาสมองถูกตัว
        buy_prob = prob * 100
        sell_prob = (1 - prob) * 100

        live_signals[symbol] = {
            "signal": liq_signal.upper(),
            "buy_prob": buy_prob,
            "sell_prob": sell_prob
        }

        print(f"[{time.strftime('%H:%M:%S')}] 🔍 {symbol} | SMC: {liq_signal.upper()} | AI BUY: {buy_prob:.1f}% | AI SELL: {sell_prob:.1f}%")

        # 4. ⚖️ เงื่อนไขการตัดสินใจลั่นไก
        final_signal = None
        if liq_signal in ["buy", "strong_buy"] and buy_prob >= AI_CONFIDENCE:
            final_signal = liq_signal
        elif liq_signal in ["sell", "strong_sell"] and sell_prob >= AI_CONFIDENCE:
            final_signal = liq_signal

        # 5. 🔫 ส่งคำสั่งเทรด
        if final_signal:
            account = get_account_info()
            if not account:
                continue
                
            # 1. คำนวณ Lot เบื้องต้นจากเงินในพอร์ต
            raw_lot = calculate_lot_size(account["balance"], risk_percentage=RISK_PERCENT)
            
            # 👇 [เพิ่มใหม่] 2. ตรวจสอบและปรับขนาด Lot ให้ตรงกับกฎของโบรกเกอร์ (สำคัญมาก!)
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                print(f"⚠️ [Trade] ไม่พบข้อมูลของเหรียญ {symbol} ข้ามการเทรด")
                continue
                
            min_lot = symbol_info.volume_min  # Lot ขั้นต่ำที่โบรกยอมรับ
            step_lot = symbol_info.volume_step # สเต็ปการเพิ่ม Lot (เช่น ทีละ 0.01 หรือ 0.1)
            
            # บังคับ Lot ให้ไม่ต่ำกว่าขั้นต่ำ และปัดเศษให้ตรงกับสเต็ปที่โบรกเกอร์กำหนด
            lot = max(raw_lot, min_lot)
            lot = round(lot / step_lot) * step_lot
            lot = round(lot, 3) # กันทศนิยมล้น
            
            print(f"🚀 [BOT] AI ตัดสินใจเข้าเทรด {symbol} ฝั่ง {final_signal.upper()} ด้วยขนาด {lot} Lot!")
            
            result = send_order(symbol, final_signal, lot)
            
            # 6. 💾 บันทึกประวัติลง Database (เหมือนเดิม)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                save_new_trade(
                    ticket_id=result.order, 
                    symbol=symbol, 
                    trade_type=final_signal, 
                    entry_price=result.price
                )
                # 👇 [เพิ่มใหม่] 7. 📱 ส่งแจ้งเตือนเข้า Telegram
                msg = (
                    f"🚨 <b>QUANTUM AI EXECUTED</b> 🚨\n\n"
                    f"🎯 <b>Signal:</b> {final_signal.upper()}\n"
                    f"💱 <b>Symbol:</b> {symbol}\n"
                    f"💰 <b>Entry Price:</b> {result.price}\n"
                    f"📦 <b>Lot Size:</b> {lot}\n"
                    f"🤖 <b>AI Confidence:</b> {buy_prob if final_signal in ['buy', 'strong_buy'] else sell_prob:.1f}%\n"
                    f"⏱️ <b>Time:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                send_telegram_message(msg)
                
# ==========================================
# 🛑 สคริปต์สำหรับรันบอทแบบ Standalone (เปิดแยกใน Terminal)
# ==========================================
if __name__ == "__main__":
    print("🤖 กำลังปลุก Quantum AI Trader PRO...")
    if connect_mt5():
        try:
            while True:
                run_bot_cycle()
                time.sleep(10) # ให้บอทพักหายใจ 10 วินาที ก่อนสแกนตลาดรอบใหม่
        except KeyboardInterrupt:
            print("\n🛑 หยุดการทำงานของบอทด้วยผู้ใช้")
            mt5.shutdown()