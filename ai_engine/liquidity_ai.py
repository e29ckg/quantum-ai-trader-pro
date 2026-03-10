import pandas as pd

def detect_sl_clusters(df: pd.DataFrame, lookback: int = 20, threshold_pct: float = 0.001):
    """
    หาโซน Stop Loss (แหล่งสภาพคล่อง) ของรายย่อยจาก Swing High/Low
    """
    # หา High และ Low สูงสุด/ต่ำสุด ในช่วงเวลาที่ผ่านมา (ไม่รวมแท่งปัจจุบัน)
    recent_high = df['high'].rolling(window=lookback).max().iloc[-2]
    recent_low = df['low'].rolling(window=lookback).min().iloc[-2]

    # สร้างกรอบโซน (Cluster) ที่คนน่าจะวาง SL ไว้
    top_cluster_min = recent_high * (1 - threshold_pct)
    top_cluster_max = recent_high * (1 + threshold_pct)

    bottom_cluster_min = recent_low * (1 - threshold_pct)
    bottom_cluster_max = recent_low * (1 + threshold_pct)

    return {
        "top_cluster": (top_cluster_min, top_cluster_max),
        "bottom_cluster": (bottom_cluster_min, bottom_cluster_max),
    }

def liquidity_filter(df: pd.DataFrame, raw_signal: str) -> str:
    """
    กรองสัญญาณเทรด: ดูว่าราคากวาด Stop Loss ไปหรือยัง
    """
    if df is None or len(df) < 25:
        return raw_signal

    clusters = detect_sl_clusters(df)
    
    last_close = df['close'].iloc[-1]
    last_high = df['high'].iloc[-1]
    last_low = df['low'].iloc[-1]

    top_min, top_max = clusters['top_cluster']
    bot_min, bot_max = clusters['bottom_cluster']

    # 🟢 ตรวจจับฝั่ง BUY: กราฟทุบหลอกกิน SL ขา Buy (กวาด Low เดิม) แล้วดึงกลับขึ้นมา
    if raw_signal == "buy":
        if last_low <= bot_max and last_close > bot_max:
            return "strong_buy" # รายใหญ่กวาดออเดอร์แล้ว! เข้าซื้อตามได้เลย
        elif bot_min <= last_close <= bot_max:
            return "hold" # อันตราย ราคากำลังคลุกฝุ่นอยู่ในดง SL

    # 🔴 ตรวจจับฝั่ง SELL: กราฟลากขึ้นไปกิน SL ขา Sell (กวาด High เดิม) แล้วทุบลงมา
    elif raw_signal == "sell":
        if last_high >= top_min and last_close < top_min:
            return "strong_sell" # รายใหญ่กวาดออเดอร์แล้ว! ทุบตามได้เลย
        elif top_min <= last_close <= top_max:
            return "hold" # อันตราย กำลังลากเคลียร์ออเดอร์

    return raw_signal # ถ้าราคาไม่ได้อยู่ใกล้โซน SL ก็ใช้สัญญาณปกติ