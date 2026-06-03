import MetaTrader5 as mt5
import pandas as pd

# ==========================================
# ⚙️ 1. ตั้งค่าพารามิเตอร์จำลอง (Simulator Settings)
# ==========================================
SYMBOL = "XAUUSDm"
TIMEFRAME = mt5.TIMEFRAME_M1
BARS_TO_TEST = 10000 
INITIAL_BALANCE = 50.0 
CONTRACT_SIZE = 100.0 

# 🌟 การตั้งค่ากลยุทธ์ (ปรับปรุงสมดุล Risk/Reward)
START_LOT = 0.01
QUICK_PROFIT_TARGET = 5 # 🔼 ปรับเพิ่มเป้ากำไรจาก 2.0 เป็น 3.5 เพื่อให้คุ้มความเสี่ยงมากขึ้น
MAX_DRAWDOWN_USD = 30.0   # 🔽 ลดเพดานขาดทุนจาก 30.0 เหลือ 20.0 (แพ้ 1 ครั้ง จะใช้เวลาทวงคืนแค่ ~6 รอบ)

# 🚑 การตั้งค่าโหมดแก้เกม (DCA)
MAX_POSITIONS = 3          
DCA_STEP_USD = 5         # 🔼 ถ่างระยะแก้ไม้ จาก 2.0 เป็น 3.5 ดอลลาร์ (ป้องกันบอทยิงไม้ถี่ไปตอนกราฟสะบัดแรง)
DCA_LOT_MULT = 1.5         

# 🎯 การตั้งค่า X-Sniper V6 (กรองสัญญาณให้คมขึ้น)
MAX_GAP_USD = 7.0          # 🔽 ลดจาก 10.0 เป็น 7.0 (ถ้ากราฟกระชากแรงเกิน 7 เหรียญ บอทจะไม่เสี่ยงเข้า)
MIN_BOUNCE_RATIO = 0.35    # 🔼 เพิ่มจาก 0.30 เป็น 0.40 (รอกราฟคอนเฟิร์มการเด้งกลับถึง 40% ก่อนค่อยยิง)

def run_advanced_backtest():
    print(f"🤖 กำลังเชื่อมต่อ MT5 เพื่อดึงข้อมูล {SYMBOL}...")
    if not mt5.initialize():
        print("เชื่อมต่อ MT5 ไม่สำเร็จ!")
        return

    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, BARS_TO_TEST)
    mt5.shutdown()
    
    if rates is None:
        print("ดึงข้อมูลไม่สำเร็จ!")
        return

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print(f"✅ โหลดข้อมูลสำเร็จ: {len(df)} แท่งเทียน")
    print("⏳ กำลังจำลองการเทรดระบบ DCA + Basket Close...")

    balance = INITIAL_BALANCE
    positions = [] 
    basket_history = [] # เก็บประวัติเป็น 'รอบ' (Basket) แทนการเก็บรายไม้

    for i in range(25, len(df)):
        current_bar = df.iloc[i]
        prev_bar = df.iloc[i-1]
        
        # ----------------------------------------
        # 🧹 1. อัปเดต PnL รวมของทุกออเดอร์ในหน้าตัก
        # ----------------------------------------
        total_pnl = 0.0
        for pos in positions:
            if pos['type'] == 'buy':
                pos['floating_pnl'] = (current_bar['close'] - pos['entry_price']) * CONTRACT_SIZE * pos['lot']
            else:
                pos['floating_pnl'] = (pos['entry_price'] - current_bar['close']) * CONTRACT_SIZE * pos['lot']
            total_pnl += pos['floating_pnl']

        # ----------------------------------------
        # 🎯 2. ตรวจสอบเงื่อนไขการปิดตะกร้า (Basket Close / Panic Close)
        # ----------------------------------------
        if len(positions) > 0:
            closed_basket = False
            status = ""
            
            if total_pnl >= QUICK_PROFIT_TARGET:
                closed_basket = True
                status = "Win (TP Basket)"
            elif total_pnl <= MAX_DRAWDOWN_USD:
                closed_basket = True
                status = "Loss (Panic Close)"
                
            if closed_basket:
                balance += total_pnl
                basket_history.append({
                    'close_time': current_bar['time'],
                    'trades_count': len(positions),
                    'net_pnl': total_pnl,
                    'status': status
                })
                positions.clear() # ล้างพอร์ตเพื่อเริ่มรอบใหม่
                
                # 💥 เพิ่มระบบดักพอร์ตแตกตรงนี้ 💥
                if balance <= 0:
                    print(f"\n💥 [MARGIN CALL] พอร์ตแตก! ยอดคงเหลือ: ${balance:.2f} (เงินทุนหมด หยุดการจำลองทันที)")
                    break # สั่งทำลายลูป หยุด Backtest ทันที!
                
                continue # ถ้ายังมีเงินอยู่ ให้ข้ามไปเทสแท่งถัดไปเลย

        # ----------------------------------------
        # 🚑 3. ตรวจสอบการยิงไม้แก้ (DCA)
        # ----------------------------------------
        if len(positions) > 0 and len(positions) < MAX_POSITIONS:
            latest_pos = positions[-1]
            drag_distance = 0.0
            
            # คำนวณว่าโดนลากจากไม้ล่าสุดไปเท่าไหร่แล้ว
            if latest_pos['type'] == 'buy':
                drag_distance = latest_pos['entry_price'] - current_bar['close']
            else:
                drag_distance = current_bar['close'] - latest_pos['entry_price']
                
            if drag_distance >= DCA_STEP_USD:
                new_lot = round(latest_pos['lot'] * DCA_LOT_MULT, 2)
                positions.append({
                    'type': latest_pos['type'],
                    'entry_price': current_bar['close'],
                    'lot': new_lot,
                    'floating_pnl': 0.0
                })

        # ----------------------------------------
        # 🚀 4. ตรวจจับสัญญาณเข้าเทรดไม้แรก (X-Sniper)
        # ----------------------------------------
        if len(positions) == 0:
            closed_5_highs = df['high'].iloc[i-5:i].values
            closed_5_lows = df['low'].iloc[i-5:i].values
            
            is_x_below = (closed_5_lows[2] == min(closed_5_lows)) 
            is_x_above = (closed_5_highs[2] == max(closed_5_highs))
            
            kz21_low = df['low'].iloc[i-21:i].min()
            kz21_high = df['high'].iloc[i-21:i].max()
            
            signal = None
            
            if is_x_below:
                recent_high_oez = df['high'].iloc[i-8:i].max() 
                x_low = closed_5_lows[2]
                drop_usd = recent_high_oez - x_low
                bounce_usd = prev_bar['close'] - x_low
                bounce_ratio = bounce_usd / drop_usd if drop_usd > 0 else 0
                
                if (drop_usd <= MAX_GAP_USD) and (bounce_ratio >= MIN_BOUNCE_RATIO) and (x_low <= kz21_low):
                    signal = 'buy'

            elif is_x_above:
                recent_low_oez = df['low'].iloc[i-8:i].min()
                x_high = closed_5_highs[2]
                pump_usd = x_high - recent_low_oez
                pullback_usd = x_high - prev_bar['close']
                bounce_ratio = pullback_usd / pump_usd if pump_usd > 0 else 0
                
                if (pump_usd <= MAX_GAP_USD) and (bounce_ratio >= MIN_BOUNCE_RATIO) and (x_high >= kz21_high):
                    signal = 'sell'

            if signal:
                positions.append({
                    'type': signal,
                    'entry_price': current_bar['open'],
                    'lot': START_LOT,
                    'floating_pnl': 0.0
                })

    # ==========================================
    # 📊 5. สรุปผลลัพธ์และคำแนะนำหน้า Dashboard
    # ==========================================
    total_baskets = len(basket_history)
    if total_baskets > 0:
        win_baskets = [b for b in basket_history if b['net_pnl'] > 0]
        loss_baskets = [b for b in basket_history if b['net_pnl'] <= 0]
        win_rate = (len(win_baskets) / total_baskets) * 100
        net_profit = balance - INITIAL_BALANCE
        
        print("\n" + "="*50)
        # เปลี่ยนหัวรายงานให้เป็นสีแดงถ้าพอร์ตแตก
        if balance <= 0:
            print("☠️ BACKTEST FAILED: MARGIN CALL (ล้างพอร์ต) ☠️")
        else:
            print("🏆 ADVANCED BACKTEST REPORT (DCA + BASKET CLOSE)")
        print("="*50)
        
        print(f"💰 ทุนเริ่มต้น: ${INITIAL_BALANCE:.2f} | ยอดคงเหลือ: ${balance:.2f}")
        print(f"📈 กำไรสุทธิ: ${net_profit:.2f}")
        print(f"🧺 จำนวนรอบที่เทรด (Baskets): {total_baskets} รอบ")
        print(f"🟢 รวบตึงสำเร็จ (Win): {len(win_baskets)} รอบ | 🔴 โดนตัดไฟ (Loss): {len(loss_baskets)} รอบ")
        print(f"🎯 อัตราชนะต่อรอบ (Win Rate): {win_rate:.2f}%")
        print("="*50)
        
        if balance > 0:
            print("⚙️ สรุปคำแนะนำสำหรับการตั้งค่าหน้า Dashboard:")
            print(f"  - เปิดโหมด Quick Scalp: [ON]")
            print(f"  - Quick Profit Target (เป้ารวบตึง): {QUICK_PROFIT_TARGET}")
            print(f"  - Max Allowed Loss (ตัดไฟฉุกเฉิน): {abs(MAX_DRAWDOWN_USD)}")
            print(f"  - Recovery Mode (โหมดแก้เกม): [ON]")
            print(f"  - Max Recovery Trades (จำนวนไม้สูงสุด): {MAX_POSITIONS}")
            print(f"  - Recovery Lot Multiplier (ตัวคูณ Lot): {DCA_LOT_MULT}")
            print("="*50)
    else:
        print("\n⚠️ ไม่พบสัญญาณเข้าเทรด ลองปรับพารามิเตอร์ดูครับ!")

if __name__ == "__main__":
    run_advanced_backtest()