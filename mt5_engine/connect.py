import MetaTrader5 as mt5

def connect_mt5():
    """
    ฟังก์ชันเชื่อมต่อกับ Terminal ของ MetaTrader 5 ที่เปิดอยู่บน Windows
    """
    if not mt5.initialize():
        print(f"❌ [MT5 Error] ไม่สามารถเชื่อมต่อ MT5 ได้. Error Code: {mt5.last_error()}")
        return False
        
    print("✅ [MT5] เชื่อมต่อกับ MetaTrader 5 สำเร็จ!")
    return True

def get_account_info():
    """
    ดึงข้อมูลพอร์ตการลงทุนปัจจุบัน (เพื่อนำไปคำนวณ Lot Size หรือแสดงบน Dashboard)
    """
    if not connect_mt5():
        return None
        
    account = mt5.account_info()
    if account is None:
        print(f"❌ [MT5 Error] ไม่สามารถดึงข้อมูลบัญชีได้. Error Code: {mt5.last_error()}")
        return None
        
    return {
        "login": account.login,
        "server": account.server,
        "balance": account.balance,
        "equity": account.equity,
        "margin_free": account.margin_free
    }

def disconnect_mt5():
    """
    ฟังก์ชันสำหรับตัดการเชื่อมต่อ (ปิดปลั๊ก)
    """
    mt5.shutdown()
    print("🔌 [MT5] ตัดการเชื่อมต่อเรียบร้อยแล้ว")