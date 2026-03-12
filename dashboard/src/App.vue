<template>
  <div>
    <div v-if="!isAuthenticated" class="login-wrapper">
      <div class="login-box">
        <h2 class="title-glow">🧠 Quantum AI</h2>
        <p class="subtitle">Institutional Control Panel</p>
        
        <form @submit.prevent="handleLogin">
          <input v-model="loginForm.username" type="text" placeholder="Username (admin)" required />
          <input v-model="loginForm.password" type="password" placeholder="Password" required />
          <button type="submit" class="btn-login">ACCESS SYSTEM</button>
          <p v-if="loginError" class="error-msg">{{ loginError }}</p>
        </form>
      </div>
    </div>

    <div v-else class="dashboard-container">
      <header class="header">
        <h1>🧠 Quantum AI <span class="version-tag">PRO</span></h1>
        <div class="header-actions">
          <span class="status-badge" :class="wsStatusClass">
            {{ wsStatusText }} | {{ isRunning ? '🟢 BOT ONLINE' : '🔴 BOT OFFLINE' }}
          </span>
          <button @click="handleLogout" class="btn-logout">🚪 Logout</button>
        </div>
      </header>

      <main class="grid-layout">
        <section class="card account-info">
          <h2>Account Overview</h2>
          <div class="stats">
            <p>Balance: <strong>${{ formatMoney(account.balance) }}</strong></p>
            <p>Equity: <strong class="text-glow">${{ formatMoney(account.equity) }}</strong></p>
            <p class="profit" :class="{'loss': botData.profit_today < 0}">
              Profit Today: <strong>{{ botData.profit_today >= 0 ? '+' : '' }}${{ formatMoney(botData.profit_today) }}</strong>
            </p>
          </div>
        </section>

        <section class="card control-panel">
          <h2>🤖 AI Signal Radar</h2>
          
          <div class="signal-grid">
            <div v-for="(data, sym) in botData.live_signals" :key="sym" class="signal-box">
              <div class="signal-header">
                <span class="symbol-text">{{ sym }}</span>
                <span class="signal-badge" :class="data.signal.toLowerCase()">{{ data.signal }}</span>
              </div>
              
              <div class="signal-bar-container">
                <div class="signal-bar buy" :style="{ width: data.buy_prob + '%' }"></div>
                <div class="signal-bar sell" :style="{ width: data.sell_prob + '%' }"></div>
              </div>
              
              <div class="signal-stats">
                <span class="buy-text">B: {{ data.buy_prob.toFixed(1) }}%</span>
                <span class="sell-text">S: {{ data.sell_prob.toFixed(1) }}%</span>
              </div>
            </div>
            <div v-if="Object.keys(botData.live_signals || {}).length === 0" style="color:#8b949e; font-size: 0.9em; grid-column: 1 / -1; text-align: center; padding: 10px;">
                *รอการเชื่อมต่อ... หรือไม่มีคู่เงินที่กำลังสแกน
            </div>
          </div>
          
          <div class="actions">
            <button v-if="!isRunning" @click="toggleBot('start')" class="btn-start">🚀 START AI TRADER</button>
            <button v-else @click="toggleBot('stop')" class="btn-stop">🛑 STOP AI TRADER</button>
          </div>

          <div class="confidence-control">
            <h3 style="margin-top: 0; color: #58a6ff; font-size: 1.1em; border-bottom: 1px solid #30363d; padding-bottom: 10px;">
              ⚙️ AI System Settings
            </h3>
            
            <div class="setting-group">
                <div class="confidence-header">
                    <span class="confidence-title">🤖 AI Confidence Threshold</span>
                    <span class="confidence-value text-green">{{ formSettings.confidence }}%</span>
                </div>
                <input type="range" min="50.0" max="80.0" step="0.5" v-model="formSettings.confidence" class="confidence-slider" />
            </div>

            <div class="setting-group">
                <div class="confidence-header">
                    <span class="confidence-title">💰 Risk Per Trade (%)</span>
                    <span class="confidence-value text-purple">{{ formSettings.risk_percent }}%</span>
                </div>
                <input type="range" min="0.1" max="5.0" step="0.1" v-model="formSettings.risk_percent" class="confidence-slider risk-slider" />
            </div>

            <div class="setting-group" style="margin-bottom: 15px;">
                <div class="confidence-header">
                    <span class="confidence-title">💱 Trading Symbols</span>
                </div>
                <input type="text" v-model="formSettings.symbols" class="symbol-input" placeholder="e.g. BTCUSDm,XAUUSDm" />
                <p style="font-size: 11px; color: #8b949e; margin-top: 5px; margin-bottom: 0;">*คั่นแต่ละเหรียญด้วยเครื่องหมายลูกน้ำ (,) ตัวพิมพ์เล็ก/ใหญ่มีผล</p>
            </div>
            
            <button @click="handleSaveSettings" class="btn-save-settings">
                💾 APPLY ALL SETTINGS
            </button>
          </div>
        </section>
      </main>

      <section class="card history-section">
        <div class="history-header">
          <h2>📜 Live Trade History</h2>
          <button @click="fetchTradeHistory" class="btn-refresh">🔄 Refresh</button>
        </div>

        <div class="table-container">
          <table class="premium-table">
            <thead>
              <tr>
                <th>Ticket ID</th>
                <th>Time</th>
                <th>Symbol</th>
                <th>Type</th>
                <th>Entry Price</th>
                <th>Status</th>
                <th>Profit / Loss</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="tradeHistory.length === 0">
                <td colspan="7" class="text-center">Waiting for AI to execute trades...</td>
              </tr>
              <tr v-for="trade in tradeHistory" :key="trade.id">
                <td>#{{ trade.ticket_id }}</td>
                <td class="time-col">{{ trade.timestamp }}</td>
                <td class="font-bold">{{ trade.symbol }}</td>
                <td>
                  <span :class="['badge-type', trade.trade_type.toLowerCase()]">
                    {{ trade.trade_type }}
                  </span>
                </td>
                <td>{{ trade.entry_price.toFixed(5) }}</td>
                <td>
                  <span :class="['badge-status', trade.status.toLowerCase()]">
                    {{ trade.status }}
                  </span>
                </td>
                <td :class="getProfitClass(trade.profit)">
                  <strong>{{ formatProfit(trade.profit) }}</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue';

// ==========================================
// ⚙️ ตัวแปร State ต่างๆ
// ==========================================
const isAuthenticated = ref(!!localStorage.getItem('access_token'));
const loginForm = ref({ username: '', password: '' });
const loginError = ref('');

// ดึง Hostname ปัจจุบันที่ผู้ใช้เปิดเว็บอยู่
const currentHost = window.location.hostname;

// URL สำหรับ API และ WS วิ่งผ่าน Nginx (ไม่ต้องใส่ :8000)
const API_URL = `http://${currentHost}`; 
const WS_URL = `ws://${currentHost}/ws/status`; 

const ws = ref(null);
const isConnected = ref(false);
const isRunning = ref(false);
const account = ref({ balance: 0, equity: 0 });
const botData = ref({ current_symbol: '-', last_signal: 'HOLD', profit_today: 0, live_signals: {} });
const tradeHistory = ref([]);

// State สำหรับเก็บค่าการตั้งค่าจาก Database
const formSettings = ref({
    confidence: 51.0,
    risk_percent: 1.0,
    symbols: "BTCUSDm,XAUUSDm"
});

// Helpers
const formatMoney = (val) => Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const formatProfit = (profit) => {
  if (profit === null || profit === undefined) return "-";
  const sign = profit > 0 ? "+" : "";
  return `${sign}$${profit.toFixed(2)}`;
};
const getProfitClass = (profit) => {
  if (!profit) return "text-neutral";
  return profit > 0 ? "text-profit" : "text-loss";
};

const wsStatusText = computed(() => isConnected.value ? '⚡ WS CONNECTED' : '🔌 WS DISCONNECTED');
const wsStatusClass = computed(() => isConnected.value ? 'ws-connected' : 'ws-disconnected');

// ==========================================
// 🔐 ระบบ Authentication
// ==========================================
const handleLogin = async () => {
  loginError.value = '';
  try {
    const formData = new URLSearchParams();
    formData.append('username', loginForm.value.username);
    formData.append('password', loginForm.value.password);

    const res = await fetch(`${API_URL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData
    });

    const data = await res.json();
    if (res.ok) {
      localStorage.setItem('access_token', data.access_token);
      isAuthenticated.value = true;
      initDashboard();
    } else {
      loginError.value = "Access Denied: Invalid Credentials";
    }
  } catch (error) {
    loginError.value = "Cannot connect to AI Server.";
  }
};

const handleLogout = () => {
  localStorage.removeItem('access_token');
  isAuthenticated.value = false;
  if (ws.value) ws.value.close();
};

// ==========================================
// 📡 ดึงข้อมูลประวัติการเทรดผ่าน API
// ==========================================
const fetchTradeHistory = async () => {
  const token = localStorage.getItem('access_token');
  if (!token) return;

  try {
    const res = await fetch(`${API_URL}/api/trades`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (res.status === 401) {
      handleLogout(); return;
    }
    
    const responseData = await res.json();
    if (responseData.status === "success") {
      tradeHistory.value = responseData.data;
    }
  } catch (error) {
    console.error("Fetch history error:", error);
  }
};

// ==========================================
// 🎛️ ดึงและบันทึกค่าการตั้งค่าศูนย์กลาง (เซฟลง DB)
// ==========================================
const fetchSettings = async () => {
    try {
        const res = await fetch(`${API_URL}/api/settings/bot`);
        if (res.ok) {
            const data = await res.json();
            formSettings.value.confidence = data.confidence;
            formSettings.value.risk_percent = data.risk_percent;
            formSettings.value.symbols = data.symbols;
        }
    } catch (error) {
        console.error("Failed to fetch settings:", error);
    }
};

const handleSaveSettings = async () => {
    try {
        const payload = {
            confidence: parseFloat(formSettings.value.confidence),
            risk_percent: parseFloat(formSettings.value.risk_percent),
            symbols: formSettings.value.symbols
        };
        
        const res = await fetch(`${API_URL}/api/settings/bot`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            alert(`✅ บันทึกการตั้งค่าลงฐานข้อมูลสำเร็จ!\n\nAI Accuracy: ${payload.confidence}%\nRisk/Trade: ${payload.risk_percent}%\nActive Symbols: ${payload.symbols}`);
        } else {
            alert("❌ บันทึกข้อมูลไม่สำเร็จ");
        }
    } catch (error) {
        console.error("Error updating settings:", error);
        alert("❌ เกิดข้อผิดพลาดในการเชื่อมต่อกับเซิร์ฟเวอร์");
    }
};

// ==========================================
// ⚡ ระบบ WebSockets (รับค่า Real-time)
// ==========================================
const connectWebSocket = () => {
  ws.value = new WebSocket(WS_URL);

  ws.value.onopen = () => { isConnected.value = true; };

  ws.value.onmessage = (event) => {
    const data = JSON.parse(event.data);
    isRunning.value = data.bot.is_running;
    botData.value = data.bot;
    account.value = data.account;
  };

  ws.value.onclose = () => {
    isConnected.value = false;
    setTimeout(connectWebSocket, 3000); // Reconnect ถ้ายกเลิกการเชื่อมต่อ
  };
};

const toggleBot = (action) => {
  if (ws.value && isConnected.value) {
    ws.value.send(JSON.stringify({ action: action }));
  }
};

// ==========================================
// 🚀 เริ่มทำงานเมื่อหน้าเว็บโหลด
// ==========================================
const initDashboard = () => {
  fetchTradeHistory();
  fetchSettings(); // ดึงการตั้งค่าล่าสุดจาก Database
  connectWebSocket();
  setInterval(fetchTradeHistory, 10000); // อัปเดตตารางทุกๆ 10 วินาที
};

onMounted(() => {
  if (isAuthenticated.value) {
    initDashboard();
  }
});

onUnmounted(() => {
  if (ws.value) ws.value.close();
});
</script>

<style scoped>
/* ==========================================
   🎨 สไตล์ CSS ระดับ Institutional
   ========================================== */
:global(html), :global(body), :global(#app) { 
  margin: 0; padding: 0; width: 100%; min-height: 100vh; 
  background-color: #0d1117; color: #c9d1d9; 
  font-family: 'Segoe UI', system-ui, sans-serif; overflow-x: hidden; 
}
/* 🔐 Login Screen */
.login-wrapper { display: flex; justify-content: center; align-items: center; height: 100vh; padding: 20px; box-sizing: border-box; }
.login-box { background: #161b22; padding: 40px; border-radius: 12px; border: 1px solid #30363d; text-align: center; width: 100%; max-width: 380px; box-shadow: 0 8px 32px rgba(0,0,0,0.6); box-sizing: border-box; }
.title-glow { color: #58a6ff; text-shadow: 0 0 10px rgba(88,166,255,0.4); margin-bottom: 5px; }
.subtitle { color: #8b949e; margin-bottom: 30px; font-size: 0.9em; letter-spacing: 1px; }
.login-box input { width: 100%; padding: 14px; margin-bottom: 15px; border-radius: 6px; border: 1px solid #30363d; background: #010409; color: white; box-sizing: border-box; outline: none; transition: 0.3s; }
.login-box input:focus { border-color: #58a6ff; }
.btn-login { width: 100%; padding: 14px; background: linear-gradient(180deg, #2ea043 0%, #238636 100%); color: white; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; letter-spacing: 1px; }
.btn-login:hover { filter: brightness(1.2); }
.error-msg { color: #f85149; margin-top: 15px; font-size: 0.9em; }

/* 📊 Dashboard */
.dashboard-container { padding: 30px; max-width: 1400px; margin: 0 auto; box-sizing: border-box; }
.header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 15px; margin-bottom: 30px; }
.version-tag { font-size: 0.4em; vertical-align: top; background: #e34c26; padding: 2px 6px; border-radius: 4px; color: white; }
.header-actions { display: flex; align-items: center; gap: 15px; }
.status-badge { padding: 6px 12px; border-radius: 6px; font-size: 0.85em; font-weight: bold; }
.ws-connected { border: 1px solid #2ea043; color: #2ea043; background: rgba(46,160,67,0.1); }
.ws-disconnected { border: 1px solid #f85149; color: #f85149; background: rgba(248,81,73,0.1); }
.btn-logout { background: transparent; color: #8b949e; border: 1px solid #30363d; padding: 6px 12px; border-radius: 6px; cursor: pointer; transition: 0.2s; }
.btn-logout:hover { color: #f85149; border-color: #f85149; }

/* 🗂️ Cards & Grid */
.grid-layout { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 25px; }
.card { background: #161b22; padding: 25px; border-radius: 12px; border: 1px solid #30363d; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
.stats p { font-size: 1.1em; margin: 10px 0; color: #8b949e; }
.stats strong { color: #c9d1d9; font-size: 1.2em; }
.text-glow { text-shadow: 0 0 10px rgba(201,209,217,0.3); }
.profit strong { color: #3fb950; font-size: 1.4em; }
.profit.loss strong { color: #f85149; }

/* 🤖 Controls */
.symbol-text { color: #f0b37e; font-size: 1.2em; }
.signal { font-size: 1.2em; font-weight: bold; }
.actions { margin-top: 20px; }
.btn-start, .btn-stop { padding: 14px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; transition: 0.2s; font-size: 1.1em; color: white; }
.btn-start { background: linear-gradient(180deg, #2ea043 0%, #238636 100%); }
.btn-start:hover { filter: brightness(1.2); box-shadow: 0 0 15px rgba(46,160,67,0.4); }
.btn-stop { background: linear-gradient(180deg, #f85149 0%, #da3633 100%); }
.btn-stop:hover { filter: brightness(1.2); box-shadow: 0 0 15px rgba(248,81,73,0.4); }

/* 👇 สไตล์กล่องควบคุม Settings */
.confidence-control { margin-top: 25px; padding: 20px; background-color: #010409; border-radius: 8px; border: 1px solid #30363d; }
.setting-group { margin-bottom: 20px; }
.confidence-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.confidence-title { color: #c9d1d9; font-weight: bold; font-size: 0.95em; }
.confidence-value { font-weight: bold; font-size: 1.1em; }
.text-green { color: #3fb950; text-shadow: 0 0 8px rgba(63,185,80,0.4); }
.text-purple { color: #d2a8ff; text-shadow: 0 0 8px rgba(210,168,255,0.4); }
.confidence-slider { width: 100%; cursor: pointer; accent-color: #3fb950; height: 6px; background: #21262d; border-radius: 3px; outline: none; }
.risk-slider { accent-color: #d2a8ff; }
.symbol-input { width: 100%; padding: 12px; background: #161b22; border: 1px solid #30363d; color: #f0b37e; border-radius: 6px; font-weight: bold; font-size: 1em; box-sizing: border-box; outline: none; transition: 0.2s; }
.symbol-input:focus { border-color: #58a6ff; }
.btn-save-settings { width: 100%; padding: 12px; background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; }
.btn-save-settings:hover { background: #30363d; color: white; border-color: #8b949e; }

/* 📜 Table */
.history-section { margin-top: 25px; }
.history-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.btn-refresh { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 8px 16px; border-radius: 6px; cursor: pointer; transition: 0.2s; }
.btn-refresh:hover { background: #30363d; color: white; }
.table-container { overflow-x: auto; -webkit-overflow-scrolling: touch; } 
.premium-table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.95em; min-width: 700px; }
.premium-table th { background: #010409; padding: 14px 15px; color: #8b949e; border-bottom: 2px solid #30363d; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; font-size: 0.85em; }
.premium-table td { padding: 14px 15px; border-bottom: 1px solid #21262d; white-space: nowrap; }
.premium-table tbody tr:hover { background: #1c2128; }
.time-col { color: #8b949e; font-size: 0.9em; }
.font-bold { font-weight: bold; color: #e6edf3; }
.badge-type { padding: 4px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; }
.badge-type.buy { background: rgba(46, 160, 67, 0.15); color: #3fb950; }
.badge-type.sell { background: rgba(248, 81, 73, 0.15); color: #f85149; }
.badge-status { padding: 4px 8px; border-radius: 4px; font-size: 0.85em; border: 1px solid; }
.badge-status.open { border-color: #d2a8ff; color: #d2a8ff; }
.badge-status.closed { border-color: #8b949e; color: #8b949e; }
.text-profit { color: #3fb950; font-weight: bold; }
.text-loss { color: #f85149; font-weight: bold; }
.text-neutral { color: #8b949e; }
.text-center { text-align: center; color: #8b949e; padding: 30px !important; }

/* 🎯 AI Radar Grid */
.signal-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 20px; }
.signal-box { background: #010409; border: 1px solid #30363d; border-radius: 8px; padding: 12px; }
.signal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.signal-badge { font-size: 0.75em; font-weight: bold; padding: 3px 6px; border-radius: 4px; text-transform: uppercase; }
.signal-badge.buy, .signal-badge.strong_buy { background: rgba(46,160,67,0.2); color: #3fb950; border: 1px solid #3fb950; }
.signal-badge.sell, .signal-badge.strong_sell { background: rgba(248,81,73,0.2); color: #f85149; border: 1px solid #f85149; }
.signal-badge.hold, .signal-badge.wait { background: rgba(139,148,158,0.2); color: #8b949e; border: 1px solid #8b949e; }
.signal-bar-container { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: #21262d; margin-bottom: 8px; }
.signal-bar { transition: width 0.5s ease-in-out; }
.signal-bar.buy { background: #3fb950; }
.signal-bar.sell { background: #f85149; }
.signal-stats { display: flex; justify-content: space-between; font-size: 0.75em; font-weight: bold; }
.buy-text { color: #3fb950; }
.sell-text { color: #f85149; }

/* ==========================================
   📱 MOBILE RESPONSIVE 
   ========================================== */
@media (max-width: 768px) {
  .dashboard-container { padding: 15px; } 
  .header { flex-direction: column; align-items: flex-start; gap: 15px; }
  .header h1 { margin: 0; font-size: 1.6em; }
  .header-actions { width: 100%; justify-content: space-between; }
  .history-header { flex-direction: column; align-items: stretch; gap: 15px; }
  .btn-refresh { width: 100%; padding: 12px; } 
  .card { padding: 20px; } 
}
@media (max-width: 480px) {
  .login-box { padding: 30px 20px; } 
  .status-badge { font-size: 0.75em; padding: 6px 10px; }
}
</style>