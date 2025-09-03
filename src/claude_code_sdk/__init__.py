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
    CanUseTool,
    ClaudeCodeOptions,
    ContentBlock,
    HookCallback,
    HookContext,
    HookMatcher,
    McpServerConfig,
    Message,
    PermissionMode,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolPermissionContext,
    ToolPermissionResponse,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
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
    # Tool callbacks
    "CanUseTool",
    "ToolPermissionContext",
    "ToolPermissionResponse",
    "HookCallback",
    "HookContext",
    "HookMatcher",
    # Errors
    "ClaudeSDKError",
    "CLIConnectionError",
    "CLINotFoundError",
    "ProcessError",
    "CLIJSONDecodeError",
]
