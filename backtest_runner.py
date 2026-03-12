import os
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler

# 🛡️ Safe Mode AI
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
from tensorflow.keras.models import load_model

from mt5_engine.connect import connect_mt5

# ==========================================
# 📊 เครื่องยนต์คำนวณสถิติ (ที่ลูกพี่เขียนไว้ + ปรับแก้ SL)
# ==========================================
class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0, risk_per_trade: float = 0.01):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.risk_per_trade = risk_per_trade
        self.trades = []
        self.equity_curve = [initial_capital]

    def execute_trade(self, entry_time, entry_price, signal, exit_price, sl_distance):
        # ป้องกัน error หารศูนย์
        if sl_distance <= 0: sl_distance = 0.0001 
        
        risk_amount = self.balance * self.risk_per_trade
        position_size = risk_amount / sl_distance

        if signal in ["buy", "strong_buy"]:
            pnl = (exit_price - entry_price) * position_size
        elif signal in ["sell", "strong_sell"]:
            pnl = (entry_price - exit_price) * position_size
        else:
            pnl = 0

        self.balance += pnl
        self.equity_curve.append(self.balance)

        self.trades.append({
            "time": entry_time,
            "signal": signal,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "sl_distance": sl_distance,
            "pnl": pnl,
            "balance": self.balance
        })

    def generate_report(self):
        if not self.trades:
            print("❌ ไม่มีการเทรดเกิดขึ้นในระบบ")
            return None

        df_trades = pd.DataFrame(self.trades)
        
        total_trades = len(df_trades)
        winning_trades = len(df_trades[df_trades['pnl'] > 0])
        win_rate = (winning_trades / total_trades) * 100

        total_profit = df_trades[df_trades['pnl'] > 0]['pnl'].sum()
        total_loss = abs(df_trades[df_trades['pnl'] < 0]['pnl'].sum())
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        equity_series = pd.Series(self.equity_curve)
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100

        print("\n" + "="*50)
        print("📊 QUANTUM AI - BACKTEST REPORT")
        print("="*50)
        print(f"ทุนเริ่มต้น:     ${self.initial_capital:,.2f}")
        print(f"ยอดเงินสุดท้าย:   ${self.balance:,.2f}")
        print(f"กำไรสุทธิ:       ${self.balance - self.initial_capital:,.2f} ({((self.balance / self.initial_capital) - 1) * 100:.2f}%)")
        print("-" * 50)
        print(f"จำนวนการเทรด:   {total_trades} ไม้")
        print(f"Win Rate:      {win_rate:.2f}%")
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Max Drawdown:  {max_drawdown:.2f}%")
        print("="*50 + "\n")
        
        return df_trades

# ==========================================
# 🛠️ ฟังก์ชันเตรียมข้อมูล (เหมือน V3.0 เป๊ะๆ)
# ==========================================
def add_indicators(df):
    df['EMA_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    # คำนวณ ATR เพื่อใช้ทำ Trailing Stop ใน Backtest
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()
    
    df.dropna(inplace=True)
    return df

# ==========================================
# 🚀 ระบบจำลองการเทรด (Simulation Runner)
# ==========================================
def run_backtest(symbol: str, timeframe=mt5.TIMEFRAME_M15, bars=5000, confidence_target=0.60):
    print(f"\n⏳ กำลังดึงข้อมูลย้อนหลัง {bars} แท่ง สำหรับ {symbol}...")
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None:
        print("❌ ไม่สามารถดึงข้อมูลจาก MT5 ได้")
        return

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df = add_indicators(df)
    
    # โหลดสมอง AI 
    model_path = f"ai_engine/model_{symbol}.h5"
    if not os.path.exists(model_path):
        print(f"❌ ไม่พบไฟล์สมอง {model_path} กรุณาเทรน AI ก่อน!")
        return
        
    print("🧠 กำลังโหลดสมอง AI V3.0...")
    model = load_model(model_path, compile=False)
    
    features = ['open', 'high', 'low', 'close', 'tick_volume', 'EMA_20', 'EMA_50', 'RSI_14']
    # เผื่อชื่อคอลัมน์ volume สลับกัน
    if 'tick_volume' not in df.columns and 'volume' in df.columns:
        features[4] = 'volume'
        
    data_to_scale = df[features].values
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data_to_scale)

    # เตรียม Engine ตั้งทุน 10,000 เหรียญ เสี่ยง 1% ต่อไม้
    engine = BacktestEngine(initial_capital=10000.0, risk_per_trade=0.01)
    
    # ตัวแปรสถานะออเดอร์
    in_trade = False
    trade_type = None
    entry_price = 0.0
    sl = 0.0
    entry_time = None
    sl_distance_initial = 0.0

    print("⚡ เริ่มจำลองการเทรดแบบแท่งต่อแท่ง (Bar-by-Bar)...")
    
    SEQ_LENGTH = 60
    # เริ่มลูปตั้งแต่แท่งที่ 60 เป็นต้นไป (เพราะ AI ต้องมองย้อน 60 แท่ง)
    for i in range(SEQ_LENGTH, len(df)):
        # 👇 แทรก 2 บรรทัดนี้เข้าไป บอทจะรายงานทุกๆ 1,000 แท่ง
        if i % 1000 == 0:
            print(f"🔄 กำลังประมวลผลแท่งที่ {i} / {len(df)}...")            
        current_bar = df.iloc[i]
        current_time = current_bar['time']
        close_price = current_bar['close']
        high_price = current_bar['high']
        low_price = current_bar['low']
        atr = current_bar['ATR']
        
        # 1. 🛡️ เช็คสถานะออเดอร์ที่ถืออยู่ (จำลองการชน SL หรือ Trailing Stop)
        if in_trade:
            trade_closed = False
            exit_price = 0.0
            
            if trade_type == "buy":
                # เลื่อน Trailing Stop ตาม (2 ATR)
                new_sl = close_price - (atr * 2.0)
                if new_sl > sl: sl = new_sl 
                
                # เช็คว่าราคาร่วงมาชน SL ไหม (มองจากจุดต่ำสุดของแท่งปัจจุบัน)
                if low_price <= sl:
                    exit_price = sl
                    trade_closed = True
                    
            elif trade_type == "sell":
                # เลื่อน Trailing Stop ตาม (2 ATR)
                new_sl = close_price + (atr * 2.0)
                if new_sl < sl: sl = new_sl
                
                # เช็คว่าราคาพุ่งไปชน SL ไหม (มองจากจุดสูงสุดของแท่งปัจจุบัน)
                if high_price >= sl:
                    exit_price = sl
                    trade_closed = True
                    
            # ถ้าโดนชน SL ให้ส่งข้อมูลให้ Engine บันทึกกำไร/ขาดทุน
            if trade_closed:
                engine.execute_trade(entry_time, entry_price, trade_type, exit_price, sl_distance_initial)
                in_trade = False
            continue # ถ้ามีออเดอร์อยู่ จะไม่เปิดออเดอร์ซ้อน

        # 2. 🧠 ถ้ามือว่าง ให้ AI ทายผลแท่งถัดไป
        recent_data = scaled_data[i - SEQ_LENGTH : i]
        X_input = np.array([recent_data])
        pred = model.predict(X_input, verbose=0)[0][0]
                
        buy_prob = pred
        sell_prob = 1.0 - pred
        
        # 👇 เอาโค้ด 2 บรรทัดนี้ไปวางต่อท้าย เพื่อแอบดูตัวเลข
        if i % 1000 == 0:
            print(f"🔄 แท่งที่ {i} | AI มอง BUY: {buy_prob*100:.1f}% | SELL: {sell_prob*100:.1f}%")
        
        # 3. 🎯 ลั่นไกเปิดออเดอร์ใหม่ (สมมติว่าถ้า EMA20 > EMA50 เป็นเทรนขาขึ้น ค่อยเปิด BUY)
        ema_trend = "up" if current_bar['EMA_20'] > current_bar['EMA_50'] else "down"
        
        if ema_trend == "up" and buy_prob >= confidence_target:
            in_trade = True
            trade_type = "buy"
            entry_price = close_price
            entry_time = current_time
            sl_distance_initial = atr * 2.0
            sl = entry_price - sl_distance_initial
            
        elif ema_trend == "down" and sell_prob >= confidence_target:
            in_trade = True
            trade_type = "sell"
            entry_price = close_price
            entry_time = current_time
            sl_distance_initial = atr * 2.0
            sl = entry_price + sl_distance_initial

    # สร้างรายงานเมื่อจำลองเสร็จ
    report_df = engine.generate_report()
    
    # เซฟประวัติการเทรดลง Excel ไว้ดูเล่นได้ด้วย
    if report_df is not None:
        report_df.to_excel(f"backtest_report_{symbol}.xlsx", index=False)
        print(f"💾 บันทึกประวัติการเทรดลงไฟล์ backtest_report_{symbol}.xlsx เรียบร้อย!")

if __name__ == "__main__":
    if connect_mt5():
        # ทดสอบรัน Backtest ทองคำ ย้อนหลัง 10,000 แท่ง โดยตั้งเป้าความมั่นใจ AI ที่ 60%
        run_backtest(symbol="XAUUSDm", timeframe=mt5.TIMEFRAME_M15, bars=10000, confidence_target=0.54)
        mt5.shutdown()