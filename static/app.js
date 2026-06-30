const API_BASE = "";

let token = localStorage.getItem("tz_crm_token") || "";
let activeConversation = null; // { channel, external_id }
let inboxPollTimer = null;

const loginScreen = document.getElementById("loginScreen");
const appScreen = document.getElementById("appScreen");

function showApp(){
  loginScreen.hidden = true;
  appScreen.hidden = false;
  loadOrders();
  loadConversations();
  startInboxPolling();
}
function showLogin(){
  appScreen.hidden = true;
  loginScreen.hidden = false;
  stopInboxPolling();
}

if(token){ showApp(); } else { showLogin(); }

document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const password = document.getElementById("loginPassword").value;
  const errorEl = document.getElementById("loginError");
  errorEl.textContent = "";
  try{
    const res = await fetch(`${API_BASE}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password })
    });
    if(!res.ok) throw new Error("bad credentials");
    const data = await res.json();
    token = data.token;
    localStorage.setItem("tz_crm_token", token);
    showApp();
  } catch(err){
    errorEl.textContent = "Невірний пароль";
  }
});

document.getElementById("logoutBtn").addEventListener("click", () => {
  localStorage.removeItem("tz_crm_token");
  token = "";
  showLogin();
});

function authHeaders(){
  return { "Authorization": `Bearer ${token}` };
}
async function handleAuthError(res){
  if(res.status === 401){
    localStorage.removeItem("tz_crm_token");
    token = "";
    showLogin();
    return true;
  }
  return false;
}

/* ===== Вкладки ===== */
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.getElementById("ordersTab").hidden = tab !== "orders";
    document.getElementById("inboxTab").hidden = tab !== "inbox";
  });
});

/* ===== Заявки ===== */
const STATUS_LABELS = {
  new: "Нова", confirmed: "Підтверджена", cooking: "Готується",
  delivering: "В дорозі", done: "Виконана", cancelled: "Скасована"
};
const SOURCE_LABELS = {
  website: "Сайт", telegram: "Telegram", viber: "Viber",
  whatsapp: "WhatsApp", instagram: "Instagram", phone: "Телефонія",
  "website-chat": "Чат на сайті"
};

document.getElementById("refreshOrdersBtn").addEventListener("click", loadOrders);
document.getElementById("filterSource").addEventListener("change", loadOrders);
document.getElementById("filterStatus").addEventListener("change", loadOrders);

async function loadOrders(){
  const source = document.getElementById("filterSource").value;
  const status = document.getElementById("filterStatus").value;
  const params = new URLSearchParams();
  if(source) params.set("source", source);
  if(status) params.set("status", status);

  const res = await fetch(`${API_BASE}/api/orders?${params}`, { headers: authHeaders() });
  if(await handleAuthError(res)) return;
  const orders = await res.json();
  renderOrders(orders);
}

function renderOrders(orders){
  const body = document.getElementById("ordersBody");
  const emptyState = document.getElementById("ordersEmptyState");

  if(orders.length === 0){
    body.innerHTML = "";
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;

  body.innerHTML = orders.map(o => `
    <tr>
      <td>${o.id}</td>
      <td>${SOURCE_LABELS[o.source] || o.source}</td>
      <td>${escapeHtml(o.name) || "—"}</td>
      <td>${escapeHtml(o.phone) || "—"}</td>
      <td>${escapeHtml(o.address) || "—"}</td>
      <td>${formatItems(o.items)}</td>
      <td>${o.total} ₴</td>
      <td>${new Date(o.created_at).toLocaleString("uk-UA")}</td>
      <td>
        <select data-order-id="${o.id}" class="status-select">
          ${Object.entries(STATUS_LABELS).map(([val, label]) =>
            `<option value="${val}" ${val === o.status ? "selected" : ""}>${label}</option>`
          ).join("")}
        </select>
      </td>
    </tr>
  `).join("");

  document.querySelectorAll(".status-select").forEach(sel => {
    sel.addEventListener("change", async (e) => {
      const id = e.target.dataset.orderId;
      await fetch(`${API_BASE}/api/orders/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ status: e.target.value })
      });
    });
  });
}

function formatItems(items){
  if(!items || items.length === 0) return "—";
  return items.map(i => `${escapeHtml(i.name)} ×${i.qty}`).join(", ");
}

/* ===== Повідомлення (інбокс) ===== */
document.getElementById("refreshInboxBtn").addEventListener("click", loadConversations);

async function loadConversations(){
  const res = await fetch(`${API_BASE}/api/conversations`, { headers: authHeaders() });
  if(await handleAuthError(res)) return;
  const conversations = await res.json();
  renderConversationList(conversations);
  updateUnreadBadge(conversations);
}

function updateUnreadBadge(conversations){
  const count = conversations.filter(c => c.unread).length;
  const badge = document.getElementById("unreadBadge");
  if(count > 0){
    badge.hidden = false;
    badge.textContent = count;
  } else {
    badge.hidden = true;
  }
}

function renderConversationList(conversations){
  const list = document.getElementById("conversationItems");
  const emptyState = document.getElementById("inboxEmptyState");

  if(conversations.length === 0){
    list.innerHTML = "";
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;

  list.innerHTML = conversations.map(c => {
    const isActive = activeConversation && activeConversation.channel === c.channel && activeConversation.external_id === c.external_id;
    return `
      <li class="conversation-item ${isActive ? "active" : ""} ${c.unread ? "unread" : ""}"
          data-channel="${c.channel}" data-external-id="${escapeAttr(c.external_id)}">
        <div class="conversation-item-top">
          <span class="conversation-name">${escapeHtml(c.customer_name) || "Без імені"}</span>
          <span class="conversation-channel-tag">${SOURCE_LABELS[c.channel] || c.channel}</span>
        </div>
        <p class="conversation-preview">${escapeHtml(c.last_message)}</p>
        <span class="conversation-time">${new Date(c.last_at).toLocaleString("uk-UA")}</span>
      </li>
    `;
  }).join("");

  document.querySelectorAll(".conversation-item").forEach(item => {
    item.addEventListener("click", () => {
      openConversation(item.dataset.channel, item.dataset.externalId);
    });
  });
}

async function openConversation(channel, externalId){
  activeConversation = { channel, external_id: externalId };
  document.querySelectorAll(".conversation-item").forEach(item => {
    item.classList.toggle("active", item.dataset.channel === channel && item.dataset.externalId === externalId);
  });
  await loadThread();
}

async function loadThread(){
  if(!activeConversation) return;
  const { channel, external_id } = activeConversation;
  const res = await fetch(`${API_BASE}/api/conversations/${channel}/${encodeURIComponent(external_id)}`, { headers: authHeaders() });
  if(await handleAuthError(res)) return;
  if(!res.ok) return;
  const messages = await res.json();
  renderThread(messages);
}

function renderThread(messages){
  const panel = document.getElementById("threadPanel");
  const channelLabel = activeConversation ? (SOURCE_LABELS[activeConversation.channel] || activeConversation.channel) : "";
  const customerName = messages.length ? messages[messages.length - 1].customer_name : "";

  panel.innerHTML = `
    <div class="thread-head">
      <strong>${escapeHtml(customerName) || "Без імені"}</strong>
      <span class="conversation-channel-tag">${channelLabel}</span>
    </div>
    <div class="thread-messages" id="threadMessages">
      ${messages.map(m => `
        <div class="thread-bubble ${m.direction === "out" ? "thread-bubble-out" : "thread-bubble-in"}">
          ${escapeHtml(m.body)}
          <span class="thread-bubble-time">${new Date(m.created_at).toLocaleTimeString("uk-UA", {hour: "2-digit", minute: "2-digit"})}</span>
        </div>
      `).join("")}
    </div>
    <form id="replyForm" class="reply-form">
      <textarea id="replyText" rows="2" placeholder="Напишіть відповідь..." required></textarea>
      <button type="submit" class="btn btn-primary">Надіслати</button>
    </form>
    <p id="replyStatus" class="error"></p>
  `;

  const threadMessages = document.getElementById("threadMessages");
  threadMessages.scrollTop = threadMessages.scrollHeight;

  document.getElementById("replyForm").addEventListener("submit", sendReply);
}

async function sendReply(e){
  e.preventDefault();
  if(!activeConversation) return;
  const textEl = document.getElementById("replyText");
  const text = textEl.value.trim();
  if(!text) return;

  const statusEl = document.getElementById("replyStatus");
  statusEl.textContent = "";
  const submitBtn = e.target.querySelector("button[type=submit]");
  submitBtn.disabled = true;

  try{
    const { channel, external_id } = activeConversation;
    const res = await fetch(`${API_BASE}/api/conversations/${channel}/${encodeURIComponent(external_id)}/reply`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ text })
    });
    if(!res.ok){
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    textEl.value = "";
    await loadThread();
    await loadConversations();
  } catch(err){
    statusEl.textContent = "Не вдалось надіслати: " + err.message;
  } finally {
    submitBtn.disabled = false;
  }
}

function startInboxPolling(){
  stopInboxPolling();
  inboxPollTimer = setInterval(() => {
    loadConversations();
    if(activeConversation) loadThread();
  }, 8000);
}
function stopInboxPolling(){
  if(inboxPollTimer) clearInterval(inboxPollTimer);
  inboxPollTimer = null;
}

/* ===== Допоміжне ===== */
function escapeHtml(str){
  if(!str) return str;
  return String(str).replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
}
function escapeAttr(str){
  return escapeHtml(str);
}
