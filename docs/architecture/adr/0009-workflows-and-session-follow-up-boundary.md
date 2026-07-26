---
status: accepted
date: 2026-07-26
---

# 分离任务编排、会话跟进与项目上下文

早期 AgentHub 会话 MVP 只观察 Agent 原生状态并精确打开会话，明确不在 AgentHub 内发送消息，也不提供人工标记。新的产品规划需要按顺序自动执行多个任务，并允许用户标记暂停后需要继续跟进的会话。这两项能力都会扩展早期产品边界，但它们的状态来源、生命周期和风险不同。

因此新增 Workflows 模块，独立拥有 Workflow、Task、TaskRun、任务顺序、自动推进、暂停策略和结果会话关联。只有用户预先确认并进入队列的任务可以由 Workflows 执行 Adapter 发送；Sessions 不发送任务，也不承担调度状态机。任意即时聊天、权限批准和自动生成新任务不在该边界内。

用户会话标记继续归 Sessions 模块，通过 `SessionAnnotation` 保存待跟进状态、标签、备注和提醒时间。该数据是 AgentHub 本地元数据，与 Agent 原生运行状态及系统推导的关注状态分别存储、展示和清除，用户操作不能覆盖可信原生事实。

项目暂不建立独立 Projects 模块，只作为 Workflows 内部的 `ProjectContext`，包含项目名称和工作目录。只有项目开始拥有独立配置和生命周期，并被 Sessions、Capabilities 或其他模块共同引用时，才重新评估 Projects 模块的 Interface 和 seam。

该决策使任务调度复杂度集中在 Workflows，使会话观察和用户跟进保持在 Sessions，并避免在项目只有轻量上下文时提前增加浅模块。
