"""Type definitions for Claude SDK."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

from typing_extensions import NotRequired  # For Python < 3.11 compatibility

# Permission modes
PermissionMode = Literal["default", "acceptEdits", "plan", "bypassPermissions"]


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


# Hook events
HookEvent = Literal[
    "PreToolUse",
    "PostToolUse",
    "Notification",
    "UserPromptSubmit",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "SubagentStop",
    "PreCompact",
]


# Base hook input with common fields
@dataclass
class BaseHookInput:
    """Base hook input with common fields."""

    session_id: str
    transcript_path: str
    cwd: str
    permission_mode: str | None = None


# Individual hook input types
@dataclass
class PreToolUseHookInput:
    """Pre-tool use hook input."""

    hook_event_name: Literal["PreToolUse"]
    session_id: str
    transcript_path: str
    cwd: str
    tool_name: str
    tool_input: Any
    permission_mode: str | None = None


@dataclass
class PostToolUseHookInput:
    """Post-tool use hook input."""

    hook_event_name: Literal["PostToolUse"]
    session_id: str
    transcript_path: str
    cwd: str
    tool_name: str
    tool_input: Any
    tool_response: Any
    permission_mode: str | None = None


@dataclass
class NotificationHookInput:
    """Notification hook input."""

    hook_event_name: Literal["Notification"]
    session_id: str
    transcript_path: str
    cwd: str
    message: str
    permission_mode: str | None = None
    title: str | None = None


@dataclass
class UserPromptSubmitHookInput:
    """User prompt submit hook input."""

    hook_event_name: Literal["UserPromptSubmit"]
    session_id: str
    transcript_path: str
    cwd: str
    prompt: str
    permission_mode: str | None = None


@dataclass
class SessionStartHookInput:
    """Session start hook input."""

    hook_event_name: Literal["SessionStart"]
    session_id: str
    transcript_path: str
    cwd: str
    source: Literal["startup", "resume", "clear", "compact"]
    permission_mode: str | None = None


@dataclass
class SessionEndHookInput:
    """Session end hook input."""

    hook_event_name: Literal["SessionEnd"]
    session_id: str
    transcript_path: str
    cwd: str
    reason: Literal["clear", "logout", "prompt_input_exit", "other"]
    permission_mode: str | None = None


@dataclass
class StopHookInput:
    """Stop hook input."""

    hook_event_name: Literal["Stop"]
    session_id: str
    transcript_path: str
    cwd: str
    stop_hook_active: bool
    permission_mode: str | None = None


@dataclass
class SubagentStopHookInput:
    """Subagent stop hook input."""

    hook_event_name: Literal["SubagentStop"]
    session_id: str
    transcript_path: str
    cwd: str
    stop_hook_active: bool
    permission_mode: str | None = None


@dataclass
class PreCompactHookInput:
    """Pre-compact hook input."""

    hook_event_name: Literal["PreCompact"]
    session_id: str
    transcript_path: str
    cwd: str
    trigger: Literal["manual", "auto"]
    permission_mode: str | None = None
    custom_instructions: str | None = None


# Union type for all hook inputs
HookInput = (
    PreToolUseHookInput
    | PostToolUseHookInput
    | NotificationHookInput
    | UserPromptSubmitHookInput
    | SessionStartHookInput
    | SessionEndHookInput
    | StopHookInput
    | SubagentStopHookInput
    | PreCompactHookInput
)


@dataclass
class HookJSONOutput:
    """Hook callback output."""

    continue_: bool | None = None  # 'continue' is reserved in Python
    suppress_output: bool | None = None
    stop_reason: str | None = None
    decision: Literal["approve", "block"] | None = None
    system_message: str | None = None

    # PreToolUse specific
    permission_decision: Literal["allow", "deny", "ask"] | None = None
    permission_decision_reason: str | None = None
    reason: str | None = None

    # Hook-specific outputs (for future extension)
    hook_specific_output: dict[str, Any] | None = None


# Hook callback signature
HookCallback = Callable[
    [HookInput, str | None, dict[str, Any]],  # input, tool_use_id, options
    Awaitable[HookJSONOutput],
]


@dataclass
class HookCallbackMatcher:
    """Hook callback matcher with optional pattern matching."""

    matcher: str | None = None
    hooks: list[HookCallback] = field(default_factory=list)


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
    hooks: dict[HookEvent, list[HookCallbackMatcher]] | None = None
