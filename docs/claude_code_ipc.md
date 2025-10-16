# Claude Code CLI IPC 依赖与报文规范

## 1. IPC 依赖概览
- Python SDK 通过 `SubprocessCLITransport` 启动 `claude` 命令行进程，统一追加 `--output-format stream-json`、`--verbose` 以及按需的系统提示词、工具白名单/黑名单、模型、权限模式、MCP、Hook 与自定义 CLI 标志；在流式模式下还会拼接 `--input-format stream-json` 以维持 stdin 事件流。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L33-L200】
- 传输层在启动 CLI 时会合并系统环境变量、用户自定义 `env` 与 SDK 标识，支持自定义工作目录、stderr 处理器，并在 `_read_stdout` 中处理行缓冲、JSON 解析与进程退出异常。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L204-L456】
- `InternalClient` 与 `Query` 组成运行时控制平面，负责初始化握手、控制请求发送与分派、Hook/MCP 桥接以及对话消息路由，构成 SDK 到 CLI 的完整 IPC 链路。【F:src/claude_agent_sdk/_internal/client.py†L34-L105】【F:src/claude_agent_sdk/_internal/query.py†L53-L205】
- CLI 输出的 JSON 行在进入业务层之前由 `message_parser` 解析为强类型数据对象；对应的数据结构、控制协议类型与字段映射集中在 `types.py` 内部定义中。【F:src/claude_agent_sdk/_internal/message_parser.py†L24-L172】【F:src/claude_agent_sdk/types.py†L409-L612】

### 1.1 进程启动与运行时约束
- CLI 可执行文件路径会先通过 `shutil.which` 及常见目录进行探测，若未找到则抛出 `CLINotFoundError` 并提示安装与 PATH 配置方法。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L61-L85】
- 若未设置 `CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK`，SDK 会在建立传输前执行 `claude -v` 并校验版本号是否不低于 `2.0.0`，不足时打印警告信息。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L458-L498】
- 非流式模式使用 `--print -- <prompt>` 将初始提示语写入 CLI；流式模式保持 stdin 打开以传输 JSON 行并在输入结束后调用 `end_input()` 关闭写端。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L194-L261】【F:src/claude_agent_sdk/_internal/query.py†L513-L521】
- stderr 可交由用户回调或调试流处理；所有异步任务组与子进程在关闭时都会显式清理，避免资源泄漏。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L225-L346】
- 连接前 `query()` 与 `ClaudeSDKClient` 会分别设置 `CLAUDE_CODE_ENTRYPOINT`（值为 `sdk-py` / `sdk-py-client`）用于标识调用入口；`SubprocessCLITransport` 会在合并环境变量时强制写入 `CLAUDE_CODE_ENTRYPOINT` 与 `CLAUDE_AGENT_SDK_VERSION`，供 CLI 侧进行客户端识别与兼容性判断。【F:src/claude_agent_sdk/query.py†L12-L95】【F:src/claude_agent_sdk/client.py†L1-L116】【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L204-L303】

### 1.2 STDIO 信道与消息调度
- 所有 IPC 报文均以换行分隔 JSON (`application/jsonl`) 传输。`SubprocessCLITransport` 会在读取 stdout 时累积缓冲并反复解析，超出最大缓冲或遇到无效 JSON 时抛出 `CLIJSONDecodeError`；若 CLI 以非零码退出则抛出 `ProcessError`。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L352-L456】
- `Query` 在读取消息时优先处理控制报文（`control_response` / `control_request` / `control_cancel_request`），其余类型投递至会话消息通道；当 CLI 发来控制请求时会根据 subtype 调用权限回调、Hook 或 MCP 桥接，并以 JSON 行写回结果或错误。【F:src/claude_agent_sdk/_internal/query.py†L154-L316】

### 1.3 CLI 参数映射与运行时配置
`ClaudeAgentOptions` 暴露的主要开关都会在 `_build_command()` 中转换为命令行参数，涵盖系统提示词（`--system-prompt`/`--append-system-prompt`）、工具白名单/黑名单（`--allowedTools`/`--disallowedTools`）、轮次数限制（`--max-turns`）、模型/权限模式相关开关（`--model`、`--permission-mode`、`--permission-prompt-tool`、`--continue`、`--resume`、`--settings`、`--setting-sources`）、目录挂载（`--add-dir`）、MCP 配置（`--mcp-config`，会在传递 SDK 自建服务器时移除 `instance` 字段）、流式消息控制（`--include-partial-messages`、`--fork-session`）、多 Agent 定义（`--agents`）以及自定义扩展标志（`extra_args` 会被透传为 `--<flag> <value>` 或布尔开关）。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L87-L193】

启动过程中还会根据 `ClaudeAgentOptions` 合并用户环境变量、设置工作目录、选择运行用户以及决定是否管道 stderr，从而允许在受限环境中精细化控制 CLI 进程的行为。【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L214-L303】

### 1.4 初始化握手返回值
- 成功连接后 `Query.initialize()` 会把 CLI 通过 `control_response.success` 返回的初始化负载缓存到 `_initialization_result`，供后续查询使用。【F:src/claude_agent_sdk/_internal/query.py†L131-L146】
- `ClaudeSDKClient.get_server_info()` 直接回传该结构，其中通常包含 CLI 公布的命令列表、输出风格以及能力标志，帮助上层根据 CLI 版本裁剪体验。【F:src/claude_agent_sdk/client.py†L263-L296】

> CLI 返回的字段会随版本演进而扩展；SDK 仅做透明透传，调用方应做好可选字段判空处理。

## 2. IPC 接口清单
| 接口方向 | 触发方 | 报文类型 | 描述 | Schema 小节 |
| --- | --- | --- | --- | --- |
| SDK → CLI | SDK | `control_request.initialize` | 流式模式初始化 Hook 映射与能力信息。【F:src/claude_agent_sdk/_internal/query.py†L107-L145】 | [3.2.1](#321-control_request-sdk--cli) |
| SDK → CLI | SDK | `control_request.interrupt` | 用户请求打断当前轮会话。【F:src/claude_agent_sdk/_internal/query.py†L491-L499】 | [3.2.1](#321-control_request-sdk--cli) |
| SDK → CLI | SDK | `control_request.set_permission_mode` | 动态切换权限模式（`default`/`acceptEdits`/`plan`/`bypassPermissions`）。【F:src/claude_agent_sdk/_internal/query.py†L495-L502】 | [3.2.1](#321-control_request-sdk--cli) |
| SDK → CLI | SDK | `control_request.set_model` | 切换 Claude 模型或恢复默认值。【F:src/claude_agent_sdk/_internal/query.py†L504-L511】 | [3.2.1](#321-control_request-sdk--cli) |
| SDK → CLI | SDK | `user`/`system` 等会话输入 | `ClaudeSDKClient.query()` 将字符串或自定义 JSON 消息写入 CLI stdin。【F:src/claude_agent_sdk/client.py†L170-L199】【F:src/claude_agent_sdk/_internal/query.py†L513-L521】 | [3.4](#34-输入流事件) |
| CLI → SDK | CLI | `control_response.success` / `control_response.error` | 对 SDK 控制请求的成功或失败应答。【F:src/claude_agent_sdk/_internal/query.py†L294-L348】【F:src/claude_agent_sdk/types.py†L598-L612】 | [3.2.2](#322-control_response-sdk--cli) |
| CLI → SDK | CLI | `control_request.can_use_tool` | CLI 在执行工具前征询权限与参数更新。【F:src/claude_agent_sdk/_internal/query.py†L206-L256】 | [3.2.3](#323-control_request-cli--sdk) |
| CLI → SDK | CLI | `control_request.hook_callback` | CLI 触发已注册 Hook，SDK 返回规范化结果字段。【F:src/claude_agent_sdk/_internal/query.py†L258-L273】 | [3.2.3](#323-control_request-cli--sdk) |
| CLI → SDK | CLI | `control_request.mcp_message` | CLI 将 MCP JSON-RPC 报文交由 SDK 托管的 MCP 服务器处理。【F:src/claude_agent_sdk/_internal/query.py†L274-L289】【F:src/claude_agent_sdk/_internal/query.py†L357-L489】 | [3.2.3](#323-control_request-cli--sdk) |
| CLI → SDK | CLI | `control_cancel_request` | CLI 侧的取消通知，当前 Python SDK 占位忽略该报文。【F:src/claude_agent_sdk/_internal/query.py†L186-L189】 | [3.2.4](#324-control_cancel_request-cli--sdk) |
| CLI → SDK | CLI | `user` 会话消息 | CLI 会在会话流中回放或补充用户消息，保持上下文完整性并驱动 Hook/工具分支逻辑，由 `message_parser` 解析为 `UserMessage` 对象。【F:src/claude_agent_sdk/_internal/message_parser.py†L34-L66】 | [3.3](#33-会话消息) |
| CLI → SDK | CLI | `assistant`/`result`/`system`/`stream_event` 等会话消息 | Claude Code 主输出流，包含助手内容、执行统计与流式事件，由 `message_parser` 解析为强类型对象。【F:src/claude_agent_sdk/_internal/query.py†L191-L204】【F:src/claude_agent_sdk/_internal/message_parser.py†L24-L172】 | [3.3](#33-会话消息) |

## 3. 报文规范（OpenAPI 风格）
以下规范使用 OpenAPI 3.1 风格描述 STDIO 报文。除特殊说明外，报文均为 UTF-8 编码的换行分隔 JSON（`application/jsonl`）。

```yaml
openapi: 3.1.0
info:
  title: Claude Code CLI IPC Protocol
  version: 1.0.0
servers:
  - url: stdio://claude
    description: SDK 通过标准输入输出与 Claude Code CLI 通信
paths:
  /sdk-to-cli/control-request:
    post:
      summary: SDK 发送控制请求
      description: 通过向 CLI 标准输入写入 JSON 行触发控制操作。
      requestBody:
        required: true
        content:
          application/jsonl:
            schema:
              $ref: '#/components/schemas/ControlRequestEnvelope'
      responses:
        "202":
          description: CLI 通过 `control_response` 报文异步响应
  /sdk-to-cli/message:
    post:
      summary: SDK 推送业务消息
      description: 在流式模式下传递用户、系统等消息块。
      requestBody:
        required: true
        content:
          application/jsonl:
            schema:
              oneOf:
                - $ref: '#/components/schemas/UserMessageEnvelope'
                - $ref: '#/components/schemas/SystemMessageEnvelope'
      responses:
        "202":
          description: CLI 通过主输出流异步返回助手消息
  /cli-to-sdk/control-response:
    get:
      summary: CLI 返回控制请求结果
      description: SDK 从标准输出读取 `control_response` 报文，并匹配 `request_id`。
      responses:
        "200":
          content:
            application/jsonl:
              schema:
                $ref: '#/components/schemas/ControlResponseEnvelope'
  /cli-to-sdk/control-request:
    get:
      summary: CLI 主动发起控制请求
      description: CLI 请求 SDK 处理工具权限、Hook 回调或 MCP 桥接。
      responses:
        "200":
          content:
            application/jsonl:
              schema:
                $ref: '#/components/schemas/ControlRequestEnvelope'
  /cli-to-sdk/message:
    get:
      summary: CLI 主输出消息
      description: 包含助手回答、执行结果、系统提示与流式事件。
      responses:
        "200":
          content:
            application/jsonl:
              schema:
                oneOf:
                  - $ref: '#/components/schemas/UserMessageEnvelope'
                  - $ref: '#/components/schemas/AssistantMessageEnvelope'
                  - $ref: '#/components/schemas/ResultMessageEnvelope'
                  - $ref: '#/components/schemas/SystemMessageEnvelope'
                  - $ref: '#/components/schemas/StreamEventEnvelope'
components:
  schemas:
    ControlRequestEnvelope:
      type: object
      required: [type, request_id, request]
      properties:
        type:
          type: string
          const: control_request
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
    InitializeRequest:
      type: object
      required: [subtype]
      properties:
        subtype:
          type: string
          const: initialize
        hooks:
          type: object
          nullable: true
          description: 包含 Hook 匹配器与生成的回调 ID 列表。
          additionalProperties:
            type: array
            items:
              type: object
              properties:
                matcher:
                  type: object
                  nullable: true
                hookCallbackIds:
                  type: array
                  items:
                    type: string
      description: 流式模式下由 `_send_control_request` 触发，构建自注册的 Hook 配置。【F:src/claude_agent_sdk/_internal/query.py†L116-L145】
    InitializeSuccessPayload:
      type: object
      description: CLI 在初始化成功时返回的元数据，典型字段包含 `commands`（可用指令）、`output_style`/`output_styles`（当前与可选输出格式）及其他能力标志，SDK 不做强制约束并原样缓存。【F:src/claude_agent_sdk/_internal/query.py†L131-L146】【F:src/claude_agent_sdk/client.py†L263-L296】
    InterruptRequest:
      type: object
      required: [subtype]
      properties:
        subtype:
          type: string
          const: interrupt
      description: 请求 CLI 中断当前任务。【F:src/claude_agent_sdk/_internal/query.py†L491-L494】
    SetPermissionModeRequest:
      type: object
      required: [subtype, mode]
      properties:
        subtype:
          type: string
          const: set_permission_mode
        mode:
          type: string
      description: 动态调整权限模式。【F:src/claude_agent_sdk/_internal/query.py†L495-L502】
    SetModelRequest:
      type: object
      required: [subtype]
      properties:
        subtype:
          type: string
          const: set_model
        model:
          type: string
          nullable: true
      description: 切换 Claude 模型，允许 `null` 表示使用 CLI 默认模型。【F:src/claude_agent_sdk/_internal/query.py†L504-L511】
    CanUseToolRequest:
      type: object
      required: [subtype, tool_name, input]
      properties:
        subtype:
          type: string
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
      description: CLI 请求执行工具时征询权限，SDK 返回 allow/deny 结果与可选的参数/权限更新。【F:src/claude_agent_sdk/types.py†L552-L558】【F:src/claude_agent_sdk/_internal/query.py†L215-L252】
    HookCallbackRequest:
      type: object
      required: [subtype, callback_id]
      properties:
        subtype:
          type: string
          const: hook_callback
        callback_id:
          type: string
        input:
          type: object
          nullable: true
        tool_use_id:
          type: string
          nullable: true
      description: CLI 触发注册 Hook 的回调，SDK 查找并调用对应函数后返回结果字段。【F:src/claude_agent_sdk/types.py†L572-L577】【F:src/claude_agent_sdk/_internal/query.py†L258-L272】
    McpMessageRequest:
      type: object
      required: [subtype, server_name, message]
      properties:
        subtype:
          type: string
          const: mcp_message
        server_name:
          type: string
        message:
          type: object
      description: CLI 将 MCP JSON-RPC 报文交由 SDK 托管的 MCP Server 处理，响应以 `mcp_response` 回写。【F:src/claude_agent_sdk/types.py†L579-L582】【F:src/claude_agent_sdk/_internal/query.py†L274-L289】
    ControlResponseEnvelope:
      type: object
      required: [type, response]
      properties:
        type:
          type: string
          const: control_response
        response:
          oneOf:
            - $ref: '#/components/schemas/ControlSuccessResponse'
            - $ref: '#/components/schemas/ControlErrorResponse'
      description: 控制请求回执封装，对应 `ControlResponse` 定义。【F:src/claude_agent_sdk/types.py†L598-L612】
    ControlSuccessResponse:
      type: object
      required: [subtype, request_id]
      properties:
        subtype:
          type: string
          const: success
        request_id:
          type: string
        response:
          oneOf:
            - $ref: '#/components/schemas/InitializeSuccessPayload'
            - type: object
          nullable: true
      description: 控制请求成功响应，`response` 字段内容依赖具体子类型；初始化场景会返回 CLI 公布的元数据。【F:src/claude_agent_sdk/_internal/query.py†L234-L289】
    ControlErrorResponse:
      type: object
      required: [subtype, request_id, error]
      properties:
        subtype:
          type: string
          const: error
        request_id:
          type: string
        error:
          type: string
      description: 控制请求失败响应，携带错误描述字符串。【F:src/claude_agent_sdk/_internal/query.py†L303-L315】
    ControlCancelRequestEnvelope:
      type: object
      required: [type]
      properties:
        type:
          type: string
          const: control_cancel_request
        request_id:
          type: string
          nullable: true
        reason:
          type: string
          nullable: true
      description: CLI 侧的取消通知，目前 SDK 未实现处理逻辑。【F:src/claude_agent_sdk/_internal/query.py†L186-L189】
    UserMessageEnvelope:
      type: object
      required: [type, message]
      properties:
        type:
          type: string
          const: user
        message:
          $ref: '#/components/schemas/UserMessagePayload'
        parent_tool_use_id:
          type: string
          nullable: true
      description: SDK 写入 CLI 的用户消息封装，同时也被 CLI 回放用户输入时复用同一结构。【F:src/claude_agent_sdk/client.py†L170-L199】【F:src/claude_agent_sdk/_internal/message_parser.py†L34-L66】
    UserMessagePayload:
      type: object
      required: [role, content]
      properties:
        role:
          type: string
          const: user
        content:
          oneOf:
            - type: string
            - type: array
              items:
                $ref: '#/components/schemas/ContentBlock'
    SystemMessageEnvelope:
      type: object
      required: [type, subtype]
      properties:
        type:
          type: string
          const: system
        subtype:
          type: string
        data:
          type: object
      description: CLI 与 SDK 之间的系统状态推送或统计信息。
    AssistantMessageEnvelope:
      type: object
      required: [type, message]
      properties:
        type:
          type: string
          const: assistant
        message:
          type: object
          required: [role, content, model]
          properties:
            role:
              type: string
              const: assistant
            content:
              type: array
              items:
                $ref: '#/components/schemas/ContentBlock'
            model:
              type: string
        parent_tool_use_id:
          type: string
          nullable: true
      description: Claude Code CLI 输出的助手回复消息。【F:src/claude_agent_sdk/_internal/message_parser.py†L47-L83】
    ResultMessageEnvelope:
      type: object
      required: [type, subtype, duration_ms, duration_api_ms, is_error, num_turns, session_id]
      properties:
        type:
          type: string
          const: result
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
      description: CLI 输出的整体会话统计或工具执行结果。【F:src/claude_agent_sdk/_internal/message_parser.py†L120-L150】
    StreamEventEnvelope:
      type: object
      required: [type, uuid, session_id, event]
      properties:
        type:
          type: string
          const: stream_event
        uuid:
          type: string
        session_id:
          type: string
        event:
          type: object
        parent_tool_use_id:
          type: string
          nullable: true
      description: CLI 推送的流式事件封装。【F:src/claude_agent_sdk/_internal/message_parser.py†L152-L172】
    ContentBlock:
      type: object
      required: [type]
      properties:
        type:
          type: string
          enum: [text, thinking, tool_use, tool_result]
        text:
          type: string
        thinking:
          type: string
        signature:
          type: string
        id:
          type: string
        name:
          type: string
        input:
          type: object
        tool_use_id:
          type: string
        content:
          oneOf:
            - type: string
            - type: array
              items:
                type: object
          nullable: true
        is_error:
          type: boolean
          nullable: true
      description: CLI 可能返回的内容块类型，对应工具调用、思考或文本片段。【F:src/claude_agent_sdk/types.py†L409-L444】
```

### 3.2 控制通道
#### 3.2.1 `control_request`（SDK → CLI）
SDK 在 `_send_control_request` 中将控制请求序列化为 JSON 行写入 CLI stdin，并等待匹配 `request_id` 的 `control_response`；发送失败会抛出 `CLIConnectionError` 并终止后续写入。【F:src/claude_agent_sdk/_internal/query.py†L317-L355】【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L352-L378】

- **流式模式限制**：仅当 `Query` 运行在流式模式（`is_streaming_mode=True`）时才会发送控制请求，否则直接返回 `None`，提醒调用方无需初始化额外控制通道。【F:src/claude_agent_sdk/_internal/query.py†L118-L144】
- **响应超时**：SDK 会为每个控制请求注册事件并在 60 秒超时时间内等待响应；若 CLI 未在期限内返回 `control_response`，SDK 将清理挂起状态并抛出 `Control request timeout` 异常。【F:src/claude_agent_sdk/_internal/query.py†L317-L358】

#### 3.2.2 `control_response`（SDK ↔ CLI）
当 CLI 返回控制响应或 SDK 处理 CLI 控制请求后，双方都会写入 `ControlSuccessResponse` 或 `ControlErrorResponse`。成功响应中常见字段包括工具授权结果（`behavior`、`updatedInput`、`updatedPermissions`、`message`、`interrupt`）、Hook 回调输出（`async`、`continue`、`hookSpecificOutput` 等字段会在 Python 端与 CLI 之间转换为 `async_`/`continue_`）以及 MCP 桥接响应（`mcp_response`）。【F:src/claude_agent_sdk/_internal/query.py†L234-L289】

#### 3.2.3 `control_request`（CLI → SDK）
CLI 通过 stdout 推送控制请求，`Query` 在 `_handle_control_request` 中根据 subtype 分派。`can_use_tool` 会调用用户权限回调，`hook_callback` 会执行已注册 Hook，`mcp_message` 会将 JSON-RPC 报文转发给 MCP Server 并返回封装后的结果；未识别的 subtype 会返回错误响应。【F:src/claude_agent_sdk/_internal/query.py†L206-L315】

##### MCP 桥接支持的 JSON-RPC 方法
- `initialize`：返回 `protocolVersion`、`tools` 能力和 `serverInfo`，当前仅声明工具能力且未实现 `listChanged` 推送。【F:src/claude_agent_sdk/_internal/query.py†L360-L410】
- `tools/list`：调用 MCP 服务器的 `ListToolsRequest` 处理器并将工具元数据（名称、描述、输入 Schema）序列化为 JSON-RPC 结果。【F:src/claude_agent_sdk/_internal/query.py†L411-L435】
- `tools/call`：将 CLI 传入的工具名称与参数组装为 `CallToolRequest` 并转换返回内容块（文本、图片等），必要时透出 `is_error` 标志。【F:src/claude_agent_sdk/_internal/query.py†L437-L469】
- `notifications/initialized`：简单确认通知并回传空结果。未被列出的其他方法会返回 `-32601` 错误，异常情况下统一映射为 `-32603`。【F:src/claude_agent_sdk/_internal/query.py†L471-L489】

若 CLI 指定的 `server_name` 未注册，则立即返回 `-32601` 错误并复用原始请求 `id`，以便 CLI 侧正确回溯失败原因。【F:src/claude_agent_sdk/_internal/query.py†L373-L381】

#### 3.2.4 `control_cancel_request`（CLI → SDK）
CLI 可发送 `{"type": "control_cancel_request"}` 以尝试取消控制请求；Python SDK 当前仅记录日志并忽略该报文，尚未实现取消逻辑。【F:src/claude_agent_sdk/_internal/query.py†L186-L189】

### 3.3 会话消息
CLI 输出的会话消息会被 `message_parser` 解析为 `UserMessage`、`AssistantMessage`、`SystemMessage`、`ResultMessage` 与 `StreamEvent` dataclass，覆盖对话内容、工具调用、成本统计及流式事件等场景。【F:src/claude_agent_sdk/_internal/message_parser.py†L24-L172】【F:src/claude_agent_sdk/types.py†L409-L498】
其中 `UserMessage` 可出现在 CLI 输出流中，用于回放用户输入或在多阶段流程中注入追加指令，确保后续 Hook、工具调用与 MCP 会话获得完整上下文。【F:src/claude_agent_sdk/_internal/message_parser.py†L34-L66】

### 3.4 输入流事件
- **字符串 prompt**：`ClaudeSDKClient.query()` 会构造 `{"type": "user"}` 信封并写入 CLI。【F:src/claude_agent_sdk/client.py†L170-L199】
- **异步输入流**：SDK 会逐条透传用户提供的 JSON 消息，并在发送完毕后调用 `end_input()` 关闭 stdin；若传输层失效则抛出 `CLIConnectionError` 并停止写入。【F:src/claude_agent_sdk/_internal/query.py†L513-L521】【F:src/claude_agent_sdk/_internal/transport/subprocess_cli.py†L352-L377】

> 注：当 CLI 需要字段名 `async`、`continue` 时，Python 端对应 `HookCallbackResult` 会使用 `async_`、`continue_` 存储并在发送/接收时自动转换，避免与 Python 关键字冲突。【F:src/claude_agent_sdk/_internal/query.py†L34-L50】【F:src/claude_agent_sdk/types.py†L552-L612】

上述文档覆盖了当前 SDK 与 Claude Code CLI 之间基于 STDIO 的控制与会话通道，可作为自定义传输实现、协议调试或文档化参考。
