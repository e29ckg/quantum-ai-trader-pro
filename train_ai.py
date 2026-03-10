import MetaTrader5 as mt5
from mt5_engine.connect import connect_mt5, disconnect_mt5
from mt5_engine.data_feed import get_candles
from ai_engine.prediction_ai import train_lstm

if connect_mt5():
    print("📥 กำลังดึงข้อมูลกราฟย้อนหลัง 2,000 แท่ง เพื่อส่งให้ AI เรียนรู้...")
    
    # ดึงกราฟ BTCUSD ย้อนหลังมาให้ AI หารูปแบบ (ใช้เวลาแป๊บนึง)
    df = get_candles("BTCUSDm", mt5.TIMEFRAME_M15, 2000)
    
    if df is not None:
        print("🧠 ข้อมูลพร้อมแล้ว! เริ่มกระบวนการสร้างสมอง (Deep Learning)...")
        train_lstm(df) # เรียกใช้ฟังก์ชันเทรน AI
    else:
        print("❌ ดึงข้อมูลไม่สำเร็จ ตรวจสอบการเชื่อมต่อ MT5")
        
    disconnect_mt5()