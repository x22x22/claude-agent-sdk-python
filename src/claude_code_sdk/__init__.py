"""Claude SDK for Python."""

from ._errors import (
    ClaudeSDKError,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    ProcessError,
)
from ._internal.transport import Transport
from .client import ClaudeSDKClient
from .query import query
from .types import (
    AssistantMessage,
    ClaudeCodeOptions,
    ContentBlock,
    HookCallback,
    HookCallbackMatcher,
    HookEvent,
    HookInput,
    HookJSONOutput,
    McpServerConfig,
    Message,
    NotificationHookInput,
    PermissionMode,
    PostToolUseHookInput,
    PreCompactHookInput,
    PreToolUseHookInput,
    ResultMessage,
    SessionEndHookInput,
    SessionStartHookInput,
    StopHookInput,
    SubagentStopHookInput,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    UserPromptSubmitHookInput,
)

__version__ = "0.0.20"

__all__ = [
    # Main exports
    "query",
    # Transport
    "Transport",
    "ClaudeSDKClient",
    # Types
    "PermissionMode",
    "McpServerConfig",
    "UserMessage",
    "AssistantMessage",
    "SystemMessage",
    "ResultMessage",
    "Message",
    "ClaudeCodeOptions",
    "TextBlock",
    "ThinkingBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    "ContentBlock",
    # Hook types
    "HookEvent",
    "HookCallback",
    "HookCallbackMatcher",
    "HookInput",
    "HookJSONOutput",
    "PreToolUseHookInput",
    "PostToolUseHookInput",
    "NotificationHookInput",
    "UserPromptSubmitHookInput",
    "SessionStartHookInput",
    "SessionEndHookInput",
    "StopHookInput",
    "SubagentStopHookInput",
    "PreCompactHookInput",
    # Errors
    "ClaudeSDKError",
    "CLIConnectionError",
    "CLINotFoundError",
    "ProcessError",
    "CLIJSONDecodeError",
]
