# AgentHub

AgentHub 是面向 Windows、macOS、Linux 桌面环境的本地 AI Agent 管理中枢。当前 MVP 用于聚合 Codex、Claude Code、OpenCode 等工具的内部会话；后续在同一应用内增加 Skill、MCP Server 和 Agent 插件管理。

## 仓库结构

```text
AgentHub/
├── .codegraph/               # CodeGraph 项目标记；本机索引数据库不提交
├── agent.md                  # 项目约定与 Agent 协作规则
├── src/
│   └── agent_hub/            # AgentHub 模块化单体实现
├── docs/
│   ├── README.md             # 产品范围与文档索引
│   ├── architecture/         # 统一系统架构与 ADR
│   ├── modules/              # 各模块的需求、设计、测试与验证
│   ├── process/              # 路线图、待办和经验
│   ├── guides/               # 操作与开发指南
│   └── prototypes/           # 非生产原型
├── scripts/                  # 维护与验证脚本
├── requirements.txt
├── start.bat
└── start.sh
```

修改产品行为或架构前，先阅读[文档索引](./docs/README.md)、[系统架构](./docs/architecture/architecture.md)和对应模块的 `requirements.md`。

## 代码索引

本项目统一使用 CodeGraph 理解源码关系，不再维护 Graphify 索引。首次克隆或本机尚无索引时执行：

```powershell
codegraph init .
codegraph status .
```

查询代码优先使用 `codegraph explore "问题"` 或 `codegraph node <符号或文件>`；源码变更后执行 `codegraph sync .`。`.codegraph/.gitignore` 会随仓库提交，实际索引数据库仅保存在本机。详细说明见 [CodeGraph 使用指南](./docs/guides/codegraph.md)。

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

## SkillBridge 迁移状态

SkillBridge 的 Skill 扫描、状态聚合、目录共享、备份与回滚能力已经分别提取到 `agent_hub/capabilities`、`agent_hub/operations` 和 `agent_hub/platform`。旧的独立应用源码已经从 `src/` 移除；历史需求和逐文件迁移结论见 [SkillBridge 迁移记录](./docs/modules/capabilities/references/skill-bridge-migration.md)，完整旧实现仍可通过 Git 历史追溯。
