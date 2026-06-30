// Панель і API живуть на одному сервісі/домені, тому базовий шлях порожній
const API_BASE = "";

let token = localStorage.getItem("tz_crm_token") || "";

const loginScreen = document.getElementById("loginScreen");
const appScreen = document.getElementById("appScreen");

function showApp(){
  loginScreen.hidden = true;
  appScreen.hidden = false;
  loadOrders();
}
function showLogin(){
  appScreen.hidden = true;
  loginScreen.hidden = false;
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

document.getElementById("refreshBtn").addEventListener("click", loadOrders);
document.getElementById("filterSource").addEventListener("change", loadOrders);
document.getElementById("filterStatus").addEventListener("change", loadOrders);

const STATUS_LABELS = {
  new: "Нова",
  confirmed: "Підтверджена",
  cooking: "Готується",
  delivering: "В дорозі",
  done: "Виконана",
  cancelled: "Скасована"
};
const SOURCE_LABELS = {
  website: "Сайт",
  telegram: "Telegram",
  viber: "Viber",
  whatsapp: "WhatsApp",
  instagram: "Instagram",
  phone: "Телефонія"
};

async function loadOrders(){
  const source = document.getElementById("filterSource").value;
  const status = document.getElementById("filterStatus").value;
  const params = new URLSearchParams();
  if(source) params.set("source", source);
  if(status) params.set("status", status);

  const res = await fetch(`${API_BASE}/api/orders?${params}`, {
    headers: { "Authorization": `Bearer ${token}` }
  });

  if(res.status === 401){
    localStorage.removeItem("tz_crm_token");
    token = "";
    showLogin();
    return;
  }

  const orders = await res.json();
  renderOrders(orders);
}

function renderOrders(orders){
  const body = document.getElementById("ordersBody");
  const emptyState = document.getElementById("emptyState");

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
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ status: e.target.value })
      });
    });
  });
}

function formatItems(items){
  if(!items || items.length === 0) return "—";
  return items.map(i => `${escapeHtml(i.name)} ×${i.qty}`).join(", ");
}

function escapeHtml(str){
  if(!str) return str;
  return str.replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
}
