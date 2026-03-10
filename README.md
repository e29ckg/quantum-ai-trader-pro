# 🧠 Quantum AI Trader PRO

ระบบเทรดอัตโนมัติระดับสถาบันการเงิน (Institutional Grade Auto-Trading System) ผสานพลังของปัญญาประดิษฐ์ Deep Learning (LSTM) เข้ากับหลักการเทรดแบบ Smart Money Concepts (SMC) พร้อมหน้าต่างควบคุม (Dashboard) แบบ Real-time ผ่าน Web Browser

## ✨ ฟีเจอร์หลัก (Key Features)
* **AI Deep Learning (LSTM):** วิเคราะห์ความน่าจะเป็นของทิศทางราคา (Probability) จากกราฟย้อนหลัง
* **SMC Liquidity Filter:** กรองสัญญาณหลอก เทรดเฉพาะตอนที่มีการกวาดสภาพคล่อง (Liquidity Sweep)
* **Multi-Assets Scanning:** สแกนและเทรดได้หลายคู่เงินพร้อมกัน (เช่น BTCUSDm, XAUUSDm, EURUSDm)
* **Auto Risk Management:** คำนวณ Lot Size อัตโนมัติจาก % ความเสี่ยง และมีระบบ Trailing Stop ล็อกกำไร
* **Real-time Dashboard:** หน้าเว็บ Vue 3 ควบคุมบอทและดูประวัติการเทรดสดๆ พร้อมระบบ WebSockets

---

## 💻 ความต้องการของระบบ (System Requirements)

1. **OS:** Windows 10 หรือ 11 (จำเป็นต้องใช้ Windows เพื่อรัน MetaTrader 5)
2. **Python:** **เวอร์ชัน 3.10.x** (⚠️ *สำคัญมาก: แนะนำ 3.10.11 เพื่อความเสถียรของ TensorFlow ไม่แนะนำให้ใช้ 3.11 หรือ 3.12*)
3. **Node.js:** เวอร์ชัน 18.0 ขึ้นไป (สำหรับรันหน้าเว็บ Vue 3)
4. **MetaTrader 5 (MT5):** ติดตั้งโปรแกรมและล็อกอินบัญชีเทรด (Demo/Real) ให้เรียบร้อย
5. **C++ Redistributable:** ต้องติดตั้ง [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) (เพื่อไม่ให้ TensorFlow Error)

---

## 🛠️ ขั้นตอนการติดตั้ง (Installation Guide)

### 1. โคลนโปรเจกต์และตั้งค่า Backend (Python)
เปิด Terminal (Command Prompt) แล้วรันคำสั่งตามนี้:
```bash
# 1. สร้าง Environment ด้วย Python 3.10
py -3.10 -m venv venv

# 2. เปิดใช้งาน Environment
venv\Scripts\activate

# 3. ติดตั้งไลบรารีทั้งหมด
pip install -r requirements.txt

```

### 2. ตั้งค่า Frontend (Vue 3)

เปิด Terminal หน้าต่างใหม่ แล้วเข้าไปที่โฟลเดอร์ dashboard:

```bash
cd dashboard
npm install

```

### 3. ตั้งค่าไฟล์ความลับ (.env)

สร้างไฟล์ชื่อ `.env` ไว้ที่โฟลเดอร์นอกสุดของโปรเจกต์ และใส่ข้อมูลดังนี้:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
SECRET_KEY=your_random_secret_key_here

MT5_LOGIN=12345678
MT5_PASSWORD=your_mt5_password
MT5_SERVER=Exness-MT5Trial6

# ==========================================
# 📱 TELEGRAM NOTIFICATIONS (แจ้งเตือนผ่านไลน์/เทเลแกรม)
# ==========================================
TELEGRAM_BOT_TOKEN=712345xxxxxx
TELEGRAM_CHAT_ID=1234567890

# ==========================================
# ⚙️ BOT TRADING SETTINGS (ตั้งค่าระบบบอท)
# ==========================================
# ใส่ชื่อคู่เงินคั่นด้วยลูกน้ำ (ห้ามมีเว้นวรรค)
TRADE_SYMBOLS=BTCUSDm,XAUUSDm,EURUSDm

# กรอบเวลาที่ต้องการเทรด (M1, M5, M15, M30, H1, H4, D1)
TRADE_TIMEFRAME=M15

# ความเสี่ยงต่อ 1 ไม้ (เป็นเปอร์เซ็นต์ของพอร์ต)
RISK_PERCENT=1.0

# ความมั่นใจขั้นต่ำของ AI (เปอร์เซ็นต์ 1-100)
AI_CONFIDENCE=70.0

```

---

## 🚀 วิธีการใช้งาน (How to Run)

**ขั้นตอนที่ 1: สอนสมอง AI (ทำแค่ครั้งแรก หรือสัปดาห์ละครั้ง)**
ก่อนรันบอท ต้องสร้างไฟล์สมองกล `.h5` ให้มันก่อน (อย่าลืมเปิดโปรแกรม MT5 ไว้ด้วย)

```bash
venv\Scripts\activate
python train_ai.py

```

*(รอจนกว่าระบบจะขึ้นว่า ✅ บันทึกสมอง AI สำเร็จ!)*

**ขั้นตอนที่ 2: เปิดใช้งานระบบทั้งหมด**
เพียงแค่ดับเบิ้ลคลิกที่ไฟล์ **`start.bat`** ระบบจะทำการเปิดทั้ง Backend (FastAPI) และ Frontend (Vue 3) ให้อัตโนมัติ จากนั้นเข้าใช้งานผ่านเบราว์เซอร์ได้ที่: `http://localhost:5173`

---

## 🔧 ข้อเสนอแนะการแก้ไขปัญหา (Troubleshooting)

| ปัญหาที่พบ (Error) | สาเหตุและวิธีแก้ไข |
| --- | --- |
| **หน้าเว็บ Profit / Loss เป็นเครื่องหมาย `-**` | ยังไม่ได้เปิดออเดอร์ หรือลืมเปลี่ยนชื่อฟังก์ชันดึงฐานข้อมูลใน `api/server.py` ให้ตรงกับใน `database/db.py` (เช่น `get_all_trades`) |
| **AI วิเคราะห์ได้ `50.0%` เป๊ะๆ ตลอดเวลา** | บอทหาไฟล์สมองกลไม่เจอ ให้รันคำสั่ง `python train_ai.py` เพื่อสร้างสมองกลขึ้นมาใหม่ |
| **Error `msvcp140_1.dll` ตอนรันเซิร์ฟเวอร์** | Windows ขาดไฟล์รันไทม์ ให้ดาวน์โหลดและติดตั้ง [VC++ Redistributable](https://www.google.com/url?sa=E&source=gmail&q=https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| **Error `Failed to load _pywrap_tensorflow_internal**` | คุณกำลังใช้ Python เวอร์ชันที่ใหม่เกินไป (เช่น 3.12) ให้ลบโฟลเดอร์ `venv` ทิ้ง แล้วสร้างใหม่ด้วย Python 3.10 |
| **หน้าเว็บขึ้น `Cannot connect to AI Server` (บนโดเมนจริง)** | ติดปัญหา CORS ให้ไปแก้ใน `api/server.py` เปลี่ยน `allow_origins=["*"]` และแก้ไฟล์ `start.bat` ให้รัน Backend บน Host `0.0.0.0` |
| **บอทวิเคราะห์ได้สัญญาณ BUY/SELL แต่ไม่ยอมเปิดออเดอร์** | ลืมกดปุ่ม **"Algo Trading"** ในแถบเมนูด้านบนของโปรแกรม MT5 ให้เป็นสีเขียว |

---

*Developed with ❤️ by Quantum AI Team*
