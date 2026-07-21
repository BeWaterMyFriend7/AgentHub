const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

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

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.message || "请求失败");
  }
  return data;
}

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  $("#toastWrap").appendChild(node);
  setTimeout(() => node.remove(), 3200);
}

function showModal(title, html) {
  $("#modalTitle").textContent = title;
  $("#modalContent").innerHTML = html;
  $("#modal").classList.remove("hidden");
}

function closeModal() {
  $("#modal").classList.add("hidden");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function initials(name) {
  return name.split(/\s+/).map(x => x[0]).join("").slice(0, 2).toUpperCase();
}

function renderStats(summary) {
  const cards = [
    ["会话总数", summary.total, "◈", "已聚合的内部会话"],
    ["执行中", summary.executing, "●", "Agent 正常执行"],
    ["等待授权 / 输入", summary.waiting, "!", "需要立即介入"],
    ["等待验收", summary.awaiting_review, "✓", "执行结束待检查"],
    ["任务中断", summary.interrupted, "×", "需要恢复或排查"],
  ];

  $("#stats").innerHTML = cards.map(([label, value, icon, note]) => `
    <div class="stat">
      <div class="stat-head">
        <span>${label}</span>
        <span class="stat-icon">${icon}</span>
      </div>
      <div class="stat-value">${value}</div>
      <div class="stat-note">${note}</div>
    </div>
  `).join("");
}

function attentionCard(session) {
  return `
    <article class="attention-card">
      <div>
        <h3>${escapeHtml(session.agent_name)} · ${escapeHtml(session.title)}</h3>
        <p>${escapeHtml(session.status_reason)}</p>
        <div class="attention-meta">
          <span class="badge ${session.status}">${statusText[session.status]}</span>
          <span class="badge unknown">${escapeHtml(session.project_name)}</span>
          <span class="badge unknown">${escapeHtml(session.confidence)} 可信度</span>
        </div>
      </div>
      <button class="button small primary" data-open-session="${session.id}">
        打开会话
      </button>
    </article>
  `;
}

function renderAttention(items) {
  $("#attentionCount").textContent = items.length;
  $("#attentionList").innerHTML = items.length
    ? items.map(attentionCard).join("")
    : `<div class="empty">当前没有需要人工介入的会话。</div>`;
}

function planPercent(session) {
  if (!session.total_steps) return 0;
  return Math.round((session.completed_steps / session.total_steps) * 100);
}

function sessionCard(session) {
  const percent = planPercent(session);
  return `
    <article class="session-card">
      <div class="logo">${initials(session.agent_name)}</div>

      <div>
        <div class="session-title">
          <h3>${escapeHtml(session.agent_name)} · ${escapeHtml(session.title)}</h3>
          <span class="badge ${session.status}">${statusText[session.status]}</span>
        </div>
        <div class="goal">${escapeHtml(session.current_goal)}</div>
        <div class="meta">
          项目：${escapeHtml(session.project_name)}
          · 状态来源：${escapeHtml(session.status_source)}
          · 可信度：${escapeHtml(session.confidence)}
        </div>
        <div class="activity">最近活动：${escapeHtml(session.last_activity)}</div>
      </div>

      <div class="plan">
        <div class="plan-head">
          <span>规划进度</span>
          <strong>${session.completed_steps} / ${session.total_steps || "-"}</strong>
        </div>
        <div class="progress"><span style="width:${percent}%"></span></div>
        <div class="current-step">当前步骤：${escapeHtml(session.current_step)}</div>
      </div>

      <button class="button small ${session.resumable ? "soft" : ""}"
        data-open-session="${session.id}"
        ${session.resumable ? "" : "disabled"}>
        ${session.status === "closed" ? "查看会话" : "打开会话"}
      </button>
    </article>
  `;
}

function renderSessions() {
  const keyword = $("#searchInput").value.trim().toLowerCase();
  const status = $("#statusFilter").value;

  const filtered = sessions.filter(session => {
    const haystack = [
      session.agent_name,
      session.title,
      session.project_name,
      session.current_goal,
      session.current_step,
    ].join(" ").toLowerCase();

    return (!keyword || haystack.includes(keyword))
      && (status === "all" || session.status === status);
  });

  $("#sessionList").innerHTML = filtered.length
    ? filtered.map(sessionCard).join("")
    : `<div class="empty">没有匹配的会话。</div>`;
}

function capabilityRow(label, supported) {
  return `
    <div class="capability">
      <span>${label}</span>
      <span class="${supported ? "yes" : "no"}">${supported ? "支持" : "不支持"}</span>
    </div>
  `;
}

function agentCard(agent) {
  const c = agent.capabilities;
  return `
    <article class="tool-card">
      <div class="tool-title">
        <h2>${escapeHtml(agent.name)}</h2>
        <span class="badge ${agent.connected ? "executing" : "interrupted"}">
          ${agent.connected ? "已连接" : "未连接"}
        </span>
      </div>
      <p>
        ${escapeHtml(agent.adapter_type)}<br>
        状态来源：${escapeHtml(agent.status_source)}<br>
        连接：${escapeHtml(agent.endpoint)}
      </p>
      <div class="capabilities">
        ${capabilityRow("内部会话发现", c.session_discovery)}
        ${capabilityRow("独立状态识别", c.status_detection)}
        ${capabilityRow("规划 / Todo 读取", c.plan_reading)}
        ${capabilityRow("精确恢复会话", c.exact_resume)}
        ${capabilityRow("事件流", c.event_stream)}
      </div>
      <button class="button small primary" data-probe-agent="${agent.id}">
        探测接入能力
      </button>
    </article>
  `;
}

function renderAgents() {
  $("#toolGrid").innerHTML = agents.map(agentCard).join("");
}

async function loadData(showToast = false) {
  try {
    const [summary, allSessions, attention, agentList] = await Promise.all([
      api("/api/summary"),
      api("/api/sessions"),
      api("/api/attention"),
      api("/api/agents"),
    ]);

    sessions = allSessions;
    agents = agentList;
    renderStats(summary);
    renderAttention(attention);
    renderSessions();
    renderAgents();

    if (showToast) toast("会话状态已刷新");
  } catch (error) {
    toast(error.message);
  }
}

async function openSession(sessionId) {
  try {
    const result = await api(`/api/sessions/${encodeURIComponent(sessionId)}/open`, {
      method: "POST",
    });
    showModal(
      result.ok ? "已调用会话恢复适配器" : "无法精确恢复",
      `<div class="result-box ${result.ok ? "success" : "error"}">
        <strong>${escapeHtml(result.message)}</strong>
        <p>动作：${escapeHtml(result.action)}</p>
        <p>恢复目标：${escapeHtml(result.resume_target || "无")}</p>
        <p>当前为 Demo。接入真实 Agent 后，这里会调用 App Server、Hooks、Server API 或 CLI Resume。</p>
      </div>`
    );
  } catch (error) {
    toast(error.message);
  }
}

async function probeAgent(agentId) {
  try {
    const result = await api(`/api/agents/${encodeURIComponent(agentId)}/probe`, {
      method: "POST",
    });
    const rows = [
      ...(result.checks || []).map(item => `<li>✓ ${escapeHtml(item)}</li>`),
      ...(result.failures || []).map(item => `<li>× ${escapeHtml(item)}</li>`),
    ].join("");

    showModal(
      result.title,
      `<div class="result-box ${result.ok ? "success" : "error"}">
        <strong>${escapeHtml(result.message)}</strong>
        <ul>${rows}</ul>
      </div>`
    );
    await loadData();
  } catch (error) {
    toast(error.message);
  }
}

async function advanceDemo() {
  $("#tickBtn").disabled = true;
  try {
    const result = await api("/api/demo/tick", { method: "POST" });
    toast(result.message);
    await loadData();
  } catch (error) {
    toast(error.message);
  } finally {
    $("#tickBtn").disabled = false;
  }
}

$$(".nav").forEach(button => {
  button.addEventListener("click", () => {
    $$(".nav").forEach(item => item.classList.remove("active"));
    $$(".page").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    $("#" + button.dataset.page).classList.add("active");
  });
});

document.addEventListener("click", event => {
  const open = event.target.closest("[data-open-session]");
  if (open) openSession(open.dataset.openSession);

  const probe = event.target.closest("[data-probe-agent]");
  if (probe) probeAgent(probe.dataset.probeAgent);
});

$("#searchInput").addEventListener("input", renderSessions);
$("#statusFilter").addEventListener("change", renderSessions);
$("#refreshBtn").addEventListener("click", () => loadData(true));
$("#tickBtn").addEventListener("click", advanceDemo);
$("#modalClose").addEventListener("click", closeModal);
$("#modalOk").addEventListener("click", closeModal);
$("#modal").addEventListener("click", event => {
  if (event.target.id === "modal") closeModal();
});

loadData();
setInterval(() => loadData(false), 5000);
