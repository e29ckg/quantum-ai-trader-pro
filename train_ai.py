import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report
import joblib
import os
from sklearn.utils.class_weight import compute_sample_weight

# ==========================================
# 1. ปรุงวัตถุดิบ (Feature Engineering)
# ==========================================
def add_features(df):
    print("⏳ กำลังสร้าง Features (สัดส่วนและความเร่ง)...")
    df = df.copy()
    
    # คำนวณ ATR (ความผันผวน)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(14).mean()
    df['ATR_50'] = tr.rolling(50).mean()
    
    # 🌟 ฟีเจอร์เทพ: สัดส่วนความผันผวน (Volatility Squeeze/Expansion)
    df['Volatility_Ratio'] = df['ATR_14'] / df['ATR_50']
    
    # คำนวณ EMA
    df['EMA_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # 🌟 ฟีเจอร์เทพ: ระยะห่างจากเส้นค่าเฉลี่ย (Price Distance)
    df['Dist_EMA20'] = (df['close'] - df['EMA_20']) / df['EMA_20'] * 100
    df['Dist_EMA50'] = (df['close'] - df['EMA_50']) / df['EMA_50'] * 100
    
    # 🌟 ฟีเจอร์เทพ: ความชันของเทรนด์ (Momentum)
    df['Trend_Slope'] = (df['EMA_20'] - df['EMA_20'].shift(5)) / df['EMA_20'].shift(5) * 100
    
    # RSI แบบง่าย (ประหยัดไลบรารี)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))

    df.dropna(inplace=True)
    return df

# ==========================================
# 2. สอนเป้าหมาย (Triple Barrier Labeling)
# ==========================================
def apply_triple_barrier(df, atr_sl_mult=1.0, rr_ratio=1.5, max_bars=30):
    print(f"🎯 กำลังแปะป้ายข้อมูล (Labeling) ด้วย TP 1:{rr_ratio} และ SL x{atr_sl_mult}...")
    labels = []
    
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    atrs = df['ATR_14'].values

    for i in range(len(df)):
        if i + max_bars >= len(df):
            labels.append(2) # 2 = HOLD (ข้อมูลไม่พอให้ตัดสินใจ)
            continue

        entry = closes[i]
        sl_dist = atrs[i] * atr_sl_mult
        tp_dist = sl_dist * rr_ratio

        buy_tp = entry + tp_dist
        buy_sl = entry - sl_dist
        sell_tp = entry - tp_dist
        sell_sl = entry + sl_dist

        label = 2 # เริ่มต้นให้เป็น 2 (HOLD) ไปก่อน
        
        for j in range(1, max_bars + 1):
            future_high = highs[i+j]
            future_low = lows[i+j]

            # เช็คว่าโดนฝั่งไหนก่อนกัน?
            hit_buy_tp = future_high >= buy_tp
            hit_buy_sl = future_low <= buy_sl
            hit_sell_tp = future_low <= sell_tp
            hit_sell_sl = future_high >= sell_sl

            # ถ้ากราฟพุ่งทะลุ TP ฝั่ง BUY ก่อนโดน SL
            if hit_buy_tp and not hit_buy_sl:
                label = 1 # 1 = BUY ชนะ!
                break
            # ถ้ากราฟร่วงทะลุ TP ฝั่ง SELL ก่อนโดน SL
            elif hit_sell_tp and not hit_sell_sl:
                label = 0 # 0 = SELL ชนะ!
                break
            # ถ้าชน SL ทั้งคู่ หรือกราฟสวิงกิน 2 ฝั่ง (ตลาดมั่ว)
            elif hit_buy_sl or hit_sell_sl:
                label = 2 # 2 = HOLD (สวิงมั่ว อย่าเทรด)
                break
                
        labels.append(label)
        
    df['Target'] = labels
    return df

# ==========================================
# 3. สร้างและฝึกสมองกล (XGBoost Training)
# ==========================================
# ==========================================
# 3. สร้างและฝึกสมองกล (XGBoost Training)
# ==========================================
# ==========================================
# 3. สร้างและฝึกสมองกล (XGBoost Training)
# ==========================================
def train_quantum_model(csv_file_path):
    print(f"\n🚀 เริ่มต้นกระบวนการฝึก AI จากไฟล์: {csv_file_path}")
    
    # 1. โหลดข้อมูล (🌟 ท่าไม้ตายสูงสุด: บังคับ UTF-16 + ไม่มีหัวตาราง + คั่นด้วยลูกน้ำ)
    try:
        # MT5 ส่วนใหญ่ใช้ UTF-16
        df = pd.read_csv(csv_file_path, encoding='utf-16', sep=',', header=None)
    except Exception:
        try:
            # เผื่อหลุดเป็น UTF-8 มา
            df = pd.read_csv(csv_file_path, encoding='utf-8', sep=',', header=None)
        except Exception as e:
            print(f"❌ โหลดไฟล์ไม่ได้เลยครับ: {e}")
            return

    # นับจำนวนคอลัมน์ แล้วตั้งชื่อให้มันใหม่แบบเผด็จการ!
    num_cols = len(df.columns)
    
    if num_cols == 7:
        # แบบที่ 1: วันและเวลาอยู่คอลัมน์เดียวกัน
        df.columns = ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread']
    elif num_cols == 8:
        # แบบที่ 2: วัน และ เวลา แยกคอลัมน์กัน
        df.columns = ['date', 'time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread']
    elif num_cols >= 9:
        # แบบที่ 3: มี Real Volume โผล่มาด้วย
        cols = ['date', 'time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
        for i in range(9, num_cols):
            cols.append(f'extra_{i}')
        df.columns = cols
    else:
        print(f"❌ รูปแบบไฟล์ประหลาดมากครับ มีแค่ {num_cols} คอลัมน์ บอทงง!")
        return

    # เคลียร์ข้อมูลที่อาจจะเป็นข้อความ (String) ให้กลายเป็นตัวเลข (Float) ทั้งหมด
    for col in ['open', 'high', 'low', 'close', 'tick_volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # ลบแถวที่แปลงเป็นตัวเลขไม่ได้ทิ้งไป (กัน Error)
    df.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)

    print(f"✅ โหลดข้อมูลสำเร็จ! พบกราฟทั้งหมด {len(df)} แท่ง")
    print(f"🎯 คอลัมน์พร้อมใช้งาน: {df.columns.tolist()}")
            
    # 2. ปรุงข้อมูล และแปะป้าย
    # ------------------------------------------------
    # 🌟 แก้จุดที่ 1: ลดสเปคให้ AI เห็นตัวอย่างการชนะมากขึ้น
    # ------------------------------------------------
    df = add_features(df)
    # ลด rr_ratio จาก 1.5 เหลือ 1.2 และเพิ่ม max_bars เป็น 60 ให้กราฟมีเวลาวิ่งชนเป้า
    df = apply_triple_barrier(df, atr_sl_mult=1.0, rr_ratio=1.2, max_bars=60)
    
    df = df.iloc[:-60] # ลบข้อมูล 60 แท่งสุดท้ายทิ้ง (ป้องกันกราฟอนาคตแหว่ง)

    features = ['tick_volume', 'Volatility_Ratio', 'Dist_EMA20', 'Dist_EMA50', 'Trend_Slope', 'RSI_14']
    X = df[features]
    y = df['Target']

    split_idx = int(len(df) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    print(f"📊 จำนวนข้อมูลเรียน: {len(X_train)} แท่ง | จำนวนข้อมูลสอบ: {len(X_test)} แท่ง")

    # ------------------------------------------------
    # 🌟 แก้จุดที่ 2: ท่าไม้ตาย "ตบกบาลถ่วงน้ำหนัก"
    # ------------------------------------------------
    # บังคับให้คลาสที่โผล่มาน้อย (BUY/SELL) มีน้ำหนักคะแนน "มหาศาล" 
    # AI จะไม่กล้าเมิน BUY/SELL อีกต่อไป!
    weights = compute_sample_weight(class_weight='balanced', y=y_train)

    model = xgb.XGBClassifier(
        objective='multi:softprob',
        num_class=3,
        max_depth=6,                # 🌟 เพิ่มความลึกสมองกลเป็น 6 ให้มันคิดซับซ้อนขึ้น
        learning_rate=0.05,
        n_estimators=300,           # 🌟 เพิ่มจำนวนต้นไม้เป็น 300 ต้น
        random_state=42
    )

    print("🤖 AI กำลังอ่านกราฟและจำลองการเทรด (Training แบบดุดัน!)...")
    
    # 🌟 ยัด weights เข้าไปตอน fit เพื่อบังคับให้มันสนใจ BUY/SELL
    model.fit(X_train, y_train, sample_weight=weights)

    # 4. สอบวัดผลความแม่นยำ
    predictions = model.predict(X_test)
    print("\n✅ ผลการสอบของ AI (Test Results - ฉบับดุดัน):")
    print(classification_report(y_test, predictions, target_names=['SELL (0)', 'BUY (1)', 'HOLD (2)']))

    # 5. บันทึกสมองกลก้อนใหม่
    if not os.path.exists('models'):
        os.makedirs('models')
    
    model_path = 'models/xgboost_quantum_v4.pkl'
    joblib.dump(model, model_path)
    print(f"💾 บันทึกสมองกลสำเร็จ! ไฟล์อยู่ที่: {model_path}")
    print("🔥 พร้อมนำไปเสียบเข้ากับยานแม่ Quantum AI PRO แล้วครับลูกพี่!")

# ------------------------------------------
# ▶️ จุดสตาร์ทการทำงาน (ใส่ชื่อไฟล์ CSV กราฟของลูกพี่ตรงนี้)
# ------------------------------------------
if __name__ == "__main__":
    # ⚠️ ข้อควรระวัง: ลูกพี่ต้องไปโหลด History Data (OHLCV) จาก MT5 
    # ออกมาเป็นไฟล์ .csv (เช่น 'XAUUSD_M15.csv') แล้วเอามาวางในโฟลเดอร์เดียวกันก่อนรันนะครับ!
    
    csv_file = "XAUUSDmM15.csv" # เปลี่ยนชื่อไฟล์ตรงนี้
    
    if os.path.exists(csv_file):
        train_quantum_model(csv_file)
    else:
        print(f"❌ หาไฟล์ '{csv_file}' ไม่เจอครับลูกพี่! ไปโหลดจาก MT5 มาใส่ก่อนนะครับ")