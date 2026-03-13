import MetaTrader5 as mt5

def send_order(symbol: str, signal: str, lot: float, sl: float = 0.0, tp: float = 0.0):
    """
    ส่งคำสั่งซื้อขายเข้าสู่ตลาดจริง (Market Execution)
    
    :param symbol: คู่เงินที่ต้องการเทรด เช่น "BTCUSD"
    :param signal: สัญญาณจาก AI ("buy", "strong_buy", "sell", "strong_sell")
    :param lot: ขนาดไม้ที่จะเปิด (Lot Size)
    :param sl: ราคา Stop Loss (ถ้ามี)
    :param tp: ราคา Take Profit (ถ้ามี)
    :return: Object ผลลัพธ์จาก MT5 (ถ้าสำเร็จ) หรือ None (ถ้าล้มเหลว)
    """
    # 1. เช็คว่าคู่เงินนี้เปิดให้เทรดบนกระดานหรือไม่
    if not mt5.symbol_select(symbol, True):
        print(f"❌ [Trade] ไม่พบเจอคู่เงิน {symbol} หรือโบรกเกอร์ไม่เปิดให้เทรด")
        return None

    # 2. ดึงราคาปัจจุบัน (Tick) ล่าสุด
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"❌ [Trade] ไม่สามารถดึงราคาปัจจุบันของ {symbol} ได้")
        return None

    # 3. กำหนดประเภทออเดอร์และราคาที่จะเข้า
    if signal.lower() in ["buy", "strong_buy"]:
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask # ซื้อที่ราคา Ask
    elif signal.lower() in ["sell", "strong_sell"]:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid # ขายที่ราคา Bid
    else:
        print(f"⚠️ [Trade] สัญญาณไม่ถูกต้อง: {signal}")
        return None

    # 4. สร้างชุดคำสั่ง (Request Payload)
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot),
        "type": order_type,
        "price": price,
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 20,           # ยอมรับการคลาดเคลื่อนของราคาได้กี่จุด (Slippage)
        "magic": 777777,           # เลขรหัสประจำตัวของบอท (เพื่อไม่ให้ไปตีกับออเดอร์ที่คนกดมือ)
        "comment": "Quantum AI",   # ลายเซ็นต์ของบอท
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC, # เติมออเดอร์ทันทีเท่าที่มี ถ้าไม่ครบให้ยกเลิกส่วนที่เหลือ
    }

    # 5. ลั่นไกส่งคำสั่ง!
    result = mt5.order_send(request)

    # 6. ตรวจสอบผลลัพธ์
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ [Trade] เปิดออเดอร์ล้มเหลว! Error: {result.retcode}, รายละเอียด: {result.comment}")
        return None
        
    # 🌟 [เพิ่มการโชว์ SL ใน Log]
    print(f"✅ [Trade] ยิงออเดอร์ {signal.upper()} สำเร็จ! Ticket: {result.order}, Lot: {lot}, Price: {result.price}, SL: {sl}")
    return result