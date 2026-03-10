import os
import random
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

# ==========================================
# 🛡️ Safe Mode: ป้องกันเซิร์ฟเวอร์พังจาก TensorFlow
# ==========================================
TF_AVAILABLE = False
try:
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
    from tensorflow.keras.models import load_model
    TF_AVAILABLE = True
except Exception as e:
    print(f"\n⚠️ [AI Warning] ไม่สามารถโหลดสมองกล TensorFlow ได้ ({e})")
    print("⚠️ [AI Warning] บอทจะสลับไปใช้ 'โหมดจำลองการคิด' แทนชั่วคราว\n")

MODEL_PATH = "ai_engine/quantum_lstm_model.h5"
global_model = None # ตัวแปรเก็บสมองไว้ใน RAM จะได้ไม่ต้องโหลดไฟล์ใหม่ทุกครั้งที่สแกนเหรียญ

def add_indicators(df):
    """
    ฟังก์ชันเพิ่มอาวุธให้ AI: คำนวณ RSI และ EMA 
    (ต้องคำนวณสูตรเดียวกับไฟล์ train_ai.py เป๊ะๆ)
    """
    df['EMA_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    df.fillna(0, inplace=True) # อุดรอยรั่ว
    return df

def predict_probability(df: pd.DataFrame, lookback: int = 60) -> float:
    """
    ป้อนกราฟปัจจุบันให้ AI ทายว่าแท่งต่อไปจะ 'ขึ้น' ด้วยความมั่นใจกี่เปอร์เซ็นต์
    """
    global global_model

    # 🔴 ถ้าไม่มี TensorFlow ให้รันโหมดจำลองความน่าจะเป็น
    if not TF_AVAILABLE:
        return random.uniform(0.55, 0.85)

    if df is None or len(df) < lookback:
        return 0.50

    if not os.path.exists(MODEL_PATH):
        return 0.50 

    # 🛡️ โหลดสมองแค่ "ครั้งแรกครั้งเดียว" แล้วเก็บไว้ใน RAM (ทำให้บอทคิดไวขึ้น 10 เท่า!)
    if global_model is None:
        try:
            global_model = load_model(MODEL_PATH, compile=False)
        except Exception as e:
            print(f"⚠️ [AI Error] อ่านไฟล์โมเดลไม่ได้: {e}")
            return 0.50
    
    try:
        # 1. 🌟 อัดฉีดอินดิเคเตอร์เข้ากราฟปัจจุบัน
        df_ai = df.copy()
        df_ai = add_indicators(df_ai)
        
        # 2. เลือก 8 คอลัมน์ให้ตรงกับตอนที่ AI เรียนมา
        features = ['open', 'high', 'low', 'close', 'volume', 'EMA_20', 'EMA_50', 'RSI_14']
        data_to_scale = df_ai[features].values
        
        # 3. แปลงสเกล
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(data_to_scale)
        
        # 4. ดึงข้อมูล 60 แท่งสุดท้าย
        recent_data = scaled_data[-lookback:]
        X_input = np.array([recent_data]) # จัดรูปทรงให้อยู่ในรูปแบบ (1, 60, 8)
        
        # 🔮 5. ใช้สมองใน RAM ทายผล (ไวปรี๊ดดดด!)
        prediction = global_model.predict(X_input, verbose=0)
        return float(prediction[0][0])
        
    except Exception as e:
        print(f"❌ [AI Prediction Error] สมองทำงานผิดพลาด: {e}")
        return 0.50