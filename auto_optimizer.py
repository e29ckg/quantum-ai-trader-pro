import MetaTrader5 as mt5
import pandas as pd
import itertools
import time

# ==========================================
# ⚙️ 1. ตั้งค่าการดึงข้อมูล (Data Settings)
# ==========================================
SYMBOL = "XAUUSDm"
TIMEFRAME = mt5.TIMEFRAME_M1
BARS_TO_TEST = 10000 
INITIAL_BALANCE = 100.0 
CONTRACT_SIZE = 100.0 
START_LOT = 0.01
DCA_LOT_MULT = 1.5         
MAX_POSITIONS = 3          

# ==========================================
# 🧬 2. กำหนดช่วงตัวเลขที่ต้องการให้ AI สุ่มหา (Grid Search)
# ==========================================
# AI จะเอาตัวเลขในวงเล็บเหล่านี้มาจับคู่ผสมกันทุกรูปแบบ (เช่น 3x3x3x3x3 = 243 รูปแบบ)
grid_params = {
    'target': [2.0, 3.5, 5.0],              # ลองเป้ากำไรหลายๆ ระยะ
    'drawdown': [-15.0, -20.0, -30.0],      # ลองลิมิตตัดไฟหลายๆ ระดับ
    'dca_step': [2.5, 3.5, 5.0],            # ลองระยะห่างไม้แก้หลายๆ แบบ
    'max_gap': [5.0, 7.0, 10.0],            # ลองระยะกระชากของ X-Sniper
    'min_bounce': [0.35, 0.45, 0.55]        # ลองความลึกของการย่อตัว (%)
}

# ---------------------------------------------------------
# 🧠 เครื่องยนต์จำลองการเทรด (รับพารามิเตอร์มาเทสทีละชุด)
# ---------------------------------------------------------
def simulate_trading(df_records, params):
    balance = INITIAL_BALANCE
    positions = [] 
    total_baskets = 0
    win_baskets = 0

    target = params['target']
    drawdown = params['drawdown']
    dca_step = params['dca_step']
    max_gap = params['max_gap']
    min_bounce = params['min_bounce']

    for i in range(25, len(df_records)):
        current_bar = df_records[i]
        prev_bar = df_records[i-1]
        
        # 1. อัปเดต PnL รวม
        total_pnl = 0.0
        for pos in positions:
            if pos['type'] == 'buy':
                pos['floating_pnl'] = (current_bar['close'] - pos['entry_price']) * CONTRACT_SIZE * pos['lot']
            else:
                pos['floating_pnl'] = (pos['entry_price'] - current_bar['close']) * CONTRACT_SIZE * pos['lot']
            total_pnl += pos['floating_pnl']

        # 2. ตรวจสอบ Basket Close / Panic Close
        if len(positions) > 0:
            if total_pnl >= target:
                balance += total_pnl
                total_baskets += 1
                win_baskets += 1
                positions.clear()
                continue
            elif total_pnl <= drawdown:
                balance += total_pnl
                total_baskets += 1
                positions.clear()
                continue

        # 3. ตรวจสอบ DCA
        if len(positions) > 0 and len(positions) < MAX_POSITIONS:
            latest_pos = positions[-1]
            if latest_pos['type'] == 'buy':
                drag_distance = latest_pos['entry_price'] - current_bar['close']
            else:
                drag_distance = current_bar['close'] - latest_pos['entry_price']
                
            if drag_distance >= dca_step:
                new_lot = round(latest_pos['lot'] * DCA_LOT_MULT, 2)
                positions.append({
                    'type': latest_pos['type'], 'entry_price': current_bar['close'],
                    'lot': new_lot, 'floating_pnl': 0.0
                })

        # 4. สัญญาณ X-Sniper V6 (เข้าไม้แรก)
        if len(positions) == 0:
            # ดึงข้อมูล 5 แท่งย้อนหลัง
            closed_5_highs = [df_records[idx]['high'] for idx in range(i-5, i)]
            closed_5_lows = [df_records[idx]['low'] for idx in range(i-5, i)]
            
            is_x_below = (closed_5_lows[2] == min(closed_5_lows)) 
            is_x_above = (closed_5_highs[2] == max(closed_5_highs))
            
            kz21_low = min([df_records[idx]['low'] for idx in range(i-21, i)])
            kz21_high = max([df_records[idx]['high'] for idx in range(i-21, i)])
            
            signal = None
            if is_x_below:
                recent_high_oez = max([df_records[idx]['high'] for idx in range(i-8, i)])
                x_low = closed_5_lows[2]
                drop_usd = recent_high_oez - x_low
                bounce_usd = prev_bar['close'] - x_low
                bounce_ratio = bounce_usd / drop_usd if drop_usd > 0 else 0
                
                if (drop_usd <= max_gap) and (bounce_ratio >= min_bounce) and (x_low <= kz21_low):
                    signal = 'buy'

            elif is_x_above:
                recent_low_oez = min([df_records[idx]['low'] for idx in range(i-8, i)])
                x_high = closed_5_highs[2]
                pump_usd = x_high - recent_low_oez
                pullback_usd = x_high - prev_bar['close']
                bounce_ratio = pullback_usd / pump_usd if pump_usd > 0 else 0
                
                if (pump_usd <= max_gap) and (bounce_ratio >= min_bounce) and (x_high >= kz21_high):
                    signal = 'sell'

            if signal:
                positions.append({
                    'type': signal, 'entry_price': current_bar['open'],
                    'lot': START_LOT, 'floating_pnl': 0.0
                })

    net_profit = balance - INITIAL_BALANCE
    win_rate = (win_baskets / total_baskets * 100) if total_baskets > 0 else 0
    return net_profit, total_baskets, win_rate

# ==========================================
# 🚀 ระบบขับเคลื่อน Optimizer (Main Runner)
# ==========================================
def run_optimizer():
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
    df_records = df.to_dict('records') # แปลงเป็น Dict เพื่อให้ลูปรันได้เร็วกว่า pandas
    
    # สร้างรูปแบบการสุ่มทั้งหมด (Combinations)
    keys, values = zip(*grid_params.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    total_runs = len(combinations)
    print(f"✅ โหลดข้อมูลสำเร็จ: {len(df)} แท่งเทียน")
    print(f"🔥 เริ่มกระบวนการ Auto-Optimize จำนวน {total_runs} รูปแบบ...")
    
    best_profit = -999999.0
    best_params = None
    best_stats = None

    start_time = time.time()

    for idx, params in enumerate(combinations):
        # พิมพ์หลอดโหลดความคืบหน้า (Progress)
        if idx % 10 == 0:
            progress = (idx / total_runs) * 100
            print(f"\r⏳ กำลังประมวลผล... [{progress:.1f}%] ทดสอบรูปแบบที่ {idx}/{total_runs}", end="")
            
        net_profit, total_baskets, win_rate = simulate_trading(df_records, params)
        
        # คัดเลือกเฉพาะชุดที่ทำกำไรได้เยอะที่สุด
        if net_profit > best_profit and total_baskets > 5: # ต้องมีการเทรดอย่างน้อย 5 รอบขึ้นไป
            best_profit = net_profit
            best_params = params
            best_stats = (total_baskets, win_rate)

    time_taken = time.time() - start_time
    print("\n\n" + "="*50)
    print("🏆 ค้นพบพารามิเตอร์เทพ (BEST PARAMETERS FOUND!) 🏆")
    print("="*50)
    print(f"⏱️ ใช้เวลาประมวลผลทั้งหมด: {time_taken:.2f} วินาที")
    
    if best_params:
        print(f"💰 กำไรสุทธิที่ทำได้สูงสุด: +${best_profit:.2f} (จากทุน ${INITIAL_BALANCE:.2f})")
        print(f"🧺 จำนวนรอบที่เทรด: {best_stats[0]} รอบ | 🎯 Win Rate: {best_stats[1]:.2f}%")
        print("\n⚙️ เอาค่าเหล่านี้ไปกรอกในหน้า Dashboard ได้เลยครับ:")
        print(f"  - Quick Profit Target: {best_params['target']}")
        print(f"  - Max Allowed Loss: {abs(best_params['drawdown'])}")
        print(f"  - DCA Step (ดอลลาร์): {best_params['dca_step']}")
        print(f"  - Max Vertical Gap USD: {best_params['max_gap']}")
        print(f"  - Min Retracement (Bounce): {best_params['min_bounce']}")
    else:
        print("⚠️ ไม่พบรูปแบบใดเลยที่ทำกำไรได้ (กราฟอาจจะวิ่งทางเดียวโหดเกินไป) ลองขยาย Grid ดูครับ!")
    print("="*50)

if __name__ == "__main__":
    run_optimizer()