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
          <h2>Bot Controls</h2>
          <p>Trading Pair: <strong class="symbol-text">{{ botData.current_symbol }}</strong></p>
          <p>Live AI Signal: 
            <strong class="signal" :class="botData.last_signal">
              {{ botData.last_signal.toUpperCase() }}
            </strong>
          </p>
          
          <div class="actions">
            <button v-if="!isRunning" @click="toggleBot('start')" class="btn-start">🚀 START AI TRADER</button>
            <button v-else @click="toggleBot('stop')" class="btn-stop">🛑 STOP AI TRADER</button>
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
const API_URL = "http://localhost:8000"; // ถ้าเอาขึ้น VPS จริง ให้เปลี่ยนเป็น IP เซิร์ฟเวอร์

const ws = ref(null);
const isConnected = ref(false);
const isRunning = ref(false);
const account = ref({ balance: 0, equity: 0 });
const botData = ref({ current_symbol: '-', last_signal: 'HOLD', profit_today: 0 });
const tradeHistory = ref([]);

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
// ⚡ ระบบ WebSockets (รับค่า Real-time)
// ==========================================
const connectWebSocket = () => {
  ws.value = new WebSocket('ws://localhost:8000/ws/status');

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
:global(body) { margin: 0; font-family: 'Segoe UI', system-ui, sans-serif; background-color: #0d1117; color: #c9d1d9; }

/* 🔐 Login Screen */
.login-wrapper { display: flex; justify-content: center; align-items: center; height: 100vh; }
.login-box { background: #161b22; padding: 40px; border-radius: 12px; border: 1px solid #30363d; text-align: center; width: 350px; box-shadow: 0 8px 32px rgba(0,0,0,0.6); }
.title-glow { color: #58a6ff; text-shadow: 0 0 10px rgba(88,166,255,0.4); margin-bottom: 5px; }
.subtitle { color: #8b949e; margin-bottom: 30px; font-size: 0.9em; letter-spacing: 1px; }
.login-box input { width: 100%; padding: 14px; margin-bottom: 15px; border-radius: 6px; border: 1px solid #30363d; background: #010409; color: white; box-sizing: border-box; outline: none; transition: 0.3s; }
.login-box input:focus { border-color: #58a6ff; }
.btn-login { width: 100%; padding: 14px; background: linear-gradient(180deg, #2ea043 0%, #238636 100%); color: white; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; letter-spacing: 1px; }
.btn-login:hover { filter: brightness(1.2); }
.error-msg { color: #f85149; margin-top: 15px; font-size: 0.9em; }

/* 📊 Dashboard */
.dashboard-container { padding: 30px; max-width: 1400px; margin: 0 auto; }
.header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 15px; margin-bottom: 30px; }
.version-tag { font-size: 0.4em; vertical-align: top; background: #e34c26; padding: 2px 6px; border-radius: 4px; color: white; }
.header-actions { display: flex; align-items: center; gap: 15px; }
.status-badge { padding: 6px 12px; border-radius: 6px; font-size: 0.85em; font-weight: bold; }
.ws-connected { border: 1px solid #2ea043; color: #2ea043; background: rgba(46,160,67,0.1); }
.ws-disconnected { border: 1px solid #f85149; color: #f85149; background: rgba(248,81,73,0.1); }
.btn-logout { background: transparent; color: #8b949e; border: 1px solid #30363d; padding: 6px 12px; border-radius: 6px; cursor: pointer; transition: 0.2s; }
.btn-logout:hover { color: #f85149; border-color: #f85149; }

/* 🗂️ Cards & Grid */
.grid-layout { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 25px; }
.card { background: #161b22; padding: 25px; border-radius: 12px; border: 1px solid #30363d; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
.stats p { font-size: 1.1em; margin: 10px 0; color: #8b949e; }
.stats strong { color: #c9d1d9; font-size: 1.2em; }
.text-glow { text-shadow: 0 0 10px rgba(201,209,217,0.3); }
.profit strong { color: #3fb950; font-size: 1.4em; }
.profit.loss strong { color: #f85149; }

/* 🤖 Controls */
.symbol-text { color: #f0b37e; font-size: 1.2em; }
.signal { font-size: 1.2em; font-weight: bold; }
.signal.buy, .signal.strong_buy { color: #3fb950; text-shadow: 0 0 8px rgba(63,185,80,0.4); }
.signal.sell, .signal.strong_sell { color: #f85149; text-shadow: 0 0 8px rgba(248,81,73,0.4); }
.signal.hold { color: #8b949e; }
.actions { margin-top: 20px; }
.btn-start { background: linear-gradient(180deg, #2ea043 0%, #238636 100%); color: white; padding: 14px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; transition: 0.2s; font-size: 1.1em; }
.btn-start:hover { filter: brightness(1.2); box-shadow: 0 0 15px rgba(46,160,67,0.4); }
.btn-stop { background: linear-gradient(180deg, #f85149 0%, #da3633 100%); color: white; padding: 14px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; transition: 0.2s; font-size: 1.1em; }
.btn-stop:hover { filter: brightness(1.2); box-shadow: 0 0 15px rgba(248,81,73,0.4); }

/* 📜 Table */
.history-section { margin-top: 25px; }
.history-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.btn-refresh { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 8px 16px; border-radius: 6px; cursor: pointer; transition: 0.2s; }
.btn-refresh:hover { background: #30363d; color: white; }
.table-container { overflow-x: auto; }
.premium-table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.95em; }
.premium-table th { background: #010409; padding: 14px 15px; color: #8b949e; border-bottom: 2px solid #30363d; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; font-size: 0.85em; }
.premium-table td { padding: 14px 15px; border-bottom: 1px solid #21262d; }
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
</style>