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
let discoveredCandidates = [];
let providerState = { providers: [], defaults: [], integrations: [] };
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
    ["会话总数", summary.total, "ALL", "all"],
    ["执行中", summary.executing, "RUN", "executing"],
    ["等待介入", summary.waiting, "WAIT", "waiting"],
    ["等待验收", summary.awaiting_review, "REVIEW", "awaiting_review"],
    ["任务中断", summary.interrupted, "STOP", "interrupted"],
  ];
  $("#stats").innerHTML = cards.map(([label, value, code, filterValue]) => `
    <article class="stat" data-filter-status="${filterValue}">
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

function renderExecuting(items) {
  $("#executingCount").textContent = items.length;
  $("#executingList").innerHTML = items.length
    ? items.map(attentionCard).join("")
    : '<div class="empty">当前没有正在执行的会话。</div>';
}

function planPercent(session) {
  return session.total_steps ? Math.round(session.completed_steps / session.total_steps * 100) : 0;
}

function sessionCard(session) {
  const hasPlan = session.total_steps > 0;
  const percent = planPercent(session);
  const ignoredClass = session.ignored ? "ignored" : "";
  const ignoredBadge = session.ignored ? '<span class="badge ignored-badge">已忽略</span>' : "";
  const agent = agents.find(item => item.id === session.agent_id);
  const routable = ["codex", "claude_code"].includes(agent?.agent_type);
  const routeLabel = session.provider_id && session.model_id
    ? `${session.provider_id}/${session.model_id}`
    : "未配置路由";
  const routeMode = session.route_source === "session" ? "会话固定" : session.route_source === "default" ? "跟随默认" : "未绑定";
  return `
    <article class="session-card ${ignoredClass}">
      <div class="agent-avatar">${initials(session.agent_name)}</div>
      <div class="session-main">
        <div class="session-title">
          <div>
            <div class="card-kicker">${escapeHtml(session.agent_name)} · ${escapeHtml(session.project_name)}</div>
            <h3>${escapeHtml(session.title)}</h3>
          </div>
          <div class="badges">
            <span class="badge ${session.status}">${statusText[session.status]}</span>
            ${ignoredBadge}
          </div>
        </div>
        <p class="goal">${escapeHtml(session.current_goal || session.status_reason)}</p>
        <div class="session-meta">来源：${escapeHtml(session.status_source)} · 可信度：${escapeHtml(session.confidence)}</div>
        ${routable ? `<div class="route-meta"><b>${escapeHtml(routeLabel)}</b><span>${routeMode}</span></div>` : ""}
        ${session.last_activity ? `<div class="activity">${escapeHtml(session.last_activity)}</div>` : ""}
      </div>
      <div class="session-actions">
        <button class="button small" data-open-session="${escapeHtml(session.id)}" ${session.resumable ? "" : "disabled"}>打开会话</button>
        ${routable ? `<button class="button small" data-route-session="${escapeHtml(session.id)}">模型路由</button>` : ""}
        ${session.status === "interrupted" ? `
          <button class="button small primary" data-mark-complete="${escapeHtml(session.id)}">标记完成</button>
        ` : ""}
      </div>
    </article>
  `;
}

function renderSessions() {
  const keyword = $("#searchInput").value.trim().toLowerCase();
  const status = $("#statusFilter").value;
  const showIgnored = $("#showIgnored").checked;
  const filtered = sessions.filter(session => {
    const text = [session.agent_name, session.title, session.project_name, session.current_goal, session.current_step].join(" ").toLowerCase();
    const keywordMatch = !keyword || text.includes(keyword);
    const statusMatch = status === "all" || session.status === status;
    const ignoredMatch = showIgnored || !session.ignored;
    return keywordMatch && statusMatch && ignoredMatch;
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

function providerById(providerId) {
  return providerState.providers.find(item => item.id === providerId);
}

function defaultFor(client) {
  return providerState.defaults.find(item => item.client === client);
}

function integrationFor(client) {
  return providerState.integrations.find(item => item.client === client) || { active: false, changed_externally: false };
}

function providerOptions(selected = "") {
  return providerState.providers
    .filter(item => item.enabled)
    .map(item => `<option value="${escapeHtml(item.id)}" ${item.id === selected ? "selected" : ""}>${escapeHtml(item.name)} · ${escapeHtml(item.protocol)}</option>`)
    .join("");
}

function modelOptions(providerId, selected = "") {
  const provider = providerById(providerId);
  return (provider?.models || []).map(model => `<option value="${escapeHtml(model)}" ${model === selected ? "selected" : ""}>${escapeHtml(model)}</option>`).join("");
}

function routeCard(client, label) {
  const route = defaultFor(client);
  const providerId = route?.provider_id || providerState.providers.find(item => item.enabled)?.id || "";
  const model = route?.model || providerById(providerId)?.models?.[0] || "";
  const integration = integrationFor(client);
  const stateClass = integration.changed_externally ? "disconnected" : integration.active ? "connected" : "disabled";
  const stateText = integration.changed_externally ? "配置已外部修改" : integration.active ? "代理已接管" : "尚未接管";
  return `
    <article class="route-card" data-client-route="${client}">
      <div class="route-card-head">
        <div><span class="card-kicker">CLIENT ROUTE</span><h3>${label}</h3></div>
        <span class="connection ${stateClass}">${stateText}</span>
      </div>
      <label class="form-field"><span>Provider</span><select data-route-provider>${providerOptions(providerId)}</select></label>
      <label class="form-field"><span>模型</span><select data-route-model>${modelOptions(providerId, model)}</select></label>
      <p class="integration-path">${escapeHtml(integration.config_path || "")}</p>
      <div class="tool-actions">
        <button class="button small primary" data-save-route="${client}">保存默认路由</button>
        <button class="button small" data-toggle-integration="${client}" data-active="${integration.active}">${integration.active ? "恢复原配置" : "启用客户端接管"}</button>
      </div>
    </article>
  `;
}

function providerCard(provider) {
  const models = provider.models.length ? provider.models.join(" · ") : "未声明模型";
  return `
    <article class="provider-card ${provider.enabled ? "" : "profile-disabled"}">
      <div class="tool-title">
        <div><div class="card-kicker">${escapeHtml(provider.protocol)}</div><h2>${escapeHtml(provider.name)}</h2></div>
        <span class="connection ${provider.credential_available || !provider.secret_env ? "connected" : "disconnected"}">${provider.secret_env ? (provider.credential_available ? "凭据可用" : "凭据缺失") : "无需凭据"}</span>
      </div>
      <div class="target" title="${escapeHtml(provider.base_url)}">${escapeHtml(provider.base_url)}</div>
      <p class="provider-models">${escapeHtml(models)}</p>
      <div class="provider-env">环境变量：${escapeHtml(provider.secret_env || "无")}</div>
      <div class="tool-actions">
        <button class="button small primary" data-test-provider="${escapeHtml(provider.id)}">测试连接</button>
        <button class="button small" data-edit-provider="${escapeHtml(provider.id)}">编辑</button>
        <button class="button small ghost-danger" data-delete-provider="${escapeHtml(provider.id)}">删除</button>
      </div>
    </article>
  `;
}

function renderProviders() {
  $("#routeGrid").innerHTML = [
    routeCard("codex", "Codex"),
    routeCard("claude_code", "Claude Code"),
  ].join("");
  $("#providerCount").textContent = providerState.providers.length;
  $("#providerGrid").innerHTML = providerState.providers.length
    ? providerState.providers.map(providerCard).join("")
    : '<div class="empty">尚未添加 Provider。先新增厂商，再为 Codex 或 Claude Code 设置默认路由。</div>';
}

async function loadData(showToast = false) {
  try {
    const [dashboard, types, providerPayload] = await Promise.all([
      api("/api/dashboard"),
      api("/api/agent-types"),
      api("/api/providers"),
    ]);
    sessions = dashboard.sessions;
    agents = dashboard.agents;
    adapterTypes = types;
    providerState = providerPayload;
    renderStats(dashboard.summary);
    renderAttention(dashboard.attention);
    const executing = sessions.filter(s => s.status === "executing");
    renderExecuting(executing);
    renderSessions();
    renderAgents();
    renderProviders();
    if (showToast) toast("会话状态已刷新");
  } catch (error) {
    toast(error.message);
  }
}

async function saveDefaultRoute(client) {
  const card = document.querySelector(`[data-client-route="${client}"]`);
  const providerId = card.querySelector("[data-route-provider]").value;
  const model = card.querySelector("[data-route-model]").value;
  if (!providerId || !model) throw new Error("请先选择 Provider 和模型");
  await api(`/api/providers/routes/${client}`, {
    method: "PUT",
    body: JSON.stringify({ provider_id: providerId, model }),
  });
  toast("默认模型路由已保存");
  await loadData();
}

async function toggleClientIntegration(client, active) {
  const action = active ? "disable" : "enable";
  const result = await api(`/api/clients/${client}/integration/${action}`, { method: "POST" });
  toast(result.message);
  await loadData();
}

async function testProvider(providerId) {
  const result = await api(`/api/providers/${encodeURIComponent(providerId)}/test`, { method: "POST" });
  showModal(result.ok ? "Provider 连接成功" : "Provider 连接失败", `
    <div class="result-box ${result.ok ? "success" : "error"}">
      <strong>${escapeHtml(result.message)}</strong>
      <p>${result.models?.length ? `发现模型：${escapeHtml(result.models.join("、"))}` : "未返回模型列表"}</p>
    </div>
  `, { cancel: false });
}

function openProviderForm(provider = null) {
  showModal(provider ? "编辑 Provider" : "新增 Provider", `
    <form id="providerForm" class="profile-form">
      <label class="form-field"><span>Provider ID</span><input name="id" value="${escapeHtml(provider?.id || "")}" pattern="[a-z0-9](?:[a-z0-9_]|-)*" ${provider ? "readonly" : ""} required /></label>
      <label class="form-field"><span>显示名称</span><input name="name" value="${escapeHtml(provider?.name || "")}" required /></label>
      <label class="form-field"><span>上游协议</span><select name="protocol">
        <option value="openai_responses" ${provider?.protocol === "openai_responses" ? "selected" : ""}>OpenAI Responses</option>
        <option value="openai_compatible" ${provider?.protocol === "openai_compatible" ? "selected" : ""}>OpenAI-compatible Chat Completions</option>
        <option value="anthropic" ${provider?.protocol === "anthropic" ? "selected" : ""}>Anthropic Messages</option>
      </select></label>
      <label class="form-field"><span>Base URL</span><input name="base_url" value="${escapeHtml(provider?.base_url || "")}" placeholder="https://api.example.com/v1" required /></label>
      <label class="form-field"><span>API Key 环境变量名</span><input name="secret_env" value="${escapeHtml(provider?.secret_env || "")}" placeholder="PROVIDER_API_KEY" /></label>
      <label class="form-field"><span>模型列表（每行一个）</span><textarea name="models" rows="5" placeholder="model-a\nmodel-b">${escapeHtml((provider?.models || []).join("\n"))}</textarea></label>
      <label class="toggle-field"><input type="checkbox" name="enabled" ${provider?.enabled === false ? "" : "checked"} /><span>启用此 Provider</span></label>
    </form>
  `, {
    confirmText: provider ? "保存 Provider" : "创建 Provider",
    onConfirm: async () => saveProvider(provider),
  });
}

async function saveProvider(existing) {
  const form = $("#providerForm");
  if (!form.reportValidity()) return false;
  const data = new FormData(form);
  const payload = {
    id: data.get("id").trim(),
    name: data.get("name").trim(),
    protocol: data.get("protocol"),
    base_url: data.get("base_url").trim(),
    secret_env: data.get("secret_env").trim(),
    models: data.get("models").split(/\r?\n|,/).map(item => item.trim()).filter(Boolean),
    enabled: data.get("enabled") === "on",
  };
  await api(existing ? `/api/providers/${encodeURIComponent(existing.id)}` : "/api/providers", {
    method: existing ? "PUT" : "POST",
    body: JSON.stringify(payload),
  });
  toast(existing ? "Provider 已更新" : "Provider 已创建");
  await loadData();
  return true;
}

function confirmDeleteProvider(provider) {
  showModal("删除 Provider", `<div class="confirm-copy">确定删除 <strong>${escapeHtml(provider.name)}</strong>？引用它的默认路由会同时失效。</div>`, {
    confirmText: "确认删除",
    danger: true,
    onConfirm: async () => {
      await api(`/api/providers/${encodeURIComponent(provider.id)}`, { method: "DELETE" });
      toast("Provider 已删除");
      await loadData();
      return true;
    },
  });
}

function openSessionRouteForm(session) {
  const selectedProvider = session.provider_id || providerState.providers.find(item => item.enabled)?.id || "";
  if (!selectedProvider) {
    toast("请先添加 Provider");
    return;
  }
  showModal("设置会话模型路由", `
    <form id="sessionRouteForm" class="profile-form">
      <p class="type-description">${escapeHtml(session.title)}<br />旧会话默认保持当前绑定；勾选跟随默认后会移除会话级固定路由。</p>
      <label class="form-field"><span>Provider</span><select id="sessionRouteProvider">${providerOptions(selectedProvider)}</select></label>
      <label class="form-field"><span>模型</span><select id="sessionRouteModel">${modelOptions(selectedProvider, session.model_id || "")}</select></label>
      <label class="toggle-field"><input id="sessionFollowDefault" type="checkbox" ${session.follows_default_route ? "checked" : ""} /><span>从下一轮开始跟随客户端默认路由</span></label>
    </form>
  `, {
    confirmText: "保存会话路由",
    onConfirm: async () => {
      const followDefault = $("#sessionFollowDefault").checked;
      await api(`/api/sessions/${encodeURIComponent(session.id)}/route`, {
        method: "PUT",
        body: JSON.stringify({
          follow_default: followDefault,
          provider_id: followDefault ? null : $("#sessionRouteProvider").value,
          model: followDefault ? null : $("#sessionRouteModel").value,
        }),
      });
      toast("会话路由已更新");
      await loadData();
      return true;
    },
  });
  $("#sessionRouteProvider").addEventListener("change", event => {
    $("#sessionRouteModel").innerHTML = modelOptions(event.target.value);
    $("#sessionFollowDefault").checked = false;
  });
  $("#sessionRouteModel").addEventListener("change", () => {
    $("#sessionFollowDefault").checked = false;
  });
}

async function discoverAgents() {
  try {
    const result = await api("/api/agents/discover");
    discoveredCandidates = result.candidates;
    if (discoveredCandidates.length === 0) {
      toast("未发现已安装的 Agent");
      return;
    }
    showDiscoveryModal();
  } catch (error) {
    toast(error.message);
  }
}

async function markSessionComplete(sessionId) {
  try {
    await api(`/api/sessions/${encodeURIComponent(sessionId)}/mark-complete`, {
      method: "POST",
    });
    toast("会话已标记为完成");
    await loadData();
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

function showDiscoveryModal() {
  const candidatesList = discoveredCandidates.map((candidate, index) => {
    const confidenceBadge = {
      high: '<span class="confidence-badge high">高可信</span>',
      medium: '<span class="confidence-badge medium">中等</span>',
      low: '<span class="confidence-badge low">需配置</span>',
    }[candidate.confidence];
    return `
      <div class="discovery-card">
        <div class="discovery-head">
          <label class="discovery-checkbox">
            <input type="checkbox" data-candidate-index="${index}" ${candidate.confidence !== "low" ? "checked" : ""} />
            <div>
              <strong>${escapeHtml(candidate.name)}</strong>
              <span>${escapeHtml(candidate.description)}</span>
            </div>
          </label>
          ${confidenceBadge}
        </div>
        <div class="discovery-details">
          ${candidate.check_details.map(detail => `<div>• ${escapeHtml(detail)}</div>`).join("")}
        </div>
      </div>
    `;
  }).join("");

  showModal("发现 Agent 候选配置", `
    <div class="discovery-list">
      <p class="discovery-intro">已在本机发现以下 Agent，可选择添加到 AgentHub：</p>
      ${candidatesList}
      <p class="discovery-note">提示：添加后可在 Agent 配置页面修改路径和参数</p>
    </div>
  `, {
    confirmText: "添加选中项",
    onConfirm: async () => {
      const selected = [...document.querySelectorAll("[data-candidate-index]:checked")].map(
        el => discoveredCandidates[parseInt(el.dataset.candidateIndex)]
      );
      if (selected.length === 0) {
        toast("未选择任何 Agent");
        return false;
      }
      let successCount = 0;
      for (const candidate of selected) {
        try {
          await api("/api/agents", {
            method: "POST",
            body: JSON.stringify({
              name: candidate.name,
              agent_type: candidate.agent_type,
              adapter_kind: candidate.adapter_kind,
              data_path: candidate.data_path || null,
              endpoint: candidate.endpoint || "",
              executable: candidate.executable || null,
              enabled: true,
            }),
          });
          successCount++;
        } catch (error) {
          console.error(`添加 ${candidate.name} 失败:`, error);
        }
      }
      toast(`成功添加 ${successCount} 个 Agent Profile`);
      await loadData();
      return true;
    },
  });
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
  const stat = event.target.closest("[data-filter-status]");
  if (stat) {
    const status = stat.dataset.filterStatus;
    // 处理"等待介入"的特殊情况，需要多个状态
    if (status === "waiting") {
      $("#statusFilter").value = "waiting_permission";
    } else {
      $("#statusFilter").value = status;
    }
    $("#statusFilter").dispatchEvent(new Event("change"));
  }
  const ignore = event.target.closest("[data-mark-complete]");
  if (ignore) markSessionComplete(ignore.dataset.markComplete);
  const routeSession = event.target.closest("[data-route-session]");
  if (routeSession) openSessionRouteForm(sessions.find(item => item.id === routeSession.dataset.routeSession));
  const saveRoute = event.target.closest("[data-save-route]");
  if (saveRoute) saveDefaultRoute(saveRoute.dataset.saveRoute).catch(error => toast(error.message));
  const integration = event.target.closest("[data-toggle-integration]");
  if (integration) toggleClientIntegration(
    integration.dataset.toggleIntegration,
    integration.dataset.active === "true",
  ).catch(error => toast(error.message));
  const test = event.target.closest("[data-test-provider]");
  if (test) testProvider(test.dataset.testProvider).catch(error => toast(error.message));
  const editProvider = event.target.closest("[data-edit-provider]");
  if (editProvider) openProviderForm(providerById(editProvider.dataset.editProvider));
  const deleteProvider = event.target.closest("[data-delete-provider]");
  if (deleteProvider) confirmDeleteProvider(providerById(deleteProvider.dataset.deleteProvider));
});

document.addEventListener("change", event => {
  const providerSelect = event.target.closest("[data-route-provider]");
  if (providerSelect) {
    const card = providerSelect.closest("[data-client-route]");
    card.querySelector("[data-route-model]").innerHTML = modelOptions(providerSelect.value);
  }
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
$("#showIgnored").addEventListener("change", renderSessions);
$("#refreshBtn").addEventListener("click", () => loadData(true));
$("#addAgentBtn").addEventListener("click", () => openProfileForm());
$("#discoverAgentsBtn").addEventListener("click", discoverAgents);
$("#addProviderBtn").addEventListener("click", () => openProviderForm());

loadData();
setInterval(() => loadData(false), 30000);
