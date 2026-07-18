# AgentHub 项目约定

## 项目使命

AgentHub 是 AI 编码工具的本地管理中枢。它聚合 Agent 内部会话，并逐步管理 Skill、MCP Server、插件等可复用能力。产品必须展示真实的内部状态并执行精确操作；仅检测到进程或窗口，不等于已经管理对应会话或能力。

## 仓库导航

- `src/agent_hub/`：当前会话聚合 MVP。
- `src/skill_bridge/`：Skill 发现、共享、审计、回滚和 Windows Junction 处理的参考实现。
- `docs/requirements/`：产品需求与范围。
- `docs/architecture/`：当前架构与子系统边界。
- `docs/architecture/adr/`：需要长期保留的架构决策。
- `docs/testing/`：测试策略与验证证据。
- `docs/prototypes/`：一次性 UI 或技术原型。
- `docs/guides/`：运维和开发操作指南。
- `docs/planning/`：路线图与可执行待办。
- `docs/learnings/`：按日期记录的经验与可复用结论。
- `scripts/`：仓库维护、迁移和验证脚本。

开始工作前先阅读 `docs/README.md`，不得把原型当作生产代码使用。

## 工程规则

1. Agent、Skill、MCP Server 和插件接入必须位于明确的适配器边界之后，能力发现逻辑不得泄漏到 UI 层。
2. 文件系统和工具原生 API 是事实来源。除非 ADR 另有说明，持久化状态只作为缓存或审计记录。
3. 破坏性能力操作必须验证目标；适用时先备份；同时记录审计信息并提供补偿或回滚路径。
4. HTTP Handler 保持轻量：领域状态映射属于 Service，原生调用属于 Adapter 或 Platform，持久化属于 Repository。
5. 新增状态或生命周期转换时，必须补充单元测试，并记录原生事件到统一模型的映射关系。
6. 代码变更导致需求、ADR、测试证据或 TODO 失效时，应在同一次变更中同步更新。优先新增小型编号 ADR，不直接改写历史决定。
7. 先运行聚焦测试，交付前再运行完整验证套件。

## 常用命令

- Windows：`start.bat`
- Linux/macOS：`./start.sh`
- 直接运行：设置 `PYTHONPATH=src`，然后执行 `python -m agent_hub.main`
- SkillBridge 参考实现：进入 `src/skill_bridge` 后执行 `python main.py`

