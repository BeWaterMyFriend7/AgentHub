# 2026-07-26 Codex 会话接入验证

## 验证目标

验证 AgentHub 能在不读取认证信息、不依赖窗口标题和进程猜测的前提下，发现真实 Codex Desktop 任务、读取稳定原生 Thread ID、识别轮次状态，并按原生 ID 定位任务。

## 数据来源

- `CODEX_HOME/state_*.sqlite`：选择版本号最大的状态库，`threads` 表提供原生 Thread ID、标题、工作目录、rollout 路径和更新时间。
- `rollout-*.jsonl`：提供 `task_started`、`task_complete`、`turn_aborted`、`request_user_input`、`update_plan` 和 Agent 消息。
- `codex://threads/<thread-id>`：Codex Desktop 注册的任务深链。

未使用 API Key、ChatGPT Cookie、账号 Token、窗口标题或“进程存在即运行中”等推断。

## 自动验证

执行：

```powershell
$env:PYTHONPATH="$PWD\src"
.venv\Scripts\python.exe scripts\verify_codex_sessions.py --limit 100
```

本机结果：

```text
probe_ok=True
sessions=100 stable_ids=true
status_counts=executing:1,waiting_permission:0,waiting_input:0,awaiting_review:0,interrupted:2,closed:97,unknown:0
```

当前 AgentHub 任务 `019f8df7-c340-7252-9089-ce0910fbfe91` 被识别为 `executing`，状态证据为当前轮次已有 `task_started` 且尚无完成或中断事件。多个历史任务由 `task_complete` 映射为 `closed`，两个被中止的审查任务由 `turn_aborted` 映射为 `interrupted`。

## 状态边界

- `closed` 表示最近轮次已结束，不表示任务不能继续。
- 未匹配的 `request_user_input` 可可靠识别为 `waiting_input`；收到对应调用结果后恢复为 `executing`。
- 当前本地持久化记录没有稳定的等待授权事件。首版不根据命令内容或界面状态推断 `waiting_permission`。
- rollout 缺失、损坏或尾部生命周期不完整时返回 `unknown`。
- 异常崩溃可能来不及写入终止事件，因此仅由“已有 `task_started`、尚无终止事件”得到的 `executing` 标记为中等可信度。
- 首版采用周期扫描，不声明实时事件流。

## 精确定位

可选执行：

```powershell
.venv\Scripts\python.exe scripts\verify_codex_sessions.py `
  --open-session 019f8df7-c340-7252-9089-ce0910fbfe91
```

Adapter 会调用 `codex://threads/019f8df7-c340-7252-9089-ce0910fbfe91`。目标包含稳定原生 Thread ID，属于精确任务定位，不是简单激活 Codex 窗口。

## 结论

Codex 已达到本地任务发现、轮次状态检测、规划读取和精确定位能力。等待授权和 App Server 实时事件尚未接入，因此当前实现是可靠轮询接入，而不是完整实时事件接入。
