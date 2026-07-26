# OpenCode 真实会话接入验证

## 验证环境

- 日期：2026-07-26
- OpenCode Desktop：1.18.5
- OpenCode Server：1.18.4
- 启动方式：官方 `opencode serve --pure`，监听本机回环地址
- 认证：Basic Auth，用户名固定为 `opencode`，密码由运行时环境变量注入且未写入仓库
- 验证端点：`/global/health`、`/api/session`、`/api/session/active`、`/session/status`、`/session/{sessionID}/todo`、`/session/{sessionID}/message`

## 验证结果

- 两次独立扫描均返回 100 个会话，内部身份和原生会话 ID 顺序一致。
- 至少三个不同工作目录的会话可独立读取，包含 `xhs`、`kylinos-init` 和 `Obsidian Vault`。
- 多个会话返回独立 Todo，实测数量包含 1、3、4、6 等不同结果，未生成模拟计划项。
- 活动会话可由原生 `running`/`busy` 状态识别；历史会话仅能确认 inactive，因此统一状态保持 `unknown`。
- 指定原生会话 `ses_078998ff1ffeS3XoPrQd6RKIRn` 已通过官方 CLI `attach --session` 启动恢复，进程保持运行且命令行准确携带该 ID 和工作目录。
- 恢复命令不包含密码，认证仅通过 `OPENCODE_SERVER_PASSWORD` 环境变量传递。

三个独立项目样本：

| 原生会话 ID | 工作目录 | 原生状态结论 | Todo 数量 |
| --- | --- | --- | ---: |
| `ses_0a3ce2467ffenWkqzHZZb443JH` | `D:\DATA\0-0-PROJECT\ai\xhs` | inactive，归一化为 unknown | 7 |
| `ses_1260a96cbffeuIEHS1q9RoSNkZ` | `D:\DATA\0-0-PROJECT\ai\kylinos-init` | inactive，归一化为 unknown | 7 |
| `ses_0a92cabe0ffekqgDvV0NvBJMnZ` | `D:\BeWater\Documents\Obsidian Vault` | inactive，归一化为 unknown | 3 |

## 接入等级

当前判定为部分轮询接入：会话发现、Todo、最近活动和精确恢复命令均已验证，恢复进程也保持运行；但本轮无法自动读取 TUI 画面，尚缺少“视觉确认进入正确会话”的最终证据。事件流也尚未接入，因此不声明完整接入或实时事件能力；历史会话完成状态不做推断。

## 复验命令

```powershell
$env:PYTHONPATH = "$PWD\src"
$env:OPENCODE_SERVER_PASSWORD = "<本机 Server 密码>"
.venv\Scripts\python.exe scripts\verify_opencode_sessions.py `
  --endpoint http://127.0.0.1:<port> `
  --executable <opencode.exe> `
  --resume-session <原生会话ID>
```
