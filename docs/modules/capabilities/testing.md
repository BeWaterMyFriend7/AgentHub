# Capabilities 模块测试策略

## 单元测试

- Skill 描述、MCP 配置和插件 Manifest 解析。
- 能力身份、来源、内容指纹和同名冲突判定。
- 真实目录、目录链接、本地副本、断链和原生加载状态归一化。
- 插件所有权、共享引用和用户修改识别。
- 敏感字段脱敏，确保 UI、日志、数据库和导出不出现明文秘密。

## Adapter 与类型契约测试

- 每个 Agent 对三种能力分别声明发现、注册、刷新、加载检查和卸载支持。
- 同一能力在至少两个 Agent 上能被独立发现并聚合到正确来源。
- 不支持目录发现时使用原生配置模式或明确标记不支持。
- 文件链接存在但 Agent 未加载时不得返回完整可用。

## 集成测试

- 使用临时目录和临时配置验证扫描、重新扫描和状态收敛。
- 验证目录内容或原生配置被外部修改后，状态和内容指纹能够刷新。
- 插件卸载保留被其他插件引用的 Skill，并识别独占 Skill/MCP。
- 插件更新与用户修改冲突时输出差异和可选决策，不自动覆盖。

## API 与 UI 验收

- Skill、MCP、插件使用一致的来源与安装语言，同时展示类型专属字段。
- 能力矩阵、过滤、详情、兼容性、健康和原生加载状态与事实来源一致。
- 秘密只显示变量名和“已配置/未配置”，不显示明文。
- Skill 共享 API：临时目录验证矩阵、共享规划-确认执行、幂等共享、取消共享与未知 Agent 错误。

## BDD

- [`skill-safe-sharing.feature`](./bdd/skill-safe-sharing.feature)：Skill 安全共享的业务结果。
- [`capability-folder-sharing.feature`](./bdd/capability-folder-sharing.feature)：三种能力的跨平台目录共享和原生加载验证。
- [`plugin-lifecycle.feature`](./bdd/plugin-lifecycle.feature)：插件所有权、卸载和更新冲突。

文件系统变更、备份和回滚的故障注入由 [`operations/testing.md`](../operations/testing.md) 负责。
