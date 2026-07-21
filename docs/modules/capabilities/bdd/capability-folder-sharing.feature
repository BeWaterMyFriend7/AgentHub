# language: zh-CN
@capability @sharing @cross-platform
功能: 通过目录链接共享同一能力来源
  为了让多个 Agent 使用同一份 Skill、MCP 或插件内容
  作为本地 Agent 用户
  我希望系统根据操作系统建立安全的目录引用并验证 Agent 已经加载

  场景大纲: 使用平台原生目录链接共享能力
    假如“<能力类型>”具有可访问的目录来源
    并且当前操作系统为“<操作系统>”
    当用户向目标 Agent 启用共享安装
    那么系统应使用“<链接类型>”引用同一能力来源
    并且不应复制能力内容

    例子:
      | 能力类型 | 操作系统 | 链接类型 |
      | Skill | Windows | NTFS Junction |
      | MCP Server | macOS | Symbolic Link |
      | Agent 插件 | Linux | Symbolic Link |

  场景: 文件已链接但 Agent 尚未加载
    假如目标 Agent 的能力目录已经存在正确链接
    但是目标 Agent 尚未识别该能力
    当 AgentHub 刷新能力状态
    那么该安装应显示为“已分发但未原生加载”
    并且不得显示为完整可用

  场景: 目标 Agent 不支持目录发现
    假如目标 Agent 只能通过原生配置注册某类能力
    当用户尝试使用目录链接共享该能力
    那么系统应调用对应 Adapter 的原生配置模式或标记不支持
    并且不得仅凭链接存在声明共享成功
