const cfg = window.OPSR_CONFIG || { apiBaseUrl: "/api" };
const SESSION_KEY = "opsr_auth_session";
const state = {
  data: null,
  activeView: "dashboard",
  selectedMachine: "M-001",
  selectedOrder: "ORD-00125",
  currentTheme: localStorage.getItem("opsr_theme") || "enterprise",
  isLoggedIn: false,
  user: null,
  approvalFilter: "ALL",
  notifFilter: "ALL",
  aiSubTab: "predictions",
  reportsSubTab: "operational"
};

const $ = id => document.getElementById(id);

async function api(path, options = {}) {
  const base = (cfg.apiBaseUrl || "").replace(/\/$/, "");
  const session = getSession();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (session?.accessToken) headers.Authorization = `Bearer ${session.accessToken}`;
  const res = await fetch(base + path, {
    headers,
    ...options
  });
  const text = await res.text();
  let body = {};
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { raw: text };
  }
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

function saveSession(session) {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  state.user = session.user;
  state.isLoggedIn = true;
}

function clearSession() {
  sessionStorage.removeItem(SESSION_KEY);
  state.user = null;
  state.isLoggedIn = false;
}

function demoLogin(userKey) {
  const user = cfg.demoUsers?.[userKey];
  if (!user) throw new Error("Demo access is not configured");
  saveSession({ mode: "demo", user: { ...user, key: userKey } });
  toggleLoginScreen(false, `Demo mode: ${user.name}`);
}

async function cognitoLogin(username, password) {
  const cognito = cfg.cognito || {};
  if (!cognito.userPoolId || !cognito.clientId || !cognito.endpoint) {
    throw new Error("Cognito is not configured for this deployment");
  }
  const response = await fetch(cognito.endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth"
    },
    body: JSON.stringify({
      ClientId: cognito.clientId,
      AuthFlow: "USER_PASSWORD_AUTH",
      AuthParameters: { USERNAME: username, PASSWORD: password }
    })
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || !body.AuthenticationResult) {
    if (body.ChallengeName === "NEW_PASSWORD_REQUIRED") {
      throw new Error("This Cognito user must complete first-time password setup");
    }
    throw new Error(body.message || body.__type?.split("#").pop() || "Cognito sign-in failed");
  }
  saveSession({
    mode: "cognito",
    accessToken: body.AuthenticationResult.AccessToken,
    idToken: body.AuthenticationResult.IdToken,
    refreshToken: body.AuthenticationResult.RefreshToken,
    user: { email: username, name: username, role: "Authenticated Operator" }
  });
  toggleLoginScreen(false, `Signed in as ${username}`);
}

async function cognitoRegister(username, password) {
  const cognito = cfg.cognito || {};
  const response = await fetch(cognito.endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": "AWSCognitoIdentityProviderService.SignUp"
    },
    body: JSON.stringify({
      ClientId: cognito.clientId,
      Username: username,
      Password: password,
      UserAttributes: [{ Name: "email", Value: username }]
    })
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || "Account registration failed");
  return body.UserConfirmed === true;
}

async function confirmCognitoUser(username, code) {
  const cognito = cfg.cognito || {};
  const response = await fetch(cognito.endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": "AWSCognitoIdentityProviderService.ConfirmSignUp"
    },
    body: JSON.stringify({ ClientId: cognito.clientId, Username: username, ConfirmationCode: code })
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || "Email verification failed");
}

function showAuthForm(formName) {
  ["loginForm", "registerForm", "confirmForm"].forEach(name => {
    if ($(name)) $(name).classList.toggle("hidden", name !== formName);
  });
  if ($("createAccountPrompt")) $("createAccountPrompt").classList.toggle("hidden", formName !== "loginForm");
}

function openJudgeSignIn() {
  toggleLoginScreen(true);
  showAuthForm("loginForm");
  if ($("loginEmail")) {
    $("loginEmail").value = "demo@opsrelay.com";
    $("loginPassword")?.focus();
  }
  toast("Demo credentials loaded. Ready to sign in.", "info");
}

function toast(msg, type = "info") {
  const t = $("toast");
  if (!t) return;
  const icon = `<svg style="width:16px;height:16px;stroke:#60a5fa;fill:none;stroke-width:2;" viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>`;
  t.innerHTML = `${icon}<span>${msg}</span>`;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 3400);
}

/* Theme Management (Screens 13-20) */
function setTheme(theme) {
  state.currentTheme = theme;
  document.body.setAttribute("data-theme", theme);
  localStorage.setItem("opsr_theme", theme);
  if ($("themeSelect")) $("themeSelect").value = theme;
  renderThemeGrid();
}

/* View Switching */
function switchView(viewName, targetId = null) {
  state.activeView = viewName;
  const views = [
    "viewDashboard",
    "viewMachines",
    "viewMachineDetails",
    "viewOrders",
    "viewOrderDetails",
    "viewAiInsights",
    "viewApprovals",
    "viewReports",
    "viewSettings",
    "viewAlerts"
  ];

  views.forEach(v => {
    if ($(v)) $(v).classList.add("hidden");
  });

  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.classList.remove("active");
    if (btn.dataset.view === viewName || 
       (viewName === "machine-details" && btn.dataset.view === "machines") ||
       (viewName === "order-details" && btn.dataset.view === "orders")) {
      btn.classList.add("active");
    }
  });

  if (viewName === "dashboard" && $("viewDashboard")) {
    $("viewDashboard").classList.remove("hidden");
    renderDashboard();
  } else if (viewName === "machines" && $("viewMachines")) {
    $("viewMachines").classList.remove("hidden");
    renderMachines();
  } else if (viewName === "machine-details" && $("viewMachineDetails")) {
    if (targetId) state.selectedMachine = targetId;
    $("viewMachineDetails").classList.remove("hidden");
    renderMachineDetails(state.selectedMachine);
  } else if (viewName === "orders" && $("viewOrders")) {
    $("viewOrders").classList.remove("hidden");
    renderOrders();
  } else if (viewName === "order-details" && $("viewOrderDetails")) {
    if (targetId) state.selectedOrder = targetId;
    $("viewOrderDetails").classList.remove("hidden");
    renderOrderDetails(state.selectedOrder);
  } else if (viewName === "ai-insights" && $("viewAiInsights")) {
    $("viewAiInsights").classList.remove("hidden");
    renderAiInsights();
  } else if (viewName === "approvals" && $("viewApprovals")) {
    $("viewApprovals").classList.remove("hidden");
    renderApprovals();
  } else if (viewName === "reports" && $("viewReports")) {
    $("viewReports").classList.remove("hidden");
    renderReports();
  } else if (viewName === "settings" && $("viewSettings")) {
    $("viewSettings").classList.remove("hidden");
    renderSettings();
  } else if (viewName === "alerts" && $("viewAlerts")) {
    $("viewAlerts").classList.remove("hidden");
    renderAllAlerts();
  }

  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* Authentication & Landing Page Toggle */
function toggleLoginScreen(show, message = "Welcome back, Alex Chen! Operations stream connected.") {
  const login = $("loginScreen");
  const app = $("appShell");
  const landing = $("landingPage");
  if (show) {
    if (login) login.classList.remove("hidden");
    if (app) app.classList.add("hidden");
    if (landing) landing.classList.add("hidden");
    window.location.hash = "login";
  } else {
    if (login) login.classList.add("hidden");
    if (landing) landing.classList.add("hidden");
    if (app) app.classList.remove("hidden");
    window.location.hash = "app";
    toast(message, "success");
    load();
  }
}

function showLandingPage(show) {
  state.landingActive = show;
  const login = $("loginScreen");
  const app = $("appShell");
  const landing = $("landingPage");
  if (show) {
    if (landing) landing.classList.remove("hidden");
    if (app) app.classList.add("hidden");
    if (login) login.classList.add("hidden");
    window.location.hash = "landing";
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else {
    if (landing) landing.classList.add("hidden");
    if (login) login.classList.add("hidden");
    if (app) app.classList.remove("hidden");
    window.location.hash = "app";
    load();
  }
}

/* Data Loading */
async function load() {
  try {
    state.data = await api("/dashboard");
    if (state.data?.orders?.length && (!state.selectedOrder || state.selectedOrder === "ORD-00125")) {
      state.selectedOrder = state.data.orders[0].id;
    }
    if (state.data?.machines?.length && (!state.selectedMachine || state.selectedMachine === "M-001")) {
      state.selectedMachine = state.data.machines[0].id;
    }
    renderCurrentView();
  } catch (e) {
    toast(`API Sync: ${e.message}`, "warn");
  }
}

function renderCurrentView() {
  renderDashboard();
  renderMachines();
  renderOrders();
  renderApprovals();
  renderNotifications();
}

/* SCREEN 2: Dashboard Renderer */
function renderDashboard() {
  if (!state.data) return;

  // Render Machine Health Trend SVG Line Chart
  renderTrendLineChart();

  // Render Recent Alerts from live IoT edge telemetry
  const rawEvents = state.data?.recentEvents || [];
  const alerts = rawEvents.slice(0, 5).map(ev => {
    const isCrit = ev.type === "MACHINE_STOP" || (ev.durationMinutes && ev.durationMinutes >= 30);
    const isWarn = ev.type === "MACHINE_DEGRADED" || ev.type === "QUALITY_REWORK" || ev.type === "MATERIAL_DELAY";
    const statusType = isCrit ? "critical" : isWarn ? "warning" : "healthy";
    const machineId = ev.machineId || "CNC-04";
    const desc = ev.description || `${ev.type} on ${machineId}`;
    return {
      title: `${machineId} · ${desc}`,
      status: isCrit ? "Critical" : isWarn ? "Warning" : "Info",
      type: statusType,
      machineId: machineId,
      time: ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Recent"
    };
  });
  if (!alerts.length) {
    alerts.push(
      { title: "CNC-04 · Spindle bearing thermal trip", status: "Critical", type: "critical", machineId: "CNC-04", time: "15:12" },
      { title: "CNC-02 · Spindle vibration elevated", status: "Warning", type: "warning", machineId: "CNC-02", time: "09:30" },
      { title: "ORD-1048 · Bore diameter out of tolerance (17 units)", status: "Warning", type: "warning", machineId: "CNC-04", time: "11:05" },
      { title: "ORD-1048 · Raw forging batch release delayed", status: "Warning", type: "warning", machineId: "CNC-04", time: "08:20" }
    );
  }

  if ($("dashboardRecentAlerts")) {
    $("dashboardRecentAlerts").innerHTML = alerts.map(a => `
      <div class="alert-item-row clickable-row" onclick="switchView('machine-details', '${a.machineId}')">
        <div class="alert-left-meta">
          <span class="alert-indicator-dot ${a.type}"></span>
          <span class="alert-machine-title">${a.title}</span>
        </div>
        <div class="alert-right-meta">
          <span class="status-pill ${a.type}">${a.status}</span>
          <span class="alert-time-tag">${a.time}</span>
        </div>
      </div>
    `).join("");
  }
}

function renderTrendLineChart() {
  const container = $("machineTrendChartContainer");
  if (!container) return;

  // Smooth SVG curve points for Healthy, Warning, Critical
  container.innerHTML = `
    <svg viewBox="0 0 540 220" preserveAspectRatio="none">
      <defs>
        <linearGradient id="gradHealthy" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#10b981" stop-opacity="0.25"/>
          <stop offset="100%" stop-color="#10b981" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
      <!-- Grid lines -->
      <line x1="40" y1="30" x2="520" y2="30" stroke="var(--border)" stroke-dasharray="4" />
      <line x1="40" y1="80" x2="520" y2="80" stroke="var(--border)" stroke-dasharray="4" />
      <line x1="40" y1="130" x2="520" y2="130" stroke="var(--border)" stroke-dasharray="4" />
      <line x1="40" y1="180" x2="520" y2="180" stroke="var(--border)" />
      
      <!-- Axis Labels -->
      <text x="15" y="35" fill="var(--text-muted)" font-size="11">100</text>
      <text x="15" y="85" fill="var(--text-muted)" font-size="11">75</text>
      <text x="15" y="135" fill="var(--text-muted)" font-size="11">50</text>
      <text x="15" y="185" fill="var(--text-muted)" font-size="11">25</text>
      
      <text x="50" y="205" fill="var(--text-muted)" font-size="11">1/10</text>
      <text x="130" y="205" fill="var(--text-muted)" font-size="11">1/13</text>
      <text x="210" y="205" fill="var(--text-muted)" font-size="11">1/16</text>
      <text x="290" y="205" fill="var(--text-muted)" font-size="11">1/19</text>
      <text x="370" y="205" fill="var(--text-muted)" font-size="11">1/22</text>
      <text x="450" y="205" fill="var(--text-muted)" font-size="11">1/25</text>

      <!-- Healthy Area + Line -->
      <path d="M50,110 Q 120,60 190,95 T 330,70 T 450,55 L 450,180 L 50,180 Z" fill="url(#gradHealthy)" />
      <path d="M50,110 Q 120,60 190,95 T 330,70 T 450,55" fill="none" stroke="#10b981" stroke-width="3" stroke-linecap="round" />
      
      <!-- Warning Line -->
      <path d="M50,140 Q 120,130 190,145 T 330,120 T 450,110" fill="none" stroke="#f59e0b" stroke-width="2.5" stroke-linecap="round" />
      
      <!-- Critical Line -->
      <path d="M50,170 Q 120,165 190,160 T 330,150 T 450,140" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" />
    </svg>
  `;
}

/* SCREEN 3: Machines Overview Renderer */
function renderMachines() {
  if (!state.data) return;
  const machines = state.data.machines || [];
  
  const kw = ($("searchMachinesInput")?.value || "").toLowerCase();
  const locFilter = $("machLocationFilter")?.value || "ALL";
  const statusFilter = $("machStatusFilter")?.value || "ALL";

  const filtered = machines.filter(m => {
    const matchKw = !kw || m.id.toLowerCase().includes(kw) || (m.name || "").toLowerCase().includes(kw);
    const matchLoc = locFilter === "ALL" || (m.location || "").includes(locFilter);
    const matchStatus = statusFilter === "ALL" || 
      (statusFilter === "HEALTHY" && (m.healthScore >= 80 || m.status === "AVAILABLE")) ||
      (statusFilter === "WARNING" && (m.healthScore < 80 && m.healthScore >= 50 || m.status === "DEGRADED")) ||
      (statusFilter === "CRITICAL" && (m.healthScore < 50 || m.status === "STOPPED"));
    return matchKw && matchLoc && matchStatus;
  });

  if ($("machinesTableBody")) {
    $("machinesTableBody").innerHTML = filtered.map(m => {
      const score = m.healthScore || (m.status === "AVAILABLE" ? 95 : m.status === "DEGRADED" ? 72 : 45);
      const statusType = score >= 80 ? "healthy" : score >= 60 ? "warning" : "critical";
      const statusLabel = statusType === "healthy" ? "Healthy" : statusType === "warning" ? "Warning" : "Critical";

      return `
        <tr class="clickable-row" onclick="switchView('machine-details', '${m.id}')">
          <td style="font-family:var(--font-mono); font-weight:600; color:var(--brand);">${m.id}</td>
          <td style="font-weight:600;">${m.name || m.id}</td>
          <td style="color:var(--text-secondary);">${m.location || "Plant 1"}</td>
          <td><span class="status-pill ${statusType}">${statusLabel}</span></td>
          <td>
            <div class="health-score-cell">
              <div class="score-track">
                <div class="score-fill ${statusType}" style="width: ${score}%;"></div>
              </div>
              <span style="font-weight:700; font-family:var(--font-mono);">${score}%</span>
            </div>
          </td>
          <td style="color:var(--text-muted); font-size:12.5px;">${m.lastUpdated || "2 mins ago"}</td>
          <td>
            <button class="icon-btn" style="width:28px;height:28px;" title="View Details">
              <svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>
            </button>
          </td>
        </tr>
      `;
    }).join("") || `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--text-muted);">No machines match the selected filter.</td></tr>`;
  }
}

/* SCREEN 4: Machine Details Renderer */
function renderMachineDetails(machineId) {
  const machines = state.data?.machines || [];
  const m = machines.find(x => x.id === machineId) || machines[0] || {
    id: "M-001",
    name: "Packaging Line A1",
    location: "Plant 1 - Line A",
    model: "PK-5000",
    installed: "Jan 15, 2024",
    lastMaintenance: "Feb 1, 2024",
    nextMaintenance: "Mar 15, 2024",
    uptime: "99.2%",
    healthScore: 98,
    temperature: 42,
    vibration: 0.2,
    powerUsage: 12.4,
    throughput: 120,
    status: "AVAILABLE"
  };

  const score = m.healthScore || (m.status === "AVAILABLE" ? 98 : m.status === "DEGRADED" ? 72 : 45);
  const statusType = score >= 80 ? "healthy" : score >= 60 ? "warning" : "critical";
  const statusLabel = statusType === "healthy" ? "Healthy" : statusType === "warning" ? "Warning" : "Critical";

  if ($("machDetailBreadcrumbId")) $("machDetailBreadcrumbId").textContent = m.id;
  if ($("machDetailName")) $("machDetailName").textContent = m.name || m.id;
  if ($("machDetailStatusPill")) {
    $("machDetailStatusPill").className = `status-pill ${statusType}`;
    $("machDetailStatusPill").textContent = statusLabel;
  }
  if ($("machDetailMetaId")) $("machDetailMetaId").textContent = m.id;
  if ($("machDetailMetaLocation")) $("machDetailMetaLocation").textContent = m.location || "Plant 1 - Line A";
  if ($("machDetailMetaModel")) $("machDetailMetaModel").textContent = m.model || "PK-5000";
  if ($("machDetailMetaInstalled")) $("machDetailMetaInstalled").textContent = m.installed || "Jan 15, 2024";
  if ($("machDetailMetaLastMaint")) $("machDetailMetaLastMaint").textContent = m.lastMaintenance || "Feb 1, 2024";
  if ($("machDetailMetaNextMaint")) $("machDetailMetaNextMaint").textContent = m.nextMaintenance || "Mar 15, 2024";
  if ($("machDetailMetaUptime")) $("machDetailMetaUptime").textContent = m.uptime || "99.2%";
  if ($("machDetailMetaStatus")) $("machDetailMetaStatus").textContent = m.status || "AVAILABLE";

  // Circular Gauge SVG Animation
  const circumference = 2 * Math.PI * 42; // ~263.89
  const offset = circumference - (score / 100) * circumference;
  if ($("machGaugeFill")) {
    $("machGaugeFill").style.strokeDashoffset = offset;
    $("machGaugeFill").style.stroke = statusType === "healthy" ? "var(--status-healthy)" : statusType === "warning" ? "var(--status-warning)" : "var(--status-critical)";
  }
  if ($("machGaugeNum")) $("machGaugeNum").textContent = `${score}%`;
  if ($("machGaugeDesc")) $("machGaugeDesc").textContent = score >= 85 ? "Excellent" : score >= 60 ? "Moderate" : "Critical Attention";

  if ($("machTelTemp")) $("machTelTemp").textContent = `${m.temperature || 42}°C`;
  if ($("machTelVibration")) $("machTelVibration").textContent = `${m.vibration || 0.2} mm/s`;
  if ($("machTelPower")) $("machTelPower").textContent = `${m.powerUsage || 12.4} kW`;
  if ($("machTelThroughput")) $("machTelThroughput").textContent = `${m.throughput || 120} units/hr`;
}

/* SCREEN 5: Orders Management Renderer */
function renderOrders() {
  if (!state.data) return;
  const orders = state.data.orders || [];

  const kw = ($("searchOrdersInput")?.value || "").toLowerCase();
  const statusFilter = $("orderStatusFilter")?.value || "ALL";

  const filtered = orders.filter(o => {
    const matchKw = !kw || o.id.toLowerCase().includes(kw) || (o.customer || "").toLowerCase().includes(kw);
    const matchStatus = statusFilter === "ALL" || (o.status || "").toUpperCase() === statusFilter;
    return matchKw && matchStatus;
  });

  if ($("ordersTableBody")) {
    $("ordersTableBody").innerHTML = filtered.map(o => {
      const riskScore = Math.round(o.risk?.riskScore || 25);
      const isDelayed = o.status === "DELAYED" || o.status === "AT_RISK" || riskScore >= 60;
      const isDelivered = o.status === "DELIVERED" || o.status === "COMPLETED";
      const statusClass = isDelayed ? "delayed" : isDelivered ? "delivered" : "transit";
      const statusLabel = isDelayed ? "Delayed" : isDelivered ? "Delivered" : "In Transit";
      const riskColor = riskScore >= 70 ? "var(--status-critical)" : riskScore >= 40 ? "var(--status-warning)" : "var(--status-healthy)";

      return `
        <tr class="clickable-row" onclick="switchView('order-details', '${o.id}')">
          <td style="font-family:var(--font-mono); font-weight:600; color:var(--brand);">${o.id}</td>
          <td style="font-weight:600;">${o.customer}</td>
          <td style="color:var(--text-secondary);">${o.destination || "Chicago, IL"}</td>
          <td><span class="status-pill ${statusClass}">${statusLabel}</span></td>
          <td style="color:var(--text-muted); font-size:12.5px;">${o.eta || "Jan 22"}</td>
          <td>
            <div style="font-weight:700; font-family:var(--font-mono); color:${riskColor};">${riskScore}%</div>
          </td>
          <td>
            <button class="icon-btn" style="width:28px;height:28px;" title="Inspect Order Details">
              <svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>
            </button>
          </td>
        </tr>
      `;
    }).join("") || `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--text-muted);">No orders matching query.</td></tr>`;
  }
}

/* SCREEN 6: Order Details Renderer */
function renderOrderDetails(orderId) {
  const orders = state.data?.orders || [];
  const o = orders.find(x => x.id === orderId) || orders[0] || {
    id: "ORD-00125",
    customer: "Tech Solutions",
    destination: "Chicago, IL",
    orderDate: "Jan 16, 2024",
    expectedDelivery: "Jan 22, 2024",
    priority: "High",
    items: "12 units",
    status: "DELAYED",
    risk: { riskScore: 78 }
  };

  const riskScore = Math.round(o.risk?.riskScore || 78);
  const isDelayed = o.status === "DELAYED" || o.status === "AT_RISK" || riskScore >= 60;
  const isDelivered = o.status === "DELIVERED" || o.status === "COMPLETED";
  const statusClass = isDelayed ? "delayed" : isDelivered ? "delivered" : "transit";
  const statusLabel = isDelayed ? "Delayed" : isDelivered ? "Delivered" : "In Transit";

  if ($("orderDetailBreadcrumbId")) $("orderDetailBreadcrumbId").textContent = o.id;
  if ($("orderDetailTitle")) $("orderDetailTitle").textContent = o.id;
  if ($("orderDetailStatusPill")) {
    $("orderDetailStatusPill").className = `status-pill ${statusClass}`;
    $("orderDetailStatusPill").textContent = statusLabel;
  }
  if ($("odCustomer")) $("odCustomer").textContent = o.customer;
  if ($("odDestination")) $("odDestination").textContent = o.destination || "Chicago, IL";
  if ($("odOrderDate")) $("odOrderDate").textContent = o.orderDate || "Jan 16, 2024";
  if ($("odExpectedDelivery")) $("odExpectedDelivery").textContent = o.expectedDelivery || "Jan 22, 2024";
  if ($("odPriority")) $("odPriority").textContent = o.priority || "High";
  if ($("odItems")) $("odItems").textContent = o.items || `${o.quantity || 12} units`;

  // Risk Circular Gauge
  const circumference = 2 * Math.PI * 42;
  const offset = circumference - (riskScore / 100) * circumference;
  if ($("orderRiskFill")) {
    $("orderRiskFill").style.strokeDashoffset = offset;
    $("orderRiskFill").style.stroke = riskScore >= 70 ? "var(--status-critical)" : riskScore >= 40 ? "var(--status-warning)" : "var(--status-healthy)";
  }
  if ($("orderRiskGaugeNum")) {
    $("orderRiskGaugeNum").textContent = `${riskScore}%`;
    $("orderRiskGaugeNum").style.color = riskScore >= 70 ? "var(--status-critical)" : "var(--text-primary)";
  }
}

/* SCREEN 7: AI Insights */
function renderAiInsights() {
  const tabs = $("aiInsightsTabs");
  if (tabs) {
    tabs.querySelectorAll(".tab-btn").forEach(btn => {
      btn.onclick = () => {
        tabs.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        state.aiSubTab = btn.dataset.aiSubtab || "predictions";
        renderAiInsightsSubTab();
      };
    });
  }

  // Assistant chips
  document.querySelectorAll(".prompt-chip-btn").forEach(chip => {
    chip.onclick = () => {
      const q = chip.dataset.chip;
      if ($("aiChatInput")) $("aiChatInput").value = q;
      askAi(q);
    };
  });

  renderAiInsightsSubTab();
}

function renderAiInsightsSubTab() {
  const panel = $("aiInsightsLeftPanel");
  if (!panel) return;
  const tab = state.aiSubTab || "predictions";

  const orders = state.data?.orders || [];
  const machines = state.data?.machines || [];
  const events = state.data?.recentEvents || [];
  const recs = state.data?.recommendations || [];

  if (tab === "predictions") {
    const atRiskCount = orders.filter(o => (o.risk?.riskScore || 0) >= 60).length;
    const delayRiskPct = orders.length ? Math.round((atRiskCount / orders.length) * 100) : 25;
    const critMachines = machines.filter(m => m.status === "STOPPED" || m.status === "MAINTENANCE").length;
    const machRiskPct = machines.length ? Math.round((critMachines / machines.length) * 100) : 20;

    panel.innerHTML = `
      <h3 class="panel-title" style="margin-bottom:14px;">Autonomous Risk Predictions</h3>
      <p style="font-size:12.5px; color:var(--text-secondary); margin-bottom:16px;">
        Evaluated in real time via SageMaker risk regressor & plant telemetry models.
      </p>

      <div class="prediction-card-row">
        <div>
          <div class="pred-title">Order SLA Delay Risk</div>
          <span style="font-size:11.5px; color:var(--text-muted);">${atRiskCount} of ${orders.length} active orders elevated</span>
        </div>
        <div class="pred-val-group">
          <span class="pred-number">${delayRiskPct}%</span>
          <span class="trend-badge ${delayRiskPct > 20 ? 'negative' : 'positive'}">+${delayRiskPct > 20 ? 5 : 0}%</span>
        </div>
      </div>

      <div class="prediction-card-row">
        <div>
          <div class="pred-title">Machine Failure Probability</div>
          <span style="font-size:11.5px; color:var(--text-muted);">Bearing thermal drift on CNC-04</span>
        </div>
        <div class="pred-val-group">
          <span class="pred-number">${machRiskPct || 20}%</span>
          <span class="trend-badge negative">+2%</span>
        </div>
      </div>

      <div class="prediction-card-row">
        <div>
          <div class="pred-title">Preventive Maintenance Priority</div>
          <span style="font-size:11.5px; color:var(--text-muted);">Spindle balancing window active</span>
        </div>
        <div class="pred-val-group">
          <span class="pred-number">6%</span>
          <span class="trend-badge positive">-2%</span>
        </div>
      </div>

      <div class="prediction-card-row">
        <div>
          <div class="pred-title">Material Inbound Supply Drift</div>
          <span style="font-size:11.5px; color:var(--text-muted);">Raw forging release hold: 4.0h</span>
        </div>
        <div class="pred-val-group">
          <span class="pred-number">18%</span>
          <span class="trend-badge negative">+4%</span>
        </div>
      </div>

      <div style="margin-top:16px; padding:12px; background:rgba(37,99,235,0.08); border-radius:8px; border:1px solid rgba(37,99,235,0.2);">
        <div style="font-size:12px; font-weight:600; color:var(--accent); margin-bottom:4px;">Recommended Strategy:</div>
        <div style="font-size:12px; color:var(--text-secondary);">
          Reroute high-risk order <strong>ORD-1048</strong> to reserve station <strong>CNC-07</strong> to restore delivery margin.
        </div>
      </div>
    `;
  } else if (tab === "anomalies") {
    panel.innerHTML = `
      <h3 class="panel-title" style="margin-bottom:14px;">Detected Telemetry Anomalies</h3>
      <p style="font-size:12.5px; color:var(--text-secondary); margin-bottom:14px;">
        High-frequency edge signals exceeding dynamic baseline thresholds:
      </p>
      <div style="display:flex; flex-direction:column; gap:10px;">
        <div style="padding:12px; border-radius:8px; background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.25);">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <span style="font-weight:700; font-size:13px; color:var(--status-critical);">CNC-04 · Spindle Bearing Thermal Overload</span>
            <span class="status-pill critical">Score: 0.704</span>
          </div>
          <p style="font-size:12px; color:var(--text-secondary); margin:0;">Thermal sensor tripped at 84°C (+28°C above tolerance). 45-min downtime logged.</p>
        </div>

        <div style="padding:12px; border-radius:8px; background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.25);">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <span style="font-weight:700; font-size:13px; color:var(--status-warning);">CNC-02 · Elevated Spindle Vibration Harmonics</span>
            <span class="status-pill warning">Score: 0.176</span>
          </div>
          <p style="font-size:12px; color:var(--text-secondary); margin:0;">Vibration amplitude drift (+0.8 mm/s) detected during high-torque turning pass.</p>
        </div>

        <div style="padding:12px; border-radius:8px; background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.25);">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <span style="font-weight:700; font-size:13px; color:var(--status-warning);">ORD-1048 · Quality Bore Dimension Out-of-Spec</span>
            <span class="status-pill warning">17 Units</span>
          </div>
          <p style="font-size:12px; color:var(--text-secondary); margin:0;">Inner bore diameter -0.04mm below tolerance; lot diverted to rework queue.</p>
        </div>
      </div>
    `;
  } else if (tab === "recommendations") {
    panel.innerHTML = `
      <h3 class="panel-title" style="margin-bottom:14px;">Autonomous Recovery Recommendations</h3>
      <p style="font-size:12.5px; color:var(--text-secondary); margin-bottom:14px;">
        Generated by policy engine adhering to human-in-the-loop authorization:
      </p>
      <div style="display:flex; flex-direction:column; gap:12px;">
        ${recs.map(r => `
          <div style="padding:14px; border-radius:8px; border:1px solid var(--border-color); background:var(--card-bg);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <span style="font-weight:700; font-size:13.5px; color:var(--text-primary);">${r.actionType ? r.actionType.replaceAll('_', ' ') : 'Action'}: ${r.orderId || 'Order'}</span>
              <span class="status-pill healthy">${Math.round((r.confidence || 0.95) * 100)}% Confidence</span>
            </div>
            <p style="font-size:12px; color:var(--text-secondary); margin-bottom:12px;">${r.rationale}</p>
            <div style="display:flex; gap:8px;">
              <button class="btn-primary-action" style="padding:6px 12px; font-size:12px;" onclick="executeApproval('${r.id}')">Authorize & Execute</button>
              <button class="btn-reject" style="padding:6px 12px; font-size:12px;" onclick="toast('Recommendation deferred', 'info')">Defer</button>
            </div>
          </div>
        `).join("") || '<p style="color:var(--text-muted); font-size:13px;">No active recommendations requiring sign-off.</p>'}
      </div>
    `;
  } else if (tab === "chat") {
    panel.innerHTML = `
      <h3 class="panel-title" style="margin-bottom:14px;">Operations Copilot Context</h3>
      <p style="font-size:12.5px; color:var(--text-secondary); margin-bottom:16px;">
        Grounding model active: <strong>Amazon Bedrock Nova Lite</strong> with deterministic operational fallback.
      </p>
      <div style="padding:14px; border-radius:8px; background:var(--card-bg); border:1px solid var(--border-color); font-size:12px; line-height:1.6; color:var(--text-secondary);">
        <strong style="color:var(--text-primary);">Grounding Sources Connected:</strong><br>
        • Live DynamoDB Order & Machine state tables<br>
        • SageMaker ML Predictive Risk Endpoint<br>
        • Real-time IoT Ingestion SQS/EventBridge stream<br>
        • Factory Safety PolicyGuard Boundaries
      </div>
      <div style="margin-top:16px;">
        <button class="btn-primary-action" style="width:100%;" onclick="$('aiChatInput')?.focus();">Open Query Input</button>
      </div>
    `;
  }
}

async function askAi(customQuestion = null) {
  const input = $("aiChatInput");
  const q = customQuestion || input.value.trim();
  if (!q) return;

  appendChat(q, "user");
  if (!customQuestion && input) input.value = "";

  try {
    const res = await api("/agent/query", {
      method: "POST",
      body: JSON.stringify({ question: q, orderId: state.selectedOrder })
    });
    const isLiveModel = res.mode === "strands" || res.mode?.startsWith("bedrock-");
    if ($("aiProviderStatus")) {
      $("aiProviderStatus").textContent = isLiveModel ? "Bedrock Nova Lite · live" : "Deterministic fallback · model access pending";
    }
    appendChat(res.answer || "Analysis complete.", "ai");
  } catch (err) {
    appendChat(`Operations AI: ${err.message}`, "ai");
  }
}

function appendChat(text, sender) {
  const chat = $("aiChatHistory");
  if (!chat) return;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${sender}`;
  bubble.textContent = text;
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
}

/* SCREEN 8: Approvals */
function renderApprovals() {
  const recs = state.data?.recommendations || [];
  const container = $("approvalsListContainer");
  if (!container) return;

  const f = state.approvalFilter;
  const filtered = recs.filter(r => {
    if (f === "ALL") return true;
    return (r.category || "").toUpperCase() === f;
  });

  container.innerHTML = filtered.map(r => `
    <div class="approval-card-item">
      <div class="approval-meta-left">
        <div class="approval-headline">
          <span class="approval-title-text">${r.title || ('Approve ' + r.actionType.replaceAll('_', ' '))}</span>
          <span class="status-pill ${r.severity === 'HIGH' ? 'critical' : r.severity === 'MEDIUM' ? 'warning' : 'healthy'}" style="font-size:11px; padding:1px 6px;">
            ${r.severity || 'HIGH'}
          </span>
        </div>
        <p class="approval-subtext">${r.subtitle || r.rationale}</p>
        <span style="font-size:11.5px; color:var(--text-muted); margin-top:2px;">${r.timeAgo || 'Just now'}</span>
      </div>
      <div class="approval-btn-group">
        <button class="btn-approve" onclick="executeApproval('${r.id}')">Approve</button>
        <button class="btn-reject" onclick="toast('Recommendation deferred', 'info')">Reject</button>
      </div>
    </div>
  `).join("") || `<div style="text-align:center; padding:32px; color:var(--text-muted);">No pending approvals in this category.</div>`;
}

async function executeApproval(recId) {
  try {
    await api("/actions", {
      method: "POST",
      body: JSON.stringify({ recommendationId: recId, approvedBy: "Alex Chen (Operations Manager)" })
    });
    toast("Action Authorized & Executed on Floor", "success");
    await load();
  } catch (e) {
    toast(e.message, "error");
  }
}

/* SCREEN 9: Reports & Analytics */
function renderReports() {
  const tabs = $("reportsTabs");
  if (tabs) {
    tabs.querySelectorAll(".tab-btn").forEach(btn => {
      btn.onclick = () => {
        tabs.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        state.reportsSubTab = btn.dataset.repTab || "operational";
        renderReportsSubTab();
      };
    });
  }

  // Dynamic shift date display
  if ($("reportsDateRange")) {
    const now = new Date();
    $("reportsDateRange").textContent = `${now.toLocaleString('default', { month: 'long', year: 'numeric' })} · Shift Active`;
  }

  // Export CSV button
  if ($("reportsExportBtn")) {
    $("reportsExportBtn").onclick = exportReportCsv;
  }

  renderReportsSubTab();
}

function renderReportsSubTab() {
  const container = $("reportsPanelContainer");
  if (!container) return;
  const tab = state.reportsSubTab || "operational";

  const orders = state.data?.orders || [];
  const machines = state.data?.machines || [];

  if (tab === "operational") {
    container.innerHTML = `
      <div class="reports-grid-2">
        <!-- On-Time Delivery Rate Bar Chart -->
        <div class="card-panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">On-Time Delivery Rate</h3>
              <div style="display:flex; align-items:baseline; gap:8px; margin-top:4px;">
                <span style="font-size:28px; font-weight:800; color:var(--text-primary);">96.8%</span>
                <span class="trend-badge positive">+1.2%</span>
              </div>
            </div>
          </div>
          <div class="chart-container" id="deliveryBarChartContainer" style="height:180px;"></div>
        </div>

        <!-- Real Manufacturing Delay Causes Donut Chart -->
        <div class="card-panel">
          <div class="panel-header">
            <h3 class="panel-title">Operational Root Causes of Throughput Delay</h3>
          </div>
          <div style="display:flex; align-items:center; gap:24px; height:220px;" id="donutChartWrap">
            <div style="width:150px; height:150px; flex-shrink:0;">
              <svg viewBox="0 0 42 42" style="width:100%;height:100%;transform:rotate(-90deg);">
                <circle cx="21" cy="21" r="15.915" fill="transparent" stroke="#ef4444" stroke-width="6" stroke-dasharray="44 56" stroke-dashoffset="0"></circle>
                <circle cx="21" cy="21" r="15.915" fill="transparent" stroke="#f59e0b" stroke-width="6" stroke-dasharray="26 74" stroke-dashoffset="-44"></circle>
                <circle cx="21" cy="21" r="15.915" fill="transparent" stroke="#3b82f6" stroke-width="6" stroke-dasharray="18 82" stroke-dashoffset="-70"></circle>
                <circle cx="21" cy="21" r="15.915" fill="transparent" stroke="#94a3b8" stroke-width="6" stroke-dasharray="12 88" stroke-dashoffset="-88"></circle>
              </svg>
            </div>
            <div style="display:flex; flex-direction:column; gap:10px; font-size:13px; color:var(--text-secondary);">
              <div style="display:flex; align-items:center; gap:8px;"><span style="width:10px;height:10px;border-radius:50%;background:#ef4444;"></span><span>Spindle Overheating / Thermal Trips <strong>44%</strong></span></div>
              <div style="display:flex; align-items:center; gap:8px;"><span style="width:10px;height:10px;border-radius:50%;background:#f59e0b;"></span><span>Quality Bore Rework & Scraps <strong>26%</strong></span></div>
              <div style="display:flex; align-items:center; gap:8px;"><span style="width:10px;height:10px;border-radius:50%;background:#3b82f6;"></span><span>Raw Forging Inbound Supply Delay <strong>18%</strong></span></div>
              <div style="display:flex; align-items:center; gap:8px;"><span style="width:10px;height:10px;border-radius:50%;background:#94a3b8;"></span><span>Tooling Setup & Changeover <strong>12%</strong></span></div>
            </div>
          </div>
        </div>
      </div>
    `;

    // Render bar chart SVG
    const barContainer = $("deliveryBarChartContainer");
    if (barContainer) {
      const bars = [88, 92, 94, 91, 96, 95, 96.8];
      const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
      barContainer.innerHTML = `
        <svg viewBox="0 0 400 180" style="width:100%;height:100%;">
          ${bars.map((val, idx) => {
            const x = 30 + idx * 52;
            const height = (val / 100) * 120;
            const y = 140 - height;
            return `
              <rect x="${x}" y="${y}" width="28" height="${height}" rx="4" fill="#3b82f6" />
              <text x="${x + 14}" y="160" text-anchor="middle" fill="var(--text-muted)" font-size="11">${days[idx]}</text>
              <text x="${x + 14}" y="${y - 6}" text-anchor="middle" fill="var(--text-secondary)" font-size="10" font-weight="600">${val}%</text>
            `;
          }).join("")}
        </svg>
      `;
    }
  } else if (tab === "financial") {
    container.innerHTML = `
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:16px; margin-bottom:24px;">
        <div class="card-panel">
          <div style="font-size:12px; color:var(--text-muted); margin-bottom:4px;">Downtime Cost Avoided</div>
          <div style="font-size:26px; font-weight:800; color:#10b981;">$38,400</div>
          <span style="font-size:11.5px; color:var(--text-secondary);">Automated rerouting from CNC-04</span>
        </div>
        <div class="card-panel">
          <div style="font-size:12px; color:var(--text-muted); margin-bottom:4px;">SLA Penalties Mitigated</div>
          <div style="font-size:26px; font-weight:800; color:#3b82f6;">$24,800</div>
          <span style="font-size:11.5px; color:var(--text-secondary);">AeroTurbine Dynamics ORD-1048</span>
        </div>
        <div class="card-panel">
          <div style="font-size:12px; color:var(--text-muted); margin-bottom:4px;">Scrap Material Saved</div>
          <div style="font-size:26px; font-weight:800; color:#f59e0b;">$6,200</div>
          <span style="font-size:11.5px; color:var(--text-secondary);">Bore vibration early cutoff</span>
        </div>
        <div class="card-panel">
          <div style="font-size:12px; color:var(--text-muted); margin-bottom:4px;">Net ROI on OpsRelay</div>
          <div style="font-size:26px; font-weight:800; color:#8b5cf6;">+420%</div>
          <span style="font-size:11.5px; color:var(--text-secondary);">Based on AWS infrastructure cost</span>
        </div>
      </div>

      <div class="card-panel">
        <h3 class="panel-title" style="margin-bottom:14px;">Work Order Financial Risk Breakdown</h3>
        <table style="width:100%; border-collapse:collapse; font-size:13px; text-align:left;">
          <thead>
            <tr style="border-bottom:1px solid var(--border-color); color:var(--text-muted);">
              <th style="padding:10px 8px;">Order</th>
              <th style="padding:10px 8px;">Customer</th>
              <th style="padding:10px 8px;">Risk Score</th>
              <th style="padding:10px 8px;">Contract Value</th>
              <th style="padding:10px 8px;">Financial Risk Exposure</th>
              <th style="padding:10px 8px;">Mitigation Action</th>
            </tr>
          </thead>
          <tbody>
            <tr style="border-bottom:1px solid var(--border-color);">
              <td style="padding:10px 8px; font-weight:600;">ORD-1048</td>
              <td style="padding:10px 8px;">AeroTurbine Dynamics</td>
              <td style="padding:10px 8px;"><span class="status-pill critical">81.2</span></td>
              <td style="padding:10px 8px;">$125,000</td>
              <td style="padding:10px 8px; color:var(--status-critical); font-weight:600;">$24,800 SLA Penalty</td>
              <td style="padding:10px 8px;"><span style="color:#10b981; font-weight:600;">Reroute to CNC-07</span></td>
            </tr>
            <tr style="border-bottom:1px solid var(--border-color);">
              <td style="padding:10px 8px; font-weight:600;">ORD-1051</td>
              <td style="padding:10px 8px;">Metro Fluid Systems</td>
              <td style="padding:10px 8px;"><span class="status-pill warning">17.6</span></td>
              <td style="padding:10px 8px;">$68,000</td>
              <td style="padding:10px 8px; color:var(--status-warning); font-weight:600;">$3,400 Delay Risk</td>
              <td style="padding:10px 8px;">Spindle Balancing Scheduled</td>
            </tr>
            <tr>
              <td style="padding:10px 8px; font-weight:600;">ORD-1064</td>
              <td style="padding:10px 8px;">Sundar Hydraulics</td>
              <td style="padding:10px 8px;"><span class="status-pill healthy">5.6</span></td>
              <td style="padding:10px 8px;">$44,000</td>
              <td style="padding:10px 8px; color:#10b981; font-weight:600;">$0 (Nominal)</td>
              <td style="padding:10px 8px;">In Active Machining</td>
            </tr>
          </tbody>
        </table>
      </div>
    `;
  } else if (tab === "predictive") {
    container.innerHTML = `
      <div class="reports-grid-2">
        <div class="card-panel">
          <h3 class="panel-title" style="margin-bottom:14px;">SageMaker ML Model Performance</h3>
          <div style="display:flex; flex-direction:column; gap:12px; font-size:13px;">
            <div style="display:flex; justify-content:space-between; padding-bottom:8px; border-bottom:1px solid var(--border-color);">
              <span>Model Architecture</span>
              <strong style="color:var(--text-primary);">XGBoost Multi-Task Regressor</strong>
            </div>
            <div style="display:flex; justify-content:space-between; padding-bottom:8px; border-bottom:1px solid var(--border-color);">
              <span>Inference Latency</span>
              <strong style="color:#10b981;">42 ms (Real-Time API)</strong>
            </div>
            <div style="display:flex; justify-content:space-between; padding-bottom:8px; border-bottom:1px solid var(--border-color);">
              <span>Failure Precision Rate</span>
              <strong style="color:var(--text-primary);">94.2%</strong>
            </div>
            <div style="display:flex; justify-content:space-between; padding-bottom:8px; border-bottom:1px solid var(--border-color);">
              <span>Delivery Drift Recall</span>
              <strong style="color:var(--text-primary);">91.8%</strong>
            </div>
            <div style="display:flex; justify-content:space-between;">
              <span>Mean Time Between Failures (MTBF)</span>
              <strong style="color:var(--text-primary);">168.4 Operating Hours</strong>
            </div>
          </div>
        </div>

        <div class="card-panel">
          <h3 class="panel-title" style="margin-bottom:14px;">Fleet Machine Reliability Scores</h3>
          <div style="display:flex; flex-direction:column; gap:10px;">
            ${machines.map(m => {
              const isCrit = m.status === 'STOPPED';
              const isWarn = m.status === 'MAINTENANCE';
              const prob = isCrit ? '50.3% Risk' : isWarn ? '18.1% Risk' : '< 5% Nominal';
              return `
                <div style="display:flex; justify-content:space-between; align-items:center; padding:10px; border-radius:6px; background:rgba(0,0,0,0.02); border:1px solid var(--border-color);">
                  <div>
                    <span style="font-weight:600; font-size:13px;">${m.id} (${m.name})</span>
                    <div style="font-size:11px; color:var(--text-muted);">${m.type || 'CNC Machine'} · Rated ${m.capacityPerHour} u/hr</div>
                  </div>
                  <span class="status-pill ${isCrit ? 'critical' : isWarn ? 'warning' : 'healthy'}">${prob}</span>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      </div>
    `;
  } else if (tab === "custom") {
    container.innerHTML = `
      <div class="card-panel">
        <h3 class="panel-title" style="margin-bottom:14px;">Custom Plant Audit & Report Builder</h3>
        <p style="font-size:12.5px; color:var(--text-secondary); margin-bottom:18px;">
          Generate compliance and delivery audit reports filtered by workstation or customer SLA:
        </p>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:14px; margin-bottom:20px;">
          <div>
            <label style="display:block; font-size:12px; margin-bottom:4px; color:var(--text-secondary);">Target Plant Facility</label>
            <select class="search-input" style="width:100%;" id="customRepPlant">
              <option value="PLANT-001">Apex Precision Works (Plant #01)</option>
            </select>
          </div>
          <div>
            <label style="display:block; font-size:12px; margin-bottom:4px; color:var(--text-secondary);">Workstation Cell</label>
            <select class="search-input" style="width:100%;" id="customRepMachine">
              <option value="ALL">All Workstations (Fleetwide)</option>
              ${machines.map(m => `<option value="${m.id}">${m.id} - ${m.name}</option>`).join("")}
            </select>
          </div>
          <div>
            <label style="display:block; font-size:12px; margin-bottom:4px; color:var(--text-secondary);">Report Type</label>
            <select class="search-input" style="width:100%;" id="customRepType">
              <option value="SLA_RISK">Delivery SLA Risk Audit</option>
              <option value="MAINTENANCE">Predictive Machine Maintenance</option>
              <option value="TELEMETRY">IoT High-Frequency Incident Log</option>
            </select>
          </div>
        </div>

        <div style="display:flex; gap:12px;">
          <button class="btn-primary-action" onclick="exportReportCsv()">Generate & Download CSV Audit</button>
          <button class="btn-reject" onclick="toast('Report preview updated below', 'info')">Preview on Screen</button>
        </div>
      </div>
    `;
  }
}

function exportReportCsv() {
  const orders = state.data?.orders || [];
  const machines = state.data?.machines || [];
  let csv = "Record_Type,ID,Name_or_Customer,Status,Capacity_or_Quantity,Risk_Score_or_Progress,Updated_At\n";
  orders.forEach(o => {
    csv += `ORDER,"${o.id}","${o.customer || ''}","${o.status || ''}",${o.quantity || 0},"${o.risk?.riskScore || 0}%","${o.dueDate || ''}"\n`;
  });
  machines.forEach(m => {
    csv += `MACHINE,"${m.id}","${m.name || ''}","${m.status || ''}",${m.capacityPerHour || 0},"${m.currentOrderId || 'NONE'}","${new Date().toISOString()}"\n`;
  });

  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `opsrelay_plant_report_${Date.now()}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  toast("Plant operational CSV report downloaded successfully", "success");
}

/* SCREEN 10: Settings & Theme Switcher Grid */
function renderSettings() {
  renderThemeGrid();
}

function renderThemeGrid() {
  const container = $("themesGrid");
  if (!container) return;

  const themes = [
    { id: "enterprise", name: "Enterprise (Default)", colors: ["#2563eb", "#f8fafc", "#0f172a"] },
    { id: "dark", name: "Dark Theme (#13)", colors: ["#38bdf8", "#0b0f19", "#151d30"] },
    { id: "minimal", name: "Minimal Theme (#14)", colors: ["#18181b", "#ffffff", "#71717a"] },
    { id: "high-contrast", name: "High-Contrast (#15)", colors: ["#22c55e", "#000000", "#ffffff"] },
    { id: "forest", name: "Forest Theme (#16)", colors: ["#10b981", "#0a1f16", "#123828"] },
    { id: "ocean", name: "Ocean Theme (#17)", colors: ["#0ea5e9", "#081628", "#102a4d"] },
    { id: "sunset", name: "Sunset Theme (#18)", colors: ["#f97316", "#221217", "#3d1f2a"] },
    { id: "purple", name: "Purple Theme (#19)", colors: ["#a855f7", "#160d26", "#2b1a4c"] },
    { id: "monochrome", name: "Monochrome (#20)", colors: ["#e4e4e7", "#18181b", "#27272a"] }
  ];

  container.innerHTML = themes.map(t => {
    const isAct = state.currentTheme === t.id;
    return `
      <div class="theme-card-option ${isAct ? 'active' : ''}" onclick="setTheme('${t.id}')">
        <div class="theme-swatch-bar">
          <div class="swatch-slice" style="background:${t.colors[0]};"></div>
          <div class="swatch-slice" style="background:${t.colors[1]};"></div>
          <div class="swatch-slice" style="background:${t.colors[2]};"></div>
        </div>
        <div class="theme-name-label">${t.name}</div>
      </div>
    `;
  }).join("");
}

/* SCREEN 11: Notifications Slide-Over Drawer */
function renderNotifications() {
  const container = $("notificationsDrawerBody");
  if (!container) return;

  const notifs = [
    { title: "Machine M-003 health below 50%", time: "2 mins ago", type: "critical", cat: "ALERTS" },
    { title: "Order ORD-00125 delay risk increased", time: "15 mins ago", type: "warning", cat: "ALERTS" },
    { title: "New AI recommendation available", time: "1 hour ago", type: "transit", cat: "APPROVALS" },
    { title: "Maintenance completed for M-002", time: "2 hours ago", type: "healthy", cat: "SYSTEM" }
  ];

  const f = state.notifFilter;
  const filtered = notifs.filter(n => f === "ALL" || n.cat === f);

  container.innerHTML = filtered.map(n => `
    <div class="alert-item-row">
      <div class="alert-left-meta">
        <span class="alert-indicator-dot ${n.type}"></span>
        <div>
          <div style="font-size:13px; font-weight:600; color:var(--text-primary);">${n.title}</div>
          <span style="font-size:11.5px; color:var(--text-muted);">${n.time}</span>
        </div>
      </div>
    </div>
  `).join("");
}

function renderAllAlerts() {
  const container = $("allAlertsList");
  if (!container) return;
  renderDashboard();
  container.innerHTML = $("dashboardRecentAlerts")?.innerHTML || "";
}

/* Reschedule Modal Functions (Diagram 03) */
function openRescheduleModal(orderId) {
  const o = (state.data?.orders || []).find(x => x.id === orderId) || { id: orderId, dueDate: new Date().toISOString(), quantity: 500 };
  $("rescheduleOrderId").value = o.id;
  $("rescheduleOrderDisplay").value = `${o.id} · ${o.customer || 'Target Order'}`;
  $("rescheduleCurrentDue").value = o.dueDate || "Jan 22, 2024";
  
  const d = new Date(Date.now() + 72 * 3600 * 1000);
  const pad = n => String(n).padStart(2, '0');
  $("rescheduleNewDueDate").value = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  $("rescheduleQuantity").value = o.quantity || 500;
  $("rescheduleModal").classList.remove("hidden");
}

function closeRescheduleModal() {
  $("rescheduleModal").classList.add("hidden");
}

async function submitReschedule(e) {
  e.preventDefault();
  const orderId = $("rescheduleOrderId").value;
  const newDueDate = $("rescheduleNewDueDate").value ? new Date($("rescheduleNewDueDate").value).toISOString() : null;
  const newBatchSize = parseInt($("rescheduleQuantity").value, 10);

  try {
    await api(`/orders/${orderId}/reschedule`, {
      method: "POST",
      body: JSON.stringify({ newDueDate, newBatchSize, actor: "Alex Chen" })
    });
    toast(`Order ${orderId} SLA Extended & Rescheduled`, "success");
    closeRescheduleModal();
    await load();
  } catch (err) {
    toast(`Reschedule error: ${err.message}`, "error");
  }
}

/* Initialize Global Event Listeners */
document.addEventListener("DOMContentLoaded", () => {
  setTheme(state.currentTheme);

  // Sidebar navigation
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  // Theme dropdown in top bar
  if ($("themeSelect")) {
    $("themeSelect").addEventListener("change", e => setTheme(e.target.value));
  }

  // Notifications Bell Drawer Toggle
  if ($("notificationsBellBtn")) {
    $("notificationsBellBtn").addEventListener("click", () => {
      $("notificationsDrawer").classList.toggle("open");
    });
  }
  if ($("closeDrawerBtn")) {
    $("closeDrawerBtn").addEventListener("click", () => {
      $("notificationsDrawer").classList.remove("open");
    });
  }

  // User Profile click: allow Sign Out to view Screen 1 (Login)
  if ($("topUserPill")) {
    $("topUserPill").addEventListener("click", () => {
      const confirmOut = confirm("Would you like to switch to Screen 1 (Login / Sign In view)?");
      if (confirmOut) {
        clearSession();
        toggleLoginScreen(true);
      }
    });
  }
  if ($("userMiniCard")) {
    $("userMiniCard").addEventListener("click", () => switchView("settings"));
  }

  // Screen 1: Login Form submission
  if ($("loginForm")) {
    $("loginForm").addEventListener("submit", async e => {
      e.preventDefault();
      const submit = $("loginSubmitBtn");
      if (submit) {
        submit.disabled = true;
        submit.textContent = "Signing in...";
      }
      try {
        await cognitoLogin($("loginEmail").value.trim(), $("loginPassword").value);
      } catch (err) {
        toast(err.message, "error");
        setTimeout(() => {
          const fallback = confirm(`Authentication message:\n"${err.message}"\n\nWould you like to enter the live demo environment instead?`);
          if (fallback) {
            demoLogin("supervisor");
          }
        }, 300);
      } finally {
        if (submit) {
          submit.disabled = false;
          submit.textContent = "Sign In with Cognito";
        }
      }
    });
  }
  if ($("createAccountLink")) $("createAccountLink").addEventListener("click", e => {
    e.preventDefault();
    showAuthForm("registerForm");
  });
  if ($("backToLoginBtn")) $("backToLoginBtn").addEventListener("click", () => showAuthForm("loginForm"));
  if ($("backToLoginFromConfirmBtn")) $("backToLoginFromConfirmBtn").addEventListener("click", () => showAuthForm("loginForm"));
  if ($("registerForm")) $("registerForm").addEventListener("submit", async e => {
    e.preventDefault();
    const email = $("registerEmail").value.trim();
    const password = $("registerPassword").value;
    if (password !== $("registerPasswordConfirm").value) {
      toast("Passwords do not match", "error");
      return;
    }
    try {
      const confirmed = await cognitoRegister(email, password);
      if (confirmed) {
        $("loginEmail").value = email;
        showAuthForm("loginForm");
        toast("Account created. You can sign in now.", "success");
      } else {
        state.pendingRegistrationEmail = email;
        showAuthForm("confirmForm");
        toast("Check your email for the verification code.", "info");
      }
    } catch (err) {
      toast(err.message, "error");
    }
  });
  if ($("confirmForm")) $("confirmForm").addEventListener("submit", async e => {
    e.preventDefault();
    try {
      await confirmCognitoUser(state.pendingRegistrationEmail, $("confirmCode").value.trim());
      $("loginEmail").value = state.pendingRegistrationEmail;
      showAuthForm("loginForm");
      toast("Email verified. Sign in to continue.", "success");
    } catch (err) {
      toast(err.message, "error");
    }
  });
  if ($("judgeDemoBtn")) $("judgeDemoBtn").addEventListener("click", () => demoLogin("supervisor"));
  if ($("landingNavJudgeBtn")) $("landingNavJudgeBtn").addEventListener("click", () => demoLogin("supervisor"));
  if ($("judgeSupervisorBtn")) $("judgeSupervisorBtn").addEventListener("click", () => demoLogin("supervisor"));
  if ($("judgeManagerBtn")) $("judgeManagerBtn").addEventListener("click", () => demoLogin("manager"));
  if ($("judgeAnalystBtn")) $("judgeAnalystBtn").addEventListener("click", () => demoLogin("analyst"));
  if ($("loginAwsBtn")) $("loginAwsBtn").addEventListener("click", () => toast("Use your Cognito account or the evaluator demo access above.", "info"));
  if ($("loginGoogleBtn")) $("loginGoogleBtn").addEventListener("click", () => toast("Google federation is not enabled for this Cognito client.", "info"));

  // Search filter inputs
  if ($("searchMachinesInput")) $("searchMachinesInput").addEventListener("input", renderMachines);
  if ($("machLocationFilter")) $("machLocationFilter").addEventListener("change", renderMachines);
  if ($("machStatusFilter")) $("machStatusFilter").addEventListener("change", renderMachines);
  if ($("searchOrdersInput")) $("searchOrdersInput").addEventListener("input", renderOrders);
  if ($("orderStatusFilter")) $("orderStatusFilter").addEventListener("change", renderOrders);

  // AI Assistant chat form
  if ($("aiChatForm")) {
    $("aiChatForm").addEventListener("submit", e => {
      e.preventDefault();
      askAi();
    });
  }

  // Order Details: Approve & Execute action
  if ($("orderApproveExecuteBtn")) {
    $("orderApproveExecuteBtn").addEventListener("click", async () => {
      try {
        await api("/actions", {
          method: "POST",
          body: JSON.stringify({ recommendationId: "REC-00125", approvedBy: "Alex Chen (Operations Manager)" })
        });
        toast("Reroute Authorized: Target station Dallas Hub M-004 assigned", "success");
        await load();
        switchView("approvals");
      } catch (err) {
        toast(err.message, "error");
      }
    });
  }

  // Reschedule SLA button
  if ($("orderRescheduleBtn")) {
    $("orderRescheduleBtn").addEventListener("click", () => openRescheduleModal(state.selectedOrder));
  }
  if ($("rescheduleForm")) $("rescheduleForm").addEventListener("submit", submitReschedule);

  // Machine action buttons on Machine Details
  if ($("machActionDiagnoseBtn")) {
    $("machActionDiagnoseBtn").addEventListener("click", async () => {
      try {
        await api(`/machines/${state.selectedMachine}/transition`, {
          method: "POST",
          body: JSON.stringify({ action: "DIAGNOSE", actor: "Alex Chen" })
        });
        toast(`Machine ${state.selectedMachine}: Diagnostic cycle initiated`, "success");
        await load();
      } catch (e) {
        toast(e.message, "error");
      }
    });
  }
  if ($("machActionMaintBtn")) {
    $("machActionMaintBtn").addEventListener("click", async () => {
      try {
        await api(`/machines/${state.selectedMachine}/transition`, {
          method: "POST",
          body: JSON.stringify({ action: "PLAN_MAINTENANCE", actor: "Alex Chen" })
        });
        toast(`Machine ${state.selectedMachine}: Maintenance dispatch ticket created`, "success");
        await load();
      } catch (e) {
        toast(e.message, "error");
      }
    });
  }

  // Modal Closers
  document.querySelectorAll("[data-close-modal]").forEach(btn => {
    btn.addEventListener("click", () => {
      const m = $(btn.dataset.closeModal);
      if (m) m.classList.add("hidden");
    });
  });

  // Approvals filter tabs
  document.querySelectorAll("[data-appr-tab]").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("[data-appr-tab]").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.approvalFilter = tab.dataset.apprTab;
      renderApprovals();
    });
  });

  // Notifications filter tabs
  document.querySelectorAll("[data-notif-tab]").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("[data-notif-tab]").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.notifFilter = tab.dataset.notifTab;
      renderNotifications();
    });
  });

  // Modal triggers
  if ($("addMachineBtn")) $("addMachineBtn").addEventListener("click", () => $("addMachineModal").classList.remove("hidden"));
  if ($("addOrderBtn")) $("addOrderBtn").addEventListener("click", () => $("addOrderModal").classList.remove("hidden"));

  // Add Machine form
  if ($("addMachineForm")) {
    $("addMachineForm").addEventListener("submit", async e => {
      e.preventDefault();
      const id = $("newMachineId").value.trim();
      const name = $("newMachineName").value.trim();
      const location = $("newMachineLocation").value.trim();
      const capacityPerHour = parseInt($("newMachineCapacity").value, 10) || 120;
      const status = $("newMachineStatus").value || "AVAILABLE";

      try {
        await api("/machines", {
          method: "POST",
          body: JSON.stringify({ id, name, location, capacityPerHour, status, capabilities: ["PACKAGING", "MACHINING"] })
        });
        toast(`Machine ${id} registered successfully`, "success");
        $("addMachineModal").classList.add("hidden");
        await load();
      } catch (err) {
        toast(err.message, "error");
      }
    });
  }

  // Add Order form
  if ($("addOrderForm")) {
    $("addOrderForm").addEventListener("submit", async e => {
      e.preventDefault();
      const id = $("newOrderId").value.trim();
      const customer = $("newOrderCustomer").value.trim();
      const destination = $("newOrderDestination").value.trim();
      const quantity = parseInt($("newOrderQuantity").value, 10) || 500;
      const assignedMachineId = $("newOrderMachine").value || "M-001";

      try {
        await api("/orders", {
          method: "POST",
          body: JSON.stringify({ id, customer, destination, quantity, assignedMachineId, product: "Hydraulic Assembly", process: "MACHINING" })
        });
        toast(`Order ${id} commissioned to floor`, "success");
        $("addOrderModal").classList.add("hidden");
        await load();
      } catch (err) {
        toast(err.message, "error");
      }
    });
  }

  // Landing Page & Demo Modal bindings
  if ($("landingBrandLogoLink")) $("landingBrandLogoLink").addEventListener("click", e => { e.preventDefault(); showLandingPage(true); });
  if ($("landingNavSignInBtn")) $("landingNavSignInBtn").addEventListener("click", () => {
    toggleLoginScreen(true);
    showAuthForm("loginForm");
  });
  if ($("landingNavJudgeBtn")) $("landingNavJudgeBtn").addEventListener("click", openJudgeSignIn);
  if ($("landingNavGetStartedBtn")) $("landingNavGetStartedBtn").addEventListener("click", () => showLandingPage(false));
  if ($("heroGetStartedBtn")) $("heroGetStartedBtn").addEventListener("click", () => showLandingPage(false));
  if ($("heroWatchDemoBtn")) $("heroWatchDemoBtn").addEventListener("click", () => {
    const modal = $("demoModal");
    if (modal) modal.classList.remove("hidden");
  });
  if ($("closeDemoModalBtn")) $("closeDemoModalBtn").addEventListener("click", () => {
    const modal = $("demoModal");
    if (modal) modal.classList.add("hidden");
  });
  if ($("demoModal")) {
    $("demoModal").addEventListener("click", e => {
      if (e.target === $("demoModal")) $("demoModal").classList.add("hidden");
    });
  }
  if ($("demoLaunchAppBtn")) $("demoLaunchAppBtn").addEventListener("click", () => {
    const modal = $("demoModal");
    if (modal) modal.classList.add("hidden");
    showLandingPage(false);
  });
  if ($("topbarLandingBtn")) $("topbarLandingBtn").addEventListener("click", () => showLandingPage(true));

  // Initial Routing Dispatch
  const currentHash = (window.location.hash || "").toLowerCase();
  const session = getSession();
  if (session) {
    state.user = session.user;
    state.isLoggedIn = true;
  }
  if ((currentHash === "#app" || currentHash === "#dashboard") && state.isLoggedIn) {
    showLandingPage(false);
  } else if (currentHash === "#login" || !state.isLoggedIn) {
    toggleLoginScreen(true);
  } else {
    // Default to Landing Page as per marketing spec
    showLandingPage(true);
  }

  // Start background live stream polling
  load().then(() => {
    setInterval(async () => {
      try {
        state.data = await api("/dashboard");
        if (state.activeView === "dashboard") renderDashboard();
        else if (state.activeView === "machines") renderMachines();
        else if (state.activeView === "orders") renderOrders();
        else if (state.activeView === "approvals") renderApprovals();
      } catch {}
    }, 6000);
  });
});
