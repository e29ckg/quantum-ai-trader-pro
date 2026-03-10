def calculate_lot_size(balance: float, risk_percentage: float = 1.0, max_lot: float = 5.0) -> float:
    """
    คำนวณขนาด Lot Size อัตโนมัติจากเงินทุน (Balance)
    
    :param balance: ยอดเงินในพอร์ตปัจจุบัน
    :param risk_percentage: เปอร์เซ็นต์ความเสี่ยงที่รับได้ต่อ 1 ไม้ (เช่น 1.0%)
    :param max_lot: ขนาด Lot สูงสุดที่ยอมให้เปิดได้ (ป้องกันการเปิดไม้ใหญ่เกินไป)
    :return: ขนาด Lot Size (ทศนิยม 2 ตำแหน่ง)
    """
    if balance <= 0:
        return 0.01 # ทุนน้อยหรือติดลบ ให้เปิด Lot ต่ำสุด
        
    # คำนวณจำนวนเงินที่ยอมเสียได้ในไม้นี้
    risk_amount = balance * (risk_percentage / 100)
    
    # สูตรคำนวณ Lot แบบง่าย (ปรับเปลี่ยนได้ตามคู่เงินที่เทรด)
    # สมมติว่าความเสี่ยง 1000$ = 1.00 Lot
    lot = risk_amount / 1000.0
    
    # บังคับ Lot ให้อยู่ในกรอบที่ปลอดภัย (ต่ำสุด 0.01, สูงสุด max_lot)
    lot = max(0.01, min(lot, max_lot))
    
    # คืนค่าเป็นทศนิยม 2 ตำแหน่ง
    return round(lot, 2)

# ตัวอย่างการใช้งาน:
# lot = calculate_lot_size(10000, 1.0) 
# แปลว่า ทุน $10,000 ยอมเสี่ยง 1% ($100) -> จะได้ Lot ประมาณ 0.10