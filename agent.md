# AgentHub 项目约定

## 项目使命

AgentHub 是跨 Windows、macOS、Linux 的本地 AI Agent 管理中枢。它聚合 Agent 内部会话，并管理 Skill、MCP Server、Agent 插件等可复用能力。产品必须展示真实内部状态并执行精确操作；仅检测到进程、窗口或目录链接，不等于已经管理或原生加载对应会话或能力。

## 仓库导航

- `src/agent_hub/`：当前会话聚合 MVP，未来承载唯一的 AgentHub 应用。
- `docs/prd/`：全局产品需求、范围和业务事实来源。
- `docs/architecture/`：系统现状、系统级设计和需要长期保留的 ADR。
- `docs/modules/`：Agents、Sessions、Capabilities、Operations 的需求、设计、BDD、测试和验证证据。
- `docs/process/`：路线图、当前待办和经验记录。
- `docs/prototypes/`：一次性 UI 或技术原型。
- `docs/guides/`：运维和开发操作指南。
- `scripts/`：仓库维护、迁移和验证脚本。

开始工作前先阅读 `docs/README.md`。不得把原型当作生产代码，不得把模块需求当作总 PRD 的替代品。

## 工程规则

1. Agent、Skill、MCP Server 和插件接入必须位于明确的 Adapter 边界之后，原生发现逻辑不得泄漏到 UI。
2. 文件系统和 Agent 原生 API/配置是事实来源；持久化状态只作为配置、索引、快照或审计。
3. 破坏性操作必须验证目标，适用时先备份，记录审计，并提供补偿或回滚路径。
4. HTTP Handler 保持轻量：领域状态映射属于 Service，原生调用属于 Adapter 或 Platform，持久化属于 Repository。
5. 新增状态或生命周期转换时，必须补充单元测试，并记录原生事件到统一模型的映射。
6. 总 PRD 说明为什么做、为谁做和做什么；模块需求细化边界；设计说明如何实现；ADR 记录难以逆转的选择；BDD 表达可观察的业务行为。它们不得互相替代。
7. 代码变更导致 PRD、模块文档、ADR、BDD、验证证据或 TODO 失效时，应在同一次变更中同步更新。
8. 先运行聚焦测试，交付前再运行完整验证套件。

## 常用命令

- Windows：`start.bat`
- Linux/macOS：`./start.sh`
- 直接运行：设置 `PYTHONPATH=src`，然后执行 `python -m agent_hub.main`
