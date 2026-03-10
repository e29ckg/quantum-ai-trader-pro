import pandas as pd
from binance_engine.connect import binance_client

def get_candles(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    """
    ดึงข้อมูลกราฟแท่งเทียน (Klines) จาก Binance Futures
    
    :param symbol: คู่เงิน เช่น 'BTCUSDT', 'ETHUSDT' (ไม่มี m ต่อท้ายแล้วนะครับ)
    :param interval: Timeframe เช่น '1m', '5m', '15m', '1h', '4h', '1d'
    :param limit: จำนวนแท่งเทียนย้อนหลัง (สูงสุด 1000)
    :return: Pandas DataFrame ที่มีคอลัมน์ time, open, high, low, close, volume
    """
    if not binance_client:
        print("❌ [Binance] ไม่มีการเชื่อมต่อ API ไม่สามารถดึงกราฟได้")
        return None
        
    try:
        # 📥 1. ดึงข้อมูลจากเซิร์ฟเวอร์ Binance Futures
        klines = binance_client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        
        if not klines or len(klines) == 0:
            return None
            
        # 📊 2. แปลงข้อมูลดิบเป็นตาราง Pandas DataFrame
        # ข้อมูลจาก Binance จะเรียงมาตามนี้: [Open time, Open, High, Low, Close, Volume, Close time, ...]
        df = pd.DataFrame(klines, columns=[
            'time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        
        # ✂️ 3. ตัดมาเฉพาะคอลัมน์ที่สมอง AI ของเราต้องใช้
        df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
        
        # 🔢 4. แปลงชนิดข้อมูล (Binance ส่งตัวเลขมาเป็น "ข้อความ" ต้องแปลงเป็นทศนิยม float ก่อน)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        # ⏰ 5. แปลงเวลา Timestamp (มิลลิวินาที) ให้เป็นวันที่และเวลาที่อ่านง่าย
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        
        return df
        
    except Exception as e:
        print(f"❌ [Binance DataFeed Error] ไม่สามารถดึงกราฟ {symbol} ได้: {e}")
        return None

# ==========================================
# 🧪 ทดสอบรันไฟล์นี้ตรงๆ เพื่อเช็คว่าดึงกราฟได้ไหม
# ==========================================
if __name__ == "__main__":
    # ทดสอบดึงกราฟ Bitcoin กรอบเวลา 15 นาที ย้อนหลัง 5 แท่ง
    print("⏳ กำลังดึงข้อมูลกราฟจาก Binance Futures...")
    test_df = get_candles(symbol="BTCUSDT", interval="15m", limit=5)
    
    if test_df is not None:
        print("✅ ดึงข้อมูลสำเร็จ! หน้าตากราฟ 5 แท่งล่าสุด:")
        print(test_df)
    else:
        print("❌ ไม่สามารถดึงข้อมูลได้ โปรดเช็ค API Key หรืออินเทอร์เน็ต")