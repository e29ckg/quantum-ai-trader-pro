from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

# ==========================================
# ⚙️ ตั้งค่าการเชื่อมต่อ SQLite
# ==========================================
SQLALCHEMY_DATABASE_URL = "sqlite:///./quantum_bot.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 🗄️ โครงสร้างตาราง (Models)
# ==========================================

# 1. ตารางประวัติการเทรด (ของเดิม)
class TradeHistory(Base):
    __tablename__ = "trade_history"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, unique=True, index=True)
    symbol = Column(String, index=True)
    trade_type = Column(String)
    entry_price = Column(Float)
    status = Column(String, default="OPEN") # OPEN, CLOSED
    profit = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.now)

# 2. 🌟 [ตารางใหม่] เก็บการตั้งค่าบอทแบบถาวร
class SystemSettings(Base):
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    confidence = Column(Float, default=0.51)
    risk_percent = Column(Float, default=1.0)
    symbols = Column(String, default="BTCUSDm,XAUUSDm,EURUSDm")

# 🌟 ตารางใหม่สำหรับเก็บค่าแยกรายเหรียญ
class SymbolConfig(Base):
    __tablename__ = "symbol_configs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True)
    confidence = Column(Float, default=54.0)
    risk_percent = Column(Float, default=1.0)

# สร้างตารางทั้งหมด (ถ้ายังไม่มี)
Base.metadata.create_all(bind=engine)

# ==========================================
# 🛠️ ฟังก์ชันจัดการข้อมูล (CRUD)
# ==========================================

# --- ส่วนของการตั้งค่า (Settings) ---
def get_bot_settings_db():
    """ดึงการตั้งค่าล่าสุด หากไม่มีให้สร้างค่าเริ่มต้น"""
    db = SessionLocal()
    settings = db.query(SystemSettings).first()
    
    if not settings:
        settings = SystemSettings(
            confidence=0.51, 
            risk_percent=1.0, 
            symbols="BTCUSDm,XAUUSDm,EURUSDm"
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
        
    db.close()
    return settings

def update_bot_settings_db(new_confidence: float, new_risk: float, new_symbols: str):
    """อัปเดตการตั้งค่าลงฐานข้อมูล"""
    db = SessionLocal()
    settings = db.query(SystemSettings).first()
    
    if not settings:
        settings = SystemSettings()
        db.add(settings)
        
    settings.confidence = new_confidence
    settings.risk_percent = new_risk
    settings.symbols = new_symbols
    
    db.commit()
    db.close()

# --- ส่วนของประวัติการเทรด (Trade History) ---
def save_new_trade(ticket_id: int, symbol: str, trade_type: str, entry_price: float):
    db = SessionLocal()
    new_trade = TradeHistory(
        ticket_id=ticket_id,
        symbol=symbol,
        trade_type=trade_type,
        entry_price=entry_price
    )
    db.add(new_trade)
    db.commit()
    db.close()
    
def get_all_trades():
    db = SessionLocal()
    try:
        # 🌟 1. คำนวณเวลาเริ่มต้น (3 วันที่แล้ว นับจากตอนนี้)
        three_days_ago = datetime.now() - timedelta(days=3)
        
        # 🌟 2. เพิ่ม .filter() เข้าไปในคำสั่งดึงข้อมูล
        # ดึงมาเฉพาะออเดอร์ที่เวลา (timestamp) มากกว่าหรือเท่ากับ 3 วันที่แล้ว
        # และยังคงเรียงลำดับจากใหม่ไปเก่า (desc) และจำกัดที่ 100 ไม้เหมือนเดิม
        trades = (
            db.query(TradeHistory)
            .filter(TradeHistory.timestamp >= three_days_ago) 
            .order_by(TradeHistory.id.desc())
            .limit(100)
            .all()
        )
        
        result = []
        for t in trades:
            # 🛡️ เช็คก่อนว่ามีข้อมูลเวลาไหม ถ้าไม่มีให้ใส่ '-' แทน
            time_str = "-"
            if getattr(t, 'timestamp', None):
                try:
                    time_str = t.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                except AttributeError:
                    time_str = str(t.timestamp)
                    
            result.append({
                "ticket_id": t.ticket_id,
                "symbol": t.symbol,
                "type": getattr(t, 'trade_type', 'unknown'),
                "entry_price": t.entry_price,
                # ✂️ ตัด close_price ทิ้งไปแล้ว
                "profit": getattr(t, 'profit', 0.0),
                "status": t.status,
                "timestamp": time_str
            })
        return result
    finally:
        db.close()



# 🌟 ฟังก์ชันจัดการฐานข้อมูลรายเหรียญ
def get_symbol_config(symbol: str):
    db = SessionLocal()
    try:
        config = db.query(SymbolConfig).filter(SymbolConfig.symbol == symbol).first()
        if not config: # ถ้าเหรียญนี้เพิ่งแอดเข้ามาใหม่ ให้สร้างค่าเริ่มต้น
            config = SymbolConfig(symbol=symbol, confidence=54.0, risk_percent=1.0)
            db.add(config)
            db.commit()
            db.refresh(config)
        return {"confidence": config.confidence, "risk_percent": config.risk_percent}
    finally:
        db.close()

def update_symbol_config(symbol: str, confidence: float, risk_percent: float):
    db = SessionLocal()
    try:
        config = db.query(SymbolConfig).filter(SymbolConfig.symbol == symbol).first()
        if not config:
            config = SymbolConfig(symbol=symbol, confidence=confidence, risk_percent=risk_percent)
            db.add(config)
        else:
            config.confidence = confidence
            config.risk_percent = risk_percent
        db.commit()
        return True
    finally:
        db.close()