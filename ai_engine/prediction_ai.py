import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import os
import random # 👈 ขาดตัวนี้ไปครับ

# ==========================================
# 🛡️ Safe Mode: ป้องกันเซิร์ฟเวอร์พังจาก TensorFlow
# ==========================================
TF_AVAILABLE = False
try:
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    TF_AVAILABLE = True
except Exception as e:
    print(f"\n⚠️ [AI Warning] ไม่สามารถโหลดสมองกล TensorFlow ได้ ({e})")
    print("⚠️ [AI Warning] บอทจะสลับไปใช้ 'โหมดจำลองการคิด' (Mock Probability) แทนชั่วคราว\n")

# ใช้ Scaler แปลงสเกลราคาให้อยู่ในช่วง 0-1 (AI จะเรียนรู้ได้แม่นยำขึ้น)
scaler = MinMaxScaler(feature_range=(0, 1))
MODEL_PATH = "ai_engine/quantum_lstm_model.h5"
global_model = None

def prepare_data(df: pd.DataFrame, lookback: int = 60):
    """
    เตรียมข้อมูลให้พร้อมสำหรับป้อนเข้า LSTM (แปลงเป็น Sequence)
    """
    if not TF_AVAILABLE: 
        return None, None
        
    data = df.filter(['close']).values
    scaled_data = scaler.fit_transform(data)
    
    X, y = [], []
    for i in range(lookback, len(scaled_data)):
        X.append(scaled_data[i-lookback:i, 0])
        # กำหนดเป้าหมาย (y): 1 คือราคาแท่งถัดไปสูงกว่าแท่งปัจจุบัน (ขึ้น), 0 คือต่ำกว่า (ลง)
        target = 1 if scaled_data[i, 0] > scaled_data[i-1, 0] else 0
        y.append(target)
        
    return np.array(X), np.array(y)

def train_lstm(df: pd.DataFrame):
    """
    ฟังก์ชันสำหรับ "สอน" สมอง AI ด้วยข้อมูลย้อนหลัง
    """
    if not TF_AVAILABLE:
        print("❌ [AI] ไม่สามารถเทรนโมเดลได้ เนื่องจากไม่ได้โหลด TensorFlow")
        return

    if df is None or len(df) < 100:
        print("❌ [AI] ข้อมูลน้อยเกินไป ไม่สามารถเทรน AI ได้ (ต้องการอย่างน้อย 100 แท่ง)")
        return

    print("🚀 [AI] กำลังเริ่มกระบวนการฝึกฝน (Deep Learning Training)...")
    X, y = prepare_data(df)
    X = np.reshape(X, (X.shape[0], X.shape[1], 1)) # ปรับมิติข้อมูลให้เข้ากับ LSTM

    # สร้างโครงสร้างสมอง AI
    model = Sequential()
    model.add(LSTM(units=50, return_sequences=True, input_shape=(X.shape[1], 1)))
    model.add(Dropout(0.2))
    model.add(LSTM(units=50, return_sequences=False))
    model.add(Dropout(0.2))
    model.add(Dense(units=1, activation='sigmoid'))

    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
    
    # เริ่มเทรน
    model.fit(X, y, batch_size=32, epochs=10, verbose=1)
    
    # บันทึกสมอง AI เก็บไว้ใช้งาน
    model.save(MODEL_PATH)
    print(f"✅ [AI] บันทึกสมอง AI สำเร็จ! พร้อมใช้งานที่ {MODEL_PATH}")
    
def predict_probability(df: pd.DataFrame, lookback: int = 60) -> float:
    global global_model # เรียกใช้สมองที่เก็บไว้ใน RAM

    # 🔴 ถ้าไม่มี TensorFlow ให้รันโหมดสุ่มตัวเลข
    if not TF_AVAILABLE:
        return random.uniform(0.65, 0.85)

    if df is None or len(df) < lookback:
        return 0.50

    if not os.path.exists(MODEL_PATH):
        return 0.50 

    # 🛡️ โหลดโมเดลแค่ "ครั้งแรกครั้งเดียว" แล้วเก็บไว้ในตัวแปร global_model
    if global_model is None:
        try:
            global_model = load_model(MODEL_PATH)
        except Exception as e:
            print(f"⚠️ [AI Error] อ่านไฟล์โมเดลไม่ได้: {e}")
            return 0.50
    
    # ดึงข้อมูลมาแปลงสเกล
    recent_data = df.filter(['close']).values[-lookback:]
    full_data = df.filter(['close']).values
    scaler.fit(full_data) 
    scaled_recent = scaler.transform(recent_data)
    
    X_test = np.array([scaled_recent])
    X_test = np.reshape(X_test, (X_test.shape[0], X_test.shape[1], 1))
    
    # 🔮 ใช้สมองใน RAM ทายผล (ทำงานไวปรี๊ดดดด!)
    prediction = global_model.predict(X_test, verbose=0)
    return float(prediction[0][0])
    # 🔴 ถ้าไม่มี TensorFlow ให้รันโหมดสุ่มตัวเลขความน่าจะเป็นแบบมีหลักการ
    if not TF_AVAILABLE:
        return random.uniform(0.65, 0.85)

    # 🟢 ถ้ามี TensorFlow ให้รันสมองจริง
    if df is None or len(df) < lookback:
        return 0.50

    if not os.path.exists(MODEL_PATH):
        return 0.50 

    # 🛡️ ใส่เกราะป้องกัน: ถ้าไฟล์โมเดล .h5 เสียหาย ให้อ่านข้ามไปใช้ค่ากลางแทน
    try:
        model = load_model(MODEL_PATH)
    except Exception as e:
        print(f"⚠️ [AI Error] อ่านไฟล์โมเดลไม่ได้ (ไฟล์อาจเสียหาย): ให้ใช้ค่า 50% แทน")
        return 0.50
    
    recent_data = df.filter(['close']).values[-lookback:]
    
    full_data = df.filter(['close']).values
    scaler.fit(full_data) 
    scaled_recent = scaler.transform(recent_data)
    
    X_test = np.array([scaled_recent])
    X_test = np.reshape(X_test, (X_test.shape[0], X_test.shape[1], 1))
    
    prediction = model.predict(X_test, verbose=0)
    return float(prediction[0][0])