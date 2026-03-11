import os
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from mt5_engine.connect import connect_mt5

from dotenv import load_dotenv
load_dotenv()
env_symbols = os.environ.get("TRADE_SYMBOLS", "BTCUSDm,XAUUSDm,EURUSDm")
SYMBOLS = [s.strip() for s in env_symbols.split(",") if s.strip()]

# ==========================================
# ⚙️ ตั้งค่าการเทรน V2.0 (อัปเกรดความฉลาด)
# ==========================================
TIMEFRAME = mt5.TIMEFRAME_M15 # กรอบเวลา 15 นาที (กำลังดีที่สุดสำหรับ Day Trade)
NUM_BARS = 50000              # 🔥 [อัปเกรด] ดึงย้อนหลัง 50,000 แท่ง! (ผ่านทั้งตลาดกระทิง ตลาดหมี ไซด์เวย์ AI จะมีภูมิคุ้มกันสูงมาก)
SEQ_LENGTH = 96               # 🔥 [อัปเกรด] ดูกราฟย้อนหลัง 96 แท่ง (96 แท่ง x 15 นาที = 24 ชั่วโมงพอดี!) บอทจะเห็นภาพรวมรอบวันครบจบ
EPOCHS = 100                  # 🔥 [อัปเกรด] เรียน 100 จบ (ให้มันซึมซับแพตเทิร์นจนขึ้นใจ)
BATCH_SIZE = 32               # 🔥 [อัปเกรด] ซอยให้อ่านทีละ 32 ชุด (การซอยชุดข้อมูลให้เล็กลง จะทำให้ AI เก็บรายละเอียดและเรียนรู้ความผันผวนได้เนียนกว่า 64)

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
    if not connect_mt5(): exit()
    
    # 🌟 [เพิ่มใหม่] วนลูปสร้างสมองทีละเหรียญ!
    for symbol in SYMBOLS:
        print(f"\n==========================================")
        print(f"🧠 [AI V3.0] กำลังสร้างสมองเฉพาะทางสำหรับ: {symbol}")
        print(f"==========================================")
        
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, NUM_BARS)
        if rates is None:
            print(f"❌ ดึงข้อมูล {symbol} ไม่ได้ ข้ามไปก่อน")
            continue
            
        df = pd.DataFrame(rates)
        if 'tick_volume' in df.columns:
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        df = add_indicators(df)
        features = ['open', 'high', 'low', 'close', 'volume', 'EMA_20', 'EMA_50', 'RSI_14']
        data_to_scale = df[features].values
        
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(data_to_scale)
        X, y = create_dataset(scaled_data, SEQ_LENGTH)
        
        split_ratio = int(len(X) * 0.8)
        X_train, y_train = X[:split_ratio], y[:split_ratio]
        X_test, y_test = X[split_ratio:], y[split_ratio:]
        
        # สร้างโมเดล
        model = Sequential([
            Input(shape=(SEQ_LENGTH, len(features))),
            LSTM(128, return_sequences=True),
            Dropout(0.3),
            LSTM(64),
            Dropout(0.3),
            Dense(32, activation='relu'),
            Dense(1, activation='sigmoid')
        ])
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        
        print(f"🚀 เริ่มเทรน {symbol}...")
        model.fit(X_train, y_train, epochs=EPOCHS, batch_size=BATCH_SIZE, validation_data=(X_test, y_test), verbose=1)
        
        # 💾 บันทึกสมองแยกชื่อตามเหรียญ
        os.makedirs("ai_engine", exist_ok=True)
        model.save(f"ai_engine/model_{symbol}.h5")
        print(f"✅ บันทึกสมอง {symbol} สำเร็จ!\n")
        
    mt5.shutdown()
    print("🎉 สร้างสมองครบทุกเหรียญเรียบร้อยแล้ว!")