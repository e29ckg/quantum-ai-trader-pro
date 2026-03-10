### 📂 โครงสร้างโปรเจกต์ทั้งหมด (Project Directory Tree)

จัดเรียงโฟลเดอร์และไฟล์ตามนี้เลยครับ:

```text
quantum-ai-trader-pro/
│
├── ai_engine/                   # 🧠 ระบบสมองกล AI
│   ├── market_structure.py      # จับเทรนด์ตลาด
│   ├── strategy_selector.py     # เลือกกลยุทธ์เบื้องต้น
│   ├── liquidity_ai.py          # ตรวจจับ Stop Loss Cluster
│   ├── prediction_ai.py         # Deep Learning (LSTM)
│   └── quantum_lstm_model.h5    # ไฟล์โมเดลสมอง AI (ถูกสร้างตอนเทรน)
│
├── api/                         # 📡 ระบบ API และ WebSockets
│   ├── auth.py                  # ระบบ JWT Security (Login)
│   └── server.py                # FastAPI Server (Endpoints)
│
├── backtest/                    # ⏳ ระบบจำลองการเทรดย้อนหลัง
│   └── engine.py                # ตัวคำนวณสถิติและ Drawdown
│
├── bot/                         # 🤖 ตัวสั่งการบอทหลัก
│   └── quantum_trader.py        # ลูปการทำงานหลัก (ดึง Data -> AI -> Trade)
│
├── database/                    # 💾 ระบบฐานข้อมูล
│   ├── db.py                    # SQLAlchemy ORM
│   └── quantum_trades.db        # ไฟล์ SQLite (ถูกสร้างอัตโนมัติ)
│
├── mt5_engine/                  # ⚙️ ระบบเชื่อมต่อ MetaTrader 5
│   ├── connect.py               # จัดการการเชื่อมต่อ Terminal
│   ├── data_feed.py             # ดึงแท่งเทียนย้อนหลัง
│   └── trade_executor.py        # ส่งคำสั่งซื้อ/ขาย
│
├── risk_manager/                # 🛡️ ระบบจัดการความเสี่ยง
│   ├── risk_control.py          # คำนวณ Lot Size ตามหน้าตัก
│   └── trailing_stop.py         # ระบบเลื่อน Stop Loss ล็อกกำไร
│
├── dashboard/                   # 🖥️ หน้าเว็บควบคุม (Vue 3)
│   ├── public/
│   ├── src/
│   │   ├── App.vue              # หน้า Dashboard หลัก
│   │   └── main.js              # ไฟล์เริ่มต้น Vue
│   ├── package.json             # ไฟล์จัดการไลบรารี Frontend
│   └── Dockerfile               # สคริปต์แพ็คหน้าเว็บลง Nginx
│
├── docker-compose.yml           # 📦 ไฟล์รันระบบทั้งหมดในคำสั่งเดียว
├── Dockerfile                   # 📦 สคริปต์แพ็ค Backend ลง Python Container
├── requirements.txt             # 📚 รายชื่อไลบรารี Python (pip)
├── run_backtest.py              # 🚀 สคริปต์สั่งรัน Backtest
└── README.md                    # 📖 คู่มือการใช้งานโปรเจกต์

```

---
# 🧠 Quantum AI Trader PRO

**Institutional-Grade Algorithmic Trading Platform & SaaS** ระบบเทรดอัตโนมัติขั้นสูงที่ผสานการวิเคราะห์สภาพคล่องของตลาด (Liquidity Concepts) เข้ากับปัญญาประดิษฐ์ (Deep Learning LSTM) พร้อมหน้า Dashboard ควบคุมแบบ Real-time

---

## ✨ Features (ความสามารถหลัก)

- **Smart Money Concepts (SMC):** ตรวจจับ Liquidity Sweep และ Stop Loss Clusters เพื่อหาจุดเข้าเทรดที่ได้เปรียบระดับสถาบัน
- **Deep Learning Prediction:** ใช้โมเดล LSTM วิเคราะห์ Time-series เพื่อประเมินความน่าจะเป็น (Probability) ในการไปต่อของราคา
- **Advanced Risk Management:** คำนวณ Lot Size อัตโนมัติตามความเสี่ยงที่รับได้ พร้อมระบบ Trailing Stop เลื่อน Stop Loss ล็อกกำไรเมื่อถูกทาง
- **Real-time Web Dashboard:** ควบคุมการทำงานของบอทและดูสถานะพอร์ต/ออเดอร์แบบสดๆ ผ่าน Vue 3 และ WebSockets (Low Latency)
- **High-Performance Backtesting:** เอนจินจำลองการเทรดย้อนหลังเพื่อหาค่า Win Rate, Profit Factor และ Max Drawdown
- **Secure SaaS Architecture:** ระบบยืนยันตัวตนด้วย JWT Token สำหรับแอดมิน พร้อมฐานข้อมูลเก็บบันทึกประวัติการเทรด

---

## 🛠️ Technology Stack (เทคโนโลยีที่ใช้)

- **Backend / AI:** Python 3.10, FastAPI, TensorFlow/Keras, Pandas, Scikit-learn
- **Trading Engine:** MetaTrader 5 (MQL5 / Python API)
- **Frontend:** Vue 3, Composition API, HTML/CSS
- **Database:** SQLite (รองรับการอัปเกรดเป็น PostgreSQL)
- **Deployment:** Docker, Docker Compose, Nginx

---

## ⚙️ Prerequisites (สิ่งที่ต้องเตรียม)

⚠️ **ข้อควรระวัง:** ไลบรารี `MetaTrader5` ของ Python ต้องการระบบปฏิบัติการ **Windows** ในการเชื่อมต่อกับ Terminal
1. Windows OS หรือ Windows VPS (แนะนำ VPS สเปค 2 Core / 4GB RAM ขึ้นไป)
2. ติดตั้ง [MetaTrader 5 Terminal](https://www.metatrader5.com/) และล็อกอินบัญชีเทรด
3. ติดตั้ง [Docker Desktop สำหรับ Windows](https://www.docker.com/products/docker-desktop/)
4. Python 3.10+ และ Node.js (สำหรับการรันแบบ Development)

---

## 🚀 Installation & Deployment (วิธีติดตั้งและใช้งาน)

### 1. การติดตั้งแบบ Local Development (สำหรับทดสอบ)
เปิด Terminal และรันคำสั่งต่อไปนี้:

**ส่วนของ Backend:**
```bash
# ติดตั้งไลบรารี
pip install -r requirements.txt

# รันเซิร์ฟเวอร์ FastAPI
uvicorn api.server:app --reload

```

**ส่วนของ Frontend:**

```bash
cd dashboard
npm install
npm run dev

```

### 2. การรันระบบบน Production ด้วย Docker 🐳

เปิด Docker Desktop ตรวจสอบว่า MetaTrader 5 เปิดอยู่ จากนั้นรันคำสั่ง:

```bash
docker-compose up -d --build

```

ระบบจะทำการ Build ทั้ง Backend และ Frontend ขึ้นมาพร้อมกัน เมื่อเสร็จสิ้นสามารถเข้าใช้งาน Dashboard ได้ที่ `http://localhost` (หรือ IP ของเซิร์ฟเวอร์)

---

## 🔒 Default Login (การเข้าสู่ระบบ)

เมื่อเข้าสู่หน้า Dashboard จะพบกับหน้า Login ให้ใช้ข้อมูลเริ่มต้นดังนี้ (สามารถแก้ไขได้ใน `api/server.py` หรือ `.env`):

* **Username:** `admin`
* **Password:** `quantum2026`

---

## 📊 การรันระบบ Backtest

เพื่อทดสอบประสิทธิภาพของ AI กับข้อมูลย้อนหลัง ให้รันคำสั่ง:

```bash
python run_backtest.py

```

ระบบจะดึงข้อมูลจาก MT5 มาประมวลผลผ่าน Liquidity AI และ LSTM พร้อมสรุปผล Report ทางหน้าจอและสร้างไฟล์ `backtest_result.csv`

---

## 🤝 Disclaimer

*ระบบนี้ถูกพัฒนาขึ้นเพื่อการศึกษาและการวิจัยเชิงปริมาณ (Quantitative Research) การลงทุนมีความเสี่ยง ผู้ใช้งานควรทำการ Backtest และ Forward Test ในบัญชี Demo ให้มั่นใจก่อนนำไปรันบนบัญชีเงินจริง*
