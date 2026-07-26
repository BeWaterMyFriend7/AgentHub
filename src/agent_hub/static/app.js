const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

const statusText = {
  executing: "执行中",
  waiting_permission: "等待授权",
  waiting_input: "等待输入",
  awaiting_review: "等待验收",
  interrupted: "任务中断",
  closed: "已关闭",
  unknown: "状态未知",
};

let sessions = [];
let agents = [];
let adapterTypes = [];
let modalAction = null;

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || "请求失败");
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  $("#toastWrap").appendChild(node);
  setTimeout(() => node.remove(), 3600);
}

function showModal(title, html, options = {}) {
  $("#modalTitle").textContent = title;
  $("#modalContent").innerHTML = html;
  $("#modalOk").textContent = options.confirmText || "确定";
  $("#modalOk").classList.toggle("danger", Boolean(options.danger));
  $("#modalCancel").classList.toggle("hidden", options.cancel === false);
  modalAction = options.onConfirm || null;
  $("#modal").classList.remove("hidden");
}

function closeModal() {
  $("#modal").classList.add("hidden");
  modalAction = null;
}

function initials(name) {
  return String(name || "AG").split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase();
}

function renderStats(summary) {
  const cards = [
    ["会话总数", summary.total, "ALL"],
    ["执行中", summary.executing, "RUN"],
    ["等待介入", summary.waiting, "WAIT"],
    ["等待验收", summary.awaiting_review, "REVIEW"],
    ["任务中断", summary.interrupted, "STOP"],
  ];
  $("#stats").innerHTML = cards.map(([label, value, code]) => `
    <article class="stat">
      <div class="stat-code">${code}</div>
      <div class="stat-value">${value}</div>
      <div class="stat-label">${label}</div>
    </article>
  `).join("");
}

function attentionCard(session) {
  return `
    <article class="attention-card">
      <div>
        <div class="card-kicker">${escapeHtml(session.agent_name)} · ${escapeHtml(session.project_name)}</div>
        <h3>${escapeHtml(session.title)}</h3>
        <p>${escapeHtml(session.status_reason)}</p>
      </div>
      <div class="card-actions">
        <span class="badge ${session.status}">${statusText[session.status]}</span>
        <button class="button small" data-open-session="${escapeHtml(session.id)}">打开会话</button>
      </div>
    </article>
  `;
}

function renderAttention(items) {
  $("#attentionCount").textContent = items.length;
  $("#attentionList").innerHTML = items.length
    ? items.map(attentionCard).join("")
    : '<div class="empty">当前没有需要人工介入的会话。</div>';
}

function planPercent(session) {
  return session.total_steps ? Math.round(session.completed_steps / session.total_steps * 100) : 0;
}

function sessionCard(session) {
  const hasPlan = session.total_steps > 0;
  const percent = planPercent(session);
  return `
    <article class="session-card">
      <div class="agent-avatar">${initials(session.agent_name)}</div>
      <div class="session-main">
        <div class="session-title">
          <div>
            <div class="card-kicker">${escapeHtml(session.agent_name)} · ${escapeHtml(session.project_name)}</div>
            <h3>${escapeHtml(session.title)}</h3>
          </div>
          <span class="badge ${session.status}">${statusText[session.status]}</span>
        </div>
        <p class="goal">${escapeHtml(session.current_goal || session.status_reason)}</p>
        <div class="session-meta">来源：${escapeHtml(session.status_source)} · 可信度：${escapeHtml(session.confidence)}</div>
        ${session.last_activity ? `<div class="activity">${escapeHtml(session.last_activity)}</div>` : ""}
      </div>
      <div class="plan ${hasPlan ? "" : "no-plan"}">
        <div class="plan-head"><span>Todo 进度</span><strong>${hasPlan ? `${session.completed_steps} / ${session.total_steps}` : "未提供"}</strong></div>
        ${hasPlan ? `<div class="progress"><span style="width:${percent}%"></span></div>` : ""}
        ${session.current_step ? `<div class="current-step">当前：${escapeHtml(session.current_step)}</div>` : ""}
      </div>
      <button class="button small" data-open-session="${escapeHtml(session.id)}" ${session.resumable ? "" : "disabled"}>打开会话</button>
    </article>
  `;
}

function renderSessions() {
  const keyword = $("#searchInput").value.trim().toLowerCase();
  const status = $("#statusFilter").value;
  const filtered = sessions.filter(session => {
    const text = [session.agent_name, session.title, session.project_name, session.current_goal, session.current_step].join(" ").toLowerCase();
    return (!keyword || text.includes(keyword)) && (status === "all" || session.status === status);
  });
  $("#sessionList").innerHTML = filtered.length
    ? filtered.map(sessionCard).join("")
    : '<div class="empty">没有匹配的会话。请检查 Agent Profile 是否启用并通过探测。</div>';
}

function capabilityRow(label, supported) {
  return `<div class="capability"><span>${label}</span><b class="${supported ? "yes" : "no"}">${supported ? "支持" : "不支持"}</b></div>`;
}

function agentCard(agent) {
  const capabilities = agent.capabilities;
  const stateClass = !agent.enabled ? "disabled" : agent.connected ? "connected" : "disconnected";
  const stateText = !agent.enabled ? "已停用" : agent.connected ? "已连接" : "未连接";
  const target = agent.data_path || agent.endpoint || "未配置";
  return `
    <article class="tool-card ${agent.enabled ? "" : "profile-disabled"}">
      <div class="tool-title">
        <div>
          <div class="card-kicker">${escapeHtml(agent.agent_type)} · ${escapeHtml(agent.adapter_kind)}</div>
          <h2>${escapeHtml(agent.name)}</h2>
        </div>
        <span class="connection ${stateClass}">${stateText}</span>
      </div>
      <p class="adapter-name">${escapeHtml(agent.adapter_type)}</p>
      <div class="target" title="${escapeHtml(target)}">${escapeHtml(target)}</div>
      <div class="capabilities">
        ${capabilityRow("会话发现", capabilities.session_discovery)}
        ${capabilityRow("状态识别", capabilities.status_detection)}
        ${capabilityRow("Todo 读取", capabilities.plan_reading)}
        ${capabilityRow("精确恢复", capabilities.exact_resume)}
      </div>
      <div class="probe-message">${escapeHtml(agent.last_probe_message)}</div>
      <div class="tool-actions">
        <button class="button small primary" data-probe-agent="${agent.id}" ${agent.enabled ? "" : "disabled"}>探测</button>
        <button class="button small" data-edit-agent="${agent.id}">编辑</button>
        <button class="button small" data-toggle-agent="${agent.id}">${agent.enabled ? "停用" : "启用"}</button>
        <button class="button small ghost-danger" data-delete-agent="${agent.id}">删除</button>
      </div>
    </article>
  `;
}

function renderAgents() {
  $("#toolGrid").innerHTML = agents.length
    ? agents.map(agentCard).join("")
    : '<div class="empty">尚未配置 Agent Profile。</div>';
  const enabled = agents.filter(agent => agent.enabled).length;
  const connected = agents.filter(agent => agent.enabled && agent.connected).length;
  $("#runtimeState").innerHTML = `<b>${connected} / ${enabled} 已连接</b><span>${sessions.length} 个真实会话</span>`;
}

async function loadData(showToast = false) {
  try {
    const [dashboard, types] = await Promise.all([
      api("/api/dashboard"),
      api("/api/agent-types"),
    ]);
    sessions = dashboard.sessions;
    agents = dashboard.agents;
    adapterTypes = types;
    renderStats(dashboard.summary);
    renderAttention(dashboard.attention);
    renderSessions();
    renderAgents();
    if (showToast) toast("会话状态已刷新");
  } catch (error) {
    toast(error.message);
  }
}

async function openSession(sessionId) {
  try {
    const result = await api(`/api/sessions/${encodeURIComponent(sessionId)}/open`, { method: "POST" });
    showModal(result.ok ? "会话恢复已启动" : "无法打开会话", `
      <div class="result-box ${result.ok ? "success" : "error"}">
        <strong>${escapeHtml(result.message)}</strong>
        <p>动作：${escapeHtml(result.action)}</p>
        <p class="breakable">目标：${escapeHtml(result.resume_target || "无")}</p>
      </div>
    `, { cancel: false });
  } catch (error) {
    toast(error.message);
  }
}

async function probeAgent(agentId) {
  try {
    const result = await api(`/api/agents/${encodeURIComponent(agentId)}/probe`, { method: "POST" });
    const rows = [
      ...(result.checks || []).map(item => `<li class="check">${escapeHtml(item)}</li>`),
      ...(result.failures || []).map(item => `<li class="failure">${escapeHtml(item)}</li>`),
    ].join("");
    showModal(result.title, `<div class="result-box ${result.ok ? "success" : "error"}"><strong>${escapeHtml(result.message)}</strong><ul>${rows}</ul></div>`, { cancel: false });
    await loadData();
  } catch (error) {
    toast(error.message);
  }
}

function typeOptions(selected) {
  return adapterTypes.map(type => `<option value="${type.kind}" ${type.kind === selected ? "selected" : ""}>${escapeHtml(type.name)}</option>`).join("");
}

function fieldValue(profile, definition, key) {
  if (profile && profile[key] != null) return profile[key];
  return definition?.defaults?.[key] ?? "";
}

function renderDynamicFields(profile = null) {
  const kind = $("#adapterKind").value;
  const definition = adapterTypes.find(item => item.kind === kind);
  const labels = {
    endpoint: "Server 地址",
    data_path: "本地数据路径",
    executable: "CLI 可执行文件",
    username: "用户名",
    secret_env: "密码环境变量名",
  };
  const fields = (definition?.fields || []).filter(field => field !== "name");
  $("#dynamicFields").innerHTML = `
    <p class="type-description">${escapeHtml(definition?.description || "")}</p>
    ${fields.map(key => `
      <label class="form-field">
        <span>${labels[key] || key}</span>
        <input name="${key}" value="${escapeHtml(fieldValue(profile, definition, key))}" ${key === "endpoint" ? 'placeholder="http://127.0.0.1:4096"' : ""} />
      </label>
    `).join("")}
  `;
}

function openProfileForm(profile = null) {
  const initialKind = profile?.adapter_kind || adapterTypes[0]?.kind;
  if (!initialKind) {
    toast("没有可用的 Adapter 类型");
    return;
  }
  showModal(profile ? "编辑 Agent Profile" : "新增 Agent Profile", `
    <form id="profileForm" class="profile-form">
      <label class="form-field">
        <span>接入类型</span>
        <select id="adapterKind" name="adapter_kind">${typeOptions(initialKind)}</select>
      </label>
      <label class="form-field">
        <span>Profile 名称</span>
        <input name="name" value="${escapeHtml(profile?.name || "")}" required />
      </label>
      <div id="dynamicFields"></div>
      <label class="toggle-field"><input type="checkbox" name="enabled" ${profile?.enabled === false ? "" : "checked"} /><span>启用此 Profile 并参与会话聚合</span></label>
    </form>
  `, {
    confirmText: profile ? "保存配置" : "创建 Profile",
    onConfirm: async () => saveProfile(profile),
  });
  $("#adapterKind").addEventListener("change", () => renderDynamicFields(null));
  renderDynamicFields(profile);
}

async function saveProfile(profile) {
  const form = $("#profileForm");
  if (!form.reportValidity()) return false;
  const formData = new FormData(form);
  const kind = formData.get("adapter_kind");
  const definition = adapterTypes.find(item => item.kind === kind);
  const payload = {
    name: formData.get("name"),
    agent_type: definition.agent_type,
    adapter_kind: kind,
    enabled: formData.get("enabled") === "on",
  };
  for (const field of definition.fields || []) {
    if (field !== "name") payload[field] = formData.get(field) || null;
  }
  await api(profile ? `/api/agents/${encodeURIComponent(profile.id)}` : "/api/agents", {
    method: profile ? "PUT" : "POST",
    body: JSON.stringify(payload),
  });
  toast(profile ? "Profile 已更新" : "Profile 已创建");
  await loadData();
  return true;
}

async function toggleProfile(profile) {
  await api(`/api/agents/${encodeURIComponent(profile.id)}`, {
    method: "PUT",
    body: JSON.stringify({ enabled: !profile.enabled }),
  });
  toast(profile.enabled ? "Profile 已停用" : "Profile 已启用");
  await loadData();
}

function confirmDelete(profile) {
  showModal("删除 Agent Profile", `<div class="confirm-copy">确定删除 <strong>${escapeHtml(profile.name)}</strong>？此操作只删除 AgentHub 配置，不会删除 Agent 本地数据。</div>`, {
    confirmText: "确认删除",
    danger: true,
    onConfirm: async () => {
      await api(`/api/agents/${encodeURIComponent(profile.id)}`, { method: "DELETE" });
      toast("Profile 已删除");
      await loadData();
      return true;
    },
  });
}

$$('.nav').forEach(button => button.addEventListener("click", () => {
  $$('.nav').forEach(item => item.classList.remove("active"));
  $$('.page').forEach(item => item.classList.remove("active"));
  button.classList.add("active");
  $("#" + button.dataset.page).classList.add("active");
}));

document.addEventListener("click", event => {
  const open = event.target.closest("[data-open-session]");
  if (open) openSession(open.dataset.openSession);
  const probe = event.target.closest("[data-probe-agent]");
  if (probe) probeAgent(probe.dataset.probeAgent);
  const edit = event.target.closest("[data-edit-agent]");
  if (edit) openProfileForm(agents.find(item => item.id === edit.dataset.editAgent));
  const toggle = event.target.closest("[data-toggle-agent]");
  if (toggle) toggleProfile(agents.find(item => item.id === toggle.dataset.toggleAgent));
  const remove = event.target.closest("[data-delete-agent]");
  if (remove) confirmDelete(agents.find(item => item.id === remove.dataset.deleteAgent));
});

$("#modalOk").addEventListener("click", async () => {
  if (!modalAction) return closeModal();
  try {
    $("#modalOk").disabled = true;
    const shouldClose = await modalAction();
    if (shouldClose !== false) closeModal();
  } catch (error) {
    toast(error.message);
  } finally {
    $("#modalOk").disabled = false;
  }
});
$("#modalClose").addEventListener("click", closeModal);
$("#modalCancel").addEventListener("click", closeModal);
$("#modal").addEventListener("click", event => { if (event.target.id === "modal") closeModal(); });
$("#searchInput").addEventListener("input", renderSessions);
$("#statusFilter").addEventListener("change", renderSessions);
$("#refreshBtn").addEventListener("click", () => loadData(true));
$("#addAgentBtn").addEventListener("click", () => openProfileForm());

loadData();
setInterval(() => loadData(false), 30000);
