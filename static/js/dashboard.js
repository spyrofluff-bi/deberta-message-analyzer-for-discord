/**
 * DeBERTa-v3 Control Panel Controller
 * High-Efficiency, Lightweight JavaScript (Zero Dependencies, Zero Emojis)
 */

const state = {
  ws: null,
  guilds: [],
  selectedGuildId: null,
  messages: []
};

document.addEventListener('DOMContentLoaded', async () => {
  initWebSocket();
  await loadStatus();
  await loadGuilds();
  await loadRecentLogs();
  setupConfigForm();
  setupTester();
  setupSearchAndExport();
});

// WebSocket Live Stream Connection
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;
  const chipWs = document.getElementById('chip-ws');
  const dot = chipWs ? chipWs.querySelector('.indicator') : null;
  const txt = document.getElementById('txt-ws');

  try {
    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
      if (dot) dot.className = 'indicator';
      if (txt) txt.innerText = 'FEED: LIVE';
    };

    state.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'message_evaluated') {
          handleIncomingMessage(payload.data);
        } else if (payload.type === 'init') {
          updateSystemTelemetry(payload.engine, payload.queue);
        }
      } catch (err) {
        console.error("Payload parse error:", err);
      }
    };

    state.ws.onclose = () => {
      if (dot) dot.className = 'indicator risk';
      if (txt) txt.innerText = 'FEED: OFFLINE';
      setTimeout(initWebSocket, 3000);
    };

    state.ws.onerror = () => {
      state.ws.close();
    };
  } catch (err) {
    setTimeout(initWebSocket, 5000);
  }
}

// Handle Real-Time Stream Message
function handleIncomingMessage(msg) {
  state.messages.unshift(msg);
  if (state.messages.length > 200) state.messages.pop();

  renderStreamTable();
}

function renderStreamTable() {
  const tbody = document.getElementById('stream-tbody');
  if (!tbody) return;

  const searchVal = (document.getElementById('filter-input')?.value || '').toLowerCase();
  const flaggedOnly = document.getElementById('check-flagged-only')?.checked || false;

  const filtered = state.messages.filter(m => {
    const matchesText = (m.content || '').toLowerCase().includes(searchVal) || (m.author_name || '').toLowerCase().includes(searchVal);
    const matchesFlag = flaggedOnly ? m.flagged : true;
    return matchesText && matchesFlag;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2.5rem; color: var(--text-dim); font-family: var(--font-mono);">No messages matching current criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.slice(0, 50).map(m => {
    const isEvil = m.flagged;
    const evilPct = (m.evil_probability * 100).toFixed(1);
    const timeStr = m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour12: false }) : new Date(m.timestamp * 1000).toLocaleTimeString([], { hour12: false });

    return `
      <tr class="${isEvil ? 'flagged' : ''}">
        <td class="mono">${timeStr}</td>
        <td>
          <span class="badge ${isEvil ? 'flag' : 'pass'}">${isEvil ? 'FLAGGED' : 'PASS'}</span>
        </td>
        <td class="mono" style="font-weight: 700; color: ${isEvil ? '#fb7185' : '#34d399'};">${evilPct}%</td>
        <td><strong>${escapeHtml(m.author_name)}</strong></td>
        <td class="mono">#${escapeHtml(m.channel_name || 'DM')}</td>
        <td style="max-width: 380px; word-break: break-word;">${escapeHtml(m.content)}</td>
        <td class="mono">${m.latency_ms || 0}ms</td>
      </tr>
    `;
  }).join('');
}

// System Status Polling
async function loadStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    
    // Gateway status
    const chipGateway = document.getElementById('chip-gateway');
    const txtGateway = document.getElementById('txt-gateway');
    if (chipGateway && txtGateway) {
      const isOnline = data.bot && data.bot.online;
      const dot = chipGateway.querySelector('.indicator');
      if (dot) dot.className = `indicator ${isOnline ? '' : 'warn'}`;
      txtGateway.innerText = isOnline ? `GATEWAY: ${data.bot.username}` : 'GATEWAY: OFFLINE';
    }

    updateSystemTelemetry(data.engine, data.queue);
  } catch (err) {
    console.error("Status load error:", err);
  }
}

function updateSystemTelemetry(engine, queue) {
  if (engine) {
    const chipModel = document.getElementById('chip-model');
    const txtModel = document.getElementById('txt-model');
    if (chipModel && txtModel) {
      const isReady = engine.status === 'ready';
      const isFallback = engine.status === 'fallback';
      const dot = chipModel.querySelector('.indicator');
      if (dot) dot.className = `indicator ${isReady ? '' : (isFallback ? 'warn' : 'risk')}`;
      txtModel.innerText = isReady ? 'MODEL: READY' : (isFallback ? 'MODEL: FALLBACK' : 'MODEL: LOADING');
    }
  }

  if (queue) {
    const txtQueue = document.getElementById('txt-queue');
    if (txtQueue) txtQueue.innerText = queue.current_buffer_size || 0;
  }
}

// Guild Configuration
async function loadGuilds() {
  try {
    const res = await fetch('/api/guilds');
    const guilds = await res.json();
    state.guilds = guilds;

    const select = document.getElementById('select-guild');
    if (!select) return;

    select.innerHTML = '';
    if (guilds.length === 0) {
      select.innerHTML = '<option value="">No servers connected</option>';
      return;
    }

    guilds.forEach(g => {
      const opt = document.createElement('option');
      opt.value = g.guild_id;
      opt.innerText = g.guild_name || `Guild ${g.guild_id}`;
      select.appendChild(opt);
    });

    state.selectedGuildId = guilds[0].guild_id;
    populateGuildFields(guilds[0]);

    select.addEventListener('change', () => {
      state.selectedGuildId = parseInt(select.value, 10);
      const sel = guilds.find(g => g.guild_id === state.selectedGuildId);
      if (sel) populateGuildFields(sel);
    });
  } catch (err) {
    console.error("Guilds load error:", err);
  }
}

function populateGuildFields(guild) {
  const channelSelect = document.getElementById('select-channel');
  const slider = document.getElementById('input-threshold');
  const sliderTxt = document.getElementById('txt-threshold-val');
  const actionSelect = document.getElementById('select-action');

  if (channelSelect) {
    channelSelect.innerHTML = '<option value="">None (Logging Disabled)</option>';
    (guild.available_channels || []).forEach(ch => {
      const opt = document.createElement('option');
      opt.value = ch.id;
      opt.innerText = `#${ch.name}`;
      if (guild.log_channel_id && guild.log_channel_id === ch.id) opt.selected = true;
      channelSelect.appendChild(opt);
    });
  }

  const thresh = guild.threshold || 0.70;
  if (slider) {
    slider.value = Math.round(thresh * 100);
    slider.oninput = () => {
      if (sliderTxt) sliderTxt.innerText = `${slider.value}%`;
    };
  }
  if (sliderTxt) sliderTxt.innerText = `${Math.round(thresh * 100)}%`;
  if (actionSelect && guild.auto_action) actionSelect.value = guild.auto_action;
}

function setupConfigForm() {
  const btn = document.getElementById('btn-save-config');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    if (!state.selectedGuildId) {
      showToast("No server selected", true);
      return;
    }

    const slider = document.getElementById('input-threshold');
    const channelSelect = document.getElementById('select-channel');
    const actionSelect = document.getElementById('select-action');

    const payload = {
      guild_id: state.selectedGuildId,
      threshold: parseFloat(slider.value) / 100.0,
      log_channel_id: channelSelect.value ? parseInt(channelSelect.value, 10) : null,
      auto_action: actionSelect.value
    };

    btn.disabled = true;
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.status === 'success') {
        showToast("Configuration saved");
        await loadGuilds();
      } else {
        showToast("Error updating settings", true);
      }
    } catch (err) {
      showToast("Save error: " + err.message, true);
    } finally {
      btn.disabled = false;
    }
  });
}

// Inference Tester
function setupTester() {
  const btn = document.getElementById('btn-run-test');
  const input = document.getElementById('input-test-text');
  const latency = document.getElementById('txt-test-latency');
  const resultBox = document.getElementById('test-result-box');

  document.querySelectorAll('.preset-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if (input) input.value = chip.getAttribute('data-text');
    });
  });

  if (btn && input) {
    btn.addEventListener('click', async () => {
      const text = input.value.trim();
      if (!text) {
        showToast("Enter text to evaluate", true);
        return;
      }

      btn.disabled = true;
      btn.innerText = "Evaluating...";

      try {
        const res = await fetch('/api/test-analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        const data = await res.json();

        if (latency) latency.innerText = `LATENCY: ${data.latency_ms} MS`;

        if (resultBox) {
          const isEvil = data.evil_probability >= 0.70;
          const pct = (data.evil_probability * 100).toFixed(1);
          resultBox.style.display = 'block';
          resultBox.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <span class="badge ${isEvil ? 'flag' : 'pass'}">${isEvil ? 'VERDICT: FLAGGED' : 'VERDICT: PASS'}</span>
              <span class="mono" style="font-weight: 700; color: ${isEvil ? '#fb7185' : '#34d399'}; font-size: 0.78rem;">${pct}%</span>
            </div>
            <div class="solid-track">
              <div class="solid-fill ${isEvil ? 'flag' : ''}" style="width: ${pct}%;"></div>
            </div>
            <div style="margin-top: 4px; font-size: 0.68rem; font-family: var(--font-mono); color: var(--text-dim);">
              Top class: ${escapeHtml(data.top_label)}
            </div>
          `;
        }
      } catch (err) {
        showToast("Inference error: " + err.message, true);
      } finally {
        btn.disabled = false;
        btn.innerText = "Run Inference";
      }
    });
  }
}

// Load Recent Logs on Start
async function loadRecentLogs() {
  try {
    const res = await fetch('/api/logs?limit=40');
    const logs = await res.json();
    state.messages = logs;
    renderStreamTable();
  } catch (err) {
    console.error("Logs load error:", err);
  }
}

// Search & CSV Export
function setupSearchAndExport() {
  const filterInput = document.getElementById('filter-input');
  const checkFlagged = document.getElementById('check-flagged-only');
  const btnCsv = document.getElementById('btn-export-csv');

  if (filterInput) filterInput.addEventListener('input', renderStreamTable);
  if (checkFlagged) checkFlagged.addEventListener('change', renderStreamTable);

  if (btnCsv) {
    btnCsv.addEventListener('click', () => {
      if (state.messages.length === 0) {
        showToast("No data to export", true);
        return;
      }
      let csv = "ID,Timestamp,Author,Channel,Content,EvilProbability,TopLabel,Flagged,ActionTaken\n";
      state.messages.forEach(r => {
        const clean = `"${(r.content || '').replace(/"/g, '""')}"`;
        csv += `${r.id || ''},${r.created_at || ''},"${r.author_name || ''}","${r.channel_name || ''}",${clean},${r.evil_probability || 0},"${r.top_label || ''}",${r.flagged ? 1 : 0},"${r.action_taken || 'none'}"\n`;
      });
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `deberta_export_${Date.now()}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("CSV export ready");
    });
  }
}

function showToast(message, isError = false) {
  const existing = document.querySelector('.toast-box');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = `toast-box ${isError ? 'error' : ''}`;
  toast.innerText = message;
  document.body.appendChild(toast);

  setTimeout(() => toast.remove(), 2600);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
