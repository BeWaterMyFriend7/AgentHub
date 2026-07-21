# SkillBridge 参考实现

> 本代码保留在 `src/skill_bridge/`，作为 AgentHub 能力管理的参考实现，目前尚未接入 AgentHub 主运行进程。当前需求见 `docs/modules/capabilities/requirements.md`，早期 SkillBridge 文档归档于 `docs/modules/capabilities/references/skill-management-v1.0.md`，操作手册见 `docs/guides/skill-bridge-operations.md`。

本地 Agent Skill 共享管理器。在同一个机器上管理多个 AI 编码 Agent（如 Codex、OpenCode、Claude Code）的 Skill 目录，通过 NTFS Junction 实现"一份 Skill，多 Agent 使用"，避免重复安装和版本漂移。

---

## 架构概览

```
浏览器 (127.0.0.1:17890)
        │ HTTP / JSON
        ▼
FastAPI 服务
├── Agent 配置管理 (settings page)
├── Skill 扫描引擎 (scanner)
├── Skill 聚合与状态机 (catalog)
├── 共享操作编排 (sharing)
├── 操作日志与回滚 (database + rollback API)
└── Windows Junction 适配器 (platform/windows)
        │
        ├── C:\Users\xxx\.codex\skills\skill-a          (源: 真实目录)
        ├── C:\Users\xxx\.config\opencode\skills\skill-a (共享: Junction → 源)
        └── C:\Users\xxx\.config\claude\skills\skill-a   (无目录 → 未启用)
```

## 技术栈

| 层次     | 方案                           |
|----------|--------------------------------|
| 后端     | Python 3.10+ / FastAPI         |
| 前端     | Jinja2 服务端渲染 + vanilla JS |
| 数据库   | SQLite 3（内置 `sqlite3` 模块） |
| 系统操作 | PowerShell + NTFS Junction     |
| 样式     | 纯 CSS（无前端构建）           |

## 项目结构

```
skill-bridge/
├── main.py                     # 启动入口
├── requirements.txt
├── require.md                  # 原始需求文档
├── README.md                   # 本文档（技术说明）
├── 操作手册.md                  # 用户操作指南
├── skillbridge/                # 主包
│   ├── __init__.py
│   ├── routes.py               # FastAPI 路由 + 中间件
│   ├── config.py               # 配置常量 + 默认 Agent
│   ├── database.py             # SQLite CRUD + JSON 字段解析
│   ├── scanner.py              # 目录扫描 + SKILL.md 解析 + 指纹
│   ├── catalog.py              # Skill 聚合 + 状态判定 + 源推断
│   ├── sharing.py              # 启用/停用共享 + 回滚 + 源迁移
│   ├── models.py               # Pydantic 数据模型
│   ├── security.py             # 路径校验 + 会话令牌
│   ├── platform/
│   │   ├── __init__.py
│   │   └── windows.py          # PowerShell Junction 适配器
│   ├── templates/              # Jinja2 模板
│   │   ├── base.html
│   │   ├── index.html          # Skill 矩阵总览
│   │   ├── settings.html       # Agent 配置
│   │   ├── skill_detail.html   # Skill 详情
│   │   └── logs.html           # 操作日志
│   └── static/
│       └── style.css           # 全局样式
└── docs/ (可选，外部文档)
```

## Skill 状态机

每个 Skill 在每个 Agent 下处于以下状态之一：

| 状态           | 含义                       | 用户操作                        |
|----------------|----------------------------|---------------------------------|
| SOURCE_LOCAL   | 此 Agent 持有源目录        | 不可关闭，可迁移源              |
| SHARED_LINK    | 已共享（Junction 链接）   | 点击取消共享（仅删链接）        |
| MISSING        | 此 Agent 下无此目录        | 点击启用共享（创建 Junction）   |
| LOCAL_COPY     | 此 Agent 有独立副本        | 备份后转为共享                  |
| CONFLICT       | 内容冲突（指纹不同）       | 选择源或保留副本                |
| BROKEN_LINK    | Junction 目标不存在        | 修复链接或重新指定源            |
| INVALID        | 缺少 SKILL.md 或无权限     | 检查目录结构或权限              |

## 共享原理

SkillBridge **不复制文件**。启用共享时，在目标 Agent 的 Skill 根目录下创建 NTFS Junction（目录符号链接）：

```powershell
# 目标已存在真实目录 → 先备份再创建 Junction
if (Test-Path $target -PathType Container) {
    $backup = "$target.backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Move-Item $target $backup
}
# 创建 Junction（不复制文件）
New-Item -ItemType Junction -Path $target -Target $source
```

停用时仅删除 Junction，源目录不受影响。

## 启动

```bash
cd skill-bridge
python main.py
# 访问 http://127.0.0.1:17890
```

## API 概览

所有 JSON API 以 `/api/` 开头。POST/PUT/DELETE 需要 `X-Session-Token` 请求头。

| 方法   | 路径                                | 说明                 |
|--------|-------------------------------------|----------------------|
| GET    | /                                   | Skill 矩阵总览       |
| GET    | /settings                           | Agent 配置页         |
| GET    | /skills/{name}                      | Skill 详情页         |
| GET    | /logs                               | 操作日志页           |
| GET    | /api/agents                         | 查询 Agent 列表      |
| POST   | /api/agents                         | 新增 Agent           |
| PUT    | /api/agents/{id}                    | 修改 Agent           |
| DELETE | /api/agents/{id}                    | 删除 Agent           |
| POST   | /api/scan                           | 重新扫描             |
| GET    | /api/skills                         | 查询 Skill 矩阵      |
| GET    | /api/skills/{name}                  | 查询 Skill 详情      |
| POST   | /api/skills/{name}/share            | 启用共享             |
| DELETE | /api/skills/{name}/share/{agent}    | 停用共享             |
| POST   | /api/skills/{name}/source           | 迁移源               |
| POST   | /api/skills/batch/share             | 批量启用             |
| POST   | /api/skills/batch/unshare           | 批量停用             |
| GET    | /api/operations                     | 查询操作日志         |
| POST   | /api/operations/{id}/rollback       | 回滚操作             |
| POST   | /api/pick-folder                    | 原生文件夹选择器     |
| GET    | /api/browse                         | 目录浏览（备用）     |

## 关键设计决策

1. **Junction 而非目录复制**：NTFS Junction 是文件系统级引用，不占用额外空间，任一 Agent 修改文件立即可见。
2. **文件系统即真实来源**：每次扫描完整遍历目录，不依赖内存缓存的状态标记。
3. **先备份后操作**：目标存在真实目录时绝不直接删除，先移动到备份目录再创建 Junction。
4. **操作可回滚**：每次修改写入日志，含完整 before/after 路径信息，支持一键回滚。
5. **安全第一**：仅监听 127.0.0.1；API 携带会话令牌；路径严格校验，禁止越界访问。
