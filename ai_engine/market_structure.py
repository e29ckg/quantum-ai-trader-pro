import pandas as pd

def detect_trend(df: pd.DataFrame, lookback: int = 10) -> str:
    """
    วิเคราะห์โครงสร้างตลาด (Market Structure) เพื่อหาเทรนด์หลัก
    
    :param df: ตารางข้อมูลแท่งเทียน
    :param lookback: จำนวนแท่งเทียนย้อนหลังที่จะใช้เปรียบเทียบ
    :return: "uptrend", "downtrend", หรือ "sideway"
    """
    if df is None or len(df) < lookback + 1:
        return "sideway"

    # ราคาปิดล่าสุด เทียบกับราคาปิดเมื่อ 'lookback' แท่งที่แล้ว
    last_close = df['close'].iloc[-1]
    prev_close = df['close'].iloc[-(lookback + 1)]

    # กำหนดความกว้างของ Sideway (สมมติถ้าราคาเปลี่ยนไม่ถึง 0.05% ให้ถือว่าออกข้าง)
    threshold = prev_close * 0.0005 

    if last_close > prev_close + threshold:
        return "uptrend"
    elif last_close < prev_close - threshold:
        return "downtrend"
    else:
        return "sideway"