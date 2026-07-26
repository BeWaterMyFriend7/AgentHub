# Capabilities 模块拆分历史记录

> 状态：自动化测试记录，不是当前需求事实，也不能作为真实 Agent 能力验证证据。

## 范围

验证从 SkillBridge 提取到 AgentHub 的只读 Skill 发现、`SKILL.md` 解析、内容指纹、来源识别、共享安装、同名冲突和缺失状态聚合。

## 验证结果

- Skill Manifest 名称和中文描述可以解析。
- 内容发生变化时 SHA-256 内容指纹同步变化，不再依赖文件修改时间。
- 明确来源下可以区分来源、共享安装、用户冲突副本和缺失安装。
- 同名但来源和内容不同的 Skill 会拆成多个稳定身份，同时标记身份冲突，不压成一个逻辑能力。
- 修改来源内容只更新 fingerprint，不改变来源 ID。
- Capabilities 仅返回读模型，不执行文件系统修改。

## 命令

```powershell
$env:PYTHONPATH="$PWD\src"
.venv\Scripts\python.exe -m unittest tests.test_capability_inventory -v
```

结果：3 个 Capabilities 测试全部通过。

## 已知缺口

- 尚未接入真实 Agent Profile 的能力目录配置。
- MCP Server 和 Agent 插件仍只有公共模型，未实现类型解析器。
- 原生加载、兼容性和健康状态尚未通过真实 Agent 验证。
- 尚未提供 AgentHub HTTP API 与 UI。
