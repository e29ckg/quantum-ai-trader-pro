from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime

# ใช้ SQLite เป็นฐานข้อมูล (ไฟล์จะถูกสร้างอัตโนมัติชื่อ quantum_trades.db)
DATABASE_URL = "sqlite:///./quantum_trades.db"

# ตั้งค่า Connection (check_same_thread=False จำเป็นสำหรับ SQLite ใน FastAPI)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 📊 โครงสร้างตารางเก็บประวัติการเทรด (Trade History)
class TradeHistory(Base):
    __tablename__ = "trade_history"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, unique=True, index=True) # รหัสออเดอร์จาก MT5
    symbol = Column(String, index=True)                  # คู่เงิน เช่น BTCUSD
    trade_type = Column(String)                          # BUY หรือ SELL
    entry_price = Column(Float)                          # ราคาที่เปิดออเดอร์
    close_price = Column(Float, nullable=True)           # ราคาที่ปิดออเดอร์
    profit = Column(Float, nullable=True)                # กำไร/ขาดทุน
    status = Column(String, default="OPEN")              # สถานะ: OPEN หรือ CLOSED
    timestamp = Column(DateTime, default=datetime.datetime.utcnow) # เวลาที่เปิดไม้

# สร้าง Database และตารางทั้งหมด (ถ้ายังไม่มี)
Base.metadata.create_all(bind=engine)

def save_new_trade(ticket_id: int, symbol: str, trade_type: str, entry_price: float):
    """
    ฟังก์ชันสำหรับบันทึกออเดอร์ใหม่ลง Database ทันทีที่บอทเปิดไม้สำเร็จ
    """
    db = SessionLocal()
    try:
        new_trade = TradeHistory(
            ticket_id=ticket_id, 
            symbol=symbol, 
            trade_type=trade_type.upper(), 
            entry_price=entry_price
        )
        db.add(new_trade)
        db.commit()
        print(f"💾 [DB] บันทึกออเดอร์ใหม่ Ticket #{ticket_id} ลงฐานข้อมูลแล้ว")
    except Exception as e:
        db.rollback()
        print(f"❌ [DB Error] ไม่สามารถบันทึกออเดอร์ได้: {e}")
    finally:
        db.close()

def get_all_trades():
    """
    ดึงข้อมูลประวัติการเทรดทั้งหมดจากฐานข้อมูล เพื่อส่งไปให้หน้าเว็บ
    """
    db = SessionLocal()
    try:
        # ดึงข้อมูลทั้งหมด เรียงจากใหม่สุด (desc) ไปเก่าสุด
        trades = db.query(TradeHistory).order_by(TradeHistory.timestamp.desc()).all()
        
        # แปลงเป็น Dictionary ให้ FastAPI อ่านง่ายๆ
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
                "timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M:%S") if t.timestamp else ""
            })
        return result
    except Exception as e:
        print(f"❌ [DB Error] ไม่สามารถดึงประวัติการเทรดได้: {e}")
        return []
    finally:
        db.close()