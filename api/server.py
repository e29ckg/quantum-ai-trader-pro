from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from database.db import get_symbol_config, update_symbol_config
from pydantic import BaseModel
import asyncio
import json
import MetaTrader5 as mt5

# นำเข้าโมดูลที่เราเขียนไว้
from mt5_engine.connect import connect_mt5, get_account_info
from bot.quantum_trader import run_bot_cycle, live_signals
from api.auth import create_access_token, get_current_admin, ADMIN_USERNAME, ADMIN_PASSWORD

# 👇 นำเข้าฟังก์ชันดึงค่าจาก DB เข้ามาใช้งาน
from database.db import get_all_trades, get_bot_settings_db, update_bot_settings_db

app = FastAPI(title="Quantum AI Control Panel")

# ปลดล็อก CORS ให้หน้าเว็บเรียก API ได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BotSettings(BaseModel):
    confidence: float
    risk_percent: float
    symbols: str

# 🌟 สร้าง Model รับค่า
class SymbolSettingUpdate(BaseModel):
    confidence: float
    risk_percent: float


# ==========================================
# 🔐 Authentication
# ==========================================
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != ADMIN_USERNAME or form_data.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=400, detail="Username หรือ Password ไม่ถูกต้อง!")
    
    token = create_access_token(data={"sub": ADMIN_USERNAME})
    return {"access_token": token, "token_type": "bearer"}

# ==========================================
# 📊 API ดึงประวัติเทรด
# ==========================================
@app.get("/api/trades")
async def api_get_trades(current_admin: str = Depends(get_current_admin)):
    db_trades = get_all_trades() 
    live_trades = []
    
    for trade_data in db_trades:
        if trade_data.get("status") == "OPEN":
            ticket = trade_data["ticket_id"]
            positions = mt5.positions_get(ticket=ticket)
            
            if positions and len(positions) > 0:
                trade_data["profit"] = positions[0].profit 
            else:
                history = mt5.history_deals_get(position=ticket)
                if history and len(history) > 0:
                    total_profit = sum(deal.profit for deal in history)
                    trade_data["profit"] = total_profit
                    trade_data["status"] = "CLOSED" 
                    
        live_trades.append(trade_data)
        
    return {"status": "success", "data": live_trades}

# ==========================================
# 🎛️ API ดึงและอัปเดตการตั้งค่าบอท
# ==========================================
@app.get("/api/settings/bot")
def get_bot_settings():
    """ส่งค่าตั้งค่าปัจจุบันจาก Database ไปแสดงที่หน้าเว็บ"""
    db_settings = get_bot_settings_db()
    return {
        "confidence": db_settings.confidence * 100,
        "risk_percent": db_settings.risk_percent,
        "symbols": db_settings.symbols
    }

@app.post("/api/settings/bot")
def update_bot_settings(settings: BotSettings):
    """รับค่าที่ปรับแต่งจากหน้าเว็บมาเซฟลง Database"""
    confidence_val = settings.confidence / 100.0
    risk_val = settings.risk_percent
    
    raw_symbols = settings.symbols.split(",")
    clean_symbols = [s.strip() for s in raw_symbols if s.strip()]
    symbols_str = ",".join(clean_symbols)

    update_bot_settings_db(confidence_val, risk_val, symbols_str)

    print(f"\n💾 [Database] บันทึกการตั้งค่าถาวรเรียบร้อย!")
    print(f"   => AI Confidence : {settings.confidence}%")
    print(f"   => Risk Per Trade: {risk_val}%")
    print(f"   => Active Symbols: {symbols_str}\n")
    
    return {"status": "success"}

@app.get("/api/settings/symbol/{symbol}")
def api_get_sym_setting(symbol: str):
    return get_symbol_config(symbol)

@app.post("/api/settings/symbol/{symbol}")
def api_update_sym_setting(symbol: str, settings: SymbolSettingUpdate):
    update_symbol_config(symbol, settings.confidence, settings.risk_percent)
    return {"status": "success", "message": f"Updated {symbol}"}

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

# สถานะจำลองของบอท
bot_state = {
    "is_running": False,
    "current_symbol": "-",
    "last_signal": "HOLD",
    "profit_today": 0.0,
    "live_signals": {}
}
account_state = {"balance": 0.0, "equity": 0.0}

async def bot_stream_engine():
    """รันบอทจริงและยิงข้อมูลสถานะพอร์ตแบบ Real-time ไปที่หน้าเว็บ"""
    connect_mt5()

    while True:
        try:
            # 📥 ดึงค่าล่าสุดจาก DB เสมอ ไม่ว่าบอทจะวิ่งหรือหยุด
            db_settings = get_bot_settings_db()
            active_symbols = [s.strip() for s in db_settings.symbols.split(",") if s.strip()]

            if bot_state["is_running"]:
                # 🚀 1. โยนแค่รายชื่อเหรียญไปให้สมองบอท! (ลบ parameter อื่นทิ้งหมดแล้ว)
                await asyncio.to_thread(
                    run_bot_cycle, 
                    active_symbols
                )

            # 📊 2. ดึงข้อมูลพอร์ต "ของจริง"
            account = get_account_info()
            if account:
                account_state["balance"] = account["balance"]
                account_state["equity"] = account["equity"]
                bot_state["profit_today"] = account["equity"] - account["balance"]

                # กรองให้ส่งไปเฉพาะเหรียญที่กำลัง Active อยู่ตอนนี้ตามใน Database
                filtered_signals = {k: v for k, v in live_signals.items() if k in active_symbols}
                
                bot_state["live_signals"] = filtered_signals
                bot_state["current_symbol"] = ", ".join(active_symbols)

                # 📡 3. บรอดแคสต์ข้อมูล
                await manager.broadcast({
                    "bot": bot_state,
                    "account": account_state
                })
            
        except Exception as e:
            print(f"⚠️ [System Warning] เกิดข้อผิดพลาดในลูปบอท: {e}")

        # ให้บอทสแกนตลาดทุกๆ 5 วินาที
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(bot_stream_engine())

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
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