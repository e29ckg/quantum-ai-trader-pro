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
# global_model = None # ตัวแปรเก็บสมองไว้ใน RAM จะได้ไม่ต้องโหลดไฟล์ใหม่ทุกครั้งที่สแกนเหรียญ
global_models = {}

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

def predict_probability(df: pd.DataFrame, symbol: str, lookback: int = 60) -> float:
    global global_models

    if not TF_AVAILABLE: return random.uniform(0.55, 0.85)
    if df is None or len(df) < lookback: return 0.50

    model_path = f"ai_engine/model_{symbol}.h5" # 👈 ค้นหาสมองตามชื่อเหรียญ
    if not os.path.exists(model_path): return 0.50 

    # 🛡️ โหลดสมองใส่ RAM (ถ้ายังไม่เคยโหลด)
    if symbol not in global_models:
        try:
            global_models[symbol] = load_model(model_path, compile=False)
        except Exception as e:
            print(f"⚠️ [AI] โหลดสมอง {symbol} ไม่ได้: {e}")
            return 0.50
    
    try:
        df_ai = df.copy()
        if 'tick_volume' in df_ai.columns:
            df_ai.rename(columns={'tick_volume': 'volume'}, inplace=True)
            
        df_ai = add_indicators(df_ai)
        features = ['open', 'high', 'low', 'close', 'volume', 'EMA_20', 'EMA_50', 'RSI_14']
        
        data_to_scale = df_ai[features].values
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(data_to_scale)
        
        recent_data = scaled_data[-lookback:]
        X_input = np.array([recent_data])
        
        # 🔮 เรียกใช้สมองเฉพาะเหรียญนั้นๆ ทายผล
        prediction = global_models[symbol].predict(X_input, verbose=0)
        return float(prediction[0][0])
    except Exception as e:
        return 0.50