import MetaTrader5 as mt5
import pandas as pd

def calculate_atr(symbol, timeframe=mt5.TIMEFRAME_M15, period=14):
    """
    ฟังก์ชันแอบดูความผันผวนของตลาด (ATR) ย้อนหลัง 14 แท่ง
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, period + 1)
    if rates is None or len(rates) < period + 1:
        return None
        
    df = pd.DataFrame(rates)
    df['prev_close'] = df['close'].shift(1)
    
    # คำนวณระยะสวิง (True Range)
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['prev_close'])
    df['tr3'] = abs(df['low'] - df['prev_close'])
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    # หาค่าเฉลี่ยความผันผวน (ATR)
    atr = df['tr'].rolling(window=period).mean().iloc[-1]
    return atr

def manage_dynamic_trailing_stop(symbol, timeframe=mt5.TIMEFRAME_M15, atr_multiplier=2.0):
    """
    ฟังก์ชันเลื่อน Stop Loss อัตโนมัติตามความผันผวนของกราฟ
    :param atr_multiplier: ตัวคูณความกว้างของโล่ (2.0 คือระยะปลอดภัยมาตรฐานกองทุน)
    """
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return # ถ้าไม่มีออเดอร์วิ่งอยู่ ก็ไม่ต้องทำอะไร

    # 1. คำนวณความกว้างของโล่ ณ ปัจจุบัน
    atr = calculate_atr(symbol, timeframe)
    if atr is None:
        return
        
    stop_distance = atr * atr_multiplier # ระยะ Stop Loss ที่เหมาะสมที่สุด

    # 2. ไล่เช็คทีละออเดอร์เพื่อเลื่อนโล่ตามก้นราคาไปเรื่อยๆ
    for pos in positions:
        ticket = pos.ticket
        current_sl = pos.sl
        current_price = pos.price_current
        pos_type = pos.type # 0 = BUY, 1 = SELL

        new_sl = current_sl

        if pos_type == mt5.ORDER_TYPE_BUY:
            # ขา BUY: ถ้าราคาขึ้น ให้ดัน SL ตามขึ้นไป (ห้ามถอยลงเด็ดขาด)
            potential_sl = current_price - stop_distance
            if current_sl == 0.0 or potential_sl > current_sl:
                new_sl = potential_sl
                
        elif pos_type == mt5.ORDER_TYPE_SELL:
            # ขา SELL: ถ้าราคาลง ให้กด SL ตามลงมา
            potential_sl = current_price + stop_distance
            if current_sl == 0.0 or potential_sl < current_sl:
                new_sl = potential_sl

        # 3. ส่งคำสั่งแก้ Stop Loss ไปที่โบรกเกอร์ (ขยับทีละนิดเพื่อไม่ให้เซิร์ฟเวอร์โดนแบน)
        point = mt5.symbol_info(symbol).point
        if abs(new_sl - current_sl) > (point * 50): # ขยับเฉพาะเมื่อระยะห่างเกิน 50 จุด
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "sl": new_sl,
                "tp": pos.tp, # ปล่อย TP ไว้ที่เดิม (ถ้ามี)
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"🛡️ [Risk Manager] ขยับโล่ Trailing Stop ของ {symbol} ไปที่ {new_sl:.5f}")