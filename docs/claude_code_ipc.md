# Claude Code CLI IPC 接口调研

## 1. 概览
Claude Agent Python SDK 通过 `SubprocessCLITransport` 以子进程方式启动 `claude` 命令，默认为所有会话附加 `--output-format stream-json` 与 `--verbose`，并根据选项拼接系统提示词、工具白名单/黑名单、模型、权限模式、MCP 配置、Hook、Agent 定义及自定义 CLI 标志；流式模式额外启用 `--input-format stream-json` 以便 SDK 通过 stdin 持续推送事件。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L33-L200】

启动时，传输层会将系统环境变量、用户自定义 `env` 以及 SDK 必需的标识合并后传给子进程；若配置工作目录或 stderr 处理器，也会相应调整 `cwd`、`PWD` 与标准错误流的接收方式。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L204-L305】

高层的 `Query` 对象负责初始化握手、路由控制报文、桥接 Hook/MCP 回调，并将普通会话消息写入内存通道供 `ClaudeSDKClient` 消费，从而实现 STDIO 之上的双向控制协议。【F:src/claude_agent_sdk/_internal/query.py†L53-L205】

## 2. 进程启动与运行时约束
* CLI 可执行文件会先调用 `shutil.which` 与常见路径探测，若仍未找到则抛出 `CLINotFoundError` 并附带安装/配置指引。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L61-L85】
* 非流式模式使用 `--print -- <prompt>` 将初始提示语直接写入 CLI；流式模式保持 stdin 打开以传输 JSON 行消息。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L195-L261】
* 在未设置 `CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK` 时，SDK 会在连接前运行 `claude -v` 并检测是否满足 `2.0.0` 以上版本，否则记录告警。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L209-L498】
* stderr 可被用户回调或调试流捕获；所有 IO 资源与任务组在关闭时都会被显式清理，避免悬挂子进程。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L225-L346】

## 3. STDIO 信道与消息调度
所有 IPC 报文均以换行分隔的 JSON 文本传输。传输层会在读取 stdout 时累积缓冲以对抗 `TextReceiveStream` 可能拆分长行的问题，并在超出最大缓冲或解析失败时抛出 `CLIJSONDecodeError`；若子进程以非零码退出则改抛 `ProcessError`。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L386-L456】

`Query` 在读取消息时优先处理控制报文（`control_response` / `control_request` / `control_cancel_request`），其余类型则投递到业务流；当 CLI 发来控制请求时会根据 subtype 调用权限回调、Hook 或 MCP 桥接，并以行分隔 JSON 将结果写回 stdin。【F:src/claude_agent_sdk/_internal/query.py†L154-L316】

## 4. IPC 接口列表
下表列出当前通过 STDIO 使用的报文类型、方向及触发场景，最后一列指向对应的报文 Schema 小节。

| 接口 | 方向 | 触发场景 | Schema 小节 |
| --- | --- | --- | --- |
| `control_request` (`initialize`) | SDK → CLI | 流式模式初始化 Hook 映射与能力信息。【F:src/claude_agent_sdk/_internal/query.py†L116-L145】 | [5.2.1](#521-control_request-sdk--cli)
| `control_request` (`interrupt`) | SDK → CLI | 用户请求打断当前轮会话。【F:src/claude_agent_sdk/_internal/query.py†L491-L499】 | [5.2.1](#521-control_request-sdk--cli)
| `control_request` (`set_permission_mode`) | SDK → CLI | 动态切换权限模式（`default`/`acceptEdits`/`bypassPermissions` 等）。【F:src/claude_agent_sdk/_internal/query.py†L495-L502】 | [5.2.1](#521-control_request-sdk--cli)
| `control_request` (`set_model`) | SDK → CLI | 动态切换 Claude 模型或恢复默认值。【F:src/claude_agent_sdk/_internal/query.py†L504-L511】 | [5.2.1](#521-control_request-sdk--cli)
| `control_response` (`success`/`error`) | CLI ↔ SDK | 控制请求的成功或失败回执。【F:src/claude_agent_sdk/_internal/query.py†L294-L315】 | [5.2.2](#522-control_response-sdk--cli)
| `control_request` (`can_use_tool`) | CLI → SDK | 执行工具前向 SDK 征询权限与参数更新。【F:src/claude_agent_sdk/_internal/query.py†L215-L256】 | [5.2.3](#523-control_request-cli--sdk)
| `control_request` (`hook_callback`) | CLI → SDK | 触发注册 Hook 的回调，需返回规范化字段名。【F:src/claude_agent_sdk/_internal/query.py†L258-L273】 | [5.2.3](#523-control_request-cli--sdk)
| `control_request` (`mcp_message`) | CLI → SDK | CLI 将 MCP JSON-RPC 报文交由 SDK 内置服务器处理。【F:src/claude_agent_sdk/_internal/query.py†L274-L289】 | [5.2.3](#523-control_request-cli--sdk)
| `control_cancel_request` | CLI → SDK | 取消通知，目前 Python SDK 占位不处理。【F:src/claude_agent_sdk/_internal/query.py†L186-L189】 | [5.2.4](#524-control_cancel_request-cli--sdk)
| 会话消息：`user`/`assistant`/`system`/`result`/`stream_event` | CLI → SDK | Claude Code 输出的对话流、统计结果及流式事件，由 `message_parser` 解析为强类型对象。【F:src/claude_agent_sdk/_internal/message_parser.py†L24-L172】【F:src/claude_agent_sdk/types.py†L409-L498】 | [5.3](#53-会话消息)
| 会话输入：`user` 消息或原始 JSON 流 | SDK → CLI | `ClaudeSDKClient.query()` 将字符串或异步消息写入 CLI。【F:src/claude_agent_sdk/client.py†L170-L199】【F:src/claude_agent_sdk/_internal/query.py†L513-L521】 | [5.4](#54-输入流事件)

## 5. 报文规范（OpenAPI 风格）
以下规范使用 OpenAPI 式结构描述 STDIO 报文。除特殊说明外，所有报文均以 UTF-8 编码的换行分隔 JSON (`application/jsonl`) 传输。

### 5.1 共享组件
```yaml
components:
  schemas:
    ControlRequestEnvelope:
      type: object
      required: [type, request_id, request]
      properties:
        type:
          type: string
          enum: [control_request]
        request_id:
          type: string
          description: SDK 在 `_send_control_request` 中生成的唯一 ID。【F:src/claude_agent_sdk/_internal/query.py†L317-L346】
        request:
          oneOf:
            - $ref: '#/components/schemas/InitializeRequest'
            - $ref: '#/components/schemas/InterruptRequest'
            - $ref: '#/components/schemas/SetPermissionModeRequest'
            - $ref: '#/components/schemas/SetModelRequest'
            - $ref: '#/components/schemas/CanUseToolRequest'
            - $ref: '#/components/schemas/HookCallbackRequest'
            - $ref: '#/components/schemas/McpMessageRequest'
      description: SDK 与 CLI 双向复用的控制信封结构，对应 `SDKControlRequest` TypedDict。【F:src/claude_agent_sdk/types.py†L548-L595】

    ControlSuccessEnvelope:
      type: object
      required: [type, response]
      properties:
        type:
          type: string
          enum: [control_response]
        response:
          type: object
          required: [subtype, request_id]
          properties:
            subtype:
              type: string
              enum: [success]
            request_id:
              type: string
            response:
              type: object
              nullable: true
      description: 控制请求成功回执，对应 `ControlResponse` 定义。【F:src/claude_agent_sdk/types.py†L598-L603】

    ControlErrorEnvelope:
      allOf:
        - $ref: '#/components/schemas/ControlSuccessEnvelope'
        - type: object
          properties:
            response:
              type: object
              required: [subtype, request_id, error]
              properties:
                subtype:
                  type: string
                  enum: [error]
                request_id:
                  type: string
                error:
                  type: string
      description: 控制请求失败回执，对应 `ControlErrorResponse` 定义。【F:src/claude_agent_sdk/types.py†L604-L612】

    ConversationEnvelope:
      type: object
      required: [type]
      properties:
        type:
          type: string
          enum: [user, assistant, system, result, stream_event]
      description: Claude Code CLI 输出的会话消息外层结构，后续由 `parse_message` 转换为 dataclass。【F:src/claude_agent_sdk/_internal/message_parser.py†L24-L172】

    ToolContentBlock:
      type: object
      required: [type]
      properties:
        type:
          type: string
          enum: [text, thinking, tool_use, tool_result]
        id:
          type: string
        name:
          type: string
        input:
          type: object
        tool_use_id:
          type: string
        content:
          type: [string, array]
        is_error:
          type: boolean
        thinking:
          type: string
        signature:
          type: string
      description: CLI 可能返回的内容块类型，对应 `ContentBlock` 相关 dataclass。【F:src/claude_agent_sdk/types.py†L409-L444】
```

### 5.2 控制通道

#### 5.2.1 `control_request`（SDK → CLI）
```yaml
paths:
  /control-request:
    post:
      summary: SDK 通过 stdin 发送的控制请求。
      requestBody:
        content:
          application/jsonl:
            schema:
              $ref: '#/components/schemas/ControlRequestEnvelope'
      responses:
        '200':
          description: CLI 在 stdout 上返回的成功响应。
          content:
            application/jsonl:
              schema:
                $ref: '#/components/schemas/ControlSuccessEnvelope'
        '4xx/5xx':
          description: CLI 在 stdout 上返回的错误响应。
          content:
            application/jsonl:
              schema:
                $ref: '#/components/schemas/ControlErrorEnvelope'
```

- `InitializeRequest`
  ```yaml
  type: object
  required: [subtype]
  properties:
    subtype:
      type: string
      enum: [initialize]
    hooks:
      type: object
      nullable: true
      description: 包含 Hook 匹配器与生成的回调 ID 列表。
  description: 流式模式下由 `_send_control_request` 触发，构建自注册的 Hook 配置。【F:src/claude_agent_sdk/_internal/query.py†L116-L145】
  ```

- `InterruptRequest`
  ```yaml
  type: object
  required: [subtype]
  properties:
    subtype:
      type: string
      enum: [interrupt]
  description: 请求 CLI 中断当前任务。【F:src/claude_agent_sdk/_internal/query.py†L491-L494】
  ```

- `SetPermissionModeRequest`
  ```yaml
  type: object
  required: [subtype, mode]
  properties:
    subtype:
      type: string
      enum: [set_permission_mode]
    mode:
      type: string
  description: 动态调整权限模式（如 `default`、`acceptEdits`、`bypassPermissions`）。【F:src/claude_agent_sdk/_internal/query.py†L495-L502】
  ```

- `SetModelRequest`
  ```yaml
  type: object
  required: [subtype]
  properties:
    subtype:
      type: string
      enum: [set_model]
    model:
      type: string
      nullable: true
  description: 切换 Claude 模型，允许 `null` 表示使用 CLI 默认模型。【F:src/claude_agent_sdk/_internal/query.py†L504-L511】
  ```

#### 5.2.2 `control_response`（SDK ↔ CLI）
当 CLI 返回控制响应或 SDK 处理 CLI 控制请求后，双方都会写入 `ControlSuccessEnvelope` 或 `ControlErrorEnvelope`。SDK 的控制请求响应通过 `_send_control_request` 协程等待并匹配 `request_id`；处理 CLI 控制请求时，`Query` 也会以相同格式回复结果或错误。【F:src/claude_agent_sdk/_internal/query.py†L294-L348】【F:src/claude_agent_sdk/_internal/query.py†L303-L315】

成功回执中的 `response` 字段可包含：
* 工具授权结果（`behavior`、`updatedInput`、`updatedPermissions`、`message`、`interrupt`）。【F:src/claude_agent_sdk/_internal/query.py†L234-L253】
* Hook 回调输出（字段名会从 `async_`/`continue_` 转回 CLI 期望的 `async`/`continue`）。【F:src/claude_agent_sdk/_internal/query.py†L34-L50】【F:src/claude_agent_sdk/_internal/query.py†L258-L273】
* MCP 桥接响应（`mcp_response` 包装 JSON-RPC 回执）。【F:src/claude_agent_sdk/_internal/query.py†L274-L289】

#### 5.2.3 `control_request`（CLI → SDK）
CLI 通过 stdout 推送控制请求，`Query` 在 `_handle_control_request` 内根据 subtype 分派。【F:src/claude_agent_sdk/_internal/query.py†L206-L293】

- `CanUseToolRequest`
  ```yaml
  type: object
  required: [subtype, tool_name, input]
  properties:
    subtype:
      type: string
      enum: [can_use_tool]
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
  description: CLI 请求执行工具时征询权限，SDK 返回 allow/deny 结果与可选的参数或权限更新。【F:src/claude_agent_sdk/types.py†L552-L558】【F:src/claude_agent_sdk/_internal/query.py†L215-L252】
  ```

- `HookCallbackRequest`
  ```yaml
  type: object
  required: [subtype, callback_id]
  properties:
    subtype:
      type: string
      enum: [hook_callback]
    callback_id:
      type: string
    input:
      type: object
      nullable: true
    tool_use_id:
      type: string
      nullable: true
  description: CLI 触发注册 Hook 的回调，SDK 查找并调用对应函数后返回结果字段。【F:src/claude_agent_sdk/types.py†L572-L577】【F:src/claude_agent_sdk/_internal/query.py†L258-L272】
  ```

- `McpMessageRequest`
  ```yaml
  type: object
  required: [subtype, server_name, message]
  properties:
    subtype:
      type: string
      enum: [mcp_message]
    server_name:
      type: string
    message:
      type: object
  description: CLI 将 MCP JSON-RPC 报文交由 SDK 托管的 MCP Server 处理，响应以 `mcp_response` 回写。【F:src/claude_agent_sdk/types.py†L579-L582】【F:src/claude_agent_sdk/_internal/query.py†L274-L289】
  ```

不支持的 subtype 会触发错误回执。【F:src/claude_agent_sdk/_internal/query.py†L291-L315】

#### 5.2.4 `control_cancel_request`（CLI → SDK）
CLI 可发送 `{"type": "control_cancel_request"}` 以尝试取消请求；Python SDK 当前仅忽略该报文，尚未实现取消逻辑。【F:src/claude_agent_sdk/_internal/query.py†L186-L189】

### 5.3 会话消息
CLI 输出的会话消息会被 `message_parser` 解析为 `UserMessage`、`AssistantMessage`、`SystemMessage`、`ResultMessage` 与 `StreamEvent` dataclass，覆盖对话内容、工具调用、成本统计及流式事件等场景。【F:src/claude_agent_sdk/_internal/message_parser.py†L24-L172】【F:src/claude_agent_sdk/types.py†L409-L498】

```yaml
components:
  schemas:
    UserMessageEnvelope:
      allOf:
        - $ref: '#/components/schemas/ConversationEnvelope'
        - type: object
          required: [message]
          properties:
            message:
              type: object
              required: [content]
              properties:
                content:
                  oneOf:
                    - type: string
                    - type: array
                      items:
                        $ref: '#/components/schemas/ToolContentBlock'
            parent_tool_use_id:
              type: string
              nullable: true
    AssistantMessageEnvelope:
      allOf:
        - $ref: '#/components/schemas/ConversationEnvelope'
        - type: object
          required: [message]
          properties:
            message:
              type: object
              required: [model, content]
              properties:
                model:
                  type: string
                content:
                  type: array
                  items:
                    $ref: '#/components/schemas/ToolContentBlock'
            parent_tool_use_id:
              type: string
              nullable: true
    SystemMessageEnvelope:
      allOf:
        - $ref: '#/components/schemas/ConversationEnvelope'
        - type: object
          required: [subtype]
          properties:
            subtype:
              type: string
            data:
              type: object
    ResultMessageEnvelope:
      allOf:
        - $ref: '#/components/schemas/ConversationEnvelope'
        - type: object
          required: [subtype, duration_ms, duration_api_ms, is_error, num_turns, session_id]
          properties:
            subtype:
              type: string
            duration_ms:
              type: integer
            duration_api_ms:
              type: integer
            is_error:
              type: boolean
            num_turns:
              type: integer
            session_id:
              type: string
            total_cost_usd:
              type: number
              nullable: true
            usage:
              type: object
              nullable: true
            result:
              type: string
              nullable: true
    StreamEventEnvelope:
      allOf:
        - $ref: '#/components/schemas/ConversationEnvelope'
        - type: object
          required: [uuid, session_id, event]
          properties:
            uuid:
              type: string
            session_id:
              type: string
            event:
              type: object
            parent_tool_use_id:
              type: string
              nullable: true
```

### 5.4 输入流事件
* **字符串 prompt**：`ClaudeSDKClient.query()` 会构造 `{"type": "user"}` 信封并写入 CLI。【F:src/claude_agent_sdk/client.py†L170-L199】
* **异步输入流**：SDK 会逐条透传用户提供的 JSON 消息，并在发送完毕后调用 `end_input()` 关闭 stdin；若传输层失效则抛出 `CLIConnectionError`。【F:src/claude_agent_sdk/_internal/query.py†L513-L521】【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L352-L377】

上述文档覆盖了当前 SDK 与 Claude Code CLI 之间基于 STDIO 的所有已实现接口，可作为自定义传输实现、协议调试或文档化参考。
