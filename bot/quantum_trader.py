import time
import MetaTrader5 as mt5

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

# ==========================================
# ⚙️ ตั้งค่าพื้นฐานของบอท (อัปเกรดเป็น Multi-Assets)
# ==========================================
# 👇 ใส่คู่เงินที่ต้องการเทรดลงไปในวงเล็บนี้ได้เลย (คั่นด้วยลูกน้ำ)
SYMBOLS = ["BTCUSDm", "XAUUSDm", "EURUSDm"] 

TIMEFRAME = mt5.TIMEFRAME_M15 # กรอบเวลา 15 นาที
RISK_PERCENT = 1.0         # ความเสี่ยง 1%
AI_CONFIDENCE = 70.0       # ความมั่นใจ 70% ขึ้นไป

def run_bot_cycle():
    """
    วัฏจักรการทำงานของบอท 1 รอบ (จะวนสแกนทุกคู่เงินใน SYMBOLS)
    """
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

        prob = predict_probability(df)
        buy_prob = prob * 100
        sell_prob = (1 - prob) * 100

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
                
            lot = calculate_lot_size(account["balance"], risk_percentage=RISK_PERCENT)
            
            print(f"🚀 [BOT] AI ตัดสินใจเข้าเทรด {symbol} ฝั่ง {final_signal.upper()} ด้วยขนาด {lot} Lot!")
            
            result = send_order(symbol, final_signal, lot)
            
            # 6. 💾 บันทึกประวัติลง Database
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                save_new_trade(
                    ticket_id=result.order, 
                    symbol=symbol, 
                    trade_type=final_signal, 
                    entry_price=result.price
                )
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