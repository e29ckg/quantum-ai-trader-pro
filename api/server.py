from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import asyncio
import json
import random
from mt5_engine.connect import connect_mt5, get_account_info
from bot.quantum_trader import run_bot_cycle, SYMBOLS, live_signals
import MetaTrader5 as mt5

# นำเข้าโมดูลที่เราเขียนไว้แล้ว
from api.auth import create_access_token, get_current_admin, ADMIN_USERNAME, ADMIN_PASSWORD
from database.db import SessionLocal, TradeHistory

app = FastAPI(title="Quantum AI Control Panel")

# อนุญาตให้หน้าเว็บ Vue (ซึ่งมักจะรันคนละ Port) สามารถดึงข้อมูลได้ (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # ปลดล็อกให้เข้าได้จากทั้ง localhost และ exness.e29ckg.org
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 🗄️ Database Session
# ==========================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 🔐 Authentication Endpoints
# ==========================================
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Endpoint สำหรับให้หน้าเว็บส่ง Username/Password มาแลกกับ JWT Token
    """
    if form_data.username != ADMIN_USERNAME or form_data.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=400, detail="Username หรือ Password ไม่ถูกต้อง!")
    
    # ถ้าถูกเป๊ะ ก็ออกกุญแจให้เลย
    token = create_access_token(data={"sub": ADMIN_USERNAME})
    return {"access_token": token, "token_type": "bearer"}

# ==========================================
# 📊 API Endpoints (ต้องมี Token ถึงเข้าได้)
# ==========================================
@app.get("/api/trades")
async def api_get_trades(current_admin: str = Depends(get_current_admin)):
    # 👇 เรียกใช้ฟังก์ชันที่เราเพิ่งสร้างเมื่อกี้
    from database.db import get_all_trades 
    
    # 1. ดึงข้อมูลประวัติการเทรดทั้งหมดจากฐานข้อมูล
    db_trades = get_all_trades() 
    live_trades = []
    
    for trade_data in db_trades:
        # 2. ถ้าสถานะออเดอร์ยังเป็น "OPEN" ให้ไปขอดึงกำไรสดๆ จาก MT5
        if trade_data.get("status") == "OPEN":
            ticket = trade_data["ticket_id"]
            
            # เช็คว่าออเดอร์ยังวิ่งอยู่ไหม
            positions = mt5.positions_get(ticket=ticket)
            if positions and len(positions) > 0:
                # 🟢 ถ้ายืนยันว่ายังวิ่งอยู่ ให้ดึงกำไร (Profit) ณ วินาทีนั้นมาใส่
                trade_data["profit"] = positions[0].profit 
            else:
                # 🔴 ถ้าไม่เจอ แปลว่าออเดอร์ปิดไปแล้ว (อาจจะชน TP/SL)
                history = mt5.history_deals_get(position=ticket)
                if history and len(history) > 0:
                    total_profit = sum(deal.profit for deal in history)
                    trade_data["profit"] = total_profit
                    trade_data["status"] = "CLOSED" # เปลี่ยนสถานะให้หน้าเว็บรู้ว่าปิดแล้ว
                    
        live_trades.append(trade_data)
        
    return {"status": "success", "data": live_trades}

# ==========================================
# ⚡ WebSockets (Real-time Dashboard)
# ==========================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except:
                pass

manager = ConnectionManager()

# สถานะจำลองของบอท (เพื่อใช้แสดงบนเว็บ)
bot_state = {
    "is_running": False,
    "current_symbol": "BTCUSD",
    "last_signal": "hold",
    "profit_today": 0.0
}
account_state = {"balance": 10000.00, "equity": 10000.00}

async def bot_stream_engine():
    """รันบอทจริงและยิงข้อมูลสถานะพอร์ตแบบ Real-time ไปที่หน้าเว็บ"""
    
    # 🔌 เชื่อมต่อ MT5 รอไว้เลยตั้งแต่เปิดเซิร์ฟเวอร์
    connect_mt5()

    while True:
        try:
            if bot_state["is_running"]:
                # 🚀 1. สั่งให้สมอง AI และมือปืนทำงาน 1 รอบ (ใช้ to_thread เพื่อไม่ให้เว็บค้าง)
                await asyncio.to_thread(run_bot_cycle)

            # 📊 2. ดึงข้อมูลพอร์ต "ของจริง" จากโบรกเกอร์
            account = get_account_info()
            if account:
                account_state["balance"] = account["balance"]
                account_state["equity"] = account["equity"]
                bot_state["profit_today"] = account["equity"] - account["balance"]

                bot_state["live_signals"] = live_signals
                bot_state["current_symbol"] = ", ".join(SYMBOLS)

                # 📡 3. บรอดแคสต์ข้อมูลจริงขึ้นหน้าจอ Vue 3
                await manager.broadcast({
                    "bot": bot_state,
                    "account": account_state
                })
            
        except Exception as e:
            print(f"⚠️ [System Warning] เกิดข้อผิดพลาดในลูปบอท: {e}")

        # ให้บอทสแกนตลาดทุกๆ 5 วินาที (ไม่ให้ดึงข้อมูลถี่เกินไปจนโบรกเกอร์แบน)
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    # สั่งให้สตรีมมิ่งเริ่มทำงานพร้อมเซิร์ฟเวอร์
    asyncio.create_task(bot_stream_engine())

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """
    ช่องทางให้ Vue 3 มาเกาะสายรับข้อมูลสด และส่งคำสั่ง Start/Stop บอท
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            command = json.loads(data)
            
            if command.get("action") == "start":
                bot_state["is_running"] = True
                print("🚀 [WebCommand] สั่งเริ่มบอทเทรด!")
            elif command.get("action") == "stop":
                bot_state["is_running"] = False
                print("🛑 [WebCommand] สั่งหยุดบอทเทรด!")
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
