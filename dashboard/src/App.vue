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
        <button @click="panicCloseAll" class="btn-panic" title="ปิดทุกออเดอร์ทันที!">🚨 PANIC CLOSE</button>
          <button v-if="!isRunning" @click="toggleBot('start')" class="btn-start-nav">🚀 START AI</button>
          <button v-else @click="toggleBot('stop')" class="btn-stop-nav">🛑 STOP AI</button>
          
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

        <section class="card control-panel" style="grid-column: 1 / -1;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
             <h2 style="margin: 0; font-size: 1.5em;">🤖 AI Signal Radar</h2>
             <button @click="openGlobalSettingsModal" class="btn-global-settings">
                ⚙️ GLOBAL SETTINGS
             </button>
          </div>
          
          <div style="margin-bottom: 20px; color: #8b949e; font-size: 0.9em; display: flex; align-items: center; gap: 10px;">
              <span>Active Symbols:</span>
              <div style="display: flex; gap: 5px; flex-wrap: wrap;">
                 <span v-for="sym in activeSymbolList" :key="sym" class="mini-tag">{{ sym }}</span>
                 <span v-if="activeSymbolList.length === 0">None</span>
              </div>
          </div>
          
          <div class="signal-grid">
            <div v-for="(data, sym) in botData.live_signals" :key="sym" class="signal-box">
              <div class="signal-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <button @click="openSymbolSettingsModal(sym)" class="btn-icon-settings" title="Per-Symbol Settings">⚙️</button>
                    <span class="symbol-text">{{ sym }}</span>
                </div>
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
            <div v-if="Object.keys(botData.live_signals || {}).length === 0" style="color:#8b949e; font-size: 0.9em; grid-column: 1 / -1; text-align: center; padding: 20px;">
                *รอการเชื่อมต่อ... หรือไม่มีคู่เงินที่กำลังสแกน
            </div>
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
              <tr v-for="trade in tradeHistory" :key="trade.ticket_id">
                <td>#{{ trade.ticket_id }}</td>
                <td class="time-col">{{ trade.timestamp }}</td>
                <td class="font-bold">{{ trade.symbol }}</td>
                <td>
                  <span :class="['badge-type', trade.type.toLowerCase()]">
                    {{ trade.type.toUpperCase() }}
                  </span>
                </td>
                <td>{{ Number(trade.entry_price).toFixed(5) }}</td>
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

      <div v-if="showSymbolModal" class="modal-overlay" @click.self="closeSymbolModal">
        <div class="modal-box">
          <h3 class="modal-title">⚙️ Settings: <span class="text-glow" style="color:#f0b37e;">{{ currentEditSymbol }}</span></h3>
          <div style="background: rgba(88,166,255,0.1); border: 1px solid #58a6ff; padding: 15px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
             <div>
                <strong style="color: #58a6ff;">🤖 AI Auto-Tune Mode</strong>
                <p style="margin: 5px 0 0 0; font-size: 0.8em; color: #8b949e;">ให้ AI ปรับค่าตามสภาวะตลาดอัตโนมัติ</p>
             </div>
             <label class="switch">
                <input type="checkbox" v-model="tempSettings.auto_tune">
                <span class="slider round"></span>
             </label>
          </div>
          <p v-if="tempSettings.auto_tune" style="color: #3fb950; font-size: 0.85em; text-align: center; margin-bottom: 15px;">
            ✅ AI กำลังควบคุมค่าด้านล่างนี้อัตโนมัติ (Dynamic Adjust)
          </p>
          <div class="setting-group">
              <div class="confidence-header">
                  <span class="confidence-title">🤖 Target Confidence</span>
                  <span class="confidence-value text-green">{{ Number(tempSettings.confidence).toFixed(1) }}%</span>
              </div>
              <input type="range" min="50.0" max="80.0" step="0.5" v-model="tempSettings.confidence" class="confidence-slider" />
          </div>

          <div class="setting-group">
              <div class="confidence-header">
                  <span class="confidence-title">💰 Risk Per Trade</span>
                  <span class="confidence-value text-purple">{{ tempSettings.risk_percent }}%</span>
              </div>
              <input type="range" min="0.1" max="5.0" step="0.1" v-model="tempSettings.risk_percent" class="confidence-slider risk-slider" />
          </div>
          
          <div class="setting-group">
              <div class="confidence-header">
                  <span class="confidence-title">🛡️ SL ATR Distance</span>
                  <span class="confidence-value text-green">x{{ Number(tempSettings.atr_sl).toFixed(1) }}</span>
              </div>
              <input type="range" min="1.0" max="5.0" step="0.1" v-model="tempSettings.atr_sl" class="confidence-slider" style="accent-color: #f85149;" />
          </div>

          <div class="setting-group">
              <div class="confidence-header">
                  <span class="confidence-title">🚀 Take Profit (R:R)</span>
                  <span class="confidence-value text-green">1:{{ Number(tempSettings.rr_ratio).toFixed(1) }}</span>
              </div>
              <input type="range" min="1.0" max="5.0" step="0.1" v-model="tempSettings.rr_ratio" class="confidence-slider" style="accent-color: #58a6ff;" />
          </div>

          <div class="setting-group">
              <div class="confidence-header">
                  <span class="confidence-title">🔒 Break-Even ATR</span>
                  <span class="confidence-value text-green">x{{ Number(tempSettings.break_even).toFixed(1) }}</span>
              </div>
              <input type="range" min="1.0" max="3.0" step="0.1" v-model="tempSettings.break_even" class="confidence-slider" style="accent-color: #f0b37e;" />
          </div>
          
          <div class="modal-actions">
            <button @click="saveSymbolSettings" class="btn-save">💾 SAVE</button>
            <button @click="closeSymbolModal" class="btn-cancel">CANCEL</button>
          </div>
        </div>
      </div>

      <div v-if="showGlobalModal" class="modal-overlay" @click.self="closeGlobalModal">
        <div class="modal-box" style="max-width: 450px;">
          <h3 class="modal-title" style="color: #58a6ff;">⚙️ Global AI Settings</h3>

          <div class="setting-group">
              <div class="confidence-header">
                  <span class="confidence-title">🤖 Default AI Confidence</span>
                  <span class="confidence-value text-green">{{ Number(formSettings.confidence).toFixed(1) }}%</span>
              </div>
              <input type="range" min="50.0" max="80.0" step="0.5" v-model="formSettings.confidence" class="confidence-slider" />
          </div>

          <div class="setting-group">
              <div class="confidence-header">
                  <span class="confidence-title">💰 Default Risk Per Trade (%)</span>
                  <span class="confidence-value text-purple">{{ formSettings.risk_percent }}%</span>
              </div>
              <input type="range" min="0.1" max="5.0" step="0.1" v-model="formSettings.risk_percent" class="confidence-slider risk-slider" />
          </div>

          <div class="setting-group" style="margin-top: 20px;">
              <div class="confidence-header">
                  <span class="confidence-title">⏱️ Session Trading Time</span>
              </div>
              <div style="display: flex; gap: 15px; margin-top: 10px;">
                  <div style="flex: 1;">
                      <label style="font-size: 0.8em; color: #8b949e;">Start Time</label>
                      <input type="time" v-model="formSettings.trade_start_time" class="symbol-input" style="padding: 10px; margin-top: 5px; cursor: pointer;" />
                  </div>
                  <div style="flex: 1;">
                      <label style="font-size: 0.8em; color: #8b949e;">End Time</label>
                      <input type="time" v-model="formSettings.trade_end_time" class="symbol-input" style="padding: 10px; margin-top: 5px; cursor: pointer;" />
                  </div>
              </div>
          </div>

          <div class="setting-group" style="margin-top: 25px;">
              <div class="confidence-header">
                  <span class="confidence-title">💱 Active Trading Symbols</span>
              </div>
              
              <div class="symbol-tags" style="margin-top: 10px;">
                  <span v-for="(sym, index) in activeSymbolList" :key="index" class="symbol-tag">
                      {{ sym }}
                      <button @click.prevent="removeSymbol(sym)" class="btn-remove-sym">✕</button>
                  </span>
                  <span v-if="activeSymbolList.length === 0" style="color: #8b949e; font-size: 0.9em;">(No active symbols)</span>
              </div>

              <div class="add-symbol-wrapper" style="margin-top: 10px;">
                  <input type="text" v-model="newSymbol" class="symbol-input" placeholder="e.g. ETHUSDm" @keyup.enter="addSymbol" />
                  <button @click.prevent="addSymbol" class="btn-add-sym">➕ ADD</button>
              </div>
          </div>
          
          <div class="modal-actions" style="margin-top: 35px;">
            <button @click="handleSaveGlobalSettings" class="btn-save" style="background: #2ea043;">💾 APPLY SETTINGS</button>
            <button @click="closeGlobalModal" class="btn-cancel">CLOSE</button>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';

// ==========================================
// ⚙️ ตัวแปร State ต่างๆ
// ==========================================
const isAuthenticated = ref(!!localStorage.getItem('access_token'));
const loginForm = ref({ username: '', password: '' });
const loginError = ref('');

const currentHost = window.location.hostname;
const API_URL = `http://${currentHost}`; 
const WS_URL = `ws://${currentHost}/ws/status`; 

const ws = ref(null);
const isConnected = ref(false);
const isRunning = ref(false);
const account = ref({ balance: 0, equity: 0 });
const botData = ref({ current_symbol: '-', last_signal: 'HOLD', profit_today: 0, live_signals: {} });
const tradeHistory = ref([]);

const formSettings = ref({
    confidence: 54.0,
    risk_percent: 1.0,
    symbols: "BTCUSDm,XAUUSDm",
    trade_start_time: "00:00",
    trade_end_time: "23:59"
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
    if (res.status === 401) { handleLogout(); return; }
    const responseData = await res.json();
    if (responseData.status === "success") {
      tradeHistory.value = responseData.data;
    }
  } catch (error) { console.error("Fetch history error:", error); }
};

// ==========================================
// 💱 ระบบจัดการเหรียญ (Tags)
// ==========================================
const newSymbol = ref('');
const activeSymbolList = computed(() => {
  if (!formSettings.value.symbols) return [];
  return formSettings.value.symbols.split(',').map(s => s.trim()).filter(s => s);
});
const addSymbol = () => {
  const sym = newSymbol.value.trim();
  if (sym && !activeSymbolList.value.includes(sym)) {
    const currentList = [...activeSymbolList.value, sym];
    formSettings.value.symbols = currentList.join(',');
    newSymbol.value = '';
  }
};
const removeSymbol = (sym) => {
  const currentList = activeSymbolList.value.filter(s => s !== sym);
  formSettings.value.symbols = currentList.join(',');
};

// ==========================================
// 🎛️ ระบบดึงและบันทึกค่า Global (Modal)
// ==========================================
const showGlobalModal = ref(false);

const openGlobalSettingsModal = () => {
    fetchSettings(); // โหลดค่าล่าสุดจาก DB ก่อนเปิด
    showGlobalModal.value = true;
};
const closeGlobalModal = () => {
    showGlobalModal.value = false;
};

const fetchSettings = async () => {
    try {
        const res = await fetch(`${API_URL}/api/settings/bot`);
        if (res.ok) {
            const data = await res.json();
            formSettings.value = { ...data };
        }
    } catch (error) { console.error("Failed to fetch settings:", error); }
};

const handleSaveGlobalSettings = async () => {
    try {
        const payload = {
            confidence: parseFloat(formSettings.value.confidence),
            risk_percent: parseFloat(formSettings.value.risk_percent),
            symbols: formSettings.value.symbols,
            trade_start_time: formSettings.value.trade_start_time,
            trade_end_time: formSettings.value.trade_end_time
        };
        const res = await fetch(`${API_URL}/api/settings/bot`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            alert(`✅ บันทึกการตั้งค่าเวลาและรายชื่อเหรียญเรียบร้อย!\nเวลาเทรด: ${payload.trade_start_time} - ${payload.trade_end_time}`);
            closeGlobalModal(); // ปิดหน้าต่างตอนเซฟเสร็จ
        } else {
            alert("❌ บันทึกข้อมูลไม่สำเร็จ");
        }
    } catch (error) {
        console.error("Error updating settings:", error);
    }
};

// ==========================================
// ⚙️ ระบบตั้งค่าแยกรายเหรียญ (Modal)
// ==========================================
const showSymbolModal = ref(false);
const currentEditSymbol = ref('');
const tempSettings = ref({ confidence: 54.0, risk_percent: 1.0, atr_sl: 2.0, rr_ratio: 2.0, break_even: 1.5, auto_tune: false });

const openSymbolSettingsModal = async (sym) => {
  currentEditSymbol.value = sym;
  try {
    const res = await fetch(`${API_URL}/api/settings/symbol/${sym}`);
    if(res.ok) {
       const data = await res.json();
       tempSettings.value = { 
           confidence: data.confidence, 
           risk_percent: data.risk_percent,
           atr_sl: data.atr_sl || 2.0,
           rr_ratio: data.rr_ratio || 2.0,
           break_even: data.break_even || 1.5,
           auto_tune: data.auto_tune || false
       };
    }
  } catch(e) { console.error("Error fetching symbol settings", e); }
  showSymbolModal.value = true;
};

const closeSymbolModal = () => {
  showSymbolModal.value = false;
};

const saveSymbolSettings = async () => {
  try {
    const res = await fetch(`${API_URL}/api/settings/symbol/${currentEditSymbol.value}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            confidence: parseFloat(tempSettings.value.confidence),
            risk_percent: parseFloat(tempSettings.value.risk_percent),
            atr_sl: parseFloat(tempSettings.value.atr_sl),
            rr_ratio: parseFloat(tempSettings.value.rr_ratio),
            break_even: parseFloat(tempSettings.value.break_even),
            auto_tune: tempSettings.value.auto_tune
        })
    });
    if(res.ok) {
        alert(`✅ อัปเดตการตั้งค่าระยะเอาตัวรอดสำหรับ ${currentEditSymbol.value} เรียบร้อย!`);
        closeSymbolModal(); 
    }
  } catch(e) {
      alert("❌ เกิดข้อผิดพลาดในการเชื่อมต่อกับเซิร์ฟเวอร์");
  }
};

// ==========================================
// 🚨 ปุ่มฉุกเฉินปิดทุกออเดอร์ (Panic Close)
// ==========================================
const panicCloseAll = async () => {
  // เด้งถามเพื่อความชัวร์ ป้องกันมือลั่น
  if (confirm("🚨 คำเตือนขั้นสูงสุด: คุณแน่ใจหรือไม่ที่จะ 'ปิดทิ้งทุกออเดอร์' ในพอร์ตตอนนี้เลย? (Panic Close)")) {
    try {
      const res = await fetch(`${API_URL}/api/trades/close_all`, { method: 'POST' });
      const data = await res.json();
      
      if (res.ok && data.status === "success") {
        alert(data.message);
        fetchTradeHistory(); // สั่งให้อัปเดตตารางประวัติทันที
      } else {
        alert("❌ " + (data.message || "เกิดข้อผิดพลาดในการปิดออเดอร์"));
      }
    } catch (error) {
      alert("❌ ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ได้");
    }
  }
};

// ==========================================
// ⚡ ระบบ WebSockets
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
    setTimeout(connectWebSocket, 3000);
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
  fetchSettings(); 
  connectWebSocket();
  setInterval(fetchTradeHistory, 10000); 
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

/* 🌟 Navbar Buttons */
.btn-start-nav { background: linear-gradient(180deg, #2ea043 0%, #238636 100%); color: white; border: none; padding: 6px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; letter-spacing: 0.5px;}
.btn-start-nav:hover { filter: brightness(1.2); box-shadow: 0 0 10px rgba(46,160,67,0.4); }
.btn-stop-nav { background: linear-gradient(180deg, #f85149 0%, #da3633 100%); color: white; border: none; padding: 6px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; letter-spacing: 0.5px;}
.btn-stop-nav:hover { filter: brightness(1.2); box-shadow: 0 0 10px rgba(248,81,73,0.4); }

/* 🚨 ปุ่ม Panic Close */
.btn-panic { background: #8b0000; color: white; border: 1px solid #ff4d4d; padding: 6px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; letter-spacing: 0.5px; animation: pulseRed 2s infinite; }
.btn-panic:hover { background: #ff4d4d; color: #000; animation: none; box-shadow: 0 0 15px rgba(255,77,77,0.8); }
@keyframes pulseRed { 
  0% { box-shadow: 0 0 0 0 rgba(248,81,73,0.5); } 
  70% { box-shadow: 0 0 0 10px rgba(248,81,73,0); } 
  100% { box-shadow: 0 0 0 0 rgba(248,81,73,0); } 
}

/* 🗂️ Cards & Grid */
.grid-layout { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 25px; }
.card { background: #161b22; padding: 25px; border-radius: 12px; border: 1px solid #30363d; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
.stats p { font-size: 1.1em; margin: 10px 0; color: #8b949e; }
.stats strong { color: #c9d1d9; font-size: 1.2em; }
.text-glow { text-shadow: 0 0 10px rgba(201,209,217,0.3); }
.profit strong { color: #3fb950; font-size: 1.4em; }
.profit.loss strong { color: #f85149; }

/* ⚙️ Global Settings Button */
.btn-global-settings { background: rgba(88,166,255,0.1); color: #58a6ff; border: 1px solid #58a6ff; padding: 8px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; font-size: 0.9em; box-shadow: 0 0 10px rgba(88,166,255,0.2); }
.btn-global-settings:hover { background: #58a6ff; color: #0d1117; }
.mini-tag { background: rgba(139,148,158,0.2); border: 1px solid #30363d; color: #c9d1d9; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; }

/* 👇 สไตล์กล่องควบคุม Settings */
.setting-group { margin-bottom: 20px; }
.confidence-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.confidence-title { color: #c9d1d9; font-weight: bold; font-size: 0.95em; }
.confidence-value { font-weight: bold; font-size: 1.1em; }
.text-green { color: #3fb950; text-shadow: 0 0 8px rgba(63,185,80,0.4); }
.text-purple { color: #d2a8ff; text-shadow: 0 0 8px rgba(210,168,255,0.4); }
.confidence-slider { width: 100%; cursor: pointer; accent-color: #3fb950; height: 6px; background: #21262d; border-radius: 3px; outline: none; }
.risk-slider { accent-color: #d2a8ff; }
.symbol-input { width: 100%; padding: 12px; background: #010409; border: 1px solid #30363d; color: #f0b37e; border-radius: 6px; font-weight: bold; font-size: 1em; box-sizing: border-box; outline: none; transition: 0.2s; }
.symbol-input:focus { border-color: #58a6ff; }

/* 🏷️ Style สำหรับ Symbol Tags */
.symbol-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 15px; }
.symbol-tag { background: rgba(88,166,255,0.15); color: #58a6ff; border: 1px solid #58a6ff; padding: 6px 12px; border-radius: 20px; font-size: 0.9em; font-weight: bold; display: flex; align-items: center; gap: 8px; box-shadow: 0 0 10px rgba(88,166,255,0.2); }
.btn-remove-sym { background: rgba(248,81,73,0.2); border: none; color: #f85149; cursor: pointer; font-size: 0.9em; padding: 2px 6px; border-radius: 50%; line-height: 1; outline: none; transition: 0.2s;}
.btn-remove-sym:hover { background: #f85149; color: white; }
.add-symbol-wrapper { display: flex; gap: 10px; }
.btn-add-sym { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 0 20px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.2s; white-space: nowrap;}
.btn-add-sym:hover { background: #58a6ff; color: #0d1117; border-color: #58a6ff; box-shadow: 0 0 10px rgba(88,166,255,0.4); }

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
.signal-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 15px; margin-bottom: 20px; }
.signal-box { background: #010409; border: 1px solid #30363d; border-radius: 8px; padding: 12px; }
.signal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.symbol-text { color: #f0b37e; font-size: 1.2em; font-weight: bold; }
.signal-badge { font-size: 0.75em; font-weight: bold; padding: 3px 6px; border-radius: 4px; text-transform: uppercase; }
.signal-badge.buy, .signal-badge.strong_buy { background: rgba(46,160,67,0.2); color: #3fb950; border: 1px solid #3fb950; }
.signal-badge.sell, .signal-badge.strong_sell { background: rgba(248,81,73,0.2); color: #f85149; border: 1px solid #f85149; }
.signal-badge.hold, .signal-badge.wait, .signal-badge.sleep { background: rgba(139,148,158,0.2); color: #8b949e; border: 1px solid #8b949e; }
.signal-bar-container { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: #21262d; margin-bottom: 8px; }
.signal-bar { transition: width 0.5s ease-in-out; }
.signal-bar.buy { background: #3fb950; }
.signal-bar.sell { background: #f85149; }
.signal-stats { display: flex; justify-content: space-between; font-size: 0.75em; font-weight: bold; }
.buy-text { color: #3fb950; }
.sell-text { color: #f85149; }

/* 🌟 Settings Icon in Radar */
.btn-icon-settings { background: transparent; border: none; font-size: 1.2em; cursor: pointer; transition: 0.3s; opacity: 0.7; padding: 0;}
.btn-icon-settings:hover { opacity: 1; transform: rotate(90deg); }

/* 🌟 Modal Styles */
.modal-overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.6); display: flex; justify-content: center; align-items: center; z-index: 1000; backdrop-filter: blur(4px); }
.modal-box { background: #161b22; padding: 25px; border-radius: 12px; border: 1px solid #30363d; width: 90%; max-width: 350px; box-shadow: 0 10px 40px rgba(0,0,0,0.8); animation: modalFadeIn 0.2s ease-out; }
@keyframes modalFadeIn { from { opacity: 0; transform: translateY(-20px); } to { opacity: 1; transform: translateY(0); } }
.modal-title { margin-top: 0; color: #c9d1d9; border-bottom: 1px solid #30363d; padding-bottom: 15px; margin-bottom: 20px; font-size: 1.3em; }
.modal-actions { display: flex; gap: 12px; margin-top: 30px; }
.btn-save { flex: 1; background: #238636; color: white; border: none; padding: 12px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; }
.btn-save:hover { filter: brightness(1.2); }
.btn-cancel { flex: 1; background: transparent; border: 1px solid #8b949e; color: #8b949e; padding: 12px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; }
.btn-cancel:hover { background: #30363d; color: white; }

/* Toggle Switch */
.switch { position: relative; display: inline-block; width: 50px; height: 26px; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #30363d; transition: .4s; border-radius: 34px; }
.slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }
input:checked + .slider { background-color: #58a6ff; }
input:checked + .slider:before { transform: translateX(24px); }

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