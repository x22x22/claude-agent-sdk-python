# Claude Code CLI STDIO IPC 说明

## 1. IPC 依赖概览
SDK 通过 `SubprocessCLITransport` 以子进程方式调用 `claude` 命令行，统一附加 `--output-format stream-json` 与 `--verbose` 参数，并按选项拼接系统提示词、工具白名单/黑名单、模型、权限模式、MCP 配置、Hook、Agent 定义等开关，必要时还切换 `--input-format stream-json` 以启用流式 stdin。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L33-L200】

在连接时，传输层会合并当前环境变量、用户自定义 `env`，并写入 `CLAUDE_CODE_ENTRYPOINT` 与 `CLAUDE_AGENT_SDK_VERSION`；根据是否配置 stderr 回调或调试开关决定是否监听子进程标准错误输出。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L214-L305】

消息调度由 `Query` 类负责：流式模式下它会发送初始化控制请求、路由 CLI 发来的控制请求（如工具授权、Hook 回调、MCP 转发），并将普通会话消息推送给上层异步迭代器消费。【F:src/claude_agent_sdk/_internal/query.py†L107-L205】【F:src/claude_agent_sdk/_internal/query.py†L206-L315】

## 2. 进程启动与运行时约束
* CLI 可执行文件路径自动探测，若无法找到则抛出 `CLINotFoundError` 并给出安装与 PATH 配置建议。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L61-L85】
* 在非流式模式下 SDK 使用 `--print -- <prompt>` 将初始提示语直接传给 CLI；流式模式则保持 stdin 打开以持续发送 JSON 行消息。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L194-L263】
* CLI 版本会在连接前通过 `claude -v` 检测，若低于 `2.0.0` 会向日志与 stderr 打印警告，亦可通过 `CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK` 跳过校验。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L209-L498】

## 3. STDIO 信道与消息分帧
所有 IPC 报文均以换行分隔 JSON（`application/jsonl`）形式发送。传输层为了解决 `TextReceiveStream` 可能拆分长行的问题，会在内部累积缓冲区并尝试解析完整 JSON；超过配置的最大缓冲（默认 1 MiB）或解析失败时会抛出 `CLIJSONDecodeError`。子进程异常退出则包装为 `ProcessError`。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L352-L456】

`Query` 在读取 stdout 时会优先处理 `control_response`、`control_request` 与预留的 `control_cancel_request`，其余类型则作为会话消息推送到上层异步流。【F:src/claude_agent_sdk/_internal/query.py†L154-L205】

## 4. IPC 接口总览
下表汇总当前通过 STDIO 使用的报文类型与触发场景：

| 方向 | 报文类型 | 触发场景 |
| --- | --- | --- |
| SDK → CLI | `control_request` | 初始化、打断、切换权限模式/模型等控制指令。【F:src/claude_agent_sdk/_internal/query.py†L317-L355】 |
| SDK → CLI | `control_response` | 处理 CLI 发来的工具授权、Hook 回调、MCP 请求等控制消息后的反馈。【F:src/claude_agent_sdk/_internal/query.py†L206-L315】 |
| SDK → CLI | 会话消息（`type: "user"` 等） | `ClaudeSDKClient.query()` 将用户消息写入 CLI。【F:src/claude_agent_sdk/client.py†L170-L199】 |
| CLI → SDK | `control_response` | 对 SDK 控制请求（初始化、打断等）的响应。【F:src/claude_agent_sdk/_internal/query.py†L154-L205】 |
| CLI → SDK | `control_request` | CLI 请求工具授权、触发 Hook、转发 MCP JSON-RPC 等；SDK 需同步响应。【F:src/claude_agent_sdk/types.py†L547-L612】【F:src/claude_agent_sdk/_internal/query.py†L206-L315】 |
| CLI → SDK | `control_cancel_request` | 预留取消通知，目前 Python SDK 暂未处理（被忽略）。【F:src/claude_agent_sdk/_internal/query.py†L186-L189】 |
| CLI → SDK | 会话流消息（`user`、`assistant`、`system`、`result`、`stream_event`） | Claude Code 输出的对话内容、工具结果、系统事件与流式事件，由 `types.Message` 定义的 dataclass 表达。【F:src/claude_agent_sdk/types.py†L446-L498】 |

## 5. 报文规范（OpenAPI 风格）
以下 YAML 使用 OpenAPI 式结构描述 STDIO 报文。`channels` 区分 SDK 与 CLI 的发送方向，`components` 定义全部报文与复用的 Schema。

```yaml
openapi: 3.1.0
info:
  title: Claude Code CLI STDIO IPC
  version: 1.0.0
channels:
  sdk_to_cli:
    description: SDK 写入 CLI stdin 的报文
    messages:
      - $ref: '#/components/messages/ControlRequest'
      - $ref: '#/components/messages/ControlResponse'
      - $ref: '#/components/messages/UserMessage'
  cli_to_sdk:
    description: CLI 写入 stdout 供 SDK 消费的报文
    messages:
      - $ref: '#/components/messages/ControlResponse'
      - $ref: '#/components/messages/ControlRequest'
      - $ref: '#/components/messages/ControlCancelRequest'
      - $ref: '#/components/messages/ConversationMessage'
components:
  messages:
    ControlRequest:
      name: control_request
      payload:
        $ref: '#/components/schemas/ControlRequestEnvelope'
    ControlResponse:
      name: control_response
      payload:
        $ref: '#/components/schemas/ControlResponseEnvelope'
    ControlCancelRequest:
      name: control_cancel_request
      payload:
        $ref: '#/components/schemas/ControlCancelRequestEnvelope'
    UserMessage:
      name: user_message
      payload:
        $ref: '#/components/schemas/UserInputEnvelope'
    ConversationMessage:
      name: conversation_message
      payload:
        $ref: '#/components/schemas/ConversationEnvelope'
  schemas:
    ControlRequestEnvelope:
      type: object
      required: [type, request_id, request]
      properties:
        type:
          const: control_request
        request_id:
          type: string
        request:
          oneOf:
            - $ref: '#/components/schemas/InitializeRequest'
            - $ref: '#/components/schemas/InterruptRequest'
            - $ref: '#/components/schemas/SetPermissionModeRequest'
            - $ref: '#/components/schemas/SetModelRequest'
            - $ref: '#/components/schemas/CanUseToolRequest'
            - $ref: '#/components/schemas/HookCallbackRequest'
            - $ref: '#/components/schemas/McpMessageRequest'
    InitializeRequest:
      type: object
      required: [subtype]
      properties:
        subtype:
          const: initialize
        hooks:
          type: object
          nullable: true
          additionalProperties:
            type: array
            description: 匹配器与回调 ID 列表；由 SDK 在初始化时生成。
            items:
              type: object
              properties:
                matcher:
                  description: Hook 匹配条件，结构取决于具体 Hook 类型。
                  nullable: true
                hookCallbackIds:
                  type: array
                  items:
                    type: string
    InterruptRequest:
      type: object
      required: [subtype]
      properties:
        subtype:
          const: interrupt
    SetPermissionModeRequest:
      type: object
      required: [subtype, mode]
      properties:
        subtype:
          const: set_permission_mode
        mode:
          type: string
    SetModelRequest:
      type: object
      required: [subtype]
      properties:
        subtype:
          const: set_model
        model:
          type: string
          nullable: true
    CanUseToolRequest:
      type: object
      required: [subtype, tool_name, input]
      properties:
        subtype:
          const: can_use_tool
        tool_name:
          type: string
        input:
          type: object
        permission_suggestions:
          type: array
          items:
            type: object
          nullable: true
        blocked_path:
          type: string
          nullable: true
    HookCallbackRequest:
      type: object
      required: [subtype, callback_id]
      properties:
        subtype:
          const: hook_callback
        callback_id:
          type: string
        input:
          type: object
          nullable: true
        tool_use_id:
          type: string
          nullable: true
    McpMessageRequest:
      type: object
      required: [subtype, server_name, message]
      properties:
        subtype:
          const: mcp_message
        server_name:
          type: string
        message:
          type: object
          description: 原始 JSON-RPC 消息体，由 CLI 透传。
    ControlResponseEnvelope:
      type: object
      required: [type, response]
      properties:
        type:
          const: control_response
        response:
          oneOf:
            - $ref: '#/components/schemas/ControlSuccess'
            - $ref: '#/components/schemas/ControlError'
    ControlSuccess:
      type: object
      required: [subtype, request_id]
      properties:
        subtype:
          const: success
        request_id:
          type: string
        response:
          type: object
          nullable: true
          description: 具体负载随子类型而异；`can_use_tool` 会返回行为决策与可选的参数更新/权限建议。
          properties:
            behavior:
              type: string
              enum: [allow, deny]
            updatedInput:
              type: object
              nullable: true
            updatedPermissions:
              type: array
              items:
                type: object
              nullable: true
            message:
              type: string
              nullable: true
            interrupt:
              type: boolean
              nullable: true
            mcp_response:
              type: object
              nullable: true
        error:
          readOnly: true
          nullable: true
    ControlError:
      type: object
      required: [subtype, request_id, error]
      properties:
        subtype:
          const: error
        request_id:
          type: string
        error:
          type: string
    ControlCancelRequestEnvelope:
      type: object
      required: [type]
      properties:
        type:
          const: control_cancel_request
        request_id:
          type: string
          nullable: true
        reason:
          type: string
          nullable: true
    UserInputEnvelope:
      type: object
      required: [type, message]
      properties:
        type:
          const: user
        message:
          type: object
          properties:
            role:
              const: user
            content:
              description: 字符串或内容块列表，结构与 `UserMessage.content` 保持一致。
          additionalProperties: true
        parent_tool_use_id:
          type: string
          nullable: true
        session_id:
          type: string
          nullable: true
    ConversationEnvelope:
      type: object
      required: [type]
      properties:
        type:
          type: string
          enum: [user, assistant, system, result, stream_event]
        parent_tool_use_id:
          type: string
          nullable: true
        message:
          type: object
          description: 当 type 为 `user`/`assistant` 时包含角色与内容块；`system`/`result`/`stream_event` 含对应 dataclass 字段。
          additionalProperties: true
        subtype:
          type: string
          description: result/system 报文的子类型标识。
          nullable: true
        duration_ms:
          type: integer
          nullable: true
        duration_api_ms:
          type: integer
          nullable: true
        is_error:
          type: boolean
          nullable: true
        num_turns:
          type: integer
          nullable: true
        session_id:
          type: string
          nullable: true
        total_cost_usd:
          type: number
          nullable: true
        usage:
          type: object
          nullable: true
        result:
          type: string
          nullable: true
        uuid:
          type: string
          nullable: true
        event:
          type: object
          description: 当 type == stream_event 时为原始流事件。
          nullable: true
```

## 6. 附注
- 所有控制信道请求与响应均携带 `request_id`，由 `Query._send_control_request` 管理生命周期并在 60 秒超时后抛出异常。【F:src/claude_agent_sdk/_internal/query.py†L317-L355】
- 工具权限回调在允许时支持返回更新后的输入参数与权限建议；拒绝时可附带提示信息与 `interrupt` 标志。【F:src/claude_agent_sdk/_internal/query.py†L215-L256】
- Hook 回调会自动将 Python 关键词规避字段（`async_`、`continue_`）转换回 CLI 期望的 `async`、`continue` 字段。【F:src/claude_agent_sdk/_internal/query.py†L234-L273】
- MCP 请求桥接支持 `initialize`、`tools/list`、`tools/call` 等常见方法，并在找不到服务器或方法时返回 JSON-RPC 错误体。【F:src/claude_agent_sdk/_internal/query.py†L274-L480】

以上内容覆盖了当前 Python SDK 与 Claude Code CLI 之间通过 STDIO 交互的全部接口，可作为自定义传输实现、协议调试或版本兼容性验证的参考。
