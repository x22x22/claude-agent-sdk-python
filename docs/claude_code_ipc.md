# Claude Code CLI IPC 调研报告

## 1. IPC 通信依赖概览

Claude Agent Python SDK 通过 `SubprocessCLITransport` 启动 Claude Code CLI (`claude`) 进程，并使用标准输入/输出来交换 JSON 行消息。这一传输层会根据 `ClaudeAgentOptions` 构造启动命令、合并运行环境，并在流式模式下保持 stdin/stdout 管道常开，从而完成与 CLI 的 IPC 通信。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L33-L263】

在流式模式下，SDK 会将用户侧生成的消息对象编码为 JSON 行写入 CLI 标准输入，并持续解析 CLI 标准输出中逐行返回的 JSON 数据。传输层包含缓冲区保护、stderr 回调与进程生命周期管理逻辑，确保 IPC 渠道的稳定性。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L255-L456】

消息编排由 `Query` 类完成：它在连接建立后发送初始化控制请求，负责路由 CLI 发来的控制请求（如工具授权、Hook 回调、MCP 代理请求等），并把普通消息推送到上层消费方。【F:src/claude_agent_sdk/_internal/query.py†L64-L205】【F:src/claude_agent_sdk/_internal/query.py†L317-L355】

## 2. CLI IPC 接口列表

Claude Agent SDK 当前使用的 CLI IPC 接口可按功能分为两类：

1. **控制信道 (`control_request`/`control_response`)**：用于初始化、权限与 Hook 回调、MCP 转发、会话控制等。相关请求类型通过 TypedDict 定义，确保与 TypeScript SDK 的协议保持一致。【F:src/claude_agent_sdk/types.py†L547-L612】
2. **数据流信道（普通消息流）**：在流式对话中传递用户消息、助手输出、系统与结果消息，以及部分流事件。消息载荷由 dataclass 描述。【F:src/claude_agent_sdk/types.py†L446-L498】

### 2.1 控制信道子类型

| 子类型 | 方向 | 说明 |
| --- | --- | --- |
| `initialize` | SDK → CLI | 传递 Hook 注册信息，换取 CLI 支持能力列表。 |
| `can_use_tool` | CLI → SDK | 请求工具授权决策，可携带权限建议等上下文。|
| `hook_callback` | CLI → SDK | 触发已注册 Hook 回调。|
| `mcp_message` | CLI → SDK | 将 MCP JSON-RPC 调用转发至 SDK 内嵌服务器。|
| `interrupt` | SDK → CLI | 请求中断当前对话。|
| `set_permission_mode` | SDK → CLI | 切换权限模式。|
| `set_model` | SDK → CLI | 切换当前模型（通过 `_send_control_request` 自定义 subtype）。【F:src/claude_agent_sdk/_internal/query.py†L493-L508】|
| `control_cancel_request` | CLI → SDK | CLI 发出的取消通知，Python 端暂未实现具体处理。【F:src/claude_agent_sdk/_internal/query.py†L178-L189】|
| `mcp_response`（封装） | SDK → CLI | `mcp_message` 对应的 JSON-RPC 返回值包装在 `control_response.response` 中。|

所有控制请求均使用 JSON 行传输，字段 `type` 为 `control_request` 或 `control_response`，并带有唯一 `request_id` 以匹配响应。【F:src/claude_agent_sdk/types.py†L585-L612】【F:src/claude_agent_sdk/_internal/query.py†L317-L355】

### 2.2 数据流信道消息类型

| 消息类型 (`type`) | 说明 |
| --- | --- |
| `user` | 用户输入消息，内容可以是字符串或内容块数组。|
| `assistant` | 助手响应消息，包含模型名称及内容块序列。|
| `system` | 系统消息，通常包含状态/事件数据。|
| `result` | 会话总结与计费信息。|
| `stream_event` | 部分流事件，用于传递底层流式 API 的原始事件。|

这些消息通常由 CLI 写入 stdout，`Query.receive_messages` 会过滤掉控制信道数据，并将其作为异步迭代器暴露给 SDK 使用者。【F:src/claude_agent_sdk/types.py†L446-L498】【F:src/claude_agent_sdk/_internal/query.py†L154-L205】

## 3. 接口报文规范

下列规范以 OpenAPI 风格描述各 IPC 报文，介质为 `application/jsonl`（换行分隔 JSON 对象）。

### 3.1 初始化请求 (`initialize`)

```yaml
operationId: initializeSession
summary: 发送 Hook 注册信息，获取 CLI 初始化能力。
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required: [type, request_id, request]
        properties:
          type:
            const: control_request
          request_id:
            type: string
          request:
            type: object
            required: [subtype]
            properties:
              subtype:
                const: initialize
              hooks:
                type: object
                additionalProperties:
                  type: array
                  items:
                    type: object
                    properties:
                      matcher:
                        type: string
                        nullable: true
                      hookCallbackIds:
                        type: array
                        items:
                          type: string
responseBody:
  content:
    application/json:
      schema:
        type: object
        required: [type, response]
        properties:
          type:
            const: control_response
          response:
            type: object
            required: [subtype, request_id]
            properties:
              subtype:
                enum: [success, error]
              request_id:
                type: string
              response:
                type: object
                nullable: true
              error:
                type: string
                nullable: true
```

### 3.2 工具授权请求 (`can_use_tool`)

```yaml
operationId: evaluateToolPermission
summary: CLI 请求 SDK 判定工具调用是否允许。
requestBody:
  content:
    application/json:
      schema:
        type: object
        required: [type, request_id, request]
        properties:
          type:
            const: control_request
          request_id:
            type: string
          request:
            type: object
            required: [subtype, tool_name, input]
            properties:
              subtype:
                const: can_use_tool
              tool_name:
                type: string
              input:
                type: object
                additionalProperties: true
              permission_suggestions:
                type: array
                items:
                  type: object
                  additionalProperties: true
                nullable: true
              blocked_path:
                type: string
                nullable: true
responseBody:
  content:
    application/json:
      schema:
        type: object
        required: [type, response]
        properties:
          type:
            const: control_response
          response:
            type: object
            required: [subtype, request_id]
            properties:
              subtype:
                enum: [success, error]
              request_id:
                type: string
              response:
                type: object
                nullable: true
                properties:
                  behavior:
                    enum: [allow, deny]
                  updatedInput:
                    type: object
                    additionalProperties: true
                    nullable: true
                  updatedPermissions:
                    type: array
                    items:
                      type: object
                      additionalProperties: true
                    nullable: true
                  message:
                    type: string
                    nullable: true
                  interrupt:
                    type: boolean
                    nullable: true
              error:
                type: string
                nullable: true
```

### 3.3 Hook 回调请求 (`hook_callback`)

```yaml
operationId: invokeRegisteredHook
summary: CLI 触发 Python Hook 回调。
requestBody:
  content:
    application/json:
      schema:
        type: object
        required: [type, request_id, request]
        properties:
          type:
            const: control_request
          request_id:
            type: string
          request:
            type: object
            required: [subtype, callback_id]
            properties:
              subtype:
                const: hook_callback
              callback_id:
                type: string
              input:
                type: object
                additionalProperties: true
                nullable: true
              tool_use_id:
                type: string
                nullable: true
responseBody:
  content:
    application/json:
      schema:
        type: object
        required: [type, response]
        properties:
          type:
            const: control_response
          response:
            type: object
            required: [subtype, request_id]
            properties:
              subtype:
                enum: [success, error]
              request_id:
                type: string
              response:
                type: object
                nullable: true
                description: Hook 回调返回的 JSON，对 `async`/`continue` 字段已由 SDK 自动转换。
              error:
                type: string
                nullable: true
```

### 3.4 MCP 代理请求 (`mcp_message`)

```yaml
operationId: proxyMcpMessage
summary: CLI 通过 SDK 调用内置 MCP 服务器。
requestBody:
  content:
    application/json:
      schema:
        type: object
        required: [type, request_id, request]
        properties:
          type:
            const: control_request
          request_id:
            type: string
          request:
            type: object
            required: [subtype, server_name, message]
            properties:
              subtype:
                const: mcp_message
              server_name:
                type: string
              message:
                type: object
                additionalProperties: true
responseBody:
  content:
    application/json:
      schema:
        type: object
        required: [type, response]
        properties:
          type:
            const: control_response
          response:
            type: object
            required: [subtype, request_id]
            properties:
              subtype:
                enum: [success, error]
              request_id:
                type: string
              response:
                type: object
                nullable: true
                properties:
                  mcp_response:
                    type: object
                    additionalProperties: true
              error:
                type: string
                nullable: true
```

### 3.5 会话控制请求（`interrupt`/`set_permission_mode`/`set_model`）

```yaml
operationId: controlSession
summary: SDK 主动向 CLI 发送会话控制请求。
requestBody:
  content:
    application/json:
      schema:
        type: object
        required: [type, request_id, request]
        properties:
          type:
            const: control_request
          request_id:
            type: string
          request:
            oneOf:
              - type: object
                required: [subtype]
                properties:
                  subtype:
                    const: interrupt
              - type: object
                required: [subtype, mode]
                properties:
                  subtype:
                    const: set_permission_mode
                  mode:
                    type: string
              - type: object
                required: [subtype]
                properties:
                  subtype:
                    const: set_model
                  model:
                    type: string
                    nullable: true
responseBody:
  content:
    application/json:
      schema:
        type: object
        required: [type, response]
        properties:
          type:
            const: control_response
          response:
            type: object
            required: [subtype, request_id]
            properties:
              subtype:
                enum: [success, error]
              request_id:
                type: string
              response:
                type: object
                nullable: true
              error:
                type: string
                nullable: true
```

### 3.6 数据流消息

```yaml
operationId: streamMessages
summary: CLI 通过 stdout 推送对话与事件消息。
responseBody:
  content:
    application/jsonl:
      schema:
        type: object
        properties:
          type:
            type: string
            enum: [user, assistant, system, result, stream_event]
          message:
            type: object
            description: 对应消息体，结构由 `UserMessage`/`AssistantMessage` 等 dataclass 定义。
        examples:
          assistantMessage:
            value:
              type: assistant
              message:
                content:
                  - type: text
                    text: "Hello from Claude"
                model: claude-sonnet-4.5
          resultMessage:
            value:
              type: result
              message:
                subtype: sessionEnd
                duration_ms: 1200
                session_id: "sess-123"
                usage: {input_tokens: 1000, output_tokens: 500}
```

## 4. 结论

- Python SDK 仅依赖标准输入/输出与 Claude Code CLI 通信，所有控制与数据消息均使用换行分隔 JSON 格式。
- 控制信道通过统一的 `control_request`/`control_response` 模式承载多种子类型，使得工具权限、Hook 与 MCP 等高级特性能够在 IPC 层完成编排。
- 数据流信道按消息类型封装对话内容，与 dataclass 定义保持一致，方便上层消费与类型校验。

上述规范可作为后续实现自定义传输层或调试 CLI 通信的参考。
