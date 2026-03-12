import os
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import load_model

# นำเข้าวิชา SMC จาก AI Engine ของเรา
from ai_engine.market_structure import detect_trend
from ai_engine.strategy_selector import choose_strategy
from ai_engine.liquidity_ai import liquidity_filter
from mt5_engine.connect import connect_mt5

# ==========================================
# 📊 Backtest Engine (ตัวเดิมของลูกพี่ที่ปรับปรุงแล้ว)
# ==========================================
class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0, risk_per_trade: float = 0.01):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.risk_per_trade = risk_per_trade
        self.trades = []
        self.equity_curve = [initial_capital]

    def execute_trade(self, entry_time, entry_price, signal, exit_price, sl_distance):
        if sl_distance <= 0: sl_distance = 0.0001 
        risk_amount = self.balance * self.risk_per_trade
        position_size = risk_amount / sl_distance

        if signal in ["buy", "strong_buy"]:
            pnl = (exit_price - entry_price) * position_size
        elif signal in ["sell", "strong_sell"]:
            pnl = (entry_price - exit_price) * position_size
        else: pnl = 0

        self.balance += pnl
        self.equity_curve.append(self.balance)
        self.trades.append({
            "time": entry_time, "signal": signal, "entry": entry_price,
            "exit": exit_price, "pnl": pnl, "balance": self.balance
        })

    def generate_report(self):
        if not self.trades:
            print("❌ SMC กรองเข้มจัด! ไม่พบจุดเข้าที่ปลอดภัยเพียงพอในรอบนี้")
            return None
        df = pd.DataFrame(self.trades)
        win_rate = (len(df[df['pnl'] > 0]) / len(df)) * 100
        equity = pd.Series(self.equity_curve)
        mdd = ((equity - equity.cummax()) / equity.cummax()).min() * 100
        
        print("\n" + "🛡️" * 15)
        print("📊 SMC + AI V4.0 - PRO REPORT")
        print("🛡️" * 15)
        print(f"ยอดเงินสุดท้าย:   ${self.balance:,.2f}")
        print(f"กำไรสุทธิ:       ${self.balance - self.initial_capital:,.2f}")
        print(f"จำนวนการเทรด:   {len(df)} ไม้ (ลดลงเพราะกรองคุณภาพ)")
        print(f"Win Rate:      {win_rate:.2f}%")
        print(f"Max Drawdown:  {mdd:.2f}%")
        print("🛡️" * 15 + "\n")
        return df

# ==========================================
# 🛠️ ฟังก์ชันเตรียมข้อมูล (Feature Engineering)
# ==========================================
def add_indicators(df):
    df['EMA_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    df['RSI_14'] = 100 - (100 / (1 + (gain / loss)))
    high_low = df['high'] - df['low']
    df['ATR'] = high_low.rolling(14).mean()
    df.dropna(inplace=True)
    return df

# ==========================================
# 🚀 PRO RUNNER: ผสม SMC + AI
# ==========================================
def run_backtest_pro(symbol, bars=10000, ai_threshold=0.55):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars)
    df = pd.DataFrame(rates)
    df = add_indicators(df)
    
    model = load_model(f"ai_engine/model_{symbol}.h5", compile=False)
    engine = BacktestEngine()
    
    # ตัวแปรจำลอง
    in_trade = False
    trade_type, entry_price, sl, sl_dist_init, entry_time = None, 0, 0, 0, None
    
    # ข้อมูลสำหรับ AI
    features = ['open', 'high', 'low', 'close', 'tick_volume', 'EMA_20', 'EMA_50', 'RSI_14']
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(df[features].values)

    print(f"⚡ เริ่มซ้อมรบระบบ Full Armor (SMC + AI) สำหรับ {symbol}...")

    for i in range(60, len(df)):
        current_bar = df.iloc[i]
        
        # 1. จัดการออเดอร์เดิม (Trailing Stop)
        if in_trade:
            if trade_type == "buy":
                new_sl = current_bar['close'] - (current_bar['ATR'] * 2.0)
                if new_sl > sl: sl = new_sl
                if current_bar['low'] <= sl:
                    engine.execute_trade(entry_time, entry_price, "buy", sl, sl_dist_init)
                    in_trade = False
            else:
                new_sl = current_bar['close'] + (current_bar['ATR'] * 2.0)
                if new_sl < sl: sl = new_sl
                if current_bar['high'] >= sl:
                    engine.execute_trade(entry_time, entry_price, "sell", sl, sl_dist_init)
                    in_trade = False
            continue

        # 2. กรองด้วย SMC (วิชาที่บอทใช้จริง)
        # เราส่งเฉพาะข้อมูลย้อนหลังถึงแท่งปัจจุบันไปวิเคราะห์
        sub_df = df.iloc[i-60:i].copy()
        trend = detect_trend(sub_df)
        raw_sig = choose_strategy(trend)
        smc_sig = liquidity_filter(sub_df, raw_sig) # buy, sell, หรือ hold

        if smc_sig == "hold": continue

        # 3. ยืนยันด้วย AI V4.0
        X_input = np.array([scaled_data[i-60:i]])
        pred = model.predict(X_input, verbose=0)[0][0]
        
        # ลั่นไกเมื่อ SMC และ AI เห็นพ้องตรงกัน!
        if smc_sig in ["buy", "strong_buy"] and pred >= ai_threshold:
            in_trade, trade_type = True, "buy"
            entry_price, entry_time = current_bar['close'], current_bar['time']
            sl_dist_init = current_bar['ATR'] * 2.0
            sl = entry_price - sl_dist_init
        elif smc_sig in ["sell", "strong_sell"] and (1-pred) >= ai_threshold:
            in_trade, trade_type = True, "sell"
            entry_price, entry_time = current_bar['close'], current_bar['time']
            sl_dist_init = current_bar['ATR'] * 2.0
            sl = entry_price + sl_dist_init

    engine.generate_report()

if __name__ == "__main__":
    if connect_mt5():
        run_backtest_pro("XAUUSDm", bars=10000, ai_threshold=0.52)
        mt5.shutdown()