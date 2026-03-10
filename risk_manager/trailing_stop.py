import MetaTrader5 as mt5

def manage_trailing_stop(symbol: str, trailing_points: int = 500):
    """
    ตรวจสอบออเดอร์ที่เปิดอยู่และเลื่อน Stop Loss เพื่อล็อกกำไร
    
    :param symbol: คู่เงินที่ต้องการเช็ค เช่น "BTCUSD"
    :param trailing_points: ระยะห่างของ SL จากราคาปัจจุบัน (หน่วยเป็น Point)
    """
    # ดึงออเดอร์ทั้งหมดที่เปิดอยู่ของคู่เงินนี้
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return # ไม่มีออเดอร์เปิดอยู่ ให้ข้ามไปเลย

    # ดึงราคาปัจจุบัน
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return
        
    # ดึงค่า Point ของคู่เงินนั้นๆ (เช่น ทองคำอาจจะทศนิยม 2 ตำแหน่ง, Forex 5 ตำแหน่ง)
    point = mt5.symbol_info(symbol).point

    for pos in positions:
        request = None
        
        # 🟢 กรณีเปิดออเดอร์ BUY (ราคากำลังขึ้น)
        if pos.type == mt5.ORDER_TYPE_BUY:
            # คำนวณ SL ใหม่ให้อยู่ต่ำกว่าราคา Bid ปัจจุบัน
            new_sl = tick.bid - (trailing_points * point)
            
            # เงื่อนไขการขยับ SL: ราคาวิ่งไปไกลพอแล้ว และ SL ใหม่ต้องสูงกว่า SL เดิม
            if (tick.bid - pos.price_open) > (trailing_points * point) and (pos.sl == 0.0 or new_sl > pos.sl):
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "sl": new_sl,
                    "tp": pos.tp # เก็บค่า TP เดิมไว้
                }

        # 🔴 กรณีเปิดออเดอร์ SELL (ราคากำลังลง)
        elif pos.type == mt5.ORDER_TYPE_SELL:
            # คำนวณ SL ใหม่ให้อยู่สูงกว่าราคา Ask ปัจจุบัน
            new_sl = tick.ask + (trailing_points * point)
            
            # เงื่อนไขการขยับ SL: ราคาวิ่งลงไปไกลพอแล้ว และ SL ใหม่ต้องต่ำกว่า SL เดิม
            if (pos.price_open - tick.ask) > (trailing_points * point) and (pos.sl == 0.0 or new_sl < pos.sl):
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "sl": new_sl,
                    "tp": pos.tp
                }

        # ถ้ามีการคำนวณ SL ใหม่ ให้ส่งคำสั่งแก้ไขออเดอร์ไปยัง MT5
        if request:
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"🛡️ [Trailing Stop] เลื่อนกำไรออเดอร์ #{pos.ticket} ขยับ SL ไปที่ {new_sl:.5f}")