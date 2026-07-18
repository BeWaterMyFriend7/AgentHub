# 架构总览

## 当前运行结构

```text
浏览器 UI
  -> FastAPI 路由（src/agent_hub/main.py）
  -> 会话/能力应用服务
  -> 统一领域模型与 Repository
  -> Agent 专用 Adapter
  -> 原生 API、Hook、配置文件、CLI 或平台操作
```

当前接近生产结构的代码只实现了基于 Mock Adapter 的会话聚合。`src/skill_bridge/` 是参考子系统，尚未接入 AgentHub 主进程。

## 目标模块

- `sessions`：会话发现、状态映射、规划、待处理识别和精确恢复。
- `capabilities`：统一能力清单与生命周期契约。
- `skills`：Skill 解析、来源选择、共享、冲突处理和回滚。
- `mcp`：配置发现、敏感信息安全归一化、校验和 Server 健康检查。
- `plugins`：Manifest/Catalog 发现与原生生命周期操作。
- `agents`：各工具适配器和能力矩阵。
- `audit`：不可变操作记录与恢复元数据。
- `platform`：Windows Junction/进程能力，以及后续 POSIX 平台适配器。

UI 只消费归一化后的读取模型，不得直接解释原生配置文件或执行平台命令。

