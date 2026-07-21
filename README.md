# AgentHub

AgentHub 是面向 Windows、macOS、Linux 桌面环境的本地 AI Agent 管理中枢。当前 MVP 用于聚合 Codex、Claude Code、OpenCode 等工具的内部会话；后续在同一应用内增加 Skill、MCP Server 和 Agent 插件管理。

## 仓库结构

```text
AgentHub/
├── agent.md                  # 项目约定与 Agent 协作规则
├── src/
│   ├── agent_hub/            # 当前会话聚合应用
│   └── skill_bridge/         # Skill 管理参考实现
├── docs/
│   ├── prd/                  # 全局产品需求与范围
│   ├── architecture/         # 系统架构、系统级设计与 ADR
│   ├── modules/              # 各模块的需求、设计、BDD、测试与验证
│   ├── process/              # 路线图、待办和经验
│   ├── guides/               # 操作与开发指南
│   └── prototypes/           # 非生产原型
├── scripts/                  # 维护与验证脚本
├── requirements.txt
├── start.bat
└── start.sh
```

修改产品行为或架构前，先阅读[文档索引](./docs/README.md)和[总 PRD](./docs/prd/agenthub-v1.md)。

## 运行 AgentHub

Windows 用户可双击 `start.bat`。脚本会创建 `.venv`、安装依赖、设置 `src` 导入路径、启动 FastAPI，并打开：

```text
http://127.0.0.1:17860
```

手动启动：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = "$PWD\src"
.venv\Scripts\python.exe -m agent_hub.main
```

当前 AgentHub 使用 Mock Adapter，尚未读取或恢复真实的外部 Agent 会话。

## SkillBridge 参考实现

`src/skill_bridge/` 保存已有的 Skill 发现、共享和安全操作实现。它只作为待合并的参考子系统，不再作为独立产品发展。操作前请阅读[操作手册](./docs/guides/skill-bridge-operations.md)，并优先使用测试目录验证。
