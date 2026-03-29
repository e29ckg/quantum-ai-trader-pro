import pandas as pd
import numpy as np
import sys
import joblib
import json
import os
from datetime import datetime

# =========================================================
# 🛠️ คลาสเครื่องยนต์ Backtest (จำลองการเก็บกำไร/ขาดทุน)
# =========================================================
class BacktestEngine:
    def __init__(self, initial_balance=3000.0):
        self.balance = initial_balance
        self.equity = initial_balance
        self.trades = []
        self.peak_equity = initial_balance
        self.max_drawdown = 0.0
        
    def execute_trade(self, entry_time, entry_price, trade_type, exit_price, sl_dist, reason, lot=0.01, contract_size=100):
        if trade_type == "buy":
            profit = (exit_price - entry_price) * lot * contract_size
        else:
            profit = (entry_price - exit_price) * lot * contract_size
            
        self.balance += profit
        if self.balance > self.peak_equity:
            self.peak_equity = self.balance
        
        drawdown = (self.peak_equity - self.balance) / self.peak_equity * 100
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
            
        self.trades.append({
            "entry_time": entry_time, "type": trade_type,
            "entry": entry_price, "exit": exit_price,
            "profit": profit, "reason": reason, "balance": self.balance
        })

    def generate_report(self, config=None):
        wins = [t for t in self.trades if t['profit'] > 0]
        losses = [t for t in self.trades if t['profit'] < 0]
        be = [t for t in self.trades if t['profit'] == 0]
        
        total = len(self.trades)
        win_rate = (len(wins) / total * 100) if total > 0 else 0
        net_profit = sum(t['profit'] for t in self.trades)
        
        return {
            "total_trades": total, "win_trades": len(wins), "loss_trades": len(losses),
            "be_trades": len(be), "win_rate": round(win_rate, 1), "net_profit": round(net_profit, 2),
            "mdd": round(self.max_drawdown, 2), "final_balance": round(self.balance, 2), 
            "config": config
        }

# =========================================================
# 🚀 ฟังก์ชันจำลองการเทรดหลัก (Master Backtest Engine)
# =========================================================
def run_backtest_pro(symbol, bars=2000, df=None, model=None, sym_config=None, **kwargs):
    
    # --- 1. โหลดการตั้งค่าทั้งหมด (Global & Symbol Config) ---
    config_path = "master_config.json"
    if os.path.exists(config_path):
        with open(config_path, "r") as f: master_cfg = json.load(f)
    else:
        master_cfg = {}

    ENDLESS_TRAILING_MODE = master_cfg.get("ENDLESS_TRAILING_MODE", True)  
    QUICK_SCALP_MODE = master_cfg.get("QUICK_SCALP_MODE", False)      
    QUICK_PROFIT_TARGET = float(master_cfg.get("QUICK_PROFIT_TARGET", 5.0))    
    MAX_ALLOWED_LOSS_USD = float(master_cfg.get("MAX_ALLOWED_LOSS_USD", 30.0)) 

    if sym_config is None:
        try:
            from database.db import get_symbol_config
            sym_config = get_symbol_config(symbol)
        except:
            sym_config = {}

    is_auto_tune = sym_config.get('auto_tune', False)
    
    # 🌟 โหลดตั้งค่าโหมดแก้เกม (Recovery)
    recovery_mode = sym_config.get('recovery_mode', False)
    rec_step_atr = float(sym_config.get('recovery_step_atr', 1.0))
    rec_lot_mult = float(sym_config.get('recovery_lot_mult', 1.5))
    max_rec_trades = int(sym_config.get('max_recovery_trades', 3))
    
    # 🌟 โหลดเวลาเทรด (Time Filter)
    start_time_str = sym_config.get('trade_start_time', '00:00')
    end_time_str = sym_config.get('trade_end_time', '23:59')
    start_t = datetime.strptime(start_time_str, "%H:%M").time()
    end_t = datetime.strptime(end_time_str, "%H:%M").time()

    # --- 2. โหลดข้อมูลกราฟและโมเดล ---
    if df is None:
        try:
            from mt5_engine.data_feed import get_candles 
            import MetaTrader5 as mt5
            print(f"📊 [Backtest] กำลังโหลดกราฟ {symbol} จำนวน {bars} แท่ง...")
            df = get_candles(symbol, mt5.TIMEFRAME_M15, bars=int(bars))
            if df is None or df.empty: return {"error": "ดึงข้อมูลกราฟไม่สำเร็จ"}
        except Exception as e:
            return {"error": f"เกิดข้อผิดพลาดในการดึงกราฟ: {e}"}

    if model is None:
        try: model = joblib.load('models/xgboost_quantum_v5.pkl')
        except: pass

    # --- 3. Feature Engineering (เตรียมข้อมูลให้ AI) ---
    df_ai = df.copy()
    
    tr = pd.concat([df_ai['high'] - df_ai['low'], (df_ai['high'] - df_ai['close'].shift()).abs(), (df_ai['low'] - df_ai['close'].shift()).abs()], axis=1).max(axis=1)
    df_ai['ATR_14'] = tr.rolling(14).mean()
    df_ai['ATR_50'] = tr.rolling(50).mean()
    df_ai['Volatility_Ratio'] = df_ai['ATR_14'] / df_ai['ATR_50']
    
    df_ai['EMA_20'] = df_ai['close'].ewm(span=20, adjust=False).mean()
    df_ai['EMA_50'] = df_ai['close'].ewm(span=50, adjust=False).mean()
    df_ai['Dist_EMA20'] = (df_ai['close'] - df_ai['EMA_20']) / df_ai['EMA_20'] * 100
    df_ai['Dist_EMA50'] = (df_ai['close'] - df_ai['EMA_50']) / df_ai['EMA_50'] * 100
    df_ai['Trend_Slope'] = (df_ai['EMA_20'] - df_ai['EMA_20'].shift(5)) / df_ai['EMA_20'].shift(5) * 100
    
    delta = df_ai['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df_ai['RSI_14'] = 100 - (100 / (1 + (gain / loss)))

    df_ai['EMA_200'] = df_ai['close'].ewm(span=200, adjust=False).mean()
    df_ai['Macro_Trend'] = np.where(df_ai['close'] > df_ai['EMA_200'], 1, -1)
    
    if 'time' in df_ai.columns:
        time_col = pd.to_datetime(df_ai['time'], unit='s') if pd.api.types.is_numeric_dtype(df_ai['time']) else pd.to_datetime(df_ai['time'])
        df_ai['Hour'], df_ai['DayOfWeek'] = time_col.dt.hour, time_col.dt.dayofweek
        df_ai['ActualTime'] = time_col # เก็บเวลาไว้เช็ค Time Filter
    else:
        df_ai['Hour'], df_ai['DayOfWeek'] = df_ai.index.hour, df_ai.index.dayofweek
        df_ai['ActualTime'] = df_ai.index

    macd_line = df_ai['close'].ewm(span=12, adjust=False).mean() - df_ai['close'].ewm(span=26, adjust=False).mean()
    df_ai['MACD_hist'] = macd_line - macd_line.ewm(span=9, adjust=False).mean()

    features = ['tick_volume', 'Volatility_Ratio', 'Dist_EMA20', 'Dist_EMA50', 'Trend_Slope', 'Macro_Trend', 'RSI_14', 'Hour', 'DayOfWeek']
    df_ai.dropna(subset=features, inplace=True)

    print("🧠 AI กำลังคำนวณความน่าจะเป็นทั้งหมด (Batch Prediction)...")
    try: all_probs = model.predict_proba(df_ai[features].values)
    except: all_probs = np.random.rand(len(df_ai), 3)

    # --- 4. เตรียมเครื่องยนต์จำลองเทรด ---
    engine = BacktestEngine(initial_balance=3000.0) 
    open_positions = []
    contract_size = 100 if "XAU" in symbol else 1 
    base_lot_size = 0.01

    print(f"🤖 เริ่มจำลองการเทรด V5 (Auto-Tune: {'🟢' if is_auto_tune else '🔴'} | DCA: {'🚑' if recovery_mode else '🔴'})")
    total_steps = len(df_ai)

    # --- 5. ลูปจำลองเวลาเดินหน้า (Time-Series Loop) ---
    for i in range(total_steps):
        current_bar = df_ai.iloc[i]
        
        if i % 500 == 0 or i == total_steps - 1:
            sys.stdout.write(f"\r🚀 [รัน Backtest] |{'█' * int(30 * (i + 1) // total_steps):30}| {((i + 1) / total_steps * 100):.1f}%")
            sys.stdout.flush()

        atr_14 = current_bar['ATR_14']
        
        # ⏱️ เช็คเวลาปัจจุบันว่าอยู่ในช่วงให้เทรดไหม
        cur_time = current_bar['ActualTime'].time()
        is_trading_time = (start_t <= cur_time <= end_t) if start_t <= end_t else (cur_time >= start_t or cur_time <= end_t)

        # ⚙️ Auto-Tune Dynamic Adjustments
        if is_auto_tune:
            is_high_vol = atr_14 > (current_bar['ATR_50'] * 1.2)
            is_strong_trend = (abs(current_bar['EMA_20'] - current_bar['EMA_50']) / current_bar['EMA_50']) > 0.002
            
            cur_conf = float(sym_config.get('at_trend_strong_conf' if is_strong_trend else 'at_trend_weak_conf', 42.0)) / 100.0
            cur_rr = float(sym_config.get('at_trend_strong_rr' if is_strong_trend else 'at_trend_weak_rr', 1.0))
            cur_atr_sl = float(sym_config.get('at_vol_high_atr_sl' if is_high_vol else 'at_vol_low_atr_sl', 1.0))
            cur_be_mult = float(sym_config.get('at_vol_high_be' if is_high_vol else 'at_vol_low_be', 1.2))
        else:
            cur_conf = float(sym_config.get('confidence', 54.0)) / 100.0
            cur_rr = float(sym_config.get('rr_ratio', 1.5))
            cur_atr_sl = float(sym_config.get('atr_sl', 1.0))
            cur_be_mult = float(sym_config.get('break_even', 1.5))
            is_strong_trend = False

        # 🛡️ โซน 1: จัดการออเดอร์เก่า & Recovery DCA
        if len(open_positions) > 0:
            
            # 🎯 1.1 ระบบรวบตึง (Basket Close)
            if recovery_mode and len(open_positions) > 1:
                total_profit = sum([
                    (current_bar['close'] - p['entry']) * p['lot'] * contract_size if p['type'] == 'buy' 
                    else (p['entry'] - current_bar['close']) * p['lot'] * contract_size 
                    for p in open_positions
                ])
                if total_profit >= QUICK_PROFIT_TARGET:
                    for pos in open_positions:
                        engine.execute_trade(pos['time'], pos['entry'], pos['type'], current_bar['close'], pos['sl_dist_init'], "Basket Close 🎯", lot=pos['lot'], contract_size=contract_size)
                    open_positions = []
                    continue # จบแท่งนี้เลย

            # 🚑 1.2 ระบบยิงไม้แก้ (DCA)
            if recovery_mode and len(open_positions) < max_rec_trades:
                last_pos = open_positions[-1]
                drag_dist = (last_pos['entry'] - current_bar['close']) if last_pos['type'] == 'buy' else (current_bar['close'] - last_pos['entry'])
                
                if drag_dist >= (rec_step_atr * atr_14):
                    new_lot = round(last_pos['lot'] * rec_lot_mult, 2)
                    open_positions.append({
                        "type": last_pos['type'], "entry": current_bar['close'], "time": current_bar.name if hasattr(current_bar, 'name') else i,
                        "sl_dist_init": last_pos['sl_dist_init'], "sl": 0.0, "tp": 0.0, "be_applied": False, "lot": new_lot, "is_dca": True
                    })

            # 🧹 1.3 จัดการทีละออเดอร์ (Trailing, BE, Scalp)
            remaining_positions = []
            for pos in open_positions:
                closed = False
                cur_profit = (current_bar['close'] - pos['entry']) * pos['lot'] * contract_size if pos['type'] == "buy" else (pos['entry'] - current_bar['close']) * pos['lot'] * contract_size
                
                if QUICK_SCALP_MODE and cur_profit >= QUICK_PROFIT_TARGET:
                    engine.execute_trade(pos['time'], pos['entry'], pos['type'], current_bar['close'], pos['sl_dist_init'], "Quick Scalp ⚡", lot=pos['lot'], contract_size=contract_size)
                    closed = True

                if not closed and not ENDLESS_TRAILING_MODE and pos['tp'] > 0:
                    if pos['type'] == "buy" and current_bar['high'] >= pos['tp']:
                        engine.execute_trade(pos['time'], pos['entry'], "buy", pos['tp'], pos['sl_dist_init'], "TP", lot=pos['lot'], contract_size=contract_size)
                        closed = True
                    elif pos['type'] == "sell" and current_bar['low'] <= pos['tp']:
                        engine.execute_trade(pos['time'], pos['entry'], "sell", pos['tp'], pos['sl_dist_init'], "TP", lot=pos['lot'], contract_size=contract_size)
                        closed = True
                
                if not closed and pos['sl'] > 0:
                    if pos['type'] == "buy" and current_bar['low'] <= pos['sl']:
                        reason = "Trailing SL 🌊" if pos['be_applied'] and ENDLESS_TRAILING_MODE else ("Break-Even 🔒" if pos['be_applied'] else "SL 🔴")
                        engine.execute_trade(pos['time'], pos['entry'], "buy", pos['sl'], pos['sl_dist_init'], reason, lot=pos['lot'], contract_size=contract_size)
                        closed = True
                    elif pos['type'] == "sell" and current_bar['high'] >= pos['sl']:
                        reason = "Trailing SL 🌊" if pos['be_applied'] and ENDLESS_TRAILING_MODE else ("Break-Even 🔒" if pos['be_applied'] else "SL 🔴")
                        engine.execute_trade(pos['time'], pos['entry'], "sell", pos['sl'], pos['sl_dist_init'], reason, lot=pos['lot'], contract_size=contract_size)
                        closed = True

                if not closed:
                    if pos['type'] == "buy" and not pos['be_applied'] and current_bar['close'] > pos['entry'] + (atr_14 * cur_be_mult):
                        pos['sl'], pos['be_applied'] = pos['entry'], True
                    elif pos['type'] == "sell" and not pos['be_applied'] and current_bar['close'] < pos['entry'] - (atr_14 * cur_be_mult):
                        pos['sl'], pos['be_applied'] = pos['entry'], True
                        
                    if ENDLESS_TRAILING_MODE and pos['be_applied']:
                        trail_dist = atr_14 * cur_atr_sl
                        if pos['type'] == "buy" and (current_bar['close'] - trail_dist) > pos['sl']: pos['sl'] = current_bar['close'] - trail_dist
                        elif pos['type'] == "sell" and (current_bar['close'] + trail_dist) < pos['sl']: pos['sl'] = current_bar['close'] + trail_dist
                    
                    remaining_positions.append(pos)
                    
            open_positions = remaining_positions

        # 🎯 โซน 2: ยิงออเดอร์ใหม่ (เช็คเวลา + สัญญาณ)
        if not is_trading_time: continue # 🌟 ถ้านอกเวลา ไม่ให้ออกไม้ใหม่เลย

        buy_score = sum([current_bar['RSI_14'] > 50, current_bar['close'] > current_bar['EMA_50'], current_bar['MACD_hist'] > 0])
        sell_score = sum([current_bar['RSI_14'] < 50, current_bar['close'] < current_bar['EMA_50'], current_bar['MACD_hist'] < 0])

        smc_sig = "hold"
        if all_probs[i][1] >= cur_conf and buy_score >= 2: smc_sig = "buy"
        elif all_probs[i][0] >= cur_conf and sell_score >= 2: smc_sig = "sell"

        if smc_sig == "hold": continue
                
        sl_dist = atr_14 * cur_atr_sl
        if (sl_dist * base_lot_size * contract_size) > MAX_ALLOWED_LOSS_USD: continue 

        # กฏการเข้าไม้ (ไม้แรก หรือ Add-on)
        dca_count = sum(1 for p in open_positions if p.get('is_dca', False))
        can_open = False
        
        if len(open_positions) == 0: 
            can_open = True
        # ยิง Add-on ได้ก็ต่อเมื่อไม่มีไม้ DCA ค้างอยู่
        elif len(open_positions) == 1 and is_auto_tune and is_strong_trend and open_positions[0]['be_applied'] and open_positions[0]['type'] == smc_sig and dca_count == 0: 
            can_open = True

        if can_open:
            entry_p = current_bar['close']
            tp_p = 0.0 if ENDLESS_TRAILING_MODE else (entry_p + (sl_dist * cur_rr) if smc_sig == "buy" else entry_p - (sl_dist * cur_rr))
            sl_p = entry_p - sl_dist if smc_sig == "buy" else entry_p + sl_dist
            
            open_positions.append({
                "type": smc_sig, "entry": entry_p, "time": current_bar.name if hasattr(current_bar, 'name') else i,
                "sl_dist_init": sl_dist, "sl": sl_p, "tp": tp_p, "be_applied": False, "lot": base_lot_size, "is_dca": False
            })

    # --- 6. เก็บกวาดตอนจบกราฟ ---
    last_bar = df_ai.iloc[-1]
    for pos in open_positions:
        engine.execute_trade(pos['time'], pos['entry'], pos['type'], last_bar['close'], pos['sl_dist_init'], "End of Data 🏁", lot=pos['lot'], contract_size=contract_size)

    print("\n✅ ประมวลผลเสร็จสิ้น! กำลังส่งรายงานกลับไปที่หน้าเว็บ...")
    return engine.generate_report(config={"auto_tune": is_auto_tune, "endless_trailing": ENDLESS_TRAILING_MODE, "quick_scalp": QUICK_SCALP_MODE, "recovery_dca": recovery_mode})