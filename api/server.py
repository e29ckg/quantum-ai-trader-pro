from fastapi import FastAPI,Request, Depends, Query, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware  
from pydantic import BaseModel
from typing import Optional
import asyncio
import json
import MetaTrader5 as mt5
import os


# ==========================================
# 📦 โซนนำเข้าโมดูลของระบบ (Local Imports)
# ==========================================
from database.db import (
    get_all_trades, get_bot_settings_db, update_bot_settings_db, 
    get_symbol_config, update_symbol_config
)
from mt5_engine.connect import connect_mt5, get_account_info
from bot.quantum_trader import run_bot_cycle, live_signals
from bot.backtest import run_backtest_pro
from api.auth import create_access_token, get_current_admin, ADMIN_USERNAME, ADMIN_PASSWORD

app = FastAPI(title="Quantum AI Control Panel")

# ปลดล็อก CORS ให้หน้าเว็บเรียก API ได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


CONFIG_FILE = "master_config.json"

# ฟังก์ชันอ่านค่าตั้งค่า
def load_master_config():
    default_config = {
        "ENDLESS_TRAILING_MODE": True,
        "QUICK_SCALP_MODE": False,
        "QUICK_PROFIT_TARGET": 5.0,
        "DAILY_PROFIT_TARGET": 50.0,
        "DAILY_LOSS_LIMIT": -30.0,
        "MAX_TOTAL_POSITIONS": 3,
        "MAX_ALLOWED_LOSS_USD": 30.0
    }
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f)
        return default_config
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return default_config

# ==========================================
# 📝 โซน Data Models (Pydantic)
# ==========================================
class BotSettings(BaseModel):
    confidence: float
    risk_percent: float
    symbols: str
    # 🌟 เอาเวลาออกจาก Global Settings แล้ว

class SymbolSettingsUpdate(BaseModel):
    confidence: float
    risk_percent: float
    atr_sl: float
    rr_ratio: float
    break_even: float
    auto_tune: bool
    at_trend_strong_conf: float
    at_trend_strong_rr: float
    at_trend_weak_conf: float
    at_trend_weak_rr: float
    at_vol_high_atr_sl: float
    at_vol_high_be: float
    at_vol_low_atr_sl: float
    at_vol_low_be: float
    
    # 🌟 รับค่าเวลาเทรดรายเหรียญ
    trade_start_time: Optional[str] = "00:00"
    trade_end_time: Optional[str] = "23:59"

# ==========================================
# 🔐 API โซน: Authentication
# ==========================================
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != ADMIN_USERNAME or form_data.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=400, detail="Username หรือ Password ไม่ถูกต้อง!")
    
    token = create_access_token(data={"sub": ADMIN_USERNAME})
    return {"access_token": token, "token_type": "bearer"}

# ==========================================
# 📊 API โซน: ดึงประวัติเทรด
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
# 🎛️ API โซน: ตั้งค่าบอท (Settings)
# ==========================================
@app.get("/api/settings/bot")
def get_bot_settings():
    db_settings = get_bot_settings_db()
    return {
        "confidence": db_settings.confidence * 100,
        "risk_percent": db_settings.risk_percent,
        "symbols": db_settings.symbols
        # 🌟 ไม่ต้องส่งเวลาส่วนกลางไปให้หน้าเว็บแล้ว
    }

@app.post("/api/settings/bot")
def update_bot_settings(settings: BotSettings):
    try:
        confidence_val = settings.confidence / 100.0
        risk_val = settings.risk_percent
        clean_symbols = [s.strip() for s in settings.symbols.split(",") if s.strip()]
        symbols_str = ",".join(clean_symbols)

        # 🌟 ส่งค่า "00:00" ดัมมี่ไปหลอก Database (เพราะใน db.py เรายังบังคับรับ 5 ค่าอยู่)
        update_bot_settings_db(
            confidence_val, 
            risk_val, 
            symbols_str, 
            "00:00", 
            "23:59"
        )
        return {"status": "success"}
    except Exception as e:
        print(f"❌ [API Error] Update Global Settings: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/settings/symbol/{symbol}")
def api_get_sym_setting(symbol: str):
    return get_symbol_config(symbol)

@app.post("/api/settings/symbol/{symbol}")
def api_update_sym_setting(symbol: str, settings: SymbolSettingsUpdate): # 🌟 แก้ชื่อ Class ให้ตรง
    update_symbol_config(symbol, settings.dict())
    return {"status": "success", "message": f"Updated {symbol}"}

# ==========================================
# 🚨 API โซน: ควบคุมฉุกเฉิน & ทศสอบระบบ
# ==========================================
@app.post("/api/trades/close_all")
def api_close_all_positions():
    """ฟังก์ชันฉุกเฉิน: ทิ้งทุกออเดอร์ในพอร์ตทันที (Panic Close)"""
    try:
        if not mt5.initialize():
            return {"status": "error", "message": "ไม่สามารถเชื่อมต่อ MT5 ได้"}
            
        positions = mt5.positions_get()
        if positions is None or len(positions) == 0:
            return {"status": "success", "message": "รอดตัวไป! ไม่มีออเดอร์ค้างในพอร์ตครับ"}
            
        closed_count = 0
        for pos in positions:
            tick = mt5.symbol_info_tick(pos.symbol)
            if not tick: continue
            
            action_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if action_type == mt5.ORDER_TYPE_SELL else tick.ask
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": action_type,
                "price": price,
                "deviation": 30, 
                "magic": 9999,   
                "comment": "Panic Close (Web)",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                closed_count += 1
                
        return {"status": "success", "message": f"🔥 Panic Close ทำงาน! ปิดหนีตายสำเร็จ {closed_count} ไม้!"}
    except Exception as e:
        print(f"❌ [Panic Close Error]: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/backtest/{symbol}")
def api_run_backtest(symbol: str, bars: int = Query(5000)):
    """API รัน Backtest: แก้บั๊กเช็คสถานะให้หน้าเว็บอ่านรู้เรื่อง"""
    try:
        report = run_backtest_pro(symbol, bars=bars) 
        
        # เช็คว่ามี error ส่งกลับมาจากบอทหรือไม่
        if report and "error" in report:
            return {"status": "error", "message": report["error"]}
            
        # ถ้ามีออเดอร์ถูกเทรดจริงๆ ให้ส่ง success กลับไปหน้าเว็บ
        if report and report.get("total_trades", 0) > 0:
            report["status"] = "success"  # 🌟 ยัดป้าย success ให้หน้าเว็บรู้
            return report
        else:
            return {"status": "error", "message": "ไม่มีข้อมูลการเทรดในรอบนี้ (กราฟอาจจะวิ่งไม่ถึงเป้าเลย)"}
            
    except Exception as e:
        print(f"❌ [API Backtest Error]: {e}")
        return {"status": "error", "message": str(e)}
    
# API สำหรับดึงค่าไปโชว์หน้าเว็บ
@app.get("/api/master-settings")
def get_master_settings():
    return load_master_config()

# API สำหรับบันทึกค่าจากหน้าเว็บ
@app.post("/api/master-settings")
async def save_master_settings(request: Request):
    new_config = await request.json()
    with open(CONFIG_FILE, "w") as f:
        json.dump(new_config, f)
    return {"status": "success", "message": "Master settings updated!"}

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
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                self.disconnect(connection)

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
    print("🟢 [System] WebSocket Engine เริ่มทำงานแล้ว! ท่อส่งข้อมูลพร้อม!")
    
    while True:
        try:
            db_settings = get_bot_settings_db()
            active_symbols = [s.strip() for s in db_settings.symbols.split(",") if s.strip()]
            is_running = bot_state.get("is_running", False)

            def thread_safe_bot():
                import MetaTrader5 as mt5
                from mt5_engine.connect import connect_mt5, get_account_info
                from bot.quantum_trader import run_bot_cycle, live_signals
                
                if not mt5.initialize():
                    return None, {}
                    
                run_bot_cycle(active_symbols, is_trading_enabled=is_running)
                acc = get_account_info()
                return acc, dict(live_signals)

            try:
                acc, current_signals = await asyncio.wait_for(
                    asyncio.to_thread(thread_safe_bot), 
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                print("❌ [WS Error] MT5 ค้าง! สแกนกราฟนานเกิน 10 วินาที")
                acc, current_signals = None, bot_state.get("live_signals", {})
            except Exception as e:
                print(f"❌ [WS Error] บอทพังตอนสแกน: {e}")
                acc, current_signals = None, bot_state.get("live_signals", {})

            # 1. อัปเดตข้อมูลพอร์ต (แปลงเป็น float ธรรมดา)
            if acc:
                account_state["balance"] = float(acc["balance"])
                account_state["equity"] = float(acc["equity"])
                bot_state["profit_today"] = float(acc["equity"] - acc["balance"])

            # 🌟 2. ไฮไลท์การแก้: แปลง Numpy Float ให้เป็น Python Float ธรรมดาก่อนส่ง!
            filtered_signals = {}
            for k, v in current_signals.items():
                if k in active_symbols:
                    filtered_signals[k] = {
                        "signal": str(v.get("signal", "HOLD")),
                        "buy_prob": float(v.get("buy_prob", 50.0)),  # 🌟 ถอดเกราะ Numpy ออก
                        "sell_prob": float(v.get("sell_prob", 50.0)), # 🌟 ถอดเกราะ Numpy ออก
                        "regime": str(v.get("regime", "-")),
                        "rsi": float(v.get("rsi", 0)),       # ส่งค่า RSI
                        "ema50": float(v.get("ema50", 0)),     # ส่งค่า EMA 50
                        "macd": float(v.get("macd", 0))    # ส่งค่า MACD Histogram
                    }
                    
            bot_state["live_signals"] = filtered_signals
            bot_state["current_symbol"] = ", ".join(active_symbols)

        except Exception as e:
            print(f"⚠️ [System Warning] ลูปหลักสะดุด: {e}")

        # 📡 3. ยิงข้อมูลเข้า WebSocket (ตอนนี้ JSON จะไม่ระเบิดแล้ว)
        try:
            await manager.broadcast({
                "bot": bot_state,
                "account": account_state
            })
        except Exception as e:
            print(f"❌ [WS Error] ส่งข้อมูลผ่าน WebSocket ไม่สำเร็จ: {e}")

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