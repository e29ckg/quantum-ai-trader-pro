import MetaTrader5 as mt5
import pandas as pd
from mt5_engine.connect import connect_mt5

def get_candles(symbol: str, timeframe: int, bars: int = 200):
    """
    ดึงข้อมูลแท่งเทียนย้อนหลัง (OHLCV) จาก MT5 และแปลงเป็น Pandas DataFrame
    
    :param symbol: คู่เงินที่ต้องการเทรด เช่น "BTCUSD" หรือ "XAUUSD"
    :param timeframe: กรอบเวลา เช่น mt5.TIMEFRAME_M15, mt5.TIMEFRAME_H1
    :param bars: จำนวนแท่งเทียนที่ต้องการดึงย้อนหลัง (ค่าเริ่มต้น 200 แท่ง)
    :return: Pandas DataFrame หรือ None ถ้าดึงข้อมูลไม่สำเร็จ
    """
    # ตรวจสอบว่า MT5 เชื่อมต่ออยู่หรือไม่
    if not connect_mt5():
        return None

    # สั่งดูดข้อมูลแท่งเทียนจากตำแหน่งปัจจุบันย้อนหลังไป
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)

    if rates is None or len(rates) == 0:
        print(f"❌ [Data Feed] ไม่สามารถดึงข้อมูลแท่งเทียนของ {symbol} ได้. Error: {mt5.last_error()}")
        return None

    # แปลงข้อมูลดิบให้กลายเป็นตาราง Pandas DataFrame
    df = pd.DataFrame(rates)
    
    # แปลงคอลัมน์เวลา (time) จาก Unix Timestamp ให้เป็นรูปแบบวันที่ที่อ่านเข้าใจง่าย
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    return df

# ตัวอย่างการเรียกใช้งาน:
# df = get_candles("XAUUSD", mt5.TIMEFRAME_M15, 500)
# print(df.tail())