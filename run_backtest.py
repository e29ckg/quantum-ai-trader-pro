import pandas as pd
import MetaTrader5 as mt5
import random # เอาไว้จำลองเปอร์เซ็นต์ AI ชั่วคราวกรณีที่ยังไม่ได้เทรนโมเดล

from mt5_engine.connect import connect_mt5, disconnect_mt5
from mt5_engine.data_feed import get_candles
from ai_engine.liquidity_ai import liquidity_filter
# from ai_engine.prediction_ai import predict_probability # ใช้ของจริงเมื่อเทรนโมเดลแล้ว
from backtest.engine import BacktestEngine

def simulate_lstm_probability(trend_signal):
    """
    ฟังก์ชันจำลอง (Mock) แทน LSTM ชั่วคราวเพื่อให้ Backtest รันได้ไวขึ้น 
    โดยไม่ต้องรอประมวลผล Deep Learning ย้อนหลังทีละแท่ง
    """
    if trend_signal in ["buy", "strong_buy"]: return random.uniform(0.65, 0.95)
    if trend_signal in ["sell", "strong_sell"]: return random.uniform(0.05, 0.35)
    return 0.50

def run_historical_test(symbol="BTCUSD", timeframe=mt5.TIMEFRAME_H1, bars=5000):
    if not connect_mt5():
        return

    print(f"📥 [Backtest] กำลังดึงข้อมูลย้อนหลัง {bars} แท่งเทียน สำหรับ {symbol}...")
    df = get_candles(symbol, timeframe, bars=bars)
    
    if df is None or df.empty:
        print("❌ ดึงข้อมูลล้มเหลว")
        return

    # สร้าง Engine ทุน $10,000 เสี่ยงไม้ละ 1%
    tester = BacktestEngine(initial_capital=10000.0, risk_per_trade=0.01)

    print("🧠 [Backtest] AI กำลังจำลองการเทรดย้อนหลัง (Processing...)")
    
    # วนลูปจำลองเดินไปข้างหน้าทีละ 1 แท่งเทียน (เพื่อให้เหมือนรันจริง)
    for i in range(60, len(df) - 1):
        # ตัดข้อมูลมาแค่เท่าที่ AI ในอดีตจะมองเห็น
        current_view = df.iloc[:i].copy()
        
        last_close = current_view['close'].iloc[-1]
        prev_close = current_view['close'].iloc[-10]
        
        # 1. หาระบบ Trend พื้นฐาน
        raw_signal = "buy" if last_close > prev_close else "sell"
        
        # 2. กรองด้วย Liquidity AI
        liq_signal = liquidity_filter(current_view, raw_signal)
        
        # 3. ยืนยันด้วย Deep Learning (จำลอง)
        prob = simulate_lstm_probability(raw_signal) 
        buy_prob = prob * 100
        sell_prob = (1 - prob) * 100

        # 4. เงื่อนไขการเข้าเทรด
        entry_signal = None
        if liq_signal in ["buy", "strong_buy"] and buy_prob > 70:
            entry_signal = liq_signal
        elif liq_signal in ["sell", "strong_sell"] and sell_prob > 70:
            entry_signal = liq_signal

        # 5. ถ้า AI สั่งเทรด ให้ส่งออเดอร์เข้า Backtest Engine
        if entry_signal:
            entry_price = current_view['close'].iloc[-1]
            # จำลองการปิดออเดอร์ที่แท่งถัดไป (1 แท่งเทียน)
            exit_price = df['close'].iloc[i + 1] 
            entry_time = df['time'].iloc[i]

            tester.execute_trade(entry_time, entry_price, entry_signal, exit_price)

    # 6. พิมพ์สรุปผลงาน AI
    report_df = tester.generate_report()
    
    # 7. บันทึกประวัติการเทรดลง Excel ไว้ดูย้อนหลัง
    if report_df is not None:
        report_df.to_csv("backtest_result.csv", index=False)
        print("💾 [Backtest] บันทึกประวัติการเทรดลงไฟล์ backtest_result.csv เรียบร้อยแล้ว")

    disconnect_mt5()

if __name__ == "__main__":
    run_historical_test()