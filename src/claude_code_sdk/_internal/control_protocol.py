"""Control protocol types and handlers for SDK-CLI communication."""

from dataclasses import dataclass, field
from typing import Any, Literal

from ..types import HookEvent, PermissionMode


@dataclass
class SDKHookCallbackMatcher:
    """Hook callback matcher for control protocol."""

    matcher: str | None = None
    hook_callback_ids: list[str] = field(default_factory=list)


@dataclass
class SDKControlInitializeRequest:
    """Initialize request for control protocol."""

    subtype: Literal["initialize"]
    hooks: dict[HookEvent, list[SDKHookCallbackMatcher]] | None = None


@dataclass
class SDKControlInterruptRequest:
    """Interrupt request for control protocol."""

    subtype: Literal["interrupt"]


@dataclass
class SDKControlPermissionRequest:
    """Permission request for control protocol."""

    subtype: Literal["can_use_tool"]
    tool_name: str
    input: dict[str, Any]
    permission_suggestions: list[dict[str, Any]] | None = None
    blocked_path: str | None = None


@dataclass
class SDKControlSetPermissionModeRequest:
    """Set permission mode request for control protocol."""

    subtype: Literal["set_permission_mode"]
    mode: PermissionMode


@dataclass
class SDKHookCallbackRequest:
    """Hook callback request for control protocol."""

    subtype: Literal["hook_callback"]
    callback_id: str
    input: dict[str, Any]
    tool_use_id: str | None = None


@dataclass
class SDKControlMcpMessageRequest:
    """MCP message request for control protocol."""

    subtype: Literal["mcp_message"]
    server_name: str
    message: dict[str, Any]


# Union type for all control request subtypes
SDKControlRequestSubtype = (
    SDKControlInitializeRequest
    | SDKControlInterruptRequest
    | SDKControlPermissionRequest
    | SDKControlSetPermissionModeRequest
    | SDKHookCallbackRequest
    | SDKControlMcpMessageRequest
)


@dataclass
class SDKControlRequest:
    """Control request wrapper."""

    type: Literal["control_request"]
    request_id: str
    request: SDKControlRequestSubtype


@dataclass
class SDKControlCancelRequest:
    """Cancel a control request."""

    type: Literal["control_cancel_request"]
    request_id: str


@dataclass
class ControlSuccessResponse:
    """Successful control response."""

    subtype: Literal["success"]
    request_id: str
    response: dict[str, Any] | None = None


@dataclass
class ControlErrorResponse:
    """Error control response."""

    subtype: Literal["error"]
    request_id: str
    error: str


# Union type for control responses
ControlResponse = ControlSuccessResponse | ControlErrorResponse


@dataclass
class SDKControlResponse:
    """Control response wrapper."""

    type: Literal["control_response"]
    response: ControlResponse


@dataclass
class Command:
    """Command metadata."""

    name: str
    description: str
    argument_hint: str


@dataclass
class SDKControlInitializeResponse:
    """Initialize response from control protocol."""

    commands: list[Command]
    output_style: str
    available_output_styles: list[str]
