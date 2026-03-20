import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import xgboost as xgb
import optuna
import joblib
from datetime import datetime, timedelta
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import warnings
import sys
warnings.filterwarnings('ignore')

# ==========================================
# ⚙️ ตั้งค่าการเทรน (Hyperparameters Configuration)
# ==========================================
SYMBOL = "XAUUSDm"
TIMEFRAME = mt5.TIMEFRAME_M15
DAYS_BACK = 180       # ใช้ข้อมูลย้อนหลัง 6 เดือน
LOOKAHEAD_BARS = 48   # มองอนาคต 24 แท่ง (6 ชั่วโมงสำหรับ M15)
RR_RATIO = 1        # เป้ากำไร (Risk:Reward)
OPTUNA_TRIALS = 30    # ให้ AI จำลองสู้กันเอง 30 รอบ (ยิ่งเยอะยิ่งแม่น แต่รอนาน)

def load_and_clean_data(symbol, timeframe, days):
    """ดึงข้อมูลจาก MT5 และทำความสะอาด"""
    print(f"📥 [1/5] กำลังดึงข้อมูล {symbol} ย้อนหลัง {days} วัน...")
    if not mt5.initialize():
        print("❌ MT5 Initialize Failed!")
        return None
    
    utc_to = datetime.now()
    utc_from = utc_to - timedelta(days=days)
    rates = mt5.copy_rates_range(symbol, timeframe, utc_from, utc_to)
    
    if rates is None or len(rates) == 0:
        print("❌ ดึงข้อมูลไม่สำเร็จ!")
        return None
        
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    
    # ตัดช่วงกราฟผันผวนผิดปกติ (Spike กะทันหันเกิน 2000 จุดในแท่งเดียว - ข่าวแรง)
    df['body_size'] = abs(df['close'] - df['open'])
    df = df[df['body_size'] < 20.0] # 20.0 ทองคำ = 2000 จุด
    df.drop(columns=['body_size'], inplace=True)
    
    print(f"✅ ดึงข้อมูลสำเร็จ: {len(df)} แท่ง")
    return df

def feature_engineering(df):
    """เพิ่มสัมผัสที่ 6 ให้ AI (Multi-Timeframe & Time Features)"""
    print("🧠 [2/5] กำลังสกัด Features ขั้นสูง...")
    df_ai = df.copy()
    
    # 1. Volatility (ATR)
    high_low = df_ai['high'] - df_ai['low']
    high_close = (df_ai['high'] - df_ai['close'].shift()).abs()
    low_close = (df_ai['low'] - df_ai['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df_ai['ATR_14'] = tr.rolling(14).mean()
    df_ai['ATR_50'] = tr.rolling(50).mean()
    df_ai['Volatility_Ratio'] = df_ai['ATR_14'] / df_ai['ATR_50']
    
    # 2. Trend & Momentum (EMA & RSI)
    df_ai['EMA_20'] = df_ai['close'].ewm(span=20, adjust=False).mean()
    df_ai['EMA_50'] = df_ai['close'].ewm(span=50, adjust=False).mean()
    df_ai['EMA_200'] = df_ai['close'].ewm(span=200, adjust=False).mean() # ตัวแทน Timeframe ใหญ่ (H1/H4)
    
    df_ai['Dist_EMA20'] = (df_ai['close'] - df_ai['EMA_20']) / df_ai['EMA_20'] * 100
    df_ai['Dist_EMA50'] = (df_ai['close'] - df_ai['EMA_50']) / df_ai['EMA_50'] * 100
    df_ai['Trend_Slope'] = (df_ai['EMA_20'] - df_ai['EMA_20'].shift(5)) / df_ai['EMA_20'].shift(5) * 100
    df_ai['Macro_Trend'] = np.where(df_ai['close'] > df_ai['EMA_200'], 1, -1)
    
    delta = df_ai['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df_ai['RSI_14'] = 100 - (100 / (1 + rs))
    
    # 3. Time Features (ให้ AI รู้จักเวลาทองคำ)
    df_ai['Hour'] = df_ai.index.hour
    df_ai['DayOfWeek'] = df_ai.index.dayofweek
    
    return df_ai

def advanced_labeling(df):
    """ทำป้ายกำกับด้วยวิธี Triple Barrier (จำลองยิงออเดอร์ชน TP/SL)"""
    print("🎯 [3/5] กำลังสร้างเป้าหมายการเรียนรู้ (Triple Barrier)...")
    
    # หา High/Low ล่วงหน้า 24 แท่งแบบรวดเร็ว (Vectorized)
    future_high = df['high'].rolling(window=LOOKAHEAD_BARS).max().shift(-LOOKAHEAD_BARS)
    future_low = df['low'].rolling(window=LOOKAHEAD_BARS).min().shift(-LOOKAHEAD_BARS)
    
    # ตั้งเป้าหมาย TP/SL ของแต่ละแท่งตาม ATR หน้างาน
    target_tp_dist = df['ATR_14'] * RR_RATIO
    target_sl_dist = df['ATR_14'] * 1.0
    
    buy_tp_price = df['close'] + target_tp_dist
    buy_sl_price = df['close'] - target_sl_dist
    sell_tp_price = df['close'] - target_tp_dist
    sell_sl_price = df['close'] + target_sl_dist
    
    # เงื่อนไขชนะ/แพ้
    # ฝั่ง BUY: อนาคตต้องขึ้นไปชน TP และ ห้ามลงมาชน SL ก่อน
    buy_win = (future_high >= buy_tp_price) & (future_low > buy_sl_price)
    
    # ฝั่ง SELL: อนาคตต้องลงไปชน TP และ ห้ามขึ้นไปชน SL ก่อน
    sell_win = (future_low <= sell_tp_price) & (future_high < sell_sl_price)
    
    # ใส่ Label: 0=Sell, 1=Buy, 2=Hold
    df['Label'] = 2 
    df.loc[buy_win, 'Label'] = 1
    df.loc[sell_win, 'Label'] = 0
    
    df.dropna(inplace=True)
    return df

def optimize_hyperparameters(X_train, y_train, X_test, y_test):
    """ส่ง AI เข้าค่ายเก็บตัว Optuna (พร้อมหลอดแสดงความคืบหน้า)"""
    print(f"\n⚙️ [4/5] กำลังจัดค่ายเก็บตัว AI ({OPTUNA_TRIALS} รอบ)...")
    print("🥊 AI กำลังสุ่มสู้กันเองเพื่อหาค่าพลังที่แม่นที่สุด!\n")
    
    def objective(trial):
        params = {
            'max_depth': trial.suggest_int('max_depth', 3, 9),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.2, log=True),
            'n_estimators': trial.suggest_int('n_estimators', 100, 500),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'objective': 'multi:softprob',
            'num_class': 3,
            'eval_metric': 'mlogloss',
            'tree_method': 'hist' 
        }
        
        model = xgb.XGBClassifier(**params)
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
        preds = model.predict(X_test)
        return accuracy_score(y_test, preds)

    # 🌟 ฟังก์ชันวาดหลอด Progress Bar โชว์แบบ Real-time
    def progress_callback(study, trial):
        completed = trial.number + 1
        percent = (completed / OPTUNA_TRIALS) * 100
        best_acc = study.best_value * 100 if study.best_value else 0.0
        
        # วาดหลอดพลัง
        bar = '█' * int(40 * completed // OPTUNA_TRIALS)
        sys.stdout.write(f"\r🔥 [Training] |{bar:40}| {percent:.1f}% (👑 แม่นยำสูงสุดตอนนี้: {best_acc:.2f}%)")
        sys.stdout.flush()

    study = optuna.create_study(direction='maximize')
    optuna.logging.set_verbosity(optuna.logging.WARNING) # ปิด Log รกๆ ของ Optuna
    
    # สั่งรัน Optuna พร้อมพ่วงตัวแสดงหลอดพลัง (callbacks)
    study.optimize(objective, n_trials=OPTUNA_TRIALS, callbacks=[progress_callback])
    
    print(f"\n\n🌟 ได้ค่าพลังที่ดีที่สุดแล้ว! (ความแม่นยำสูงสุด: {study.best_value*100:.2f}%)")
    return study.best_params

def train_and_save(df):
    """เทรนรอบสุดท้ายและเซฟโมเดล V5 (พร้อมระบบดัดนิสัย AI ขี้เกียจ)"""
    features = [
        'tick_volume', 'Volatility_Ratio', 'Dist_EMA20', 
        'Dist_EMA50', 'Trend_Slope', 'Macro_Trend', 'RSI_14',
        'Hour', 'DayOfWeek'
    ]
    
    # 🌟🌟🌟 โซนดัดนิสัย AI (Class Balancing) 🌟🌟🌟
    print("⚖️ [System] กำลังปรับสมดุลข้อสอบ บังคับให้ AI เลิกขี้เกียจ...")
    df_sell = df[df['Label'] == 0]
    df_buy = df[df['Label'] == 1]
    df_hold = df[df['Label'] == 2]
    
    # หาว่าฝั่งที่น้อยที่สุด (Buy หรือ Sell) มีกี่ไม้
    min_trades = min(len(df_sell), len(df_buy))
    
    # ถ้ามีไม้น้อยไป (ต่ำกว่า 100) แปลว่าตลาดยากไป ให้ใช้ทั้งหมดที่มี
    limit_size = max(min_trades, 100) 

    # บังคับสัดส่วน 1:1:1 ไปเลย! ความกล้าจะได้เต็ม 100
    df_hold_sampled = df_hold.sample(n=min(len(df_hold), limit_size), random_state=42)
    df_sell_sampled = df_sell.sample(n=min(len(df_sell), limit_size), random_state=42)
    df_buy_sampled = df_buy.sample(n=min(len(df_buy), limit_size), random_state=42)
    
    # เอาข้อสอบที่สมดุลแล้วมาต่อกันใหม่ แล้วเรียงตามเวลาเหมือนเดิม
    df_balanced = pd.concat([df_sell_sampled, df_buy_sampled, df_hold_sampled]).sort_index()
    print(f"📊 สัดส่วนข้อสอบใหม่: Sell={len(df_sell_sampled)} | Buy={len(df_buy_sampled)} | Hold={len(df_hold_sampled)}")
    # 🌟🌟🌟 จบโซนปรับสมดุล 🌟🌟🌟

    X = df_balanced[features]
    y = df_balanced['Label']
    
    split_idx = int(len(df_balanced) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    best_params = optimize_hyperparameters(X_train, y_train, X_test, y_test)
    
    print("🤖 [5/5] กำลังหลอมรวมสมองกล V5 รอบสุดท้าย...")
    best_params['objective'] = 'multi:softprob'
    best_params['num_class'] = 3
    
    # ใช้ class_weight เพื่อย้ำให้ AI สนใจ Buy/Sell มากขึ้นไปอีก!
    final_model = xgb.XGBClassifier(**best_params)
    final_model.fit(X_train, y_train) 
    
    import os
    os.makedirs('models', exist_ok=True)
    save_path = 'models/xgboost_quantum_v5.pkl'
    joblib.dump(final_model, save_path)
    print(f"🎉 สำเร็จ! บันทึกสมองกล V5 ไว้ที่: {save_path}")
    
    preds = final_model.predict(X_test)
    print("\n📊 --- รายงานความฉลาด (Test Set - ของจริงไม่มั่วนิ่ม) ---")
    print(classification_report(y_test, preds, target_names=['Sell (0)', 'Buy (1)', 'Hold (2)']))

if __name__ == "__main__":
    print(f"🚀 เริ่มกระบวนการสร้าง AI กองทุนระดับ V5 (Symbol: {SYMBOL})")
    df_raw = load_and_clean_data(SYMBOL, TIMEFRAME, DAYS_BACK)
    if df_raw is not None:
        df_features = feature_engineering(df_raw)
        df_labeled = advanced_labeling(df_features)
        train_and_save(df_labeled)
        mt5.shutdown()
        print("\n🦅 [System] สมองกล V5 พร้อมรบแล้วลูกพี่! นำไปเสียบยานแม่ได้เลย!")