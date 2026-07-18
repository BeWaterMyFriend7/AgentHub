# BDD 业务验收场景

本目录保存从 PRD 派生的业务行为。BDD 只描述用户或外部系统可以观察到的结果，不描述类名、数据库表、内部函数或具体实现步骤。

## 与其他文档的关系

- PRD 定义产品目标、范围和业务规则。
- ADR 记录重要且难以逆转的技术选择。
- BDD 把已经确认的业务规则转换为“假如/当/那么”场景。
- `../testing.md` 定义单元测试、契约测试、集成测试和 UI 测试策略。
- `../verification/` 保存某次验证运行的真实证据。

## 编写规则

1. 每个场景只验证一个核心行为。
2. 使用业务语言，不引用内部实现。
3. 场景必须可以通过 UI、API、文件系统或 Agent 原生状态观察。
4. 尚未确认的需求留在 PRD 的待确认部分，不提前写进 BDD。
5. 一个业务规则发生变化时，应同时更新 PRD 和对应 Feature。
6. Feature 文件采用 UTF-8 和中文 Gherkin，文件名使用稳定的英文短名。

## 当前 Feature

- `session-observation.feature`：内部会话发现、待处理识别和精确恢复。
- `skill-safe-sharing.feature`：Skill 共享、备份、取消和失败恢复。
- `capability-folder-sharing.feature`：Skill、MCP、插件的跨平台目录同源共享。
- `capability-source-deletion.feature`：普通卸载、来源删除和永久清除的安全边界。
- `plugin-lifecycle.feature`：插件所有权、卸载和更新冲突。

MCP 配置编辑和插件市场接入仍按 PRD 分阶段推进；新增场景只覆盖已经确认的共享和生命周期规则。
