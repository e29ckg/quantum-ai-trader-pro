from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import asyncio
import json
import random
from mt5_engine.connect import connect_mt5, get_account_info
from bot.quantum_trader import run_bot_cycle

# นำเข้าโมดูลที่เราเขียนไว้แล้ว
from api.auth import create_access_token, get_current_admin, ADMIN_USERNAME, ADMIN_PASSWORD
from database.db import SessionLocal, TradeHistory

app = FastAPI(title="Quantum AI Control Panel")

# อนุญาตให้หน้าเว็บ Vue (ซึ่งมักจะรันคนละ Port) สามารถดึงข้อมูลได้ (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # ตอนรันจริงบน Production ควรเปลี่ยนเป็น IP ของโดเมนเรา
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
def get_trade_history(limit: int = 50, db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    """
    ดึงประวัติการเทรดล่าสุดจาก Database (ป้องกันด้วย get_current_admin)
    """
    trades = db.query(TradeHistory).order_by(TradeHistory.timestamp.desc()).limit(limit).all()
    
    result = []
    for t in trades:
        result.append({
            "id": t.id,
            "ticket_id": t.ticket_id,
            "symbol": t.symbol,
            "trade_type": t.trade_type,
            "entry_price": t.entry_price,
            "close_price": t.close_price,
            "profit": t.profit,
            "status": t.status,
            "timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M:%S") if t.timestamp else "-"
        })
        
    return {"status": "success", "data": result}

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
                # คำนวณกำไรแบบง่ายๆ (Equity - Balance)
                bot_state["profit_today"] = account["equity"] - account["balance"]
                bot_state["current_symbol"] = "BTCUSD"

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