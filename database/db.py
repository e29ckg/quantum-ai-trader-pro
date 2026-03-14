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

# 1. ตารางประวัติการเทรด
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

# 2. 🌟 [ตารางใหม่] เก็บการตั้งค่าบอทแบบถาวร (Global)
class SystemSettings(Base):
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    confidence = Column(Float, default=0.51)
    risk_percent = Column(Float, default=1.0)
    symbols = Column(String, default="BTCUSDm,XAUUSDm,EURUSDm")
    atr_sl = Column(Float, default=2.0)
    rr_ratio = Column(Float, default=2.0)
    break_even = Column(Float, default=1.5)
    trade_start_time = Column(String, default="00:00")
    trade_end_time = Column(String, default="23:59")

# 3. 🌟 ตารางสำหรับเก็บค่าแยกรายเหรียญ (Per-Symbol)
class SymbolConfig(Base):
    __tablename__ = "symbol_configs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True)
    confidence = Column(Float, default=54.0)
    risk_percent = Column(Float, default=1.0)
    atr_sl = Column(Float, default=2.0)
    rr_ratio = Column(Float, default=2.0)
    break_even = Column(Float, default=1.5)

# สร้างตารางทั้งหมด (ถ้ายังไม่มี)
Base.metadata.create_all(bind=engine)

# ==========================================
# 🛠️ ฟังก์ชันจัดการข้อมูล (CRUD)
# ==========================================

# --- ส่วนของการตั้งค่า Global (Settings) ---
def get_bot_settings_db():
    """ดึงการตั้งค่าล่าสุด หากไม่มีให้สร้างค่าเริ่มต้น"""
    db = SessionLocal()
    try:
        settings = db.query(SystemSettings).first()
        
        if not settings:
            settings = SystemSettings(
                confidence=0.51, 
                risk_percent=1.0, 
                symbols="BTCUSDm,XAUUSDm,EURUSDm",  # 🌟 ใส่ลูกน้ำตรงนี้แล้ว
                trade_start_time="00:00",
                trade_end_time="23:59"
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)
            
        return settings
    finally:
        db.close()

# 🌟 เพิ่ม start_time และ end_time เข้ามาในพารามิเตอร์
def update_bot_settings_db(new_confidence: float, new_risk: float, new_symbols: str, start_time: str, end_time: str):
    """อัปเดตการตั้งค่าลงฐานข้อมูล"""
    db = SessionLocal()
    try:
        settings = db.query(SystemSettings).first()
        
        if not settings:
            settings = SystemSettings()
            db.add(settings)
            
        settings.confidence = new_confidence
        settings.risk_percent = new_risk
        settings.symbols = new_symbols
        settings.trade_start_time = start_time  # 🌟 เซฟเวลาเริ่มต้น
        settings.trade_end_time = end_time      # 🌟 เซฟเวลาสิ้นสุด
        
        db.commit()
    finally:
        db.close()

# --- ส่วนของประวัติการเทรด (Trade History) ---
def save_new_trade(ticket_id: int, symbol: str, trade_type: str, entry_price: float):
    db = SessionLocal()
    try:
        new_trade = TradeHistory(
            ticket_id=ticket_id,
            symbol=symbol,
            trade_type=trade_type,
            entry_price=entry_price
        )
        db.add(new_trade)
        db.commit()
    finally:
        db.close()
    
def get_all_trades():
    db = SessionLocal()
    try:
        # ดึง 3 วันย้อนหลัง
        three_days_ago = datetime.now() - timedelta(days=3)
        
        trades = (
            db.query(TradeHistory)
            .filter(TradeHistory.timestamp >= three_days_ago) 
            .order_by(TradeHistory.id.desc())
            .limit(100)
            .all()
        )
        
        result = []
        for t in trades:
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
                "profit": getattr(t, 'profit', 0.0),
                "status": t.status,
                "timestamp": time_str
            })
        return result
    finally:
        db.close()

# --- ส่วนของการตั้งค่าแยกรายเหรียญ (Per-Symbol Config) ---
def get_symbol_config(symbol: str):
    db = SessionLocal()
    try:
        config = db.query(SymbolConfig).filter(SymbolConfig.symbol == symbol).first()
        if not config: 
            config = SymbolConfig(symbol=symbol, confidence=54.0, risk_percent=1.0, atr_sl=2.0, rr_ratio=2.0, break_even=1.5)
            db.add(config)
            db.commit()
            db.refresh(config)
        return {
            "confidence": config.confidence, 
            "risk_percent": config.risk_percent,
            "atr_sl": config.atr_sl,
            "rr_ratio": config.rr_ratio,
            "break_even": config.break_even
        }
    finally:
        db.close()

def update_symbol_config(symbol: str, confidence: float, risk_percent: float, atr_sl: float, rr_ratio: float, break_even: float):
    db = SessionLocal()
    try:
        config = db.query(SymbolConfig).filter(SymbolConfig.symbol == symbol).first()
        if not config:
            config = SymbolConfig(symbol=symbol, confidence=confidence, risk_percent=risk_percent, atr_sl=atr_sl, rr_ratio=rr_ratio, break_even=break_even)
            db.add(config)
        else:
            config.confidence = confidence
            config.risk_percent = risk_percent
            config.atr_sl = atr_sl
            config.rr_ratio = rr_ratio
            config.break_even = break_even
        db.commit()
        return True
    finally:
        db.close()