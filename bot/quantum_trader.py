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

# ⚙️ ตั้งค่าพื้นฐานของบอท
SYMBOL = "BTCUSDm"          # คู่เงินที่ต้องการเทรด
TIMEFRAME = mt5.TIMEFRAME_M15 # กรอบเวลา 15 นาที
RISK_PERCENT = 1.0         # ความเสี่ยง 1% ของพอร์ตต่อ 1 ไม้
AI_CONFIDENCE = 70.0       # AI ต้องมั่นใจเกิน 70% ถึงจะออกออเดอร์

def run_bot_cycle():
    """
    วัฏจักรการทำงานของบอท 1 รอบ (1 Loop)
    """
    # 1. 🛡️ เลื่อน Stop Loss ล็อกกำไรให้ออเดอร์ที่เปิดอยู่ก่อนเลย (Trailing Stop)
    manage_trailing_stop(SYMBOL, trailing_points=500)

    # เช็คว่ามีออเดอร์เปิดค้างอยู่ไหม (เพื่อป้องกันการเปิดซ้ำซ้อนเบิ้ลไม้)
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is not None and len(positions) > 0:
        # ถ้ามีออเดอร์วิ่งอยู่แล้ว ให้ข้ามการวิเคราะห์เปิดไม้ใหม่ไปก่อน รอล็อกกำไรอย่างเดียว
        return

    # 2. 📊 ดึงข้อมูลกราฟแท่งเทียนล่าสุด
    df = get_candles(SYMBOL, TIMEFRAME, bars=200)
    if df is None:
        return

    # 3. 🧠 กระบวนการคิดของ AI
    trend = detect_trend(df)                     # หารูปแบบเทรนด์
    raw_signal = choose_strategy(trend)          # เลือกฝั่งเบื้องต้น
    liq_signal = liquidity_filter(df, raw_signal) # กรองด้วย Liquidity (หาจุดกวาด Stop Loss)
    
    # ถ้าโดนสั่งให้ hold ตั้งแต่ด่านแรก ก็ไม่ต้องส่งไปให้ Deep Learning คิดให้เปลืองแรง
    if liq_signal == "hold":
        return

    prob = predict_probability(df)               # ให้ LSTM คำนวณเปอร์เซ็นต์ความแม่นยำ
    buy_prob = prob * 100
    sell_prob = (1 - prob) * 100

    print(f"[{time.strftime('%H:%M:%S')}] 🔍 วิเคราะห์ {SYMBOL} | Liquidity: {liq_signal.upper()} | AI BUY: {buy_prob:.1f}% | AI SELL: {sell_prob:.1f}%")

    # 4. ⚖️ เงื่อนไขการตัดสินใจลั่นไก (Double Confirmation)
    final_signal = None
    if liq_signal in ["buy", "strong_buy"] and buy_prob >= AI_CONFIDENCE:
        final_signal = liq_signal
    elif liq_signal in ["sell", "strong_sell"] and sell_prob >= AI_CONFIDENCE:
        final_signal = liq_signal

    # 5. 🔫 ส่งคำสั่งเทรด
    if final_signal:
        account = get_account_info()
        if not account:
            return
            
        # คำนวณขนาดไม้ตามเงินทุนจริง
        lot = calculate_lot_size(account["balance"], risk_percentage=RISK_PERCENT)
        
        print(f"🚀 [BOT] AI ตัดสินใจเข้าเทรดฝั่ง {final_signal.upper()} ด้วยขนาด {lot} Lot!")
        
        # ส่งออเดอร์เข้าตลาด
        result = send_order(SYMBOL, final_signal, lot)
        
        # 6. 💾 บันทึกประวัติลง Database
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            save_new_trade(
                ticket_id=result.order, 
                symbol=SYMBOL, 
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