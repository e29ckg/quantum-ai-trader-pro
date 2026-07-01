import os
import time
import sqlite3
import requests
import joblib
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dotenv import load_dotenv
import MetaTrader5 as mt5
import json

# ==========================================
# 📦 โซนนำเข้าโมดูลของระบบ (Local Imports)
# ==========================================
from database.db import save_new_trade, get_bot_settings_db, get_symbol_config, update_symbol_config
from mt5_engine.connect import connect_mt5, get_account_info
from mt5_engine.data_feed import get_candles
from mt5_engine.trade_executor import send_order
from ai_engine.market_structure import detect_trend
from ai_engine.strategy_selector import choose_strategy
from ai_engine.liquidity_ai import liquidity_filter
from risk_manager.risk_control import calculate_lot_size
from risk_manager.trailing_stop import manage_dynamic_trailing_stop
from utils.telegram_notifier import send_telegram_message

# โหลดค่าจากไฟล์ .env
load_dotenv()

# ==========================================
# ⚙️ โซนตั้งค่าตัวแปร Global & โหลดสมองกล AI
# ==========================================
tf_map = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1
}
env_timeframe = os.getenv("TRADE_TIMEFRAME", "M15").upper()
TIMEFRAME = tf_map.get(env_timeframe, mt5.TIMEFRAME_M15)

live_signals = {}
last_summary_date = None
news_cache = {"date": None, "events": []}

try:
    quantum_ai = joblib.load('models/xgboost_quantum_v5.pkl')
    print("🧠 [System] โหลดสมองกล XGBoost (V5) สำเร็จ พร้อมรบ!")
except Exception as e:
    quantum_ai = None
    print(f"⚠️ [System] ไม่พบสมองกล XGBoost ({e}) จะใช้ระบบพื้นฐานแทน")

# ==========================================
# 📰 โซนตัวช่วย: ตัวกรองข่าวสาร (News Filter)
# ==========================================
def is_safe_from_news(buffer_mins=30):
    global news_cache
    now = datetime.now()
    
    if news_cache["date"] != now.date():
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=5)
            root = ET.fromstring(res.content)
            
            events = []
            for item in root.findall('event'):
                impact = item.find('impact').text
                country = item.find('country').text
                if impact == 'High' and country == 'USD':
                    date_str = item.find('date').text
                    time_str = item.find('time').text
                    if time_str and time_str.lower() != "all day":
                        dt_str = f"{date_str} {time_str}"
                        try:
                            est_dt = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                            bkk_dt = est_dt + timedelta(hours=11)
                            events.append(bkk_dt)
                        except:
                            pass
            news_cache["date"] = now.date()
            news_cache["events"] = events
            print(f"\n📰 [News Filter] โหลดปฏิทินข่าวสำเร็จ! วันนี้มีข่าวกล่องแดง USD จำนวน {len(events)} รอบ 🚨")
        except Exception as e:
            print("\n📰 [News Filter] โหลดข่าวไม่สำเร็จ บอทจะเทรดตามปกติต่อไป...")
            news_cache["date"] = now.date()
            news_cache["events"] = []

    for news_time in news_cache["events"]:
        danger_start = news_time - timedelta(minutes=buffer_mins)
        danger_end = news_time + timedelta(minutes=buffer_mins)
        if danger_start <= now <= danger_end:
            return False, news_time 
            
    return True, None 

# ==========================================
# 🧠 โซนตัวช่วย: AI Predictor (XGBoost Engine)
# ==========================================
def get_xgboost_prediction(df):
    if quantum_ai is None or len(df) < 200:
        return 50.0, 50.0 

    try:
        df_ai = df.copy()
        
        # --- 1. คำนวณ Features พื้นฐาน ---
        high_low = df_ai['high'] - df_ai['low']
        high_close = (df_ai['high'] - df_ai['close'].shift()).abs()
        low_close = (df_ai['low'] - df_ai['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        df_ai['ATR_14'] = tr.rolling(14).mean()
        df_ai['ATR_50'] = tr.rolling(50).mean()
        df_ai['Volatility_Ratio'] = df_ai['ATR_14'] / df_ai['ATR_50']
        
        df_ai['EMA_20'] = df_ai['close'].ewm(span=20, adjust=False).mean()
        df_ai['EMA_50'] = df_ai['close'].ewm(span=50, adjust=False).mean()
        df_ai['Dist_EMA20'] = (df_ai['close'] - df_ai['EMA_20']) / df_ai['EMA_20'] * 100
        df_ai['Dist_EMA50'] = (df_ai['close'] - df_ai['EMA_50']) / df_ai['EMA_50'] * 100
        df_ai['Trend_Slope'] = (df_ai['EMA_20'] - df_ai['EMA_20'].shift(5)) / df_ai['EMA_20'].shift(5) * 100
        
        delta = df_ai['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_ai['RSI_14'] = 100 - (100 / (1 + rs))

        # --- 2. คำนวณ Features ใหม่สำหรับ V5 ---
        df_ai['EMA_200'] = df_ai['close'].ewm(span=200, adjust=False).mean()
        df_ai['Macro_Trend'] = np.where(df_ai['close'] > df_ai['EMA_200'], 1, -1)
        
        # 🌟 ดึงเวลาแบบเซียน (รองรับทั้ง Live และ Backtest)
        if 'time' in df_ai.columns:
            if pd.api.types.is_numeric_dtype(df_ai['time']):
                time_col = pd.to_datetime(df_ai['time'], unit='s')
            else:
                time_col = pd.to_datetime(df_ai['time'])
            df_ai['Hour'] = time_col.dt.hour
            df_ai['DayOfWeek'] = time_col.dt.dayofweek
        else:
            df_ai['Hour'] = df_ai.index.hour
            df_ai['DayOfWeek'] = df_ai.index.dayofweek

        # --- 3. จัดกลุ่ม 9 ตัวแปร ---
        features = [
            'tick_volume', 'Volatility_Ratio', 'Dist_EMA20', 
            'Dist_EMA50', 'Trend_Slope', 'Macro_Trend', 'RSI_14',
            'Hour', 'DayOfWeek'
        ]
        
        X = df_ai[features].iloc[-1].values.reshape(1, -1)
        probs = quantum_ai.predict_proba(X)[0] 
        
        sell_prob = float(probs[0])
        buy_prob = float(probs[1])  
        
        return buy_prob, sell_prob

    except Exception as e:
        print(f"❌ [AI Error] ประมวลผลพลาด: {e}")
        return 50.0, 50.0

# ==========================================
# 🥷 โซนตัวช่วย: จัดการออเดอร์ (Position Management)
# ==========================================
def close_mt5_position(position, comment="AI Reversal"):
    tick = mt5.symbol_info_tick(position.symbol)
    if not tick: return False
    
    action_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if action_type == mt5.ORDER_TYPE_SELL else tick.ask
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "position": position.ticket, "symbol": position.symbol,
        "volume": position.volume, "type": action_type, "price": price,
        "deviation": 20, "magic": 100, "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

def apply_break_even(position, df, break_even_mult=1.5):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    
    current_close = df['close'].iloc[-1]
    entry = position.price_open
    sl = position.sl
    profit_distance = break_even_mult * atr
    request = None
    
    if position.type == mt5.ORDER_TYPE_BUY:
        if current_close > entry + profit_distance and sl < entry:
            request = {"action": mt5.TRADE_ACTION_SLTP, "position": position.ticket, "symbol": position.symbol, "sl": entry, "tp": position.tp}
    elif position.type == mt5.ORDER_TYPE_SELL:
        if current_close < entry - profit_distance and (sl > entry or sl == 0.0):
            request = {"action": mt5.TRADE_ACTION_SLTP, "position": position.ticket, "symbol": position.symbol, "sl": entry, "tp": position.tp}
            
    if request:
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"🛡️ [Break-Even] เลื่อน SL บังหน้าทุน {position.symbol} เรียบร้อย!")

def sync_manual_order_to_db(pos):
    try:
        conn = sqlite3.connect("quantum_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT ticket_id FROM trade_history WHERE ticket_id = ?", (pos.ticket,))
        if not cursor.fetchone():
            trade_type = "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell"
            record_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                INSERT INTO trade_history (ticket_id, symbol, trade_type, entry_price, status, timestamp)
                VALUES (?, ?, ?, ?, 'OPEN', ?)
            ''', (pos.ticket, pos.symbol, trade_type, pos.price_open, record_time))
            conn.commit()
            print(f"📥 [DB Sync] ซิงค์ออเดอร์เปิดมือ (Ticket: {pos.ticket}) สำเร็จ!")
        conn.close()
    except Exception as e:
        print(f"⚠️ [DB Sync Error]: {e}")

def send_daily_summary(active_symbols: list):
    global last_summary_date
    now = datetime.now()
    if now.hour == 23 and last_summary_date != now.date():
        start_of_day = datetime(now.year, now.month, now.day)
        end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59)
        deals = mt5.history_deals_get(start_of_day, end_of_day)
        
        total_profit = 0.0
        total_trades = 0
        win_trades = 0
        if deals:
            for deal in deals:
                if deal.entry == 1: 
                    net_profit = deal.profit + deal.swap + deal.commission
                    total_profit += net_profit
                    total_trades += 1
                    if net_profit > 0: win_trades += 1
                        
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
        emoji = "🟢" if total_profit >= 0 else "🔴"
        msg = (f"📊 <b>สรุปผลประกอบการ (Daily Report)</b>\n"
               f"📈 <b>ออเดอร์:</b> {total_trades} ไม้\n🏆 <b>Win Rate:</b> {win_rate:.1f}%\n"
               f"💰 <b>Net Profit:</b> {emoji} <b>${total_profit:.2f}</b>")
        send_telegram_message(msg)
        last_summary_date = now.date()

def check_and_notify_closed_trades():
    try:
        conn = sqlite3.connect("quantum_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT ticket_id, symbol, trade_type, entry_price FROM trade_history WHERE status = 'OPEN'")
        open_trades = cursor.fetchall()
        
        for trade in open_trades:
            ticket_id, symbol, trade_type, entry_price = trade
            pos = mt5.positions_get(ticket=ticket_id)
            
            if pos is None or len(pos) == 0:
                deals = mt5.history_deals_get(position=ticket_id)
                if deals and len(deals) > 0:
                    net_profit = sum(d.profit + d.swap + d.commission for d in deals)
                    cursor.execute("UPDATE trade_history SET status = 'CLOSED', profit = ? WHERE ticket_id = ?", (net_profit, ticket_id))
                    conn.commit()
                    
                    emoji = "🟢" if net_profit >= 0 else "🔴"
                    profit_sign = "+" if net_profit >= 0 else ""
                    close_type = "TAKE PROFIT (TP) 🏆" if net_profit > 0 else "STOP LOSS (SL) 🛡️"
                    
                    msg = (f"🏁 <b>TRADE CLOSED ({close_type})</b> 🏁\n\n"
                           f"💱 <b>Symbol:</b> {symbol} (Ticket: #{ticket_id})\n"
                           f"💰 <b>Net Profit:</b> {emoji} <b>{profit_sign}${net_profit:.2f}</b>")
                    send_telegram_message(msg)
                    print(f"🏁 [Trade Closed] {symbol} | PnL: {profit_sign}${net_profit:.2f}")
        conn.close()
    except Exception as e:
        print(f"⚠️ [Check Closed Trades Error]: {e}")

# ==========================================
# 🧠 วัฏจักรการทำงานหลัก (Main Loop)
# ==========================================
def run_bot_cycle(active_symbols: list, is_trading_enabled: bool = True):
    if is_trading_enabled:
        send_daily_summary(active_symbols)
        check_and_notify_closed_trades()

    # ==========================================
    # 🌟🌟🌟 ควบคุมโหมดเทพ (ดึงจากหน้า Dashboard) 🌟🌟🌟
    # ==========================================
    config_path = "master_config.json"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            master_cfg = json.load(f)
    else:
        master_cfg = {
            "ENDLESS_TRAILING_MODE": True, "QUICK_SCALP_MODE": False,
            "QUICK_PROFIT_TARGET": 5.0, "DAILY_PROFIT_TARGET": 50.0,
            "DAILY_LOSS_LIMIT": -30.0, "MAX_TOTAL_POSITIONS": 3, 
            "MAX_ALLOWED_LOSS_USD": 30.0
        }

    ENDLESS_TRAILING_MODE = master_cfg.get("ENDLESS_TRAILING_MODE", True)  
    QUICK_SCALP_MODE = master_cfg.get("QUICK_SCALP_MODE", False)       
    QUICK_PROFIT_TARGET = float(master_cfg.get("QUICK_PROFIT_TARGET", 5.0))    
    DAILY_PROFIT_TARGET = float(master_cfg.get("DAILY_PROFIT_TARGET", 50.0))   
    DAILY_LOSS_LIMIT = float(master_cfg.get("DAILY_LOSS_LIMIT", -30.0))     
    MAX_TOTAL_POSITIONS = int(master_cfg.get("MAX_TOTAL_POSITIONS", 3)) 
    MAX_ALLOWED_LOSS_USD = float(master_cfg.get("MAX_ALLOWED_LOSS_USD", 30.0)) 
    MAX_GAP_USD = float(master_cfg.get("MAX_GAP_USD", 10.0))
    MIN_BOUNCE_RATIO = float(master_cfg.get("MIN_BOUNCE_RATIO", 0.30))
    KZ_BARS = int(master_cfg.get("KZ_BARS", 14))
    OEZ_BARS = int(master_cfg.get("OEZ_BARS", 5))
    # ==========================================

    # 📊 1. ตรวจสอบกำไรรายวัน & วินัยกองทุน
    today = datetime.now()
    start_of_day = datetime(today.year, today.month, today.day)
    deals = mt5.history_deals_get(start_of_day, today)
    profit_today = sum((d.profit + d.commission + d.swap) for d in deals if d.entry == mt5.DEAL_ENTRY_OUT) if deals else 0.0
                
    hit_daily_limit = False
    if profit_today >= DAILY_PROFIT_TARGET:
        if is_trading_enabled: print(f"\r🛑 [Daily Target] 🎉 วันนี้กำไรทะลุเป้า (+${profit_today:.2f}) AI งดออกไม้ใหม่! {' '*10}", end="")
        hit_daily_limit = True
    elif profit_today <= DAILY_LOSS_LIMIT:
        if is_trading_enabled: print(f"\r🛑 [Daily Drawdown] ⚠️ ขาดทุนถึงลิมิต (${profit_today:.2f}) AI งดออกไม้ใหม่! {' '*10}", end="")
        hit_daily_limit = True

    # ⏱️ 2. ตรวจสอบเวลาเทรด
    now_time = datetime.now().time()
        
    for symbol in active_symbols:
        mt5.symbol_select(symbol, True) 
        sym_config = get_symbol_config(symbol)
        
        # 🌟 ระบบเช็คเวลาแบบรายเหรียญ
        start_time_str = sym_config.get('trade_start_time', '00:00')
        end_time_str = sym_config.get('trade_end_time', '23:59')
        start_t = datetime.strptime(start_time_str, "%H:%M").time()
        end_t = datetime.strptime(end_time_str, "%H:%M").time()

        if start_t <= end_t:
            is_trading_time = (start_t <= now_time <= end_t)
        else:
            is_trading_time = (now_time >= start_t or now_time <= end_t)

        # 🚑 โหลดการตั้งค่าโหมดแก้เกม (Recovery)
        recovery_mode = sym_config.get('recovery_mode', False)
        rec_step_atr = float(sym_config.get('recovery_step_atr', 1.0))
        rec_lot_mult = float(sym_config.get('recovery_lot_mult', 1.5))
        max_rec_trades = int(sym_config.get('max_recovery_trades', 3))

        # 🛑 โค้ดดักสเปรดถ่าง
        max_spread_allowed = int(sym_config.get('max_spread', 50))
        tick = mt5.symbol_info_tick(symbol)
        sym_info = mt5.symbol_info(symbol)
        
        is_spread_ok = False
        current_spread = 0
        if tick and sym_info:
            current_spread = (tick.ask - tick.bid) / sym_info.point
            is_spread_ok = current_spread <= max_spread_allowed
        
        df = get_candles(symbol, TIMEFRAME, bars=200)
        
        if df is None or df.empty: 
            print(f"⚠️ [System] ดึงกราฟ {symbol} ไม่สำเร็จ ข้ามการประมวลผล...")
            continue

        # 📊 3. วิเคราะห์สภาวะตลาด (Market Regime)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                
        atr_14 = tr.rolling(14).mean().iloc[-1]
        atr_50 = tr.rolling(50).mean().iloc[-1]
        ema_20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema_50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]

        # 🌟 คำนวณ MACD และ RSI เพื่อทำระบบโหวต
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean().iloc[-1]
        rs = gain / loss if loss != 0 else 0
        rsi_14 = 100 - (100 / (1 + rs))

        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = (macd_line - signal_line).iloc[-1]

        current_close = df['close'].iloc[-1]
        
        # เช็คคะแนนฝั่ง BUY
        buy_score = 0
        if rsi_14 > 50: buy_score += 1                  
        if current_close > ema_50: buy_score += 1       
        if macd_hist > 0: buy_score += 1                
        is_confluence_buy = buy_score >= 2              

        # เช็คคะแนนฝั่ง SELL
        sell_score = 0
        if rsi_14 < 50: sell_score += 1                 
        if current_close < ema_50: sell_score += 1      
        if macd_hist < 0: sell_score += 1               
        is_confluence_sell = sell_score >= 2            
        
        is_high_vol = atr_14 > (atr_50 * 1.2)
        trend_dist = abs(ema_20 - ema_50) / ema_50
        is_strong_trend = trend_dist > 0.002
        
        t_str = "🔥 STRONG TREND" if is_strong_trend else "💤 SIDEWAY"
        v_str = "🌊 HIGH VOL" if is_high_vol else "🧊 LOW VOL"
        regime_text = f"{t_str} | {v_str}"

        # 🤖 4. สมองกลเปลี่ยนเกียร์ (Auto-Tune Dynamic)
        if sym_config.get('auto_tune', True):
            if is_strong_trend:
                target_confidence_percent = float(sym_config.get('at_trend_strong_conf', 60.0))
                rr_ratio = float(sym_config.get('at_trend_strong_rr', 2.0))
            else:
                target_confidence_percent = float(sym_config.get('at_trend_weak_conf', 65.0))
                rr_ratio = float(sym_config.get('at_trend_weak_rr', 1.2))
                
            if is_high_vol:
                atr_mult = float(sym_config.get('at_vol_high_atr_sl', 3.0))
                break_even_mult = float(sym_config.get('at_vol_high_be', 2.5))
            else:
                atr_mult = float(sym_config.get('at_vol_low_atr_sl', 2.0))
                break_even_mult = float(sym_config.get('at_vol_low_be', 1.5))
        else:
            target_confidence_percent = float(sym_config.get("confidence", 54.0))
            atr_mult = float(sym_config.get("atr_sl", 2.0))
            rr_ratio = float(sym_config.get("rr_ratio", 2.0))
            break_even_mult = float(sym_config.get("break_even", 1.5))
            
        risk_percent = float(sym_config.get("risk_percent", 1.0))
        manage_dynamic_trailing_stop(symbol, timeframe=TIMEFRAME, atr_multiplier=atr_mult)

        # 🎯 5. ดึงสัญญาณจาก SMC และ XGBoost
        trend = detect_trend(df)
        raw_signal = choose_strategy(trend)
        liq_signal = liquidity_filter(df, raw_signal)

        if liq_signal != "hold":
            ai_buy_prob, ai_sell_prob = get_xgboost_prediction(df)
            buy_prob = float(ai_buy_prob * 100)
            sell_prob = float(ai_sell_prob * 100)
        else:
            buy_prob, sell_prob = 50.0, 50.0

        display_signal = liq_signal.upper() if liq_signal != "hold" else "HOLD"
        
        if not is_trading_enabled:
            display_signal = "PAUSED ⏸️"
        elif not is_trading_time or hit_daily_limit:
            display_signal = "SLEEP 💤"

        live_signals[symbol] = {
            "signal": display_signal, 
            "buy_prob": buy_prob, 
            "sell_prob": sell_prob, 
            "regime": regime_text,
            "rsi": round(rsi_14, 2),       
            "ema50": round(ema_50, 2),     
            "macd": round(macd_hist, 2)    
        }

        if is_trading_enabled:
            mode_str = "🤖 [AUTO]" if sym_config.get('auto_tune', False) else "⚙️ [MANUAL]"
            print(f"[{time.strftime('%H:%M:%S')}] 🔍 {symbol} {mode_str} | SMC: {liq_signal.upper()} | B: {buy_prob:.1f}% S: {sell_prob:.1f}% | 🎯 {target_confidence_percent:.1f}% | 📊 RSI: {rsi_14:.1f} MACD: {macd_hist:.2f} | {regime_text}")

        if not is_trading_enabled:
            continue

        # ==========================================
        # 🛡️ โซนที่ 1: จัดการออเดอร์เก่า & ระบบแก้เกม
        # ==========================================
        positions = mt5.positions_get(symbol=symbol)
        
        if positions is not None and len(positions) > 0:
            main_position = None
            addon_count = 0
            dca_count = 0 
            
            # 🔍 หาไม้ล่าสุด (Newest Order)
            latest_order = max(positions, key=lambda p: p.time)
            latest_sl = latest_order.sl

            # ----------------------------------------
            # 🎯 1.1 ระบบรวบตึงอัจฉริยะ (Basket Close / Escape Mode)
            # ----------------------------------------
            total_profit = sum([p.profit for p in positions])
            num_positions = len(positions)
            
            is_escape_mode = num_positions > 2
            
            if QUICK_SCALP_MODE or is_escape_mode:
                if not is_escape_mode:
                    current_target = QUICK_PROFIT_TARGET 
                else:
                    current_target = QUICK_PROFIT_TARGET * 0.20 
                    if is_trading_enabled:
                        print(f"\r⚠️ [Escape Mode] มี {num_positions} ไม้! ลดเป้า TP เหลือ ${current_target:.2f} เพื่อเตรียมหนีตาย! {' '*5}", end="")

                if total_profit >= current_target:
                    closed_count = 0
                    for pos in positions:
                        if close_mt5_position(pos, comment="Smart Basket TP 🎯"): 
                            closed_count += 1
                    
                    if closed_count > 0:
                        status_type = "หนีตาย" if is_escape_mode else "ปกติ"
                        msg = f"🎯 <b>SMART BASKET CLOSE ({status_type})</b>\nรวบตึง {symbol} สำเร็จ {closed_count} ไม้!\n💰 กำไรสุทธิ: +${total_profit:.2f}"
                        send_telegram_message(msg)
                        print(f"\n🎯 [Basket Close] รวบตึงแบบ{status_type} ปิดไป {closed_count} ไม้ รับ PnL: +${total_profit:.2f}")
                    continue 
                
            # ----------------------------------------
            # 🚨 1.1.5 ระบบเบรกเกอร์ฉุกเฉิน (Panic Close)
            # ----------------------------------------
            if total_profit <= -MAX_ALLOWED_LOSS_USD:
                closed_count = 0
                for pos in positions:
                    if close_mt5_position(pos, comment="🚨 PANIC CLOSE"):
                        closed_count += 1
                
                if closed_count > 0:
                    msg = f"🚨 <b>EMERGENCY PANIC CLOSE</b> 🚨\nตลาดลากแรงเกินขีดจำกัด! ตัดไฟฉุกเฉิน {symbol}\nปิดไป {closed_count} ไม้\n💔 ยอดตัดขาดทุน: ${total_profit:.2f}"
                    send_telegram_message(msg)
                    print(f"\n🚨 [Circuit Breaker] ตลาดทุบแรง! ทะลุลิมิต -${MAX_ALLOWED_LOSS_USD} สับสวิตช์ตัดขาดทุน {closed_count} ไม้ (PnL: {total_profit:.2f})")
                continue

            # ----------------------------------------
            # 🔄 1.2 ซิงค์ Stop Loss ทุกไม้ ให้เท่ากับ SL ไม้ล่าสุด
            # ----------------------------------------
            if len(positions) > 1 and latest_sl != 0.0:
                for pos in positions:
                    if pos.sl != latest_sl:
                        sym_info = mt5.symbol_info(symbol)
                        if sym_info:
                            mt5.order_send({
                                "action": mt5.TRADE_ACTION_SLTP, "symbol": symbol,
                                "sl": latest_sl, "tp": pos.tp, "position": pos.ticket
                            })
                            print(f"🔄 [Sync SL] ปรับ SL ไม้ {pos.ticket} ให้เท่ากับไม้ล่าสุด ({latest_sl})")

            # ----------------------------------------
            # 🚑 1.3 ระบบยิงไม้แก้ (DCA / Martingale)
            # ----------------------------------------
            if recovery_mode and len(positions) < max_rec_trades:
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    current_price = tick.ask if latest_order.type == mt5.ORDER_TYPE_BUY else tick.bid
                    
                    if latest_order.type == mt5.ORDER_TYPE_BUY: 
                        drag_distance = latest_order.price_open - current_price
                    else: 
                        drag_distance = current_price - latest_order.price_open
                    
                    if drag_distance >= (rec_step_atr * atr_14):
                        if is_spread_ok:
                            new_lot = round(latest_order.volume * rec_lot_mult, 2)
                            dca_sig = "buy" if latest_order.type == mt5.ORDER_TYPE_BUY else "sell"
                            
                            sym_info = mt5.symbol_info(symbol)
                            sl_dist = atr_14 * atr_mult
                            new_sl = 0.0
                            if sym_info:
                                if dca_sig == "buy": 
                                    new_sl = round(tick.bid - sl_dist, sym_info.digits)
                                else: 
                                    new_sl = round(tick.ask + sl_dist, sym_info.digits)

                            print(f"🚑 [Recovery] {symbol} โดนลาก {(drag_distance/atr_14):.2f} ATR! ยิงไม้แก้ Lot: {new_lot}")
                            
                            res = send_order(symbol, dca_sig, new_lot, sl=new_sl, tp=0.0, comment="DCA Recovery")
                            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                save_new_trade(res.order, symbol, f"{dca_sig} (DCA)", res.price)
                                send_telegram_message(f"🚑 <b>DCA RECOVERY FIRED</b>\n💱 {symbol}\n📏 ระยะลาก: {drag_distance:.4f}\n🛒 Lot: {new_lot}")
                        else:
                            print(f"⚠️ [Spread Filter] อยากยิงไม้แก้ DCA แต่สเปรดถ่าง รอไปก่อน!")

            # ----------------------------------------
            # 🧹 1.3.5 ลูปนับสถานะออเดอร์ & Trailing Stop ล็อคกำไรแบบสายซิ่ง ⚡
            # ----------------------------------------
            for pos in positions:
                if pos.comment == "AI Addon": addon_count += 1
                elif pos.comment == "DCA Recovery": dca_count += 1
                else: main_position = pos
                
                # ⚡ ตั้งค่าความซิ่งของการบังหน้าทุนตรงนี้ครับ
                TRAIL_START_USD = 0.30  # จุดเริ่มทำงาน (พอกำไรถึง $0.30 ให้บอทเริ่มขยับ SL)
                TRAIL_LOCK_USD = 0.10   # ล็อคกำไรสุทธิ (ถ้ากราฟสะบัดชน SL จะยังเหลือกำไร $0.10 เพื่อจ่ายค่าคอมมิชชัน)

                if pos.profit >= TRAIL_START_USD:
                    sym_info = mt5.symbol_info(symbol)
                    if sym_info:
                        price_diff = abs(pos.price_current - pos.price_open)
                        if pos.profit > 0:
                            # คำนวณระยะทางของกราฟที่เทียบเท่ากับเงิน 1 ดอลลาร์
                            price_dist_per_usd = price_diff / pos.profit
                            # แปลงเงิน $0.10 ที่อยากล็อค ให้กลายเป็นระยะทางของจุด (Points)
                            lock_price_dist = TRAIL_LOCK_USD * price_dist_per_usd
                            
                            if pos.type == mt5.ORDER_TYPE_BUY:
                                new_sl = pos.price_open + lock_price_dist
                                # ถ้า SL ใหม่สูงกว่า SL เดิม (ขยับขึ้นบี้กำไร) ค่อยส่งคำสั่ง
                                if pos.sl < new_sl:
                                    mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": symbol, "sl": round(new_sl, sym_info.digits), "tp": pos.tp, "position": pos.ticket})
                                    print(f"🛡️ [Trailing Stop] บังหน้าทุนไม้ BUY {pos.ticket} ล็อคกำไร ${TRAIL_LOCK_USD:.2f}")
                                    
                            elif pos.type == mt5.ORDER_TYPE_SELL:
                                new_sl = pos.price_open - lock_price_dist
                                # ถ้า SL ใหม่ต่ำกว่า SL เดิม (ขยับลงบี้กำไร) หรือยังไม่มี SL ค่อยส่งคำสั่ง
                                if pos.sl == 0.0 or pos.sl > new_sl:
                                    mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": symbol, "sl": round(new_sl, sym_info.digits), "tp": pos.tp, "position": pos.ticket})
                                    print(f"🛡️ [Trailing Stop] บังหน้าทุนไม้ SELL {pos.ticket} ล็อคกำไร ${TRAIL_LOCK_USD:.2f}")
            
            # ----------------------------------------
            # 🚀 1.4 โหมด Add-On (Pyramiding)
            # ----------------------------------------
            if is_trading_time and not hit_daily_limit and sym_config.get('auto_tune', False) and main_position and addon_count < (MAX_TOTAL_POSITIONS - 1) and is_strong_trend and dca_count == 0:
                main_secured = (main_position.type == mt5.ORDER_TYPE_BUY and main_position.sl >= main_position.price_open) or \
                               (main_position.type == mt5.ORDER_TYPE_SELL and main_position.sl <= main_position.price_open and main_position.sl != 0.0)
                
                if main_secured:
                    final_addon_signal = None
                    if main_position.type == mt5.ORDER_TYPE_BUY and buy_prob >= target_confidence_percent and is_confluence_buy: 
                        final_addon_signal = "strong_buy"
                    elif main_position.type == mt5.ORDER_TYPE_SELL and sell_prob >= target_confidence_percent and is_confluence_sell: 
                        final_addon_signal = "strong_sell"
                                                
                    if final_addon_signal:
                        if not is_spread_ok:
                            print(f"⚠️ [Spread Filter] สเปรดถ่าง {current_spread:.0f} จุด ข้ามการยิงไม้ Add-On {symbol}!")
                        else:
                            tick, sym_info = mt5.symbol_info_tick(symbol), mt5.symbol_info(symbol)
                            if tick and sym_info:
                                lot = main_position.volume 
                                sl_dist, tp_dist = atr_14 * atr_mult, (atr_14 * atr_mult) * rr_ratio
                                
                                sl_price = round(tick.ask - sl_dist if main_position.type == mt5.ORDER_TYPE_BUY else tick.bid + sl_dist, sym_info.digits)
                                tp_price = 0.0 if ENDLESS_TRAILING_MODE else round(tick.ask + tp_dist if main_position.type == mt5.ORDER_TYPE_BUY else tick.bid - tp_dist, sym_info.digits)
                                    
                                result = send_order(symbol, final_addon_signal, lot, sl=sl_price, tp=tp_price, comment="AI Addon")
                                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                                    save_new_trade(result.order, symbol, final_addon_signal, result.price)
                                    send_telegram_message(f"🔥 <b>AI ADD-ON EXECUTED</b> 🔥\n💱 {symbol}\n💰 Add Entry: {result.price}")

            continue 

        # ==========================================
        # 🚀 โซนที่ 2: โซนยิงออเดอร์ใหม่ (ไม้หลัก)
        # ==========================================
        if not is_trading_time or hit_daily_limit: continue

        # 📰 2.1 หลบข่าวกล่องแดง
        try:
            is_safe, news_time = is_safe_from_news(buffer_mins=30)
            if not is_safe:
                print(f"\r📰 [News Filter] 🚨 ใกล้เวลาข่าวกล่องแดง ({news_time.strftime('%H:%M')}) บอทงดออกไม้อัตโนมัติ! {' '*10}", end="")
                continue 
        except Exception: pass
        
        # 🎯 2.2 คัดกรองสัญญาณสุดท้าย
        final_signal = None
        sig_mode = sym_config.get('signal_mode', 'ai')

        # ----------------------------------------------------
        # 🧠 โหมด 1: ใช้ AI (XGBoost + SMC + Indicators 2/3)
        # ----------------------------------------------------
        if sig_mode == "ai":
            if buy_prob >= target_confidence_percent and (liq_signal in ["buy", "strong_buy"] or is_confluence_buy):
                final_signal = "buy"
            elif sell_prob >= target_confidence_percent and (liq_signal in ["sell", "strong_sell"] or is_confluence_sell):
                final_signal = "sell"
                
        # ----------------------------------------------------
        # ⚡ โหมด 2: ใช้ Indicator ซิ่ง (EMA Cross + RSI)
        # ----------------------------------------------------
        elif sig_mode == "indicator":
            ema_9 = df['close'].ewm(span=9, adjust=False).mean().iloc[-1]
            ema_21 = df['close'].ewm(span=21, adjust=False).mean().iloc[-1]
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=9).mean().iloc[-1]
            loss = (-delta.where(delta < 0, 0)).rolling(window=9).mean().iloc[-1]
            rs = gain / loss if loss != 0 else 0
            rsi_9 = 100 - (100 / (1 + rs))

            if ema_9 > ema_21 and rsi_9 > 55:
                final_signal = "buy"
            elif ema_9 < ema_21 and rsi_9 < 45:
                final_signal = "sell"
                
        # ----------------------------------------------------
        # 🎯 Mode 3: X-Sniper V6 (Fast Action + Full Dashboard Control ⚡)
        # ----------------------------------------------------
        elif sig_mode == "x_sniper":
            closed_5_highs = df['high'].iloc[-6:-1].values
            closed_5_lows = df['low'].iloc[-6:-1].values
            
            is_x_below = (closed_5_lows[2] == min(closed_5_lows)) 
            is_x_above = (closed_5_highs[2] == max(closed_5_highs))
            current_close = df['close'].iloc[-1]
            
            # 🔍 ปรับกรอบรับ/ต้านตามค่า KZ_BARS จาก Dashboard
            kz_low = df['low'].iloc[-(KZ_BARS+1):-1].min()
            kz_high = df['high'].iloc[-(KZ_BARS+1):-1].max()
            
            if is_x_below:
                # 🔍 หาแรงเทขายจากระยะ OEZ_BARS จาก Dashboard
                recent_high_oez = df['high'].iloc[-(OEZ_BARS+1):-1].max() 
                x_low = closed_5_lows[2]
                
                drop_usd = recent_high_oez - x_low
                bounce_usd = current_close - x_low
                bounce_ratio = bounce_usd / drop_usd if drop_usd > 0 else 0
                
                is_gap_safe = drop_usd <= MAX_GAP_USD  
                is_bounced = bounce_ratio >= MIN_BOUNCE_RATIO 
                is_at_kz_bottom = (x_low <= kz_low)

                if is_trading_enabled:
                    print(f"\r🎯 [X-Sniper] 📉 Found Bottom-X! | KZ{KZ_BARS} Low?: {is_at_kz_bottom} | Drop: {drop_usd:.2f}$ (<={MAX_GAP_USD}) | Bounce: {bounce_ratio*100:.1f}% (>={MIN_BOUNCE_RATIO*100:.1f}%) {' '*5}", end="")
                    
                if is_gap_safe and is_bounced and is_at_kz_bottom:
                    print(f"\n✅ [X-Sniper] 🟢 All conditions met (Fast Action)! Executing BUY!")
                    final_signal = "buy"
                    
            elif is_x_above:
                # 🔍 หาแรงปั๊มราคาจากระยะ OEZ_BARS จาก Dashboard
                recent_low_oez = df['low'].iloc[-(OEZ_BARS+1):-1].min()
                x_high = closed_5_highs[2]
                
                pump_usd = x_high - recent_low_oez
                pullback_usd = x_high - current_close
                bounce_ratio = pullback_usd / pump_usd if pump_usd > 0 else 0
                
                is_gap_safe = pump_usd <= MAX_GAP_USD  
                is_bounced = bounce_ratio >= MIN_BOUNCE_RATIO 
                is_at_kz_top = (x_high >= kz_high)
                
                if is_trading_enabled:
                    print(f"\r🎯 [X-Sniper] 📈 Found Top-X! | KZ{KZ_BARS} High?: {is_at_kz_top} | Pump: {pump_usd:.2f}$ (<={MAX_GAP_USD}) | Pullback: {bounce_ratio*100:.1f}% (>={MIN_BOUNCE_RATIO*100:.1f}%) {' '*5}", end="")
                
                if is_gap_safe and is_bounced and is_at_kz_top:
                    print(f"\n✅ [X-Sniper] 🔴 All conditions met (Fast Action)! Executing SELL!")
                    final_signal = "sell"
            else:
                if is_trading_enabled:
                    print(f"\r🎯 [X-Sniper] ⏳ Scanning for X signal... (Waiting for confirmation) {' '*30}", end="")

        # ==========================================
        # 🚀 โซน 2.5: ส่งคำสั่งเทรด (ถ้ามีสัญญาณ)
        # ==========================================
        if final_signal:
            # 🛑 เช็คสเปรดก่อนยิงไม้หลัก
            if not is_spread_ok:
                print(f"\r⚠️ [Spread Filter] สเปรดถ่าง {current_spread:.0f} จุด (รับได้ {max_spread_allowed}) งดยิงไม้หลัก {symbol}! {' '*10}", end="")
                continue 

            account = get_account_info()
            symbol_info = mt5.symbol_info(symbol)
            if not account or not symbol_info: continue
                
            raw_lot = calculate_lot_size(account["balance"], risk_percentage=risk_percent)
            min_lot, step_lot = symbol_info.volume_min, symbol_info.volume_step
            lot = round(max(raw_lot, min_lot) / step_lot) * step_lot
            
            sl_distance, tp_distance = atr_14 * atr_mult, (atr_14 * atr_mult) * rr_ratio
            tick = mt5.symbol_info_tick(symbol)
            if not tick: continue 
                
            sl_price = tick.ask - sl_distance if final_signal in ["buy", "strong_buy"] else tick.bid + sl_distance
            tp_price = 0.0 if ENDLESS_TRAILING_MODE else (tick.ask + tp_distance if final_signal in ["buy", "strong_buy"] else tick.bid - tp_distance)
            
            sl_price = round(sl_price, symbol_info.digits)
            tp_price = round(tp_price, symbol_info.digits)

            # 🛡️ ระบบเบรกฉุกเฉินสำหรับเปิดไม้ใหม่ (Risk Failsafe)
            contract_size = symbol_info.trade_contract_size
            estimated_loss_usd = abs(tick.ask - sl_price) * lot * contract_size if final_signal in ["buy", "strong_buy"] else abs(sl_price - tick.bid) * lot * contract_size
            
            if estimated_loss_usd > MAX_ALLOWED_LOSS_USD:
                print(f"\n🚫 [Risk Control] กราฟผันผวนหนัก! เสี่ยงติดลบ ${estimated_loss_usd:.2f} (เกินลิมิต ${MAX_ALLOWED_LOSS_USD}) ยกเลิกออเดอร์!")
                continue 
            
            # 🚀 สับไกยิงไม้หลัก
            result = send_order(symbol, final_signal, lot, sl=sl_price, tp=tp_price, comment=f"Main ({sig_mode})")
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                save_new_trade(result.order, symbol, final_signal, result.price)
                msg = (f"🚨 <b>QUANTUM AI EXECUTED (ไม้หลัก)</b> 🚨\n\n🎯 <b>Signal:</b> {final_signal.upper()} [{sig_mode}]\n💱 <b>Symbol:</b> {symbol}\n💰 <b>Entry:</b> {result.price}")
                send_telegram_message(msg)

# ==========================================
# ▶️ จุดสตาร์ทการทำงาน (Main Execution)
# ==========================================
if __name__ == "__main__":
    print("🤖 กำลังปลุก Quantum AI Trader PRO V6 (Ultimate Edition)...")
    if connect_mt5():
        try:
            while True:
                settings = get_bot_settings_db()
                active_symbols = [s.strip() for s in settings.symbols.split(",") if s.strip()]
                # เปิดใช้งานบอทแบบ Standalone (เทสโดยไม่ผ่านเว็บ)
                run_bot_cycle(active_symbols, is_trading_enabled=True) 
                time.sleep(10) # รอบสแกนทุกๆ 10 วินาที
        except KeyboardInterrupt:
            print("\n🛑 หยุดการทำงานของบอทด้วยผู้ใช้")
            mt5.shutdown()