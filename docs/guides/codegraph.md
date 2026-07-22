# CodeGraph 代码索引使用指南

## 目标

AgentHub 使用 CodeGraph 作为唯一的源码关系索引，用于定位符号、查看调用链、评估修改影响和寻找关联测试。它是开发工具，不属于 AgentHub 产品运行时，也不改变产品架构或业务事实来源。

本项目不使用 Graphify，不应创建或保留 `graphify-out/`、`.graphify-venv/` 等目录。

## 仓库约定

- 仓库提交 `.codegraph/.gitignore`，用来表明项目启用了 CodeGraph。
- `.codegraph/codegraph.db`、锁、日志和守护进程文件只保存在本机，由目录内的 `.gitignore` 排除。
- 新克隆不会携带索引数据库，需要在本机重新初始化。
- CodeGraph 只负责源码导航；PRD、ADR、BDD、Markdown 和配置文件仍直接从仓库读取。

## 初始化与状态检查

在项目根目录执行：

```powershell
codegraph init .
codegraph status .
```

`status` 应显示 `Index is up to date`。如果索引已存在但需要完整重建：

```powershell
codegraph index . --force
```

## 日常查询

先使用自然语言获取相关源码和调用路径：

```powershell
codegraph explore "AgentHub 应用如何组合 Agents 和 Sessions"
```

查看一个符号的源码、调用方和被调用方，或者按行读取某个源码文件：

```powershell
codegraph node SessionHub
codegraph node src/agent_hub/bootstrap.py
```

进一步分析关系：

```powershell
codegraph callers SessionHub
codegraph callees SessionHub
codegraph impact SessionHub
codegraph affected src/agent_hub/sessions/hub.py
```

也可以把当前工作树中的源码变更通过标准输入交给 `affected`：

```powershell
git diff --name-only HEAD -- src tests | codegraph affected --stdin
```

`affected` 没有返回测试时，只表示索引没有找到依赖路径，不能据此省略模块测试或完整测试套件。

只有 CodeGraph 没有结果、文件不属于源码索引，或需要核对精确文本时，才回退到文件搜索和直接读取。

## 保持索引最新

修改源码后执行增量同步：

```powershell
codegraph sync .
codegraph status .
```

发生大规模移动、删除或解析结果异常时执行完整重建：

```powershell
codegraph index . --force
```

提交代码前至少确认：

1. `codegraph status .` 显示索引最新。
2. 对源码变更运行 `codegraph affected <文件...>` 或 `--stdin` 获取测试线索，同时仍执行项目规定的测试套件；纯文档变更无需运行该命令。
3. `.codegraph/` 中除 `.gitignore` 外没有文件进入 Git 暂存区。

## 当前初始化验证

2026-07-22 在 `dev` 分支初始化验证：

- 索引源码与测试文件：40 个。
- 符号节点：434 个。
- 关系边：1152 条。
- 后端：内置 SQLite，状态为 `Index is up to date`。

这些数字会随源码变化，仅用于证明首次索引完成，不能作为长期架构指标。
