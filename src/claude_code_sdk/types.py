"""Type definitions for Claude SDK."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

try:
    from typing import NotRequired  # Python 3.11+
except ImportError:
    from typing_extensions import NotRequired  # For Python < 3.11 compatibility

# Permission modes
PermissionMode = Literal["default", "acceptEdits", "plan", "bypassPermissions"]


# Tool callback types
@dataclass
class ToolPermissionContext:
    """Context information for tool permission callbacks."""

    signal: Any | None = None  # Future: abort signal support
    suggestions: list[str] = field(default_factory=list)  # Permission suggestions from CLI


@dataclass
class ToolPermissionResponse:
    """Response from tool permission callback."""

    allow: bool
    input: dict[str, Any] | None = None  # Optional: modified input parameters
    reason: str | None = None  # Optional: reason for decision


ToolPermissionCallback = Callable[
    [str, dict[str, Any], ToolPermissionContext],
    Awaitable[ToolPermissionResponse]
]


# Hook callback types
@dataclass
class HookContext:
    """Context information for hook callbacks."""

    signal: Any | None = None  # Future: abort signal support


HookCallback = Callable[
    [dict[str, Any], str | None, HookContext],  # input, tool_use_id, context
    Awaitable[dict[str, Any]]  # response data
]


# Hook matcher configuration
@dataclass
class HookMatcher:
    """Hook matcher configuration."""

    matcher: dict[str, Any] | None = None  # Matcher criteria
    hooks: list[HookCallback] = field(default_factory=list)  # Callbacks to invoke


# MCP Server config
class McpStdioServerConfig(TypedDict):
    """MCP stdio server configuration."""

    type: NotRequired[Literal["stdio"]]  # Optional for backwards compatibility
    command: str
    args: NotRequired[list[str]]
    env: NotRequired[dict[str, str]]


class McpSSEServerConfig(TypedDict):
    """MCP SSE server configuration."""

    type: Literal["sse"]
    url: str
    headers: NotRequired[dict[str, str]]


class McpHttpServerConfig(TypedDict):
    """MCP HTTP server configuration."""

    type: Literal["http"]
    url: str
    headers: NotRequired[dict[str, str]]


McpServerConfig = McpStdioServerConfig | McpSSEServerConfig | McpHttpServerConfig


# Content block types
@dataclass
class TextBlock:
    """Text content block."""

    text: str


@dataclass
class ThinkingBlock:
    """Thinking content block."""

    thinking: str
    signature: str


@dataclass
class ToolUseBlock:
    """Tool use content block."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResultBlock:
    """Tool result content block."""

    tool_use_id: str
    content: str | list[dict[str, Any]] | None = None
    is_error: bool | None = None


ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock


# Message types
@dataclass
class UserMessage:
    """User message."""

    content: str | list[ContentBlock]


@dataclass
class AssistantMessage:
    """Assistant message with content blocks."""

    content: list[ContentBlock]
    model: str


@dataclass
class SystemMessage:
    """System message with metadata."""

    subtype: str
    data: dict[str, Any]


@dataclass
class ResultMessage:
    """Result message with cost and usage information."""

    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    total_cost_usd: float | None = None
    usage: dict[str, Any] | None = None
    result: str | None = None


Message = UserMessage | AssistantMessage | SystemMessage | ResultMessage


@dataclass
class ClaudeCodeOptions:
    """Query options for Claude SDK."""

    allowed_tools: list[str] = field(default_factory=list)
    max_thinking_tokens: int = 8000
    system_prompt: str | None = None
    append_system_prompt: str | None = None
    mcp_servers: dict[str, McpServerConfig] | str | Path = field(default_factory=dict)
    permission_mode: PermissionMode | None = None
    continue_conversation: bool = False
    resume: str | None = None
    max_turns: int | None = None
    disallowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    permission_prompt_tool_name: str | None = None
    cwd: str | Path | None = None
    settings: str | None = None
    add_dirs: list[str | Path] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    extra_args: dict[str, str | None] = field(
        default_factory=dict
    )  # Pass arbitrary CLI flags

    # Tool permission callback
    tool_permission_callback: ToolPermissionCallback | None = None

    # Hook configurations
    hooks: dict[str, list[HookMatcher]] | None = None


# SDK Control Protocol
class SDKControlInterruptRequest(TypedDict):
    subtype: Literal["interrupt"]


class SDKControlPermissionRequest(TypedDict):
    subtype: Literal["can_use_tool"]
    tool_name: str
    input: dict[str, Any]
    # TODO: Add PermissionUpdate type here
    permission_suggestions: list[Any] | None
    blocked_path: str | None

class SDKControlInitializeRequest(TypedDict):
    subtype: Literal["initialize"]
    # TODO: Use HookEvent names as the key.
    hooks: dict[str, Any] | None


class SDKControlSetPermissionModeRequest(TypedDict):
    subtype: Literal["set_permission_mode"]
    # TODO: Add PermissionMode
    mode: str


class SDKHookCallbackRequest(TypedDict):
    subtype: Literal["hook_callback"]
    callback_id: str
    input: Any
    tool_use_id: str | None


class SDKControlMcpMessageRequest(TypedDict):
    subtype: Literal["mcp_message"]
    server_name: str
    message: Any


class SDKControlRequest(TypedDict):
    type: Literal["control_request"]
    request_id: str
    request: (
        SDKControlInterruptRequest
        | SDKControlPermissionRequest
        | SDKControlInitializeRequest
        | SDKControlSetPermissionModeRequest
        | SDKHookCallbackRequest
        | SDKControlMcpMessageRequest
    )


class ControlResponse(TypedDict):
    subtype: Literal["success"]
    request_id: str
    response: dict[str, Any] | None


class ControlErrorResponse(TypedDict):
    subtype: Literal["error"]
    request_id: str
    error: str


class SDKControlResponse(TypedDict):
    type: Literal["control_response"]
    response: ControlResponse | ControlErrorResponse
