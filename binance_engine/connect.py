import os
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import *

# โหลดรหัสลับจากไฟล์ .env
load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_SECRET_KEY")

# เชื่อมต่อกับ Binance Futures
# (ถ้าอยากเทสด้วยเงินปลอมก่อน ให้ใส่ testnet=True ไว้ใน Client)
try:
    binance_client = Client(API_KEY, API_SECRET)
    # บังคับให้ใช้ฝั่ง Futures เป็นหลัก
    binance_client.FUTURES_URL = 'https://fapi.binance.com' 
except Exception as e:
    print(f"❌ [Binance] ตั้งค่า Client ล้มเหลว: {e}")
    binance_client = None

def connect_binance():
    """เช็คการเชื่อมต่อกับเซิร์ฟเวอร์ Binance"""
    try:
        if not binance_client:
            return False
            
        # ทดสอบ PING ไปที่เซิร์ฟเวอร์
        binance_client.futures_ping()
        print("✅ [Binance] เชื่อมต่อกับเซิร์ฟเวอร์ Binance Futures สำเร็จ!")
        return True
    except Exception as e:
        print(f"❌ [Binance] ไม่สามารถเชื่อมต่อได้: {e}")
        return False

def get_binance_balance(asset="USDT"):
    """ดึงยอดเงินคงเหลือในกระเป๋า Futures (USDT)"""
    try:
        account = binance_client.futures_account()
        for balance in account['assets']:
            if balance['asset'] == asset:
                wallet_balance = float(balance['walletBalance'])
                unrealized_profit = float(balance['unrealizedProfit'])
                equity = wallet_balance + unrealized_profit
                
                return {
                    "balance": wallet_balance,
                    "equity": equity
                }
        return {"balance": 0.0, "equity": 0.0}
    except Exception as e:
        print(f"❌ [Binance] ดึงข้อมูลกระเป๋าเงินล้มเหลว: {e}")
        return None

# ==========================================
# 🧪 ทดสอบรันไฟล์นี้ตรงๆ เพื่อเช็คการเชื่อมต่อ
# ==========================================
if __name__ == "__main__":
    if connect_binance():
        acc = get_binance_balance()
        print(f"💰 ยอดเงิน Futures: {acc['balance']} USDT")
        print(f"📈 Equity รวม: {acc['equity']} USDT")