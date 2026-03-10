import os
import requests
from dotenv import load_dotenv

# โหลดค่าจากไฟล์ .env
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str):
    """
    ฟังก์ชันสำหรับส่งข้อความเข้า Telegram แบบสวยงาม (HTML Format)
    """
    # ถ้าไม่ได้ใส่ Token ไว้ใน .env ก็ข้ามไป ไม่ต้องส่ง
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML" # ทำให้ตัวหนา/ตัวเอียง/ใส่อีโมจิได้
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code != 200:
            print(f"⚠️ [Telegram] ส่งข้อความไม่สำเร็จ: {response.text}")
    except Exception as e:
        print(f"❌ [Telegram Error] เชื่อมต่อ Telegram ไม่ได้: {e}")

# ==========================================
# 🧪 เทสระบบตรงนี้ได้เลย!
# ==========================================
if __name__ == "__main__":
    print("กำลังทดสอบส่งข้อความเข้า Telegram...")
    send_telegram_message("✅ <b>ทดสอบระบบแจ้งเตือน</b>\nบอท Quantum AI พร้อมทำงานแล้วลูกพี่!")
    print("ส่งคำสั่งเรียบร้อยแล้ว เช็คในมือถือได้เลยครับ!")