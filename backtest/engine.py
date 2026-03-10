import pandas as pd
import numpy as np

class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0, risk_per_trade: float = 0.01):
        """
        ระบบจำลองพอร์ตการลงทุน
        :param initial_capital: ทุนเริ่มต้น (เช่น $10,000)
        :param risk_per_trade: ความเสี่ยงต่อไม้ (เช่น 0.01 = 1%)
        """
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.risk_per_trade = risk_per_trade
        self.trades = []
        self.equity_curve = [initial_capital]

    def execute_trade(self, entry_time, entry_price, signal, exit_price):
        """
        จำลองการเปิดและปิดออเดอร์ (คำนวณกำไร/ขาดทุน)
        """
        # คำนวณจำนวนเงินที่ยอมเสียได้ในไม้นี้
        risk_amount = self.balance * self.risk_per_trade
        
        # สมมติระยะ Stop Loss ห่างไป 1% ของราคา (เพื่อใช้คำนวณ Position Size แบบคร่าวๆ)
        sl_distance = entry_price * 0.01 
        position_size = risk_amount / sl_distance

        # คำนวณกำไร/ขาดทุน
        if signal in ["buy", "strong_buy"]:
            pnl = (exit_price - entry_price) * position_size
        elif signal in ["sell", "strong_sell"]:
            pnl = (entry_price - exit_price) * position_size
        else:
            pnl = 0

        # อัปเดตยอดเงินในพอร์ต
        self.balance += pnl
        self.equity_curve.append(self.balance)

        # บันทึกประวัติการเทรดลงสมุดจด
        self.trades.append({
            "time": entry_time,
            "signal": signal,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "balance": self.balance
        })

    def generate_report(self):
        """
        คำนวณและแสดงผลรายงานสถิติระดับสถาบัน (Hedge Fund Report)
        """
        if not self.trades:
            print("❌ ไม่มีการเทรดเกิดขึ้นในระบบ (ลองปรับเงื่อนไข AI ให้เข้าเทรดง่ายขึ้น)")
            return None

        df_trades = pd.DataFrame(self.trades)
        
        total_trades = len(df_trades)
        winning_trades = len(df_trades[df_trades['pnl'] > 0])
        win_rate = (winning_trades / total_trades) * 100

        total_profit = df_trades[df_trades['pnl'] > 0]['pnl'].sum()
        total_loss = abs(df_trades[df_trades['pnl'] < 0]['pnl'].sum())
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        # คำนวณ Max Drawdown (เปอร์เซ็นต์ที่พอร์ตเคยติดลบหนักที่สุดจากจุดสูงสุด)
        equity_series = pd.Series(self.equity_curve)
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100

        print("\n" + "="*50)
        print("📊 QUANTUM AI - BACKTEST REPORT")
        print("="*50)
        print(f"ทุนเริ่มต้น:     ${self.initial_capital:,.2f}")
        print(f"ยอดเงินสุดท้าย:   ${self.balance:,.2f}")
        print(f"กำไรสุทธิ:       ${self.balance - self.initial_capital:,.2f} ({((self.balance / self.initial_capital) - 1) * 100:.2f}%)")
        print("-" * 50)
        print(f"จำนวนการเทรด:   {total_trades} ไม้")
        print(f"Win Rate:      {win_rate:.2f}%")
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Max Drawdown:  {max_drawdown:.2f}%")
        print("="*50 + "\n")
        
        return df_trades