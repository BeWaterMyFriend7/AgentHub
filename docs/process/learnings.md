# 经验记录

本文件用于保存调研、实现、故障或测试过程中发现的、有证据支持的经验。每条记录使用 `YYYY-MM-DD：主题` 作为二级标题，按时间追加，不再为单条经验建立子目录或独立文件。

经验记录说明发生了什么，以及哪些结论可以复用。如果结论改变了长期架构选择，应新增或废止对应 ADR；如果产生后续工作，还应同步增加 TODO 或工单。

## 2026-07-22：代码索引改用 CodeGraph

- CodeGraph 直接索引 Python、JavaScript 等源码的符号、调用方、被调用方和影响关系，适合当前模块化单体的代码导航。
- `.codegraph/.gitignore` 作为项目已启用 CodeGraph 的标记提交；`codegraph.db` 是可重建的本机缓存，不进入 Git。
- 新环境执行 `codegraph init .`，日常源码变更后执行 `codegraph sync .`；查询代码关系优先使用 `explore`、`node`、`callers`、`callees`、`impact` 和 `affected`。
- CodeGraph 不索引普通 Markdown 或配置文件；查询提示没有索引结果时，再直接读取这些文件。
- 项目不再维护 Graphify 虚拟环境、图谱输出或相关忽略规则，避免两套索引事实来源并存。
