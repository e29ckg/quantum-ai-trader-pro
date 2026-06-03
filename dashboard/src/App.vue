<template>
  <div>
    <div v-if="!isAuthenticated" class="login-wrapper slide-fade">
      <div class="login-box glow-panel">
        <h2 class="title-glow pulse-slow">🧠 Quantum AI</h2>
        <p class="subtitle">Institutional Control Panel</p>
        <form @submit.prevent="handleLogin">
          <input v-model="loginForm.username" type="text" placeholder="Username (admin)" required />
          <input v-model="loginForm.password" type="password" placeholder="Password" required />
          <button type="submit" class="btn-login btn-hover-effect">ACCESS SYSTEM</button>
          <p v-if="loginError" class="error-msg">{{ loginError }}</p>
        </form>
      </div>
    </div>

    <div v-else class="dashboard-container slide-up">
      <header class="header glass-effect">
        <h1>🧠 Quantum AI <span class="version-tag">PRO V5</span></h1>
        
        <div class="nav-tabs">
            <button @click="currentView = 'dashboard'" :class="['tab-btn', { active: currentView === 'dashboard' }]">📈 COMMAND CENTER</button>
            <button @click="currentView = 'backtest'" :class="['tab-btn', { active: currentView === 'backtest' }]">🧪 QUANT LAB</button>
        </div>

        <div class="header-actions">
          <button @click="panicCloseAll" class="btn-panic" title="ปิดทุกออเดอร์ทันที!">🚨 PANIC CLOSE</button>
          <button v-if="!isRunning" @click="toggleBot('start')" class="btn-start-nav">🚀 START AI</button>
          <button v-else @click="toggleBot('stop')" class="btn-stop-nav pulse-slow">🛑 STOP AI</button>
          
          <span class="status-badge" :class="wsStatusClass">
            <span class="dot" :class="{ 'dot-blink': isConnected }"></span>
            {{ wsStatusText }} | {{ isRunning ? 'BOT ONLINE' : 'BOT OFFLINE' }}
          </span>
          <button @click="handleLogout" class="btn-logout">🚪 Logout</button>
        </div>
      </header>

      <div v-show="currentView === 'dashboard'" class="fade-in">
        
        <section class="mega-grid-top">
          
          <div class="card premium-card account-card hover-float">
            <h2 class="card-title">💳 Portfolio Status</h2>
            <div class="stats-container">
              <div class="stat-row">
                <span class="stat-label">Balance</span>
                <strong class="stat-value counter-animate">${{ formatMoney(account.balance) }}</strong>
              </div>
              <div class="stat-row">
                <span class="stat-label">Equity</span>
                <strong class="stat-value text-glow text-blue counter-animate">${{ formatMoney(account.equity) }}</strong>
              </div>
              <div class="stat-divider"></div>
              <div class="stat-row profit-row" :class="botData.profit_today >= 0 ? 'bg-profit' : 'bg-loss'">
                <span class="stat-label">Daily PnL</span>
                <strong class="stat-value" :class="botData.profit_today >= 0 ? 'text-profit' : 'text-loss'" style="font-size: 1.8em;">
                  {{ botData.profit_today >= 0 ? '+' : '' }}${{ formatMoney(botData.profit_today) }}
                </strong>
              </div>
            </div>
          </div>

          <div class="card premium-card chart-card hover-float">
            <div class="chart-header">
              <h2 class="card-title" style="margin:0; border:none;">📈 Live Equity Curve</h2>
              <span class="live-indicator"><span class="dot dot-blink"></span> Live Data</span>
            </div>
            <div id="equity-chart" style="min-height: 250px;"></div>
          </div>
        </section>

        <section class="mega-grid-middle" style="margin-top: 25px;">
          
          <div class="card premium-card master-card hover-float">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
              <h2 class="card-title" style="color: #fbbf24; margin: 0; border: none;">⚡ Master Switches</h2>
              <button @click="saveMasterConfig" class="btn-save-master">💾 SAVE</button>
            </div>
            <div class="toggles-grid">
              <div class="toggle-box">
                <span class="toggle-text">🌊 Endless Trailing</span>
                <label class="switch"><input type="checkbox" v-model="masterConfig.ENDLESS_TRAILING_MODE"><span class="slider round"></span></label>
              </div>
              <div class="toggle-box">
                <span class="toggle-text">⚡ Quick Scalp</span>
                <label class="switch"><input type="checkbox" v-model="masterConfig.QUICK_SCALP_MODE"><span class="slider round"></span></label>
              </div>
            </div>
            <div class="inputs-grid" style="margin-top: 15px;">
              <div class="input-group"><label>Quick Target ($)</label><input type="number" v-model.number="masterConfig.QUICK_PROFIT_TARGET" class="premium-input"></div>
              <div class="input-group"><label>Daily Target ($)</label><input type="number" v-model.number="masterConfig.DAILY_PROFIT_TARGET" class="premium-input text-profit"></div>
              <div class="input-group"><label>Daily Loss ($)</label><input type="number" v-model.number="masterConfig.DAILY_LOSS_LIMIT" class="premium-input text-loss"></div>
              <div class="input-group"><label>Max Loss/Trade ($)</label><input type="number" v-model.number="masterConfig.MAX_ALLOWED_LOSS_USD" class="premium-input text-warning"></div>
            </div>
          </div>

          <div class="card premium-card radar-card hover-float">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
               <h2 class="card-title" style="margin: 0; border: none;">🤖 AI Signal Radar</h2>
               <button @click="openGlobalSettingsModal" class="btn-global-settings pulse-hover">⚙️ GLOBAL SETTINGS</button>
            </div>
            <div class="signal-grid">
              <div v-for="(data, sym) in displaySignals" :key="sym" class="signal-box glass-panel">                
                <div class="signal-header">
                  <div style="display: flex; align-items: center; gap: 8px;">
                      <button @click="openSymbolSettingsModal(sym)" class="btn-icon-settings">⚙️</button>
                      <span class="symbol-text">{{ sym }}</span>
                  </div>
                  <span class="signal-badge" :class="(data.signal || 'offline').toLowerCase().split(' ')[0]">
                    {{ data.signal }}
                  </span>
                </div>
                
                <div class="signal-regime">{{ data.regime || 'WAITING FOR DATA...' }}</div>
                
                <div class="signal-bar-container">
                  <div class="signal-bar buy" :style="{ width: data.buy_prob + '%' }"></div>
                  <div class="signal-bar sell" :style="{ width: data.sell_prob + '%' }"></div>
                </div>
                
                <div class="signal-stats">
                  <span class="buy-text">B: {{ (data.buy_prob || 0).toFixed(1) }}%</span>
                  <span class="sell-text">S: {{ (data.sell_prob || 0).toFixed(1) }}%</span>
                </div>

                <div class="signal-indicators">
                  <span title="RSI">RSI: <strong :style="{ color: data.rsi > 50 ? '#10b981' : (data.rsi < 50 ? '#ef4444' : '#a1a1aa') }">{{ data.rsi !== undefined ? data.rsi.toFixed(1) : '--' }}</strong></span>
                  <span title="MACD">MACD: <strong :style="{ color: data.macd > 0 ? '#10b981' : (data.macd < 0 ? '#ef4444' : '#a1a1aa') }">{{ data.macd !== undefined ? data.macd.toFixed(2) : '--' }}</strong></span>
                  <span title="EMA">EMA: <strong style="color: #fbbf24;">{{ data.ema50 !== undefined ? data.ema50.toFixed(2) : '--' }}</strong></span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="card premium-card history-section hover-float" style="margin-top: 25px;">
          <div class="history-header">
            <h2 class="card-title" style="margin: 0; border: none;">📜 Live Trade History</h2>
            <button @click="fetchTradeHistory" class="btn-refresh">🔄 Refresh</button>
          </div>
          <div class="table-container">
            <table class="premium-table">
              <thead><tr><th>Ticket ID</th><th>Time</th><th>Symbol</th><th>Type</th><th>Entry Price</th><th>Status</th><th>Profit / Loss</th></tr></thead>
              <tbody>
                <tr v-if="tradeHistory.length === 0"><td colspan="7" class="text-center">Waiting for AI to execute trades...</td></tr>
                <tr v-for="trade in tradeHistory" :key="trade.ticket_id">
                  <td>#{{ trade.ticket_id }}</td><td class="time-col">{{ trade.timestamp }}</td><td class="font-bold">{{ trade.symbol }}</td>
                  <td><span :class="['badge-type', trade.type.toLowerCase()]">{{ trade.type.toUpperCase() }}</span></td>
                  <td>{{ Number(trade.entry_price).toFixed(5) }}</td>
                  <td><span :class="['badge-status', trade.status.toLowerCase()]">{{ trade.status }}</span></td>
                  <td :class="getProfitClass(trade.profit)"><strong>{{ formatProfit(trade.profit) }}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

      </div>

      <div v-show="currentView === 'backtest'" class="fade-in">
        
        <section class="card premium-card hover-float" style="margin-bottom: 25px;">
          <h2 class="card-title" style="color: #d2a8ff; border-color: #30363d;">
            🧪 Quant Research Laboratory
          </h2>
          <p style="color: #8b949e; font-size: 0.9em; margin-top: -10px; margin-bottom: 20px;">
            ระบบจำลองการเทรดด้วย AI (Backtest) ข้อมูลจะอ้างอิงจาก Master Switches ที่คุณเพิ่งบันทึกไป
          </p>

          <div class="backtest-controls">
            <div class="input-group">
              <label>💱 เลือกเหรียญ (Symbol)</label>
              <select v-model="btForm.symbol" class="premium-input select-styled">
                <option v-for="sym in activeSymbolList" :key="sym" :value="sym">{{ sym }}</option>
              </select>
            </div>
            <div class="input-group">
              <label>📊 จำนวนแท่งย้อนหลัง (M15)</label>
              <select v-model="btForm.bars" class="premium-input select-styled">
                <option value="1000">1,000 แท่ง (~10 วัน)</option>
                <option value="5000">5,000 แท่ง (~1.5 เดือน)</option>
                <option value="10000">10,000 แท่ง (~3 เดือน)</option>
              </select>
            </div>
            <button @click="runFullBacktest" :disabled="isBacktesting" class="btn-backtest-run">
              <span v-if="!isBacktesting">🚀 RUN SIMULATION</span>
              <span v-else class="pulse-slow">⏳ COMPUTING...</span>
            </button>
          </div>
        </section>

        <div v-if="btResult" class="mega-grid-results slide-up">
          <div class="card premium-card result-box" style="border-top: 4px solid #3fb950;">
            <h3>Net Profit</h3>
            <h1 :class="btResult.net_profit >= 0 ? 'text-profit' : 'text-loss'">
              {{ btResult.net_profit >= 0 ? '+' : '' }}${{ btResult.net_profit }}
            </h1>
            <p>Final Balance: <strong>${{ btResult.final_balance }}</strong></p>
          </div>

          <div class="card premium-card result-box" style="border-top: 4px solid #58a6ff;">
            <h3>Win Rate</h3>
            <h1 style="color: #58a6ff;">{{ btResult.win_rate }}%</h1>
            <p>ชนะ {{ btResult.win_trades }} | แพ้ {{ btResult.loss_trades }} | เสมอ {{ btResult.be_trades }}</p>
          </div>

          <div class="card premium-card result-box" style="border-top: 4px solid #f85149;">
            <h3>Max Drawdown</h3>
            <h1 style="color: #f85149;">{{ btResult.mdd }}%</h1>
            <p>ความเสี่ยงพอร์ตหดตัวสูงสุด</p>
          </div>

          <div v-if="btResult.config" class="card premium-card config-summary full-width">
            <h4 style="margin-top: 0; color: #8b949e; border-bottom: 1px solid #30363d; padding-bottom: 10px;">
              ⚙️ Parameters Used (สูตรที่ใช้ทดสอบ)
            </h4>
            <div class="config-badges">
              <span class="badge" :class="btResult.config.auto_tune ? 'active' : ''">
                🤖 Auto-Tune: {{ btResult.config.auto_tune ? 'ON (Dynamic)' : 'OFF (Manual)' }}
              </span>
              <span class="badge" :class="btResult.config.endless_trailing ? 'active-blue' : ''">
                🌊 Endless Trailing: {{ btResult.config.endless_trailing ? 'ON' : 'OFF' }}
              </span>
              <span class="badge" :class="btResult.config.quick_scalp ? 'active-purple' : ''">
                ⚡ Quick Scalp: {{ btResult.config.quick_scalp ? 'ON' : 'OFF' }}
              </span>
            </div>
          </div>
        </div>
        
        <div v-if="!btResult && !isBacktesting" class="waiting-box">
          🧪 กดปุ่ม RUN SIMULATION ด้านบนเพื่อเริ่มต้นสกัดข้อมูลและทดสอบสมองกล
        </div>
      </div>
      <div v-if="showSymbolModal" class="modal-overlay fade-in" @click.self="closeSymbolModal">
        <div class="modal-box glass-panel slide-up">
          <div class="modal-header">
            <h3 class="modal-title" style="margin: 0; border: none;">
              ⚙️ <span class="text-glow" style="color:#f0b37e;">{{ currentEditSymbol }}</span> Settings
            </h3>
            <button @click="closeSymbolModal" class="btn-close-modal">✕</button>
          </div>

          <div class="setting-group" style="margin-bottom: 20px;">
              <div class="confidence-header">
                  <span class="confidence-title">🧠 แหล่งกำเนิดสัญญาณ (Signal Source)</span>
              </div>
              <select v-model="tempSettings.signal_mode" class="premium-input text-blue" style="width: 100%; margin-top: 5px;">
                  <option value="ai">🤖 1. AI (XGBoost + SMC + โหวต)</option>
                  <option value="indicator">⚡ 2. M1 Fast Scalp (EMA Cross + RSI)</option>
                  <option value="x_sniper">🎯 3. M1 X-Sniper (ดักจุดกลับตัว X บน/ล่าง)</option>
              </select>
              <p style="font-size: 0.75em; color: #8b949e; margin-top: 5px;">* โหมด X-Sniper มีระบบ EMA 200 ป้องกันการรับมีด</p>
          </div>
          
          <div class="auto-tune-toggle-box">
             <div>
                <strong style="color: #58a6ff; font-size: 1.1em;">🤖 AI Auto-Tune</strong>
                <p style="margin: 5px 0 0 0; font-size: 0.8em; color: #8b949e;">ปรับเกียร์ตามสภาวะตลาดอัตโนมัติ</p>
             </div>
             <label class="switch">
                <input type="checkbox" v-model="tempSettings.auto_tune">
                <span class="slider round"></span>
             </label>
          </div>

          <div v-if="tempSettings.auto_tune" class="auto-tune-container slide-fade">
              <div class="mini-tabs">
                  <button @click="activeAutoTuneTab = 'trend'" :class="['mini-tab-btn', { active: activeAutoTuneTab === 'trend' }]">📈 Trend Rule</button>
                  <button @click="activeAutoTuneTab = 'volatility'" :class="['mini-tab-btn', { active: activeAutoTuneTab === 'volatility' }]">🌊 Volatility Rule</button>
              </div>

              <div v-if="activeAutoTuneTab === 'trend'" class="tab-content fade-in">
                  <p class="tab-desc text-blue">🎯 ปรับความแม่น (Conf) และเป้ากำไร (R:R)</p>
                  <div class="inputs-grid" style="margin-bottom: 10px;">
                      <div class="input-group"><label>Strong Trend Conf.</label><input type="number" v-model="tempSettings.at_trend_strong_conf" class="premium-input mini-input"></div>
                      <div class="input-group"><label>Strong Trend R:R</label><input type="number" step="0.1" v-model="tempSettings.at_trend_strong_rr" class="premium-input mini-input text-profit"></div>
                      <div class="input-group"><label>Weak/Sideway Conf.</label><input type="number" v-model="tempSettings.at_trend_weak_conf" class="premium-input mini-input"></div>
                      <div class="input-group"><label>Weak/Sideway R:R</label><input type="number" step="0.1" v-model="tempSettings.at_trend_weak_rr" class="premium-input mini-input text-warning"></div>
                  </div>
              </div>

              <div v-if="activeAutoTuneTab === 'volatility'" class="tab-content fade-in">
                  <p class="tab-desc text-loss">🛡️ ปรับระยะหลบภัย (SL) และบังหน้าทุน (BE)</p>
                  <div class="inputs-grid">
                      <div class="input-group"><label>High Vol. SL ATR</label><input type="number" step="0.1" v-model="tempSettings.at_vol_high_atr_sl" class="premium-input mini-input text-loss"></div>
                      <div class="input-group"><label>High Vol. Break-Even</label><input type="number" step="0.1" v-model="tempSettings.at_vol_high_be" class="premium-input mini-input text-blue"></div>
                      <div class="input-group"><label>Low Vol. SL ATR</label><input type="number" step="0.1" v-model="tempSettings.at_vol_low_atr_sl" class="premium-input mini-input text-warning"></div>
                      <div class="input-group"><label>Low Vol. Break-Even</label><input type="number" step="0.1" v-model="tempSettings.at_vol_low_be" class="premium-input mini-input text-blue"></div>
                  </div>
              </div>
          </div>

          <div v-show="!tempSettings.auto_tune" class="manual-settings-container slide-fade">
              <div class="setting-group">
                  <div class="confidence-header"><span class="confidence-title">🤖 Target Confidence</span><span class="confidence-value text-profit">{{ Number(tempSettings.confidence).toFixed(1) }}%</span></div>
                  <input type="range" min="30.0" max="80.0" step="0.5" v-model="tempSettings.confidence" class="premium-slider slider-green" />
              </div>
              <div class="setting-group">
                  <div class="confidence-header"><span class="confidence-title">💰 Risk Per Trade</span><span class="confidence-value text-purple">{{ tempSettings.risk_percent }}%</span></div>
                  <input type="range" min="0.1" max="5.0" step="0.1" v-model="tempSettings.risk_percent" class="premium-slider slider-purple" />
              </div>
              <div class="setting-group">
                  <div class="confidence-header"><span class="confidence-title">🛡️ SL ATR Distance</span><span class="confidence-value text-loss">x{{ Number(tempSettings.atr_sl).toFixed(1) }}</span></div>
                  <input type="range" min="0.1" max="5.0" step="0.1" v-model="tempSettings.atr_sl" class="premium-slider slider-red" />
              </div>
              <div class="setting-group">
                  <div class="confidence-header"><span class="confidence-title">🚀 Take Profit (R:R)</span><span class="confidence-value text-blue">1:{{ Number(tempSettings.rr_ratio).toFixed(1) }}</span></div>
                  <input type="range" min="0.5" max="5.0" step="0.1" v-model="tempSettings.rr_ratio" class="premium-slider slider-blue" />
              </div>
              <div class="setting-group">
                  <div class="confidence-header"><span class="confidence-title">🔒 Break-Even ATR</span><span class="confidence-value text-warning">x{{ Number(tempSettings.break_even).toFixed(1) }}</span></div>
                  <input type="range" min="0.5" max="3.0" step="0.1" v-model="tempSettings.break_even" class="premium-slider slider-orange" />
              </div>
          </div>
          
          <div class="setting-group" style="margin-top: 20px; border-top: 1px solid #30363d; padding-top: 15px;">
            <div class="setting-group" style="margin-top: 20px; border-top: 1px solid #30363d; padding-top: 15px;">
              <div class="auto-tune-toggle-box" style="background: rgba(210,168,255,0.05); border-color: rgba(210,168,255,0.2);">
                 <div>
                    <strong style="color: #d2a8ff; font-size: 1.1em;">🚑 Recovery Mode (แก้เกม)</strong>
                    <p style="margin: 5px 0 0 0; font-size: 0.8em; color: #8b949e;">เปิดไม้แก้/เบิ้ล Lot เมื่อผิดทาง (DCA)</p>
                 </div>
                 <label class="switch">
                    <input type="checkbox" v-model="tempSettings.recovery_mode">
                    <span class="slider round" style="background-color: #30363d;"></span>
                 </label>
              </div>
              
              <div class="setting-group" style="margin-top: 20px; border-top: 1px solid #30363d; padding-top: 15px;">
                <div class="confidence-header">
                    <span class="confidence-title">🛑 Risk Filters (ตัวกรองความเสี่ยง)</span>
                </div>
                <div class="inputs-grid" style="margin-top: 10px;">
                    <div class="input-group">
                        <label>Max Spread (Points)</label>
                        <input type="number" v-model="tempSettings.max_spread" class="premium-input text-loss" placeholder="เช่น 50" />
                        <p style="font-size: 0.7em; color: #8b949e; margin-top: 4px;">หยุดเทรดถ้าสเปรดถ่างเกินค่านี้</p>
                    </div>
                </div>
              </div>

              <div v-if="tempSettings.recovery_mode" class="inputs-grid slide-fade" style="margin-top: 10px;">
                  <div class="input-group">
                      <label>ระยะห่างไม้แก้ (ATR)</label>
                      <input type="number" step="0.1" v-model="tempSettings.recovery_step_atr" class="premium-input text-warning" />
                  </div>
                  <div class="input-group">
                      <label>ตัวคูณ Lot (Multiplier)</label>
                      <input type="number" step="0.1" v-model="tempSettings.recovery_lot_mult" class="premium-input text-purple" />
                  </div>
                  <div class="input-group" style="grid-column: 1 / -1;">
                      <label>จำกัดไม้แก้สูงสุด (Max Trades)</label>
                      <input type="number" v-model="tempSettings.max_recovery_trades" class="premium-input text-loss" />
                  </div>
              </div>
            </div>
            
            <div class="confidence-header">
                  <span class="confidence-title">⏱️ Trading Hours (เฉพาะเหรียญนี้)</span>
            </div>
            <div class="inputs-grid" style="margin-top: 10px;">
                <div class="input-group">
                    <label>Start Time</label>
                    <input type="time" v-model="tempSettings.trade_start_time" class="premium-input" />
                </div>
                <div class="input-group">
                    <label>End Time</label>
                    <input type="time" v-model="tempSettings.trade_end_time" class="premium-input" />
                </div>
            </div>
          </div>
          
          <div class="modal-actions">
            <button @click="saveSymbolSettings" class="btn-save-modal">💾 SAVE SETTINGS</button>
          </div>
        </div>
      </div>

      <div v-if="showGlobalModal" class="modal-overlay fade-in" @click.self="closeGlobalModal">
        <div class="modal-box glass-panel slide-up" style="max-width: 450px;">
          <div class="modal-header">
            <h3 class="modal-title" style="margin: 0; border: none; color: #58a6ff;">💱 Manage Active Symbols</h3>
            <button @click="closeGlobalModal" class="btn-close-modal">✕</button>
          </div>

          <p style="color: #8b949e; font-size: 0.9em; margin-top: 0; margin-bottom: 20px;">
            เพิ่มหรือลบเหรียญที่ต้องการให้ AI เฝ้าระวัง (ระบบจะเริ่มสแกนเหรียญใหม่ทันทีเมื่อกดบันทึก)
          </p>

          <div class="setting-group">
              <div class="symbol-tags">
                  <span v-for="(sym, index) in activeSymbolList" :key="index" class="symbol-tag">
                      {{ sym }} <button @click.prevent="removeSymbol(sym)" class="btn-remove-sym">✕</button>
                  </span>
                  <span v-if="activeSymbolList.length === 0" style="color: #8b949e; font-size: 0.9em;">(No active symbols)</span>
              </div>
              
              <div class="add-symbol-wrapper" style="margin-top: 20px; display: flex; gap: 10px;">
                  <input type="text" v-model="newSymbol" class="premium-input" placeholder="พิมพ์ชื่อเหรียญ เช่น ETHUSDm" @keyup.enter="addSymbol" style="flex: 1;" />
                  <button @click.prevent="addSymbol" class="btn-add-sym">➕ ADD</button>
              </div>
          </div>
          
          <div class="modal-actions" style="margin-top: 30px;">
            <button @click="handleSaveGlobalSettings" class="btn-save-modal" style="background: linear-gradient(180deg, #2ea043 0%, #238636 100%);">
              💾 APPLY TO SYSTEM
            </button>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import ApexCharts from 'apexcharts'; // 🌟 โหลดอาวุธลับสำหรับวาดกราฟ

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

// 🌟 ตัวแปรสำหรับจัดการกราฟ Equity
let equityChart = null;
const balanceHistory = ref([]); 

const formSettings = ref({
    confidence: 54.0,
    risk_percent: 1.0,
    symbols: "BTCUSDm,XAUUSDm",
    trade_start_time: "00:00",
    trade_end_time: "23:59"
});

const currentView = ref('dashboard');
const isBacktesting = ref(false);
const btForm = ref({ symbol: '', bars: 5000 });
const btResult = ref(null);

const newSymbol = ref('');
const showGlobalModal = ref(false);
const showSymbolModal = ref(false);
const currentEditSymbol = ref('');
const tempSettings = ref({ 
    // 🎛️ ตั้งค่าพื้นฐาน
    confidence: 54.0, risk_percent: 1.0, atr_sl: 2.0, rr_ratio: 2.0, break_even: 1.5, auto_tune: false,
    
    // 🤖 Auto-Tune
    at_trend_strong_conf: 60.0, at_trend_strong_rr: 2.0, at_trend_weak_conf: 65.0, at_trend_weak_rr: 1.2,
    at_vol_high_atr_sl: 3.0, at_vol_high_be: 2.5, at_vol_low_atr_sl: 2.0, at_vol_low_be: 1.5,
    
    // ⏱️ เวลาเทรด (รายเหรียญ)
    trade_start_time: "00:00", 
    trade_end_time: "23:59",
    
    signal_mode: "ai",

    // 🚑 โหมดแก้เกม (Recovery DCA)
    recovery_mode: false, 
    recovery_step_atr: 1.0, 
    recovery_lot_mult: 1.5, 
    max_recovery_trades: 3,

    // 🛑 ตัวกรองสเปรด
    max_spread: 50
});

// ==========================================
// ⚡ Master Switches Logic (โหมดเทพ)
// ==========================================
const masterConfig = ref({
    ENDLESS_TRAILING_MODE: true,
    QUICK_SCALP_MODE: false,
    QUICK_PROFIT_TARGET: 5.0,
    DAILY_PROFIT_TARGET: 50.0,
    DAILY_LOSS_LIMIT: -30.0,
    MAX_TOTAL_POSITIONS: 3,
    MAX_ALLOWED_LOSS_USD: 30.0
});

const fetchMasterConfig = async () => {
    try {
        const res = await fetch(`${API_URL}/api/master-settings`);
        if (res.ok) {
            const data = await res.json();
            masterConfig.value = data;
        }
    } catch (e) {
        console.error("Failed to load master settings", e);
    }
};

const saveMasterConfig = async () => {
    try {
        const res = await fetch(`${API_URL}/api/master-settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(masterConfig.value)
        });
        if (res.ok) {
            alert("✅ บันทึก Master Settings สำเร็จ! สมองกลรับทราบคำสั่งแล้ว!");
        } else {
            alert("❌ บันทึกข้อมูลไม่สำเร็จ");
        }
    } catch (e) {
        alert("❌ ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ได้");
    }
};

const activeAutoTuneTab = ref('trend');

const activeSymbolList = computed(() => {
  if (!formSettings.value.symbols) return [];
  return formSettings.value.symbols.split(',').map(s => s.trim()).filter(s => s);
});

const wsStatusText = computed(() => isConnected.value ? '⚡ WS CONNECTED' : '🔌 WS DISCONNECTED');
const wsStatusClass = computed(() => isConnected.value ? 'ws-connected' : 'ws-disconnected');

const displaySignals = computed(() => {
    const result = {};
    activeSymbolList.value.forEach(sym => {
        result[sym] = { signal: 'OFFLINE 💤', buy_prob: 0, sell_prob: 0 };
    });
    if (botData.value && botData.value.live_signals) {
        Object.keys(botData.value.live_signals).forEach(sym => {
            if (result[sym]) {
                result[sym] = botData.value.live_signals[sym];
            }
        });
    }
    return result;
});

watch(activeSymbolList, (newList) => {
    if (newList && newList.length > 0 && !newList.includes(btForm.value.symbol)) {
        btForm.value.symbol = newList[0];
    }
});

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

const runFullBacktest = async () => {
    if (!btForm.value.symbol) return alert("กรุณาเลือกเหรียญก่อน!");
    isBacktesting.value = true;
    btResult.value = null; 
    
    try {
        const res = await fetch(`${API_URL}/api/backtest/${btForm.value.symbol}?bars=${btForm.value.bars}`);
        const data = await res.json();
        
        if (res.ok && data.status === "success") {
            btResult.value = data;
        } else {
            alert("❌ สรุปผล Backtest ล้มเหลว: " + (data.message || "เกิดข้อผิดพลาด"));
        }
    } catch (error) {
        alert("❌ เกิดข้อผิดพลาดในการเชื่อมต่อกับเซิร์ฟเวอร์");
    } finally {
        isBacktesting.value = false;
    }
};

const panicCloseAll = async () => {
  if (confirm("🚨 คำเตือนขั้นสูงสุด: คุณแน่ใจหรือไม่ที่จะ 'ปิดทิ้งทุกออเดอร์' ในพอร์ตตอนนี้เลย? (Panic Close)")) {
    try {
      const res = await fetch(`${API_URL}/api/trades/close_all`, { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.status === "success") {
        alert(data.message);
        fetchTradeHistory(); 
      } else {
        alert("❌ " + (data.message || "เกิดข้อผิดพลาดในการปิดออเดอร์"));
      }
    } catch (error) {
      alert("❌ ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ได้");
    }
  }
};

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
  if (equityChart) equityChart.destroy();
};

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

const openGlobalSettingsModal = () => {
    fetchSettings(); 
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
            if(!btForm.value.symbol && activeSymbolList.value.length > 0) {
                btForm.value.symbol = activeSymbolList.value[0];
            }
        }
    } catch (error) { console.error("Failed to fetch settings:", error); }
};

const handleSaveGlobalSettings = async () => {
    try {
        // 🌟 ส่งค่าทั้งหมดกลับไปให้ API เหมือนเดิม เพื่อไม่ให้ฝั่ง Database พัง 
        // แต่บนหน้าเว็บเราปรับแค่ symbols อย่างเดียว
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
            alert(`✅ อัปเดตรายชื่อเหรียญ Active Symbols เรียบร้อยแล้ว!`);
            closeGlobalModal(); 
        } else {
            alert("❌ บันทึกข้อมูลไม่สำเร็จ");
        }
    } catch (error) {
        console.error("Error updating settings:", error);
    }
};

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
           auto_tune: data.auto_tune || false,
           at_trend_strong_conf: data.at_trend_strong_conf || 60.0,
           at_trend_strong_rr: data.at_trend_strong_rr || 2.0,
           at_trend_weak_conf: data.at_trend_weak_conf || 65.0,
           at_trend_weak_rr: data.at_trend_weak_rr || 1.2,
           at_vol_high_atr_sl: data.at_vol_high_atr_sl || 3.0,
           at_vol_high_be: data.at_vol_high_be || 2.5,
           at_vol_low_atr_sl: data.at_vol_low_atr_sl || 2.0,
           at_vol_low_be: data.at_vol_low_be || 1.5,
           trade_start_time: data.trade_start_time || "00:00",
           trade_end_time: data.trade_end_time || "23:59",
           signal_mode: data.signal_mode || "ai",
           // 🚑 โหมดแก้เกม
           recovery_mode: data.recovery_mode || false,
           recovery_step_atr: data.recovery_step_atr || 1.0,
           recovery_lot_mult: data.recovery_lot_mult || 1.5,
           max_recovery_trades: data.max_recovery_trades || 3,
           // 🛑 ตัวกรองสเปรด
           max_spread: data.max_spread || 50
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
        body: JSON.stringify(tempSettings.value)
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
// 📈 ระบบกราฟ ApexCharts (Live Equity)
// ==========================================
const initApexChart = () => {
    if (equityChart) return; 
    const options = {
        series: [{ name: 'Balance', data: [] }],
        chart: { 
            type: 'area', height: 280, background: 'transparent', 
            toolbar: { show: false }, 
            animations: { enabled: true, easing: 'linear', dynamicAnimation: { speed: 1000 } } 
        },
        colors: ['#58a6ff'],
        fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.05, stops: [0, 100] } },
        dataLabels: { enabled: false },
        stroke: { curve: 'smooth', width: 3 },
        xaxis: { type: 'datetime', labels: { style: { colors: '#8b949e' } }, axisBorder: { show: false }, axisTicks: { show: false } },
        yaxis: { labels: { style: { colors: '#8b949e' }, formatter: (value) => { return "$" + value.toFixed(2) } } },
        grid: { borderColor: '#30363d', strokeDashArray: 4, yaxis: { lines: { show: true } } },
        theme: { mode: 'dark' }
    };
    
    const chartElement = document.querySelector("#equity-chart");
    if (chartElement) {
        equityChart = new ApexCharts(chartElement, options);
        equityChart.render();
    }
};

const updateChartData = () => {
    if (!equityChart || account.value.balance === 0) return;
    const now = new Date().getTime();
    balanceHistory.value.push([now, account.value.balance]);
    
    // เก็บประวัติแค่ 50 จุดล่าสุดให้กราฟวิ่งสวยๆ ไม่กินแรม
    if (balanceHistory.value.length > 50) balanceHistory.value.shift(); 
    equityChart.updateSeries([{ data: balanceHistory.value }]);
};

// ==========================================
// 🔌 WebSocket & App Init
// ==========================================
const connectWebSocket = () => {
  ws.value = new WebSocket(WS_URL);
  ws.value.onopen = () => { isConnected.value = true; };
  ws.value.onmessage = (event) => {
    const data = JSON.parse(event.data);
    isRunning.value = data.bot.is_running;
    botData.value = data.bot;
    account.value = data.account;
    
    // 🌟 ให้กราฟอัปเดตทุกครั้งที่ข้อมูลใหม่มา
    updateChartData(); 
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

// เปลี่ยนเป็น async เพื่อใช้ nextTick รอให้ HTML วาดเสร็จก่อนแปะกราฟ
const initDashboard = async () => {
  fetchTradeHistory();
  fetchSettings();
  fetchMasterConfig(); 
  connectWebSocket();
  setInterval(fetchTradeHistory, 10000); 

  await nextTick();
  if (currentView.value === 'dashboard') initApexChart();
};

// 🌟 สลับแท็บแล้ววาดกราฟใหม่
watch(currentView, async (newView) => {
    if (newView === 'dashboard') {
        await nextTick();
        initApexChart();
    }
});

onMounted(() => {
  if (isAuthenticated.value) {
    initDashboard();
  }
});

onUnmounted(() => {
  if (ws.value) ws.value.close();
  if (equityChart) equityChart.destroy(); // ล้างกราฟคืน Memory
});
</script>

<style scoped>
/* ==========================================
   🌐 1. Base & Global Styles (สไตล์พื้นฐาน)
   ========================================== */
:global(html), :global(body), :global(#app) { 
  margin: 0; padding: 0; width: 100%; min-height: 100vh;
  background-color: #010409; /* พื้นหลังเข้มสุด สไตล์ Terminal */
  color: #c9d1d9; 
  font-family: 'Segoe UI', system-ui, sans-serif; 
  overflow-x: hidden; 
}

/* ==========================================
   🌀 2. Animations & Effects (แอนิเมชัน)
   ========================================== */
.slide-fade { animation: slideFade 0.5s cubic-bezier(0.16, 1, 0.3, 1); }
.slide-up { animation: slideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1); }
.fade-in { animation: fadeIn 0.4s ease-in-out; }
.pulse-slow { animation: pulseGlow 3s infinite; }
.pulse-hover:hover { animation: pulseGlow 1.5s infinite; }
.hover-float { transition: transform 0.3s ease, box-shadow 0.3s ease; }
.hover-float:hover { transform: translateY(-4px); box-shadow: 0 12px 30px rgba(0,0,0,0.6); z-index: 10; }

@keyframes slideFade { 
  from { opacity: 0; transform: translateY(-20px) scale(0.98); } 
  to { opacity: 1; transform: translateY(0) scale(1); } 
}
@keyframes slideUp { 
  from { opacity: 0; transform: translateY(30px); } 
  to { opacity: 1; transform: translateY(0); } 
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes pulseGlow { 
  0% { text-shadow: 0 0 10px rgba(88,166,255,0.4); box-shadow: 0 0 10px rgba(88,166,255,0.2); } 
  50% { text-shadow: 0 0 25px rgba(88,166,255,0.8); box-shadow: 0 0 20px rgba(88,166,255,0.4); } 
  100% { text-shadow: 0 0 10px rgba(88,166,255,0.4); box-shadow: 0 0 10px rgba(88,166,255,0.2); } 
}

/* ==========================================
   🔒 3. Login Screen (หน้าล็อกอิน)
   ========================================== */
.login-wrapper { display: flex; justify-content: center; align-items: center; height: 100vh; padding: 20px; box-sizing: border-box; }
.login-box { background: #161b22; padding: 40px; border-radius: 12px; border: 1px solid #30363d; text-align: center; width: 100%; max-width: 380px; box-shadow: 0 8px 32px rgba(0,0,0,0.6); box-sizing: border-box; }
.title-glow { color: #58a6ff; margin-bottom: 5px; font-size: 2em; }
.subtitle { color: #8b949e; margin-bottom: 30px; font-size: 0.9em; letter-spacing: 1px; }
.login-box input { width: 100%; padding: 14px; margin-bottom: 15px; border-radius: 6px; border: 1px solid #30363d; background: #010409; color: white; box-sizing: border-box; outline: none; transition: 0.3s; font-size: 1em; }
.login-box input:focus { border-color: #58a6ff; box-shadow: 0 0 8px rgba(88,166,255,0.3); }
.btn-login { width: 100%; padding: 14px; background: linear-gradient(180deg, #2ea043 0%, #238636 100%); color: white; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; letter-spacing: 1px; }
.btn-login:hover { filter: brightness(1.2); }
.error-msg { color: #f85149; margin-top: 15px; font-size: 0.9em; font-weight: bold; }

/* ==========================================
   🏢 4. Main Layout & Header (โครงสร้างหลัก)
   ========================================== */
.dashboard-container { padding: 20px 40px; max-width: 1600px; margin: 0 auto; box-sizing: border-box; }
.glass-effect { background: rgba(1, 4, 9, 0.85); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(255,255,255,0.05); position: sticky; top: 0; z-index: 100; padding: 15px 30px; margin: -20px -40px 30px -40px; display: flex; justify-content: space-between; align-items: center; }

.header h1 { margin: 0; font-size: 1.5em; display: flex; align-items: center; gap: 10px; }
.version-tag { font-size: 0.5em; background: #e34c26; padding: 3px 6px; border-radius: 4px; color: white; font-weight: bold; letter-spacing: 1px; }

.nav-tabs { display: flex; gap: 10px; margin-left: 30px; flex: 1; }
.tab-btn { background: transparent; color: #8b949e; border: none; padding: 8px 15px; font-weight: bold; font-size: 1em; cursor: pointer; transition: 0.2s; border-bottom: 3px solid transparent; letter-spacing: 0.5px;}
.tab-btn:hover { color: #c9d1d9; }
.tab-btn.active { color: #58a6ff; border-bottom-color: #58a6ff; text-shadow: 0 0 10px rgba(88,166,255,0.5); }

.header-actions { display: flex; align-items: center; gap: 15px; }
.btn-start-nav { background: linear-gradient(180deg, #2ea043 0%, #238636 100%); color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; box-shadow: 0 4px 10px rgba(46,160,67,0.3); }
.btn-start-nav:hover { filter: brightness(1.2); }
.btn-stop-nav { background: linear-gradient(180deg, #f85149 0%, #da3633 100%); color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; box-shadow: 0 4px 10px rgba(248,81,73,0.3); }
.btn-stop-nav:hover { filter: brightness(1.2); }
.btn-panic { background: transparent; color: #f85149; border: 1px solid #f85149; padding: 8px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; }
.btn-panic:hover { background: rgba(248,81,73,0.1); box-shadow: 0 0 15px rgba(248,81,73,0.4); }

.status-badge { padding: 6px 12px; border-radius: 6px; font-size: 0.85em; font-weight: bold; display: flex; align-items: center; }
.ws-connected { border: 1px solid #30363d; color: #c9d1d9; background: #161b22; }
.ws-disconnected { border: 1px solid #f85149; color: #f85149; background: rgba(248,81,73,0.1); }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #8b949e; margin-right: 8px; }
.dot-blink { background: #3fb950; box-shadow: 0 0 8px #3fb950; animation: blink 1.5s infinite; }
@keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }

.btn-logout { background: transparent; color: #8b949e; border: none; padding: 8px; cursor: pointer; transition: 0.2s; font-weight: bold; }
.btn-logout:hover { color: #f85149; }

/* ==========================================
   📐 5. Grids & Premium Cards (การ์ดและเลย์เอาต์)
   ========================================== */
.mega-grid-top { display: grid; grid-template-columns: 350px 1fr; gap: 25px; align-items: stretch; }
.mega-grid-middle { display: grid; grid-template-columns: 350px 1fr; gap: 25px; align-items: stretch; }

.premium-card { background: #0d1117; border: 1px solid #30363d; border-radius: 16px; padding: 25px; box-shadow: 0 4px 20px rgba(0,0,0,0.4); display: flex; flex-direction: column; }
.card-title { color: #8b949e; font-size: 1.1em; text-transform: uppercase; letter-spacing: 1px; margin-top: 0; margin-bottom: 20px; border-bottom: 1px solid #21262d; padding-bottom: 12px; }

/* ==========================================
   💳 6. Account Stats (ตัวเลขพอร์ต)
   ========================================== */
.account-card .stats-container { flex-grow: 1; display: flex; flex-direction: column; justify-content: space-evenly; gap: 15px; }
.stat-row { display: flex; justify-content: space-between; align-items: center; }
.stat-label { color: #8b949e; font-size: 1.1em; }
.stat-value { font-size: 1.8em; font-weight: bold; color: #f0f6fc; }
.stat-divider { height: 1px; background: #21262d; margin: 5px 0; }
.text-blue { color: #58a6ff !important; text-shadow: 0 0 15px rgba(88,166,255,0.4); }
.text-profit { color: #3fb950 !important; }
.text-loss { color: #f85149 !important; }
.bg-profit { background: rgba(46,160,67,0.05); border: 1px solid rgba(46,160,67,0.2); padding: 15px; border-radius: 8px; }
.bg-loss { background: rgba(248,81,73,0.05); border: 1px solid rgba(248,81,73,0.2); padding: 15px; border-radius: 8px; }

/* ==========================================
   📈 7. Chart Area (กราฟ)
   ========================================== */
.chart-card { justify-content: flex-start; }
.chart-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #21262d; padding-bottom: 12px; margin-bottom: 15px;}
.live-indicator { color: #3fb950; font-size: 0.85em; font-weight: bold; background: rgba(46,160,67,0.1); padding: 4px 12px; border-radius: 20px; border: 1px solid rgba(46,160,67,0.2); display: flex; align-items: center; }

/* ==========================================
   ⚡ 8. Master Switches (สวิตช์ควบคุมโหมด)
   ========================================== */
.btn-save-master { background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%); color: white; border: none; padding: 6px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; box-shadow: 0 4px 10px rgba(59,130,246,0.3); }
.btn-save-master:hover { filter: brightness(1.2); transform: translateY(-1px); }

.toggles-grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-bottom: 15px; }
.toggle-box { background: #161b22; border: 1px solid #30363d; padding: 12px 15px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; }
.toggle-text { font-weight: bold; color: #c9d1d9; font-size: 0.9em; }

/* Toggle Switch Design */
.switch { position: relative; display: inline-block; width: 44px; height: 24px; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #30363d; transition: .3s; border-radius: 24px; }
.slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%; }
input:checked + .slider { background-color: #58a6ff; box-shadow: 0 0 8px rgba(88,166,255,0.5); }
input:checked + .slider:before { transform: translateX(20px); }

.inputs-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.input-group label { display: block; font-size: 0.75rem; color: #8b949e; margin-bottom: 6px; }
.premium-input { width: 100%; padding: 10px; background: #010409; border: 1px solid #30363d; color: white; border-radius: 6px; font-weight: bold; box-sizing: border-box; outline: none; transition: 0.2s; }
.premium-input:focus { border-color: #58a6ff; }
.text-warning { color: #f97316 !important; }

/* ==========================================
   🤖 9. AI Signal Radar (การ์ดเรดาร์เหรียญ)
   ========================================== */
.btn-global-settings { background: rgba(88,166,255,0.1); color: #58a6ff; border: 1px solid rgba(88,166,255,0.3); padding: 6px 12px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; font-size: 0.85em; }
.btn-global-settings:hover { background: #58a6ff; color: #010409; }

.signal-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 15px; }
.glass-panel { background: linear-gradient(145deg, #161b22, #0d1117); border: 1px solid #30363d; border-radius: 12px; padding: 18px; display: flex; flex-direction: column; gap: 12px; transition: 0.3s; }
.glass-panel:hover { border-color: #58a6ff; box-shadow: 0 4px 15px rgba(88,166,255,0.1); }

.signal-header { display: flex; justify-content: space-between; align-items: center; }
.btn-icon-settings { background: transparent; border: none; font-size: 1.2em; cursor: pointer; opacity: 0.6; transition: 0.3s; padding: 0; }
.btn-icon-settings:hover { opacity: 1; transform: rotate(90deg); }
.symbol-text { color: #f0b37e; font-size: 1.2em; font-weight: bold; letter-spacing: 0.5px; }

.signal-badge { font-size: 0.75em; font-weight: bold; padding: 4px 8px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.signal-badge.buy, .signal-badge.strong_buy { background: rgba(46,160,67,0.2); color: #3fb950; border: 1px solid #3fb950; }
.signal-badge.sell, .signal-badge.strong_sell { background: rgba(248,81,73,0.2); color: #f85149; border: 1px solid #f85149; }
.signal-badge.hold, .signal-badge.wait, .signal-badge.offline { background: rgba(139,148,158,0.2); color: #8b949e; border: 1px solid #8b949e; }

.signal-regime { background: rgba(210,168,255,0.1); color: #d2a8ff; font-size: 0.75em; font-weight: bold; padding: 6px; border-radius: 6px; text-align: center; border: 1px dashed rgba(210,168,255,0.3); }

.signal-bar-container { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: #21262d; margin-top: 4px; }
.signal-bar { transition: width 0.5s ease-in-out; }
.signal-bar.buy { background: linear-gradient(90deg, #2ea043, #3fb950); }
.signal-bar.sell { background: linear-gradient(90deg, #da3633, #f85149); }
.signal-stats { display: flex; justify-content: space-between; font-size: 0.85em; font-weight: bold; }
.buy-text { color: #3fb950; }
.sell-text { color: #f85149; }

.signal-indicators { margin-top: auto; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.05); font-size: 0.8em; display: flex; justify-content: space-between; color: #8b949e; }

/* ==========================================
   📜 10. History Table (ตารางประวัติ)
   ========================================== */
.history-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #21262d; padding-bottom: 12px; margin-bottom: 15px; }
.btn-refresh { background: #161b22; border: 1px solid #30363d; color: #c9d1d9; padding: 6px 12px; border-radius: 6px; cursor: pointer; transition: 0.2s; font-size: 0.9em; }
.btn-refresh:hover { background: #30363d; color: white; }

.table-container { overflow-x: auto; } 
.premium-table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9em; min-width: 800px; }
.premium-table th { background: #010409; padding: 12px 15px; color: #8b949e; border-bottom: 2px solid #30363d; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; font-size: 0.8em; }
.premium-table td { padding: 12px 15px; border-bottom: 1px solid #21262d; white-space: nowrap; color: #c9d1d9; }
.premium-table tbody tr:hover { background: #161b22; }
.time-col { color: #8b949e; font-size: 0.9em; }
.font-bold { font-weight: bold; color: #e6edf3; }

.badge-type { padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }
.badge-type.buy { background: rgba(46, 160, 67, 0.15); color: #3fb950; }
.badge-type.sell { background: rgba(248, 81, 73, 0.15); color: #f85149; }
.badge-status { padding: 4px 8px; border-radius: 4px; font-size: 0.8em; border: 1px solid; }
.badge-status.open { border-color: #d2a8ff; color: #d2a8ff; }
.badge-status.closed { border-color: #8b949e; color: #8b949e; }
.text-center { text-align: center; color: #8b949e; padding: 30px !important; }

/* ==========================================
   📱 11. Responsive Design (รองรับจอมือถือ/แท็บเล็ต)
   ========================================== */
@media (max-width: 1100px) {
  .mega-grid-top, .mega-grid-middle { grid-template-columns: 1fr; }
  .account-card .stats-container { gap: 20px; }
  .toggles-grid { grid-template-columns: 1fr 1fr; }
}

/* ==========================================
   🧪 12. Quant Lab (Backtest Styles)
   ========================================== */
.backtest-controls {
  display: flex;
  gap: 20px;
  align-items: flex-end;
  flex-wrap: wrap;
}
.backtest-controls .input-group { flex: 1; min-width: 200px; }
.select-styled { cursor: pointer; appearance: auto; background-color: #0d1117; }

.btn-backtest-run {
  padding: 12px 25px;
  background: linear-gradient(180deg, #8957e5 0%, #6b3fb8 100%);
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: bold;
  font-size: 1.1em;
  cursor: pointer;
  transition: 0.2s;
  box-shadow: 0 4px 15px rgba(137,87,229,0.3);
  min-width: 250px;
  height: 48px;
}
.btn-backtest-run:hover:not(:disabled) { filter: brightness(1.2); transform: translateY(-2px); box-shadow: 0 6px 20px rgba(137,87,229,0.5); }
.btn-backtest-run:disabled { background: #21262d; color: #8b949e; cursor: not-allowed; box-shadow: none; border: 1px solid #30363d; }

.mega-grid-results {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 25px;
}
.result-box { text-align: center; justify-content: center; }
.result-box h3 { color: #8b949e; margin-top: 0; margin-bottom: 10px; font-size: 1.1em; text-transform: uppercase; }
.result-box h1 { font-size: 3em; margin: 5px 0 15px 0; text-shadow: 0 0 20px rgba(255,255,255,0.1); }
.result-box p { color: #8b949e; margin: 0; }

.config-summary { padding: 20px; background: rgba(1, 4, 9, 0.5); }
.config-badges { display: flex; gap: 10px; flex-wrap: wrap; }
.badge { background: #161b22; border: 1px solid #30363d; color: #8b949e; padding: 8px 15px; border-radius: 8px; font-weight: bold; font-size: 0.9em; }
.badge.active { color: #3fb950; border-color: #3fb950; background: rgba(46,160,67,0.1); }
.badge.active-blue { color: #58a6ff; border-color: #58a6ff; background: rgba(88,166,255,0.1); }
.badge.active-purple { color: #d2a8ff; border-color: #d2a8ff; background: rgba(210,168,255,0.1); }

.waiting-box {
  text-align: center; color: #8b949e; padding: 60px 20px; 
  border: 2px dashed #30363d; border-radius: 12px; 
  margin-top: 25px; font-size: 1.1em;
  background: rgba(22, 27, 34, 0.3);
}

/* ==========================================
   🎛️ 13. Modal & Sliders (หน้าต่างตั้งค่า)
   ========================================== */
.modal-overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.7); display: flex; justify-content: center; align-items: center; z-index: 1000; backdrop-filter: blur(5px); }
.modal-box { width: 90%; max-width: 400px; max-height: 85vh; overflow-y: auto; padding: 25px; display: flex; flex-direction: column; gap: 15px; }

/* Custom Scrollbar for Modal */
.modal-box::-webkit-scrollbar { width: 6px; }
.modal-box::-webkit-scrollbar-track { background: transparent; }
.modal-box::-webkit-scrollbar-thumb { background: #30363d; border-radius: 10px; }
.modal-box::-webkit-scrollbar-thumb:hover { background: #58a6ff; }

.modal-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 15px; margin-bottom: 5px; }
.btn-close-modal { background: transparent; border: none; color: #8b949e; font-size: 1.5em; cursor: pointer; transition: 0.2s; padding: 0; line-height: 1; }
.btn-close-modal:hover { color: #f85149; transform: rotate(90deg); }

.auto-tune-toggle-box { background: rgba(88,166,255,0.05); border: 1px solid rgba(88,166,255,0.2); padding: 15px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }

.mini-tabs { display: flex; background: #010409; border-radius: 8px; border: 1px solid #30363d; overflow: hidden; margin-bottom: 15px; }
.mini-tab-btn { flex: 1; padding: 10px; background: transparent; border: none; color: #8b949e; font-size: 0.85em; font-weight: bold; cursor: pointer; transition: 0.2s; }
.mini-tab-btn:hover { color: #c9d1d9; background: rgba(255,255,255,0.05); }
.mini-tab-btn.active { background: rgba(88,166,255,0.15); color: #58a6ff; }
.tab-desc { font-size: 0.8em; margin-top: 0; margin-bottom: 15px; text-align: center; font-weight: bold; }

/* 🌟 Premium Sliders */
.setting-group { margin-bottom: 20px; }
.confidence-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.confidence-title { color: #c9d1d9; font-weight: bold; font-size: 0.9em; }
.confidence-value { font-weight: bold; font-size: 1.1em; }

.premium-slider { -webkit-appearance: none; width: 100%; height: 6px; border-radius: 3px; background: #21262d; outline: none; opacity: 0.9; transition: opacity .2s; cursor: pointer; }
.premium-slider:hover { opacity: 1; }
.premium-slider::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 18px; height: 18px; border-radius: 50%; cursor: pointer; box-shadow: 0 0 10px rgba(0,0,0,0.5); border: 2px solid white; }
.slider-green::-webkit-slider-thumb { background: #3fb950; }
.slider-purple::-webkit-slider-thumb { background: #d2a8ff; }
.slider-red::-webkit-slider-thumb { background: #f85149; }
.slider-blue::-webkit-slider-thumb { background: #58a6ff; }
.slider-orange::-webkit-slider-thumb { background: #f0b37e; }

/* 🌟 Symbol Tags Manager */
.symbol-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.symbol-tag { background: rgba(88,166,255,0.1); color: #58a6ff; border: 1px solid rgba(88,166,255,0.3); padding: 6px 12px; border-radius: 20px; font-size: 0.9em; font-weight: bold; display: flex; align-items: center; gap: 8px; }
.btn-remove-sym { background: rgba(248,81,73,0.2); border: none; color: #f85149; cursor: pointer; font-size: 0.9em; padding: 2px 6px; border-radius: 50%; transition: 0.2s; line-height: 1; }
.btn-remove-sym:hover { background: #f85149; color: white; }
.btn-add-sym { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 0 20px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.2s; white-space: nowrap; }
.btn-add-sym:hover { background: #58a6ff; color: #010409; border-color: #58a6ff; }

/* Actions */
.modal-actions { display: flex; margin-top: 10px; }
.btn-save-modal { width: 100%; background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%); color: white; border: none; padding: 14px; border-radius: 8px; font-weight: bold; font-size: 1.05em; cursor: pointer; transition: 0.2s; box-shadow: 0 4px 15px rgba(59,130,246,0.4); letter-spacing: 1px; }
.btn-save-modal:hover { filter: brightness(1.2); transform: translateY(-2px); }

@media (max-width: 768px) {
  .backtest-controls { flex-direction: column; align-items: stretch; }
  .btn-backtest-run { width: 100%; }
}

@media (max-width: 768px) {
  .dashboard-container { padding: 15px; } 
  .glass-effect { flex-direction: column; align-items: flex-start; gap: 15px; padding: 15px; margin: -15px -15px 20px -15px; }
  .header h1 { font-size: 1.3em; }
  .nav-tabs { margin-left: 0; width: 100%; justify-content: flex-start; overflow-x: auto; padding-bottom: 5px; }
  .header-actions { width: 100%; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
  .btn-start-nav, .btn-stop-nav, .btn-panic { flex: 1; text-align: center; }
  .toggles-grid, .inputs-grid { grid-template-columns: 1fr; }
  .premium-card { padding: 15px; }
}

</style>