# Operations 模块拆分验证

## 范围

使用临时目录验证共享安装的预检、确认、真实目录备份、目录链接创建或移除、执行后验证、失败补偿、人工回滚和审计记录。未使用任何真实 Agent 能力目录。

## 验证结果

- 越过允许根目录和直接操作 Agent 能力根目录会在预检阶段拒绝，文件系统零修改。
- 目标存在真实目录时先移动到隔离备份，再建立共享链接。
- 链接创建失败后能够自动恢复原真实目录及用户文件。
- 用户确认后若目标状态被外部修改，执行会拒绝过期计划并保持新内容不变。
- 停用共享只移除已验证且指向预期来源的链接，来源保持完整。
- 成功的启用或停用共享均可人工回滚。
- 当前 Windows 环境已实际创建、解析和移除 NTFS Junction；真实目录不会被链接移除逻辑删除。

## 命令

```powershell
$env:PYTHONPATH="$PWD\src"
.venv\Scripts\python.exe -m unittest tests.test_capability_operations tests.test_platform_links -v
```

结果：7 个 Operations 与平台链接测试全部通过。

## 已知缺口

- macOS/Linux Symbolic Link Adapter 已实现，但本次只在 Windows 实机验证。
- 审计记录当前仅保存在内存中。
- 尚未实现来源删除、永久清除、插件生命周期、原生 Agent 配置和并发锁。
- 尚未提供修改授权、HTTP API 与 UI。
