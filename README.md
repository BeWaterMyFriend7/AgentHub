# AgentHub

AgentHub 是一个面向 Windows、macOS、Linux 桌面环境的本地 AI 编码 Agent 管理台。当前 MVP 用于聚合 Codex、Claude Code、OpenCode 等工具的内部会话；下一阶段将增加 Skill、MCP Server 和 Agent 插件管理能力。

## 仓库结构

```text
AgentHub/
├── agent.md                  # 项目约定与 Agent 协作规则
├── src/
│   ├── agent_hub/            # 会话聚合应用
│   └── skill_bridge/         # Skill 管理参考实现
├── docs/
│   ├── prd/                  # 产品需求与范围
│   ├── architecture/         # 当前架构、技术设计与 ADR
│   ├── quality/              # BDD、测试策略与验证证据
│   ├── process/              # 路线图、待办和经验
│   ├── guides/               # 操作与开发指南
│   └── prototypes/           # 非生产原型
├── scripts/                  # 维护与验证脚本
├── requirements.txt
├── start.bat
└── start.sh
```

修改产品行为或架构前，请先阅读 [`docs/README.md`](docs/README.md) 和总 PRD [`docs/prd/agenthub-v1.md`](docs/prd/agenthub-v1.md)。

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

`src/skill_bridge/` 保存已有的 Skill 管理实现及其技术说明。可独立运行：

```powershell
Set-Location src\skill_bridge
..\..\.venv\Scripts\python.exe main.py
```

服务监听 `http://127.0.0.1:17890`。它会执行真实的 Windows 文件系统操作，请先阅读操作手册，并优先使用测试目录验证。
