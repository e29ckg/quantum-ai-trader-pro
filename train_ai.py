import os
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from mt5_engine.connect import connect_mt5

# ==========================================
# ⚙️ ตั้งค่าการเทรน V2.0 (อัปเกรดความฉลาด)
# ==========================================
SYMBOL = "XAUUSDm"            # ใช้ทองคำเป็นแม่แบบในการเรียนรู้ (กราฟผันผวนดี)
TIMEFRAME = mt5.TIMEFRAME_M15 # เรียนจากกราฟ 15 นาที
NUM_BARS = 10000              # ดึงข้อมูลย้อนหลัง 10,000 แท่ง! (ของเดิม 2,000)
SEQ_LENGTH = 60               # ให้ AI ดูกราฟย้อนหลัง 60 แท่ง เพื่อทายแท่งถัดไป
EPOCHS = 50                   # วนอ่านตำรา 50 จบ (ของเดิม 10)
BATCH_SIZE = 64               # แบ่งเรียนทีละ 64 ชุด

def add_indicators(df):
    """ฟังก์ชันเพิ่มอาวุธให้ AI: คำนวณ RSI และ EMA"""
    # 1. เส้นค่าเฉลี่ย EMA 20 และ 50
    df['EMA_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # 2. RSI (Relative Strength Index) 14 แท่ง
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    # เคลียร์ค่าว่าง (NaN) ที่เกิดจากการคำนวณแท่งแรกๆ ทิ้ง
    df.dropna(inplace=True)
    return df

def create_dataset(data, seq_length):
    X, y = [], []
    for i in range(len(data) - seq_length):
        X.append(data[i:i + seq_length])
        # ถ้าแท่งถัดไปราคาปิด สูงกว่า แท่งปัจจุบัน = ให้คำตอบเป็น 1 (ขึ้น) / ถ้าต่ำกว่า = 0 (ลง)
        target = 1 if data[i + seq_length, 3] > data[i + seq_length - 1, 3] else 0
        y.append(target)
    return np.array(X), np.array(y)

if __name__ == "__main__":
    print("🤖 [AI V2.0] กำลังปลุกสมอง Quant Analyst...")
    if not connect_mt5():
        exit()

    print(f"📥 กำลังดึงข้อมูลกราฟ {SYMBOL} จำนวน {NUM_BARS} แท่ง เพื่อส่งให้ AI เรียนรู้...")
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, NUM_BARS)
    mt5.shutdown()

    if rates is None:
        print("❌ ดึงข้อมูลกราฟไม่ได้ โปรดเช็คโบรกเกอร์")
        exit()

    # 1. เตรียมข้อมูล
    df = pd.DataFrame(rates)
    df.rename(columns={'tick_volume': 'volume'}, inplace=True) # 👈 เพิ่มบรรทัดนี้เพื่อแปลภาษาให้ AI เข้าใจ
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # 🌟 2. อัดฉีดอินดิเคเตอร์เข้าสมอง AI
    df = add_indicators(df)
    
    # เลือกคอลัมน์ที่จะให้มันวิเคราะห์ (มี 8 ตัวแปรแล้ว! ทรงพลังมาก)
    features = ['open', 'high', 'low', 'close', 'volume', 'EMA_20', 'EMA_50', 'RSI_14']
    data_to_scale = df[features].values

    # 3. สเกลข้อมูล (บีบตัวเลขให้อยู่ระหว่าง 0 ถึง 1 ให้ AI คำนวณง่าย)
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data_to_scale)

    X, y = create_dataset(scaled_data, SEQ_LENGTH)

    # 4. แบ่งข้อมูล 80% ไว้เรียน (Train) และ 20% ไว้สอบวัดความแม่นยำ (Test)
    split_ratio = int(len(X) * 0.8)
    X_train, y_train = X[:split_ratio], y[:split_ratio]
    X_test, y_test = X[split_ratio:], y[split_ratio:]

    print(f"🧠 ข้อมูลพร้อมแล้ว! เริ่มกระบวนการสร้างสมอง V2.0...")
    print(f"📚 ข้อมูลเรียน: {len(X_train)} ชุด | ข้อมูลสอบ: {len(X_test)} ชุด")

    # ==========================================
    # 🧠 โครงสร้างสมอง AI (Deep Learning Architecture)
    # ==========================================
    model = Sequential([
        Input(shape=(SEQ_LENGTH, len(features))), # แก้ Warning เรื่อง Input shape
        LSTM(128, return_sequences=True),         # เซลล์สมองชั้นที่ 1 (ใหญ่ขึ้น)
        Dropout(0.3),                             # ป้องกันการจำข้อสอบ (Overfitting)
        LSTM(64),                                 # เซลล์สมองชั้นที่ 2
        Dropout(0.3),
        Dense(32, activation='relu'),
        Dense(1, activation='sigmoid')            # ผลลัพธ์: 0-1 (ความน่าจะเป็น)
    ])

    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

    # 🚀 5. เริ่มฝึกฝน
    print("🚀 [AI] กำลังเริ่มกระบวนการฝึกฝนขั้นสูง (ใช้เวลาสักครู่)...")
    history = model.fit(
        X_train, y_train,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        validation_data=(X_test, y_test),
        verbose=1
    )

    # 💾 6. บันทึกสมอง
    os.makedirs("ai_engine", exist_ok=True)
    model.save("ai_engine/quantum_lstm_model.h5")
    print("✅ [AI V2.0] อัปเกรดและบันทึกสมอง AI สำเร็จ! โคตรฉลาดบอกเลย!")