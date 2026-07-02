const API = "";
let token = localStorage.getItem("tz_crm_token") || "";
let activeConv = null;
let pollTimer = null;

// ===== LOGIN =====
const loginScreen = document.getElementById("loginScreen");
const appScreen = document.getElementById("appScreen");

if(token) showApp(); else showLogin();

document.getElementById("loginForm").addEventListener("submit", async e => {
  e.preventDefault();
  const pwd = document.getElementById("loginPassword").value;
  const errEl = document.getElementById("loginError");
  errEl.textContent = "";
  try {
    const res = await apiFetch("/api/login", "POST", {password: pwd}, false);
    if(!res.ok) throw new Error("bad");
    const d = await res.json();
    token = d.token;
    localStorage.setItem("tz_crm_token", token);
    showApp();
  } catch { errEl.textContent = "Невірний пароль"; }
});

document.getElementById("logoutBtn").addEventListener("click", () => {
  localStorage.removeItem("tz_crm_token"); token = ""; showLogin();
});

function showApp(){
  loginScreen.hidden = true;
  appScreen.hidden = false;
  loadInbox();
  loadOrders();
  loadPublications();
  loadReports();
  checkAiStatus();
  startPolling();
  loadKanban();
}
function showLogin(){ appScreen.hidden = true; loginScreen.hidden = false; stopPolling(); }

async function apiFetch(path, method = "GET", body = null, auth = true){
  const headers = {"Content-Type": "application/json"};
  if(auth) headers["Authorization"] = "Bearer " + token;
  const opts = {method, headers};
  if(body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  if(res.status === 401){ localStorage.removeItem("tz_crm_token"); token = ""; showLogin(); }
  return res;
}

// ===== SIDEBAR NAV =====
const SECTION_LOADERS = {
  inbox: () => loadInbox(),
  orders: () => loadOrders(),
  publish: () => loadPublications(),
  reports: () => loadReports(),
  kanban: () => loadKanban(),
  settings: () => checkAiStatus(),
};

document.querySelectorAll(".nav-item[data-section]").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const sec = btn.dataset.section;
    document.querySelectorAll(".section").forEach(s => s.hidden = true);
    document.getElementById(sec + "Section").hidden = false;
    if(SECTION_LOADERS[sec]) SECTION_LOADERS[sec]();
  });
});

// ===== INBOX =====
const CH_LABELS = {telegram:"Telegram",viber:"Viber",whatsapp:"WhatsApp",instagram:"Instagram","website-chat":"Чат",phone:"Телефон"};
const STATUS_PILLS = {
  ai: '<span class="status-pill pill-ai">AI</span>',
  human: '<span class="status-pill pill-human">Людина</span>',
  sales: '<span class="status-pill pill-sales">Продажі</span>',
  done: '<span class="status-pill pill-done">Завершено</span>',
};

document.getElementById("refreshInbox").addEventListener("click", loadInbox);
document.getElementById("convStatusFilter").addEventListener("change", loadInbox);

async function loadInbox(){
  const filter = document.getElementById("convStatusFilter").value;
  const url = filter ? `/api/conversations?status=${filter}` : "/api/conversations";
  const res = await apiFetch(url);
  if(!res.ok) return;
  const convs = await res.json();
  renderConvList(convs);
  const unread = convs.filter(c => c.unread).length;
  const badge = document.getElementById("inboxBadge");
  badge.hidden = unread === 0;
  badge.textContent = unread;
}

function renderConvList(convs){
  const list = document.getElementById("convList");
  const empty = document.getElementById("convEmpty");
  if(!convs.length){ list.innerHTML = ""; empty.hidden = false; return; }
  empty.hidden = true;
  list.innerHTML = convs.map(c => {
    const isActive = activeConv && activeConv.channel === c.channel && activeConv.external_id === c.external_id;
    return `<li class="conv-item ${isActive?"active":""} ${c.unread?"unread":""}" data-ch="${c.channel}" data-eid="${esc(c.external_id)}">
      <div class="conv-item-top">
        <span class="conv-name">${esc(c.customer_name)||"Без імені"}</span>
        ${STATUS_PILLS[c.status]||""}
      </div>
      <p class="conv-preview">${esc(c.last_message)}</p>
      <div class="conv-meta">
        <span class="conv-time">${fmtTime(c.last_at)}</span>
        <span class="channel-pill-small">${CH_LABELS[c.channel]||c.channel}</span>
        ${c.quality_score ? `<span class="status-pill" style="background:#f3e5f5;color:#4a148c">★${c.quality_score}</span>` : ""}
      </div>
    </li>`;
  }).join("");
  list.querySelectorAll(".conv-item").forEach(el => {
    el.addEventListener("click", () => openConv(el.dataset.ch, el.dataset.eid));
  });
}

async function openConv(channel, external_id){
  activeConv = {channel, external_id};
  await loadThread();
  loadInbox();
}

async function loadThread(){
  if(!activeConv) return;
  const {channel, external_id} = activeConv;
  const [msgRes, stateRes] = await Promise.all([
    apiFetch(`/api/conversations/${channel}/${encodeURIComponent(external_id)}`),
    apiFetch(`/api/conversations/${channel}/${encodeURIComponent(external_id)}/state`),
  ]);
  if(!msgRes.ok) return;
  const messages = await msgRes.json();
  const state = stateRes.ok ? await stateRes.json() : {status:"ai", ai_enabled: true};
  renderThread(messages, state);
}

function renderThread(messages, state){
  const panel = document.getElementById("threadPanel");
  const lastIn = messages.filter(m => m.direction==="in").pop();
  const name = lastIn?.customer_name || "Клієнт";
  const aiIcon = state.ai_enabled ? "🤖 AI увімкнено" : "🤖 AI вимкнено";
  const aiClass = state.ai_enabled ? "ai-on" : "ai-off";

  panel.innerHTML = `
    <div class="thread-head">
      <span class="thread-customer">${esc(name)}</span>
      <div class="thread-actions">
        <span class="ai-toggle ${aiClass}" id="aiToggle" style="cursor:pointer" title="Натисніть щоб перемкнути AI">${aiIcon}</span>
        ${state.status !== "done" ? `
        <div class="escalation-btns">
          ${state.status !== "human" ? `<button class="esc-btn esc-human" onclick="escalate('human')">→ Людині</button>` : ""}
          ${state.status !== "sales" ? `<button class="esc-btn esc-sales" onclick="escalate('sales')">→ Продажі</button>` : ""}
          <button class="esc-btn esc-done" onclick="escalate('done')">✓ Завершити</button>
        </div>` : '<span class="status-pill pill-done">Завершено</span>'}
      </div>
    </div>
    <div class="thread-messages" id="threadMessages">
      ${messages.map(m => bubbleHtml(m)).join("")}
    </div>
    ${state.status !== "done" ? `
    <div class="reply-area">
      <textarea id="replyText" rows="2" placeholder="Ваша відповідь..." onkeydown="replyKeydown(event)"></textarea>
      <button class="btn btn-primary" onclick="sendReply()">Надіслати</button>
    </div>
    <p id="replyErr" class="error" style="padding:0 20px 12px"></p>` : ""}
  `;

  const msgs = document.getElementById("threadMessages");
  if(msgs) msgs.scrollTop = msgs.scrollHeight;

  document.getElementById("aiToggle")?.addEventListener("click", toggleAI);
}

function bubbleHtml(m){
  if(m.sender === "system") return `<div class="bubble bubble-out-system">${esc(m.body)}<span class="bubble-time">${fmtTime(m.created_at)}</span></div>`;
  const dirClass = m.direction === "in" ? "bubble-in" : (m.sender === "ai" ? "bubble-out-ai" : "bubble-out-human");
  const senderLabel = m.direction === "out" ? (m.sender === "ai" ? "AI оператор" : m.sender === "human" ? "Оператор" : "Бот") : "";
  return `<div class="bubble ${dirClass}">
    ${senderLabel ? `<div class="bubble-sender">${senderLabel}</div>` : ""}
    ${esc(m.body)}
    <span class="bubble-time">${fmtTime(m.created_at)}</span>
  </div>`;
}

function replyKeydown(e){ if(e.key === "Enter" && (e.ctrlKey || e.metaKey)) sendReply(); }

async function sendReply(){
  if(!activeConv) return;
  const textEl = document.getElementById("replyText");
  const errEl = document.getElementById("replyErr");
  const text = textEl?.value.trim();
  if(!text) return;
  errEl.textContent = "";
  const {channel, external_id} = activeConv;
  const res = await apiFetch(`/api/conversations/${channel}/${encodeURIComponent(external_id)}/reply`, "POST", {text});
  if(res.ok){ textEl.value = ""; await loadThread(); } else { errEl.textContent = "Помилка надсилання"; }
}

async function escalate(to){
  if(!activeConv) return;
  const {channel, external_id} = activeConv;
  await apiFetch(`/api/conversations/${channel}/${encodeURIComponent(external_id)}/escalate`, "POST", {to});
  await loadThread();
  loadInbox();
  if(to === "done") setTimeout(loadReports, 3000);
}

async function toggleAI(){
  if(!activeConv) return;
  const {channel, external_id} = activeConv;
  await apiFetch(`/api/conversations/${channel}/${encodeURIComponent(external_id)}/toggle-ai`, "POST", {});
  await loadThread();
}

// ===== ORDERS =====
const ORD_STATUS = {new:"Нова",confirmed:"Підтверджена",cooking:"Готується",delivering:"В дорозі",done:"Виконана",cancelled:"Скасована"};
document.getElementById("refreshOrders").addEventListener("click", loadOrders);
document.getElementById("filterStatus").addEventListener("change", loadOrders);

async function loadOrders(){
  const st = document.getElementById("filterStatus").value;
  const url = st ? `/api/orders?status=${st}` : "/api/orders";
  const res = await apiFetch(url);
  if(!res.ok) return;
  const orders = await res.json();
  const body = document.getElementById("ordersBody");
  const empty = document.getElementById("ordersEmpty");
  if(!orders.length){ body.innerHTML = ""; empty.hidden = false; return; }
  empty.hidden = true;
  body.innerHTML = orders.map(o => `<tr>
    <td>${o.id}</td><td>${esc(o.name)||"—"}</td><td>${esc(o.phone)||"—"}</td>
    <td>${esc(o.address)||"—"}</td>
    <td>${(o.items||[]).map(i=>`${esc(i.name)} ×${i.qty}`).join(", ")||"—"}</td>
    <td>${o.total} ₴</td><td>${fmtTime(o.created_at)}</td>
    <td><select class="status-select" data-id="${o.id}" onchange="changeOrderStatus(this)">
      ${Object.entries(ORD_STATUS).map(([v,l])=>`<option value="${v}" ${v===o.status?"selected":""}>${l}</option>`).join("")}
    </select></td>
  </tr>`).join("");
}

async function changeOrderStatus(sel){
  await apiFetch(`/api/orders/${sel.dataset.id}`, "PATCH", {status: sel.value});
}

// ===== PUBLISH =====
document.getElementById("publishBtn").addEventListener("click", async () => {
  const text = document.getElementById("pubText").value.trim();
  const image_url = document.getElementById("pubImage").value.trim() || null;
  const channels = [...document.querySelectorAll(".channel-checks input:checked")].map(c=>c.value);
  const statusEl = document.getElementById("pubStatus");
  statusEl.textContent = ""; statusEl.className = "form-status";
  if(!text){ statusEl.textContent = "Введіть текст"; statusEl.classList.add("err"); return; }
  if(!channels.length){ statusEl.textContent = "Оберіть хоча б один канал"; statusEl.classList.add("err"); return; }
  document.getElementById("publishBtn").disabled = true;
  const res = await apiFetch("/api/publications", "POST", {channels, text, image_url});
  document.getElementById("publishBtn").disabled = false;
  if(res.ok){
    const pub = await res.json();
    const allOk = Object.values(pub.results||{}).every(r=>r.ok);
    statusEl.textContent = allOk ? "Опубліковано!" : "Частково опубліковано (перевірте результати)";
    statusEl.classList.add(allOk ? "ok" : "err");
    document.getElementById("pubText").value = "";
    loadPublications();
  } else { statusEl.textContent = "Помилка публікації"; statusEl.classList.add("err"); }
});

async function loadPublications(){
  const res = await apiFetch("/api/publications");
  if(!res.ok) return;
  const pubs = await res.json();
  const list = document.getElementById("pubList");
  list.innerHTML = pubs.slice(0,10).map(p => {
    const allOk = Object.values(p.results||{}).every(r=>r.ok);
    return `<li class="pub-item">
      <div class="pub-item-top">
        <span>${p.channels.join(", ")}</span>
        <span class="${allOk?"pub-status-ok":"pub-status-partial"}">${allOk?"Опубліковано":"Частково"}</span>
      </div>
      <div style="font-size:13px;color:rgba(34,27,20,.7)">${esc(p.text.slice(0,80))}${p.text.length>80?"...":""}</div>
    </li>`;
  }).join("") || "<li style='font-size:13px;color:rgba(34,27,20,.5)'>Публікацій ще немає</li>";
}

// ===== REPORTS =====
document.getElementById("refreshReports").addEventListener("click", loadReports);

async function loadReports(){
  const res = await apiFetch("/api/reports/quality");
  if(!res.ok) return;
  const reports = await res.json();
  const container = document.getElementById("reportsList");
  const empty = document.getElementById("reportsEmpty");
  if(!reports.length){ container.innerHTML = ""; empty.hidden = false; return; }
  empty.hidden = true;
  container.innerHTML = reports.map(r => {
    const scoreClass = r.score >= 8 ? "score-hi" : r.score >= 5 ? "score-mid" : "score-lo";
    return `<div class="report-card">
      <div class="report-header">
        <div>
          <div style="font-size:15px;font-weight:700">${esc(r.customer_name)||"Невідомий клієнт"}</div>
          <div style="font-size:12px;opacity:.6">${CH_LABELS[r.channel]||r.channel} · ${r.external_id}</div>
        </div>
        <div class="${scoreClass} score-circle">${r.score}</div>
      </div>
      <div class="report-section"><strong>Висновок</strong>${esc(r.summary)}</div>
      ${r.strengths?.length ? `<div class="report-section"><strong>Сильні сторони</strong><ul>${r.strengths.map(s=>`<li>${esc(s)}</li>`).join("")}</ul></div>` : ""}
      ${r.improvements?.length ? `<div class="report-section"><strong>Покращення</strong><ul>${r.improvements.map(s=>`<li>${esc(s)}</li>`).join("")}</ul></div>` : ""}
      ${r.operator_feedback ? `<div class="report-section"><strong>Фідбек оператору</strong>${esc(r.operator_feedback)}</div>` : ""}
    </div>`;
  }).join("");
}

// ===== AI STATUS CHECK (через бекенд, не напряму до Anthropic) =====
async function checkAiStatus(){
  const badge = document.getElementById("aiStatusBadge");
  if(!badge) return;
  try {
    const res = await apiFetch("/api/ai-status");
    if(res.ok){
      const d = await res.json();
      badge.textContent = d.provider === "none" ? "Потрібен API ключ" : `${d.provider_label} активний`;
      badge.className = `channel-badge ${d.provider === "none" ? "pending" : "ok"}`;
    }
  } catch {
    badge.textContent = "Недоступно";
    badge.className = "channel-badge pending";
  }
}

// ===== POLLING =====
function startPolling(){
  stopPolling();
  pollTimer = setInterval(async () => {
    loadInbox();
    if(activeConv) loadThread();
    const sec = document.querySelector(".nav-item.active")?.dataset?.section;
    if(sec === "kanban") loadKanban();
  }, 8000);
}
function stopPolling(){ if(pollTimer) clearInterval(pollTimer); pollTimer = null; }

// ===== UTILS =====
function esc(str){ if(!str) return str; return String(str).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function fmtTime(iso){ try { return new Date(iso).toLocaleString("uk-UA",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}); } catch { return iso; } }

// ===== KANBAN =====
let draggedCard = null;

document.getElementById("refreshKanban").addEventListener("click", loadKanban);
document.getElementById("kanbanChannelFilter").addEventListener("change", loadKanban);

async function loadKanban(){
  const channel = document.getElementById("kanbanChannelFilter").value;
  const url = "/api/conversations";
  const res = await apiFetch(url);
  if(!res.ok) return;
  let convs = await res.json();

  if(channel) convs = convs.filter(c => c.channel === channel);

  const cols = {ai:[], human:[], sales:[], done:[]};
  for(const c of convs){
    const st = c.status || "ai";
    if(cols[st]) cols[st].push(c);
  }

  for(const [status, cards] of Object.entries(cols)){
    const col = document.getElementById("col-" + status);
    const cnt = document.getElementById("cnt-" + status);
    if(!col) continue;
    cnt.textContent = cards.length;
    col.innerHTML = cards.map(c => `
      <div class="kanban-card" draggable="true"
           data-ch="${c.channel}" data-eid="${esc(c.external_id)}"
           data-status="${status}">
        <div class="kanban-card-top">
          <span class="kanban-card-name">${esc(c.customer_name)||"Без імені"}</span>
          <div style="display:flex;gap:4px;align-items:center">
            ${c.unread ? '<span class="kanban-card-unread"></span>' : ''}
            <span class="channel-pill-small">${CH_LABELS[c.channel]||c.channel}</span>
          </div>
        </div>
        <p class="kanban-card-msg">${esc(c.last_message)}</p>
        <div class="kanban-card-footer">
          <span class="kanban-card-time">${fmtTime(c.last_at)}</span>
          ${c.quality_score ? `<span class="status-pill" style="background:#f3e5f5;color:#4a148c">★${c.quality_score}</span>` : ""}
        </div>
      </div>
    `).join("") || '<p style="font-size:12px;color:rgba(34,27,20,.4);text-align:center;padding:16px 0">Порожньо</p>';

    col.querySelectorAll(".kanban-card").forEach(card => {
      card.addEventListener("dragstart", e => { draggedCard = card; card.classList.add("dragging"); });
      card.addEventListener("dragend", e => { card.classList.remove("dragging"); draggedCard = null; });
      card.addEventListener("click", () => {
        // Відкриваємо розмову в інбоксі
        document.querySelector('[data-section="inbox"]').click();
        openConv(card.dataset.ch, card.dataset.eid);
      });
    });
  }
}

function onDragOver(e){ e.preventDefault(); e.currentTarget.classList.add("drag-over"); }

async function onDrop(e, newStatus){
  e.preventDefault();
  e.currentTarget.classList.remove("drag-over");
  if(!draggedCard) return;
  const ch = draggedCard.dataset.ch;
  const eid = draggedCard.dataset.eid;
  const oldStatus = draggedCard.dataset.status;
  if(oldStatus === newStatus) return;
  await apiFetch(`/api/conversations/${ch}/${encodeURIComponent(eid)}/escalate`, "POST", {to: newStatus});
  await loadKanban();
  if(newStatus === "done") setTimeout(loadReports, 3000);
}

// Прибираємо drag-over при виході
document.querySelectorAll(".kanban-cards").forEach(col => {
  col.addEventListener("dragleave", e => { if(!col.contains(e.relatedTarget)) col.classList.remove("drag-over"); });
});
