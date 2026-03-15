import os
import sys
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import load_model
from dotenv import load_dotenv

from ai_engine.market_structure import detect_trend
from ai_engine.strategy_selector import choose_strategy
from ai_engine.liquidity_ai import liquidity_filter
from mt5_engine.connect import connect_mt5
from database.db import get_symbol_config

load_dotenv()

# ==========================================
# 📊 Backtest Engine 
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

    def generate_report(self, config=None):
        print("\n" + "🛡️" * 15)
        print("📊 SMC + AI V4.0 - BACKTEST REPORT")
        print("🛡️" * 15)
        
        if not self.trades:
            print("❌ ไม่พบจุดเข้าเทรดเลย!")
            return {"status": "error", "message": "ไม่พบจุดเข้าเทรดเลยในรอบนี้ (อาจกรองเข้มไป)"}
            
        df = pd.DataFrame(self.trades)
        win_rate = (len(df[df['pnl'] > 0]) / len(df)) * 100
        be_trades = len(df[df['pnl'] == 0]) 
        
        equity = pd.Series(self.equity_curve)
        mdd = ((equity - equity.cummax()) / equity.cummax()).min() * 100
        net_profit = self.balance - self.initial_capital
        
        print(f"ยอดเงินสุดท้าย:   ${self.balance:,.2f}")
        print(f"กำไรสุทธิ:       ${net_profit:,.2f}")
        print(f"จำนวนการเทรด:   {len(df)} ไม้ (ชนะ: {len(df[df['pnl'] > 0])} | แพ้: {len(df[df['pnl'] < 0])} | เสมอตัว: {be_trades})")
        print(f"Win Rate:      {win_rate:.2f}%")
        print(f"Max Drawdown:  {mdd:.2f}%")
        print("🛡️" * 15 + "\n")
        
        return {
            "status": "success",
            "final_balance": round(self.balance, 2),
            "net_profit": round(net_profit, 2),
            "total_trades": len(df),
            "win_trades": len(df[df['pnl'] > 0]),
            "loss_trades": len(df[df['pnl'] < 0]),
            "be_trades": be_trades,
            "win_rate": round(win_rate, 2),
            "mdd": round(mdd, 2),
            "config": config or {}
        }

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

def run_backtest_pro(symbol, bars=5000):
    if not mt5.terminal_info():
        connect_mt5()

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars)
    if rates is None or len(rates) == 0:
        return {"status": "error", "message": f"ดึงข้อมูลกราฟ {symbol} จาก MT5 ไม่สำเร็จ"}

    df = pd.DataFrame(rates)
    df = add_indicators(df)
    
    try:
        model = load_model(f"ai_engine/model_{symbol}.h5", compile=False)
    except Exception as e:
        return {"status": "error", "message": f"ไม่พบไฟล์โมเดล AI สำหรับ {symbol}"}

    sym_config = get_symbol_config(symbol)
    manual_conf = sym_config.get('confidence', 54.0) / 100.0
    manual_rr = sym_config.get('rr_ratio', 2.0)
    manual_atr_sl = sym_config.get('atr_sl', 2.0)
    manual_be = sym_config.get('break_even', 1.5)
    is_auto_tune = sym_config.get('auto_tune', False)

    engine = BacktestEngine()
    
    in_trade = False
    trade_type, entry_price, sl, tp, sl_dist_init, entry_time = None, 0, 0, 0, 0, None
    be_applied = False
    
    features = ['open', 'high', 'low', 'close', 'tick_volume', 'EMA_20', 'EMA_50', 'RSI_14']
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(df[features].values)

    print(f"\n⚡ เริ่มเตรียมข้อมูล Batch สำหรับ {symbol}...")
    
    # 🌟🌟🌟 อัปเกรด: AI ประมวลผลแบบ Batch (เหมาจ่ายรวดเดียว โคตรไว!) 🌟🌟🌟
    X_all = []
    for i in range(60, len(df)):
        X_all.append(scaled_data[i-60:i])
    X_all = np.array(X_all)

    print("🧠 AI กำลังคำนวณความน่าจะเป็นทั้งหมด (Batch Prediction)...")
    # สั่ง Predict รวดเดียวจบ ประหยัดเวลาไป 99%
    all_predictions = model.predict(X_all, batch_size=128, verbose=0)
    # 🌟🌟🌟 สิ้นสุดการอัปเกรด 🌟🌟🌟

    print(f"🤖 เริ่มจำลองการเทรด (Auto-Tune: {'🟢 เปิด' if is_auto_tune else '🔴 ปิด'})")
    total_steps = len(df) - 60

    for i in range(60, len(df)):
        current_bar = df.iloc[i]
        pred_idx = i - 60
        
        # ดึงค่า AI ที่คำนวณไว้แล้วมาใช้เลย (ทำให้ลูปวิ่งเร็วเป็นจรวด)
        pred = all_predictions[pred_idx][0]
        
        # --- Progress Bar ---
        current_step = pred_idx + 1
        if current_step % 500 == 0 or current_step == total_steps:
            percent = (current_step / total_steps) * 100
            sys.stdout.write(f"\r🚀 [รัน Backtest] |{'█' * int(30 * current_step // total_steps):30}| {percent:.1f}%")
            sys.stdout.flush()

        atr_14 = current_bar['ATR']

        # โหมด Auto-Tune
        if is_auto_tune:
            atr_50 = current_bar['ATR_50']
            ema_20 = current_bar['EMA_20']
            ema_50 = current_bar['EMA_50']
            
            is_high_vol = atr_14 > (atr_50 * 1.2)
            trend_dist = abs(ema_20 - ema_50) / ema_50
            is_strong_trend = trend_dist > 0.002
            
            if is_strong_trend:
                current_conf = float(os.getenv("AUTO_TREND_STRONG_CONFIDENCE", 60.0)) / 100.0
                current_rr = float(os.getenv("AUTO_TREND_STRONG_RR", 2.0))
            else:
                current_conf = float(os.getenv("AUTO_TREND_WEAK_CONFIDENCE", 65.0)) / 100.0
                current_rr = float(os.getenv("AUTO_TREND_WEAK_RR", 1.2))
                
            if is_high_vol:
                current_atr_sl = float(os.getenv("AUTO_VOL_HIGH_ATR_SL", 3.0))
                current_be_mult = float(os.getenv("AUTO_VOL_HIGH_BE", 2.5))
            else:
                current_atr_sl = float(os.getenv("AUTO_VOL_LOW_ATR_SL", 2.0))
                current_be_mult = float(os.getenv("AUTO_VOL_LOW_BE", 1.5))
        else:
            current_conf = manual_conf
            current_rr = manual_rr
            current_atr_sl = manual_atr_sl
            current_be_mult = manual_be


        # 🛡️ จัดการออเดอร์
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


        # 🎯 เข้าเทรด
        sub_df = df.iloc[i-60:i].copy()
        trend = detect_trend(sub_df)
        raw_sig = choose_strategy(trend)
        smc_sig = liquidity_filter(sub_df, raw_sig)

        if smc_sig == "hold": continue
        
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

    print("\n✅ ประมวลผลเสร็จสิ้น! กำลังส่งรายงานกลับไปที่หน้าเว็บ...")
    config_used = {
        "auto_tune": is_auto_tune,
        "confidence": sym_config.get('confidence', 54.0),
        "rr_ratio": manual_rr,
        "atr_sl": manual_atr_sl,
        "break_even": manual_be
    }
    return engine.generate_report(config=config_used)

if __name__ == "__main__":
    if connect_mt5():
        report = run_backtest_pro("XAUUSDm", bars=10000)
        mt5.shutdown()