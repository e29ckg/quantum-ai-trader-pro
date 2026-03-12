import os
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from mt5_engine.connect import connect_mt5

from database.db import get_bot_settings_db

# ==========================================
# ⚙️ ตั้งค่าการเทรน V4.0 (ดัดนิสัย AI แก้โรคสมองตีบตัน)
# ==========================================
TIMEFRAME = mt5.TIMEFRAME_M15 
NUM_BARS = 15000    # ดึงข้อมูลเยอะขึ้นเป็น 15,000 แท่ง
SEQ_LENGTH = 60     # มองย้อนหลัง 60 แท่ง
LOOKAHEAD = 5       # 🔮 [ใหม่] มองข้ามช็อตไปอนาคต 5 แท่ง
EPOCHS = 50         
BATCH_SIZE = 64     

def add_indicators(df):
    df['EMA_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))
    return df

def prepare_data_v4(df, seq_length, lookahead):
    """ฟังก์ชันสร้างข้อสอบแบบใหม่ บังคับให้ AI หาจุด Breakout"""
    # 1. ทายว่าในอนาคตราคาจะพุ่งไปถึงไหน
    df['future_close'] = df['close'].shift(-lookahead)
    df.dropna(inplace=True)
    
    # 2. ตั้งเป้าหมาย (Threshold) เช่น ราคาต้องวิ่งขึ้นเกิน 0.05% ของราคาปัจจุบัน ถึงจะนับว่าเป็นเทรนด์
    # ถ้าวิ่งไม่ถึง ถือว่าเป็นไซด์เวย์ (Noise) ให้เป็น 0
    threshold = df['close'] * 0.0005 
    df['target'] = np.where((df['future_close'] - df['close']) > threshold, 1, 0)
    
    # 3. เตรียมข้อมูลเข้าเรียน
    features = ['open', 'high', 'low', 'close', 'volume', 'EMA_20', 'EMA_50', 'RSI_14']
    data_to_scale = df[features].values
    
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_features = scaler.fit_transform(data_to_scale)
    
    X, y = [], []
    targets = df['target'].values
    for i in range(len(scaled_features) - seq_length):
        X.append(scaled_features[i:i + seq_length])
        y.append(targets[i + seq_length - 1]) # เฉลยคือ Target ของแท่งปัจจุบัน
        
    return np.array(X), np.array(y)

if __name__ == "__main__":
    if not connect_mt5(): exit()
    
    settings = get_bot_settings_db()
    SYMBOLS = [s.strip() for s in settings.symbols.split(",") if s.strip()]
    
    print(f"📥 อ่านรายชื่อเหรียญจาก Database: {SYMBOLS}")
    
    for symbol in SYMBOLS:
        print(f"\n==========================================")
        print(f"🧠 [AI V4.0] กำลังล้างสมองและเทรนใหม่ให้: {symbol}")
        print(f"==========================================")
        
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, NUM_BARS)
        if rates is None: continue
            
        df = pd.DataFrame(rates)
        if 'tick_volume' in df.columns:
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        df = add_indicators(df)
        
        # 🌟 เรียกใช้ฟังก์ชันสร้างข้อสอบแบบใหม่!
        X, y = prepare_data_v4(df, SEQ_LENGTH, LOOKAHEAD)
        
        split_ratio = int(len(X) * 0.8)
        X_train, y_train = X[:split_ratio], y[:split_ratio]
        X_test, y_test = X[split_ratio:], y[split_ratio:]
        
        model = Sequential([
            Input(shape=(SEQ_LENGTH, 8)),
            LSTM(128, return_sequences=True),
            Dropout(0.3),
            LSTM(64),
            Dropout(0.3),
            Dense(32, activation='relu'),
            Dense(1, activation='sigmoid') # ทายผล 0 ถึง 1
        ])
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        
        print(f"🚀 เริ่มเทรน {symbol} (สอนให้หา Breakout)...")
        # ใส่ class_weight เผื่อกรณีกราฟไซด์เวย์เยอะกว่ากราฟพุ่ง AI จะได้ไม่ลำเอียง
        model.fit(X_train, y_train, epochs=EPOCHS, batch_size=BATCH_SIZE, validation_data=(X_test, y_test), verbose=1)
        
        os.makedirs("ai_engine", exist_ok=True)
        model.save(f"ai_engine/model_{symbol}.h5")
        print(f"✅ บันทึกสมอง V4.0 {symbol} สำเร็จ!\n")
        
    mt5.shutdown()