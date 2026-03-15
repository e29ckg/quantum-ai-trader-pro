import os
import sys  # 🌟 เพิ่มโมดูล sys สำหรับทำ Progress Bar
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import load_model
from dotenv import load_dotenv

# นำเข้าวิชา SMC จาก AI Engine ของเรา
from ai_engine.market_structure import detect_trend
from ai_engine.strategy_selector import choose_strategy
from ai_engine.liquidity_ai import liquidity_filter
from mt5_engine.connect import connect_mt5

load_dotenv()

# ==========================================
# 📊 Backtest Engine (อัปเกรดรองรับ Auto-Tune & Break-Even)
# ==========================================
class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0, risk_per_trade: float = 0.01):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.risk_per_trade = risk_per_trade
        self.trades = []
        self.equity_curve = [initial_capital]

    def execute_trade(self, entry_time, entry_price, signal, exit_price, sl_distance, exit_reason="UNKNOWN"):
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
            "exit": exit_price, "pnl": pnl, "balance": self.balance, "reason": exit_reason
        })

    def generate_report(self):
        print("\n" + "🛡️" * 15)
        print("📊 SMC + AI V4.0 - AUTO TUNE REPORT")
        print("🛡️" * 15)
        
        if not self.trades:
            print("❌ ไม่พบจุดเข้าเทรดเลย! (กรองเข้มจัด หรือไม่มีจังหวะ)")
            return None
            
        df = pd.DataFrame(self.trades)
        win_rate = (len(df[df['pnl'] > 0]) / len(df)) * 100
        be_trades = len(df[df['pnl'] == 0]) # ไม้ที่ชนบังทุน
        
        equity = pd.Series(self.equity_curve)
        mdd = ((equity - equity.cummax()) / equity.cummax()).min() * 100
        
        print(f"ยอดเงินสุดท้าย:   ${self.balance:,.2f}")
        print(f"กำไรสุทธิ:       ${self.balance - self.initial_capital:,.2f}")
        print(f"จำนวนการเทรด:   {len(df)} ไม้ (ชนะ: {len(df[df['pnl'] > 0])} | แพ้: {len(df[df['pnl'] < 0])} | เสมอตัว: {be_trades})")
        print(f"Win Rate:      {win_rate:.2f}% (ไม่รวมไม้เสมอ)")
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
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    df['ATR'] = tr.rolling(14).mean()
    df['ATR_50'] = tr.rolling(50).mean()
    
    df.dropna(inplace=True)
    return df

# ==========================================
# 🚀 PRO RUNNER: ผสม SMC + AI + AUTO-TUNE
# ==========================================
def run_backtest_pro(symbol, bars=10000):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars)
    df = pd.DataFrame(rates)
    df = add_indicators(df)
    
    model = load_model(f"ai_engine/model_{symbol}.h5", compile=False)
    engine = BacktestEngine()
    
    in_trade = False
    trade_type, entry_price, sl, tp, sl_dist_init, entry_time = None, 0, 0, 0, 0, None
    be_applied = False
    
    features = ['open', 'high', 'low', 'close', 'tick_volume', 'EMA_20', 'EMA_50', 'RSI_14']
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(df[features].values)

    print(f"\n⚡ เริ่มซ้อมรบระบบ Full Armor + Auto-Tune สำหรับ {symbol}...")

    # 🌟 กำหนดจำนวนรอบทั้งหมดเพื่อทำ Progress Bar
    total_steps = len(df) - 60

    for i in range(60, len(df)):
        current_bar = df.iloc[i]
        
        # 🌟🌟🌟 ระบบ Progress Bar (โชว์การโหลด % แบบ Real-time) 🌟🌟🌟
        current_step = i - 60 + 1
        if current_step % 50 == 0 or current_step == total_steps:
            percent = (current_step / total_steps) * 100
            bar_length = 30
            filled_len = int(bar_length * current_step // total_steps)
            bar_visual = '█' * filled_len + '-' * (bar_length - filled_len)
            
            # ใช้ \r เพื่อให้มันพิมพ์ทับบรรทัดเดิมเสมอ จอจะได้ไม่รก
            sys.stdout.write(f"\r🚀 [กำลังรัน Backtest] |{bar_visual}| {percent:.1f}% ({current_step}/{total_steps})")
            sys.stdout.flush()
        # 🌟🌟🌟 สิ้นสุดระบบ Progress Bar 🌟🌟🌟

        # 🤖 1. สมองกล Auto-Tune
        atr_14 = current_bar['ATR']
        atr_50 = current_bar['ATR_50']
        ema_20 = current_bar['EMA_20']
        ema_50 = current_bar['EMA_50']
        
        is_high_vol = atr_14 > (atr_50 * 1.2)
        trend_dist = abs(ema_20 - ema_50) / ema_50
        is_strong_trend = trend_dist > 0.002
        
        if is_strong_trend:
            current_conf = float(os.getenv("AUTO_TREND_STRONG_CONFIDENCE", 52.0)) / 100.0
            current_rr = float(os.getenv("AUTO_TREND_STRONG_RR", 2.5))
        else:
            current_conf = float(os.getenv("AUTO_TREND_WEAK_CONFIDENCE", 58.0)) / 100.0
            current_rr = float(os.getenv("AUTO_TREND_WEAK_RR", 1.5))
            
        if is_high_vol:
            current_atr_sl = float(os.getenv("AUTO_VOL_HIGH_ATR_SL", 2.5))
            current_be_mult = float(os.getenv("AUTO_VOL_HIGH_BE", 2.0))
        else:
            current_atr_sl = float(os.getenv("AUTO_VOL_LOW_ATR_SL", 1.5))
            current_be_mult = float(os.getenv("AUTO_VOL_LOW_BE", 1.2))


        # 🛡️ 2. จัดการออเดอร์เดิม
        if in_trade:
            if trade_type == "buy":
                if current_bar['high'] >= tp:
                    engine.execute_trade(entry_time, entry_price, "buy", tp, sl_dist_init, "TP")
                    in_trade = False; continue
                
                if not be_applied and current_bar['close'] > entry_price + (atr_14 * current_be_mult):
                    sl = entry_price
                    be_applied = True
                
                if current_bar['low'] <= sl:
                    reason = "BE" if be_applied else "SL"
                    engine.execute_trade(entry_time, entry_price, "buy", sl, sl_dist_init, reason)
                    in_trade = False; continue

            else:
                if current_bar['low'] <= tp:
                    engine.execute_trade(entry_time, entry_price, "sell", tp, sl_dist_init, "TP")
                    in_trade = False; continue
                
                if not be_applied and current_bar['close'] < entry_price - (atr_14 * current_be_mult):
                    sl = entry_price
                    be_applied = True
                
                if current_bar['high'] >= sl:
                    reason = "BE" if be_applied else "SL"
                    engine.execute_trade(entry_time, entry_price, "sell", sl, sl_dist_init, reason)
                    in_trade = False; continue
            continue


        # 🎯 3. หาจังหวะเข้าเทรดใหม่
        sub_df = df.iloc[i-60:i].copy()
        trend = detect_trend(sub_df)
        raw_sig = choose_strategy(trend)
        smc_sig = liquidity_filter(sub_df, raw_sig)

        if smc_sig == "hold": continue

        X_input = np.array([scaled_data[i-60:i]])
        pred = model.predict(X_input, verbose=0)[0][0]
        
        if smc_sig in ["buy", "strong_buy"] and pred >= current_conf:
            in_trade, trade_type, be_applied = True, "buy", False
            entry_price, entry_time = current_bar['close'], current_bar['time']
            sl_dist_init = atr_14 * current_atr_sl
            sl = entry_price - sl_dist_init
            tp = entry_price + (sl_dist_init * current_rr)
            
        elif smc_sig in ["sell", "strong_sell"] and (1-pred) >= current_conf:
            in_trade, trade_type, be_applied = True, "sell", False
            entry_price, entry_time = current_bar['close'], current_bar['time']
            sl_dist_init = atr_14 * current_atr_sl
            sl = entry_price + sl_dist_init
            tp = entry_price - (sl_dist_init * current_rr)

    # พิมพ์ขึ้นบรรทัดใหม่เมื่อโหลดเสร็จ 100%
    print("\n✅ ประมวลผลเสร็จสิ้น! กำลังจัดทำรายงาน...")
    engine.generate_report()

if __name__ == "__main__":
    if connect_mt5():
        run_backtest_pro("XAUUSDm", bars=10000)
        mt5.shutdown()