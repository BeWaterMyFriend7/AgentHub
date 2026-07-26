# Workflows 模块设计

## 核心模型

- `Workflow`：任务队列及其当前状态、推进策略和版本。
- `Task`：用户定义的任务、项目上下文、目标 Agent/Profile、顺序和会话延续策略。
- `TaskRun`：某项任务的一次实际执行，保存幂等键、状态、时间、错误和稳定会话引用。
- `ProjectContext`：项目名称与工作目录的轻量值对象；当前不建立独立 Projects 模块。

项目只有在拥有独立配置、生命周期并被多个模块共同引用后才拆成新模块，避免提前增加浅 Interface。

## 编排 Interface

Workflows 对调用方提供少量高层操作：创建或修改草稿、启动、暂停、恢复、取消和读取状态。任务发送、完成判断、失败暂停和幂等恢复隐藏在模块内部，不让 UI 逐步驱动状态机。

## 执行 Adapter

不同 Agent 的任务启动和继续会话方式存在真实差异，因此在 Workflows 与 Agent 原生 Interface 之间定义执行 Adapter。Adapter 至少需要明确是否支持：

- 创建带工作目录的新会话并发送首个任务。
- 按稳定原生会话 ID 继续会话并发送后续任务。
- 返回任务启动结果和对应原生会话 ID。
- 提供可用于幂等恢复的原生请求或执行标识。

生产 Adapter 与内存测试 Adapter 共同验证该 seam。只会打开窗口、不能精确发送到目标会话的实现属于有限支持。

## 推进流程

1. 持久化 Workflow、任务快照和待启动 TaskRun。
2. 使用 TaskRun 幂等键调用执行 Adapter。
3. 保存 Adapter 返回的稳定原生会话 ID，并将任务标记为执行中。
4. 消费 Sessions 提供的归一化会话事件。
5. 收到可信完成事件时以状态机事务完成当前 TaskRun，并建立下一 TaskRun。
6. 等待介入、失败或未知状态时暂停，不自动越过当前任务。
7. 重启后根据持久化状态和原生会话事实恢复，不重复发送已启动任务。

## 模块依赖

- 依赖 Agents 获取 Profile、能力声明和执行 Adapter。
- 依赖 Sessions 获取稳定会话身份、可信状态事件和精确恢复入口。
- Sessions 不依赖 Workflows；会话仍可以独立于任务队列存在。
- Workflows 自己拥有队列和 TaskRun，不复用 Capabilities 的 Operations 模型。
