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
# ⚙️ ตั้งค่าการเทรน V4.0 (Sync กับ Quantum AI PRO)
# ==========================================
TIMEFRAME = mt5.TIMEFRAME_M15 
NUM_BARS = 15000    # ดึงข้อมูล 15,000 แท่ง
SEQ_LENGTH = 60     # มองย้อนหลัง 60 แท่ง
LOOKAHEAD = 5       # 🔮 มองข้ามช็อตไปอนาคต 5 แท่ง
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
    """ฟังก์ชันสร้างข้อสอบแบบให้เข้ากับระบบ 1=UP, 0=DOWN"""
    # 1. ดูราคาปิดในอนาคต 5 แท่ง
    df['future_close'] = df['close'].shift(-lookahead)
    df.dropna(inplace=True)
    
    # 2. 🌟 แก้ไข: 1 = อนาคตสูงกว่าปัจจุบัน (BUY), 0 = อนาคตต่ำกว่าปัจจุบัน (SELL)
    df['target'] = np.where(df['future_close'] > df['close'], 1, 0)
    
    # 3. 🌟 แก้ไข: ใช้ tick_volume ให้ตรงกับบอทเทรด 100%
    features = ['open', 'high', 'low', 'close', 'tick_volume', 'EMA_20', 'EMA_50', 'RSI_14']
    data_to_scale = df[features].values
    
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_features = scaler.fit_transform(data_to_scale)
    
    X, y = [], []
    targets = df['target'].values
    for i in range(len(scaled_features) - seq_length):
        X.append(scaled_features[i:i + seq_length])
        y.append(targets[i + seq_length - 1]) 
        
    return np.array(X), np.array(y)

if __name__ == "__main__":
    if not connect_mt5(): exit()
    
    settings = get_bot_settings_db()
    SYMBOLS = [s.strip() for s in settings.symbols.split(",") if s.strip()]
    # SYMBOLS = ["ETHUSDm"]
    
    print(f"📥 อ่านรายชื่อเหรียญจาก Database: {SYMBOLS}")
    
    for symbol in SYMBOLS:
        print(f"\n==========================================")
        print(f"🧠 [AI V4.0] กำลังล้างสมองและเทรนใหม่ให้: {symbol}")
        print(f"==========================================")
        
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, NUM_BARS)
        if rates is None: continue
            
        df = pd.DataFrame(rates)
        # ❌ ไม่ต้องแก้ชื่อคอลัมน์แล้ว ปล่อยให้เป็น tick_volume เหมือนที่ MT5 ส่งมา
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        df = add_indicators(df)
        
        # 🌟 เรียกใช้ฟังก์ชันสร้างข้อสอบ
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
            Dense(1, activation='sigmoid') 
        ])
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        
        print(f"🚀 เริ่มเทรน {symbol} (สอนให้มองอนาคต {LOOKAHEAD} แท่ง)...")
        model.fit(X_train, y_train, epochs=EPOCHS, batch_size=BATCH_SIZE, validation_data=(X_test, y_test), verbose=1)
        
        os.makedirs("ai_engine", exist_ok=True)
        model.save(f"ai_engine/model_{symbol}.h5")
        print(f"✅ บันทึกสมอง V4.0 {symbol} สำเร็จ!\n")
        
    mt5.shutdown()