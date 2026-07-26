# Agents 模块测试策略

## 单元测试

- Agent ID、版本和平台约束解析。
- Profile 路径规范化、默认值和启停状态。
- 能力矩阵的支持等级与实验性标记。

## 契约测试

所有 Agent Adapter 使用同一套契约验证：Profile 校验、稳定 Agent 身份、明确的能力声明、错误分类和无副作用探测。未实现的能力必须返回“不支持”，不得伪造空成功结果。

## 集成与平台测试

- 在临时配置和受控安装夹具中验证多 Profile 共存。
- Windows、macOS、Linux 分别验证可执行文件、路径、权限和配置位置探测。
- 验证停用或删除 Profile 不修改 Agent 原生文件。

## API 与 UI 验收

- Profile 的新增、编辑、校验、启停和错误反馈。
- 同一 Agent 产品的多个 Profile 可独立展示。
- 会话观察、任务执行与 Skill、MCP、插件支持状态分别显示。

## 当前自动化覆盖

- `test_agent_profile_store.py` 验证同一产品的 Desktop/Server Profile 可并存，且配置文件只保存密码环境变量名，不保存密码值。
- `test_application.py` 验证 Adapter 类型目录与 Profile 新增、编辑、启停、删除 API，并确认配置变更后 Runtime 立即重载。
- 浏览器真实验收验证动态配置字段、连接状态、Profile 探测结果与 200 个真实会话展示。
