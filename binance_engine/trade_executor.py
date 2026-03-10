from binance_engine.connect import binance_client

# สร้าง Class จำลองผลลัพธ์ให้หน้าตาเหมือน MT5 (บอทหลักจะได้ไม่ต้องแก้โค้ดเยอะ)
class BinanceOrderResult:
    def __init__(self, order_id, price, retcode="DONE"):
        self.order = order_id      # รหัสตั๋วออเดอร์ (Ticket ID)
        self.price = price         # ราคาที่ได้ตอนเปิดไม้
        self.retcode = retcode     # สถานะ (DONE = สำเร็จ)

def set_leverage(symbol: str, leverage: int = 20):
    """
    ตั้งค่า Leverage ให้กับคู่เงินนั้นๆ (ค่าเริ่มต้น 20x)
    """
    try:
        binance_client.futures_change_leverage(symbol=symbol, leverage=leverage)
        # เปลี่ยนโหมดเป็น Cross Margin (ถ้าอยากใช้ Isolated ต้องใช้ 'ISOLATED')
        # binance_client.futures_change_margin_type(symbol=symbol, marginType='CROSSED') 
    except Exception as e:
        # บางทีถ้าตั้งค่าเดิมอยู่แล้วมันจะ Error ฟ้องซ้ำ เลยปล่อยผ่านได้ครับ
        pass

def send_order(symbol: str, signal: str, quantity: float, leverage: int = 20):
    """
    ส่งคำสั่งเทรด (Market Order) ไปยัง Binance Futures
    
    :param symbol: คู่เงิน (เช่น 'BTCUSDT')
    :param signal: สัญญาณเทรด ('buy', 'strong_buy', 'sell', 'strong_sell')
    :param quantity: จำนวนเหรียญที่ต้องการเทรด (Lot Size)
    :param leverage: พลังงัด (Leverage)
    """
    if not binance_client:
        print("❌ [Binance] ไม่มีการเชื่อมต่อ API ไม่สามารถส่งคำสั่งได้")
        return None

    # 1. แปลงสัญญาณ AI ให้เป็นคำสั่งของ Binance
    if signal.lower() in ["buy", "strong_buy"]:
        side = "BUY"   # เปิด Long
    elif signal.lower() in ["sell", "strong_sell"]:
        side = "SELL"  # เปิด Short
    else:
        return None

    # 2. ตั้งค่า Leverage ก่อนยิงออเดอร์เสมอ (กันเหนียว)
    set_leverage(symbol, leverage)

    try:
        print(f"🔫 [Binance Executor] กำลังยิงออเดอร์ {side} {symbol} จำนวน {quantity} เหรียญ...")
        
        # 3. สั่งยิง Market Order (ซื้อ/ขาย ทันทีที่ราคาปัจจุบัน)
        order = binance_client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=quantity
        )
        
        # 4. ดึงข้อมูลราคาที่แมตช์ได้จริง (Average Price)
        order_id = order.get("orderId")
        # Binance Futures เวลาตี Market Order มักจะได้ avgPrice กลับมา
        # ถ้าไม่มี ให้ใช้ราคาล่าสุด หรือ 0.0 ไปก่อน (เดี๋ยวไปดึงอัปเดตทีหลัง)
        avg_price = float(order.get("avgPrice", 0.0)) 
        
        print(f"✅ [Binance] ออเดอร์สำเร็จ! Ticket ID: {order_id} | ราคาที่ได้: {avg_price}")
        
        # คืนค่ากลับไปเป็น Object หน้าตาเหมือนของ MT5 เป๊ะๆ
        return BinanceOrderResult(order_id=order_id, price=avg_price)

    except Exception as e:
        print(f"❌ [Binance Order Error] ยิงออเดอร์ {symbol} ไม่สำเร็จ: {e}")
        return None

# ==========================================
# 🧪 ทดสอบรันไฟล์นี้ตรงๆ (ระวัง! ถ้ารันแปลว่ายิงออเดอร์จริงๆ นะครับ)
# ==========================================
if __name__ == "__main__":
    # ทดสอบเปิด Long (BUY) XRPUSDT จำนวน 10 เหรียญ (ใช้เงินนิดเดียวเพื่อเทส)
    # test_result = send_order("XRPUSDT", "buy", 10.0, leverage=10)
    # print(test_result.order, test_result.price)
    print("⚠️ ไฟล์ Trade Executor พร้อมทำงานแล้ว (คอมเมนต์โค้ดทดสอบไว้เพื่อความปลอดภัย)")