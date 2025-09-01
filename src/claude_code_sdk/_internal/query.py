"""Query class for handling bidirectional control protocol."""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from .transport import Transport

if TYPE_CHECKING:
    from mcp.server import Server as McpServer

logger = logging.getLogger(__name__)


class Query:
    """Handles bidirectional control protocol on top of Transport.

    This class manages:
    - Control request/response routing
    - Hook callbacks
    - Tool permission callbacks
    - Message streaming
    - Initialization handshake
    """

    def __init__(
        self,
        transport: Transport,
        is_streaming_mode: bool,
        can_use_tool: Callable[
            [str, dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]
        ]
        | None = None,
        hooks: dict[str, list[dict[str, Any]]] | None = None,
        sdk_mcp_servers: dict[str, "McpServer"] | None = None,
    ):
        """Initialize Query with transport and callbacks.

        Args:
            transport: Low-level transport for I/O
            is_streaming_mode: Whether using streaming (bidirectional) mode
            can_use_tool: Optional callback for tool permission requests
            hooks: Optional hook configurations
            sdk_mcp_servers: Optional SDK MCP server instances
        """
        self.transport = transport
        self.is_streaming_mode = is_streaming_mode
        self.can_use_tool = can_use_tool
        self.hooks = hooks or {}
        self.sdk_mcp_servers = sdk_mcp_servers or {}

        # Control protocol state
        self.pending_control_responses: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.hook_callbacks: dict[str, Callable[..., Any]] = {}
        self.next_callback_id = 0
        self._request_counter = 0

        # Message stream
        self._message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._read_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._closed = False
        self._initialization_result: dict[str, Any] | None = None

    async def initialize(self) -> dict[str, Any] | None:
        """Initialize control protocol if in streaming mode.

        Returns:
            Initialize response with supported commands, or None if not streaming
        """
        if not self.is_streaming_mode:
            return None

        # Build hooks configuration for initialization
        hooks_config: dict[str, Any] = {}
        if self.hooks:
            for event, matchers in self.hooks.items():
                if matchers:
                    hooks_config[event] = []
                    for matcher in matchers:
                        callback_ids = []
                        for callback in matcher.get("hooks", []):
                            callback_id = f"hook_{self.next_callback_id}"
                            self.next_callback_id += 1
                            self.hook_callbacks[callback_id] = callback
                            callback_ids.append(callback_id)
                        hooks_config[event].append(
                            {
                                "matcher": matcher.get("matcher"),
                                "hookCallbackIds": callback_ids,
                            }
                        )

        # Send initialize request
        request = {
            "subtype": "initialize",
            "hooks": hooks_config if hooks_config else None,
        }

        response = await self._send_control_request(request)
        self._initialized = True
        self._initialization_result = response  # Store for later access
        return response

    async def start(self) -> None:
        """Start reading messages from transport."""
        if self._read_task is None:
            self._read_task = asyncio.create_task(self._read_messages())

    async def _read_messages(self) -> None:
        """Read messages from transport and route them."""
        try:
            async for message in self.transport.read_messages():
                if self._closed:
                    break

                msg_type = message.get("type")

                # Route control messages
                if msg_type == "control_response":
                    response = message.get("response", {})
                    request_id = response.get("request_id")
                    if request_id in self.pending_control_responses:
                        future = self.pending_control_responses.pop(request_id)
                        if response.get("subtype") == "error":
                            future.set_exception(
                                Exception(response.get("error", "Unknown error"))
                            )
                        else:
                            future.set_result(response)
                    continue

                elif msg_type == "control_request":
                    # Handle incoming control requests from CLI
                    asyncio.create_task(self._handle_control_request(message))
                    continue

                elif msg_type == "control_cancel_request":
                    # Handle cancel requests
                    # TODO: Implement cancellation support
                    continue

                # Regular SDK messages go to the queue
                await self._message_queue.put(message)

        except asyncio.CancelledError:
            # Task was cancelled - this is expected behavior
            logger.debug("Read task cancelled")
            raise  # Re-raise to properly handle cancellation
        except Exception as e:
            logger.error(f"Fatal error in message reader: {e}")
            # Put error in queue so iterators can handle it
            await self._message_queue.put({"type": "error", "error": str(e)})
        finally:
            # Always signal end of stream
            await self._message_queue.put({"type": "end"})

    async def _handle_control_request(self, request: dict[str, Any]) -> None:
        """Handle incoming control request from CLI."""
        request_id = request.get("request_id")
        request_data = request.get("request", {})
        subtype = request_data.get("subtype")

        try:
            response_data = {}

            if subtype == "can_use_tool":
                # Handle tool permission request
                if not self.can_use_tool:
                    raise Exception("canUseTool callback is not provided")

                response_data = await self.can_use_tool(
                    request_data.get("tool_name"),
                    request_data.get("input"),
                    {
                        "signal": None,  # TODO: Add abort signal support
                        "suggestions": request_data.get("permission_suggestions"),
                    },
                )

            elif subtype == "hook_callback":
                # Handle hook callback
                callback_id = request_data.get("callback_id")
                callback = self.hook_callbacks.get(callback_id)
                if not callback:
                    raise Exception(f"No hook callback found for ID: {callback_id}")

                response_data = await callback(
                    request_data.get("input"),
                    request_data.get("tool_use_id"),
                    {"signal": None},  # TODO: Add abort signal support
                )

            elif subtype == "mcp_request":
                # Handle SDK MCP request
                server_name = request_data.get("server_name")
                mcp_message = request_data.get("message")

                if not server_name or not mcp_message:
                    raise Exception("Missing server_name or message for MCP request")

                response_data = await self._handle_sdk_mcp_request(
                    server_name, mcp_message
                )

            else:
                raise Exception(f"Unsupported control request subtype: {subtype}")

            # Send success response
            response = {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": request_id,
                    "response": response_data,
                },
            }
            await self.transport.write(json.dumps(response) + "\n")

        except Exception as e:
            # Send error response
            response = {
                "type": "control_response",
                "response": {
                    "subtype": "error",
                    "request_id": request_id,
                    "error": str(e),
                },
            }
            await self.transport.write(json.dumps(response) + "\n")

    async def _send_control_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send control request to CLI and wait for response."""
        if not self.is_streaming_mode:
            raise Exception("Control requests require streaming mode")

        # Generate unique request ID
        self._request_counter += 1
        request_id = f"req_{self._request_counter}_{os.urandom(4).hex()}"

        # Create future for response
        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self.pending_control_responses[request_id] = future

        # Build and send request
        control_request = {
            "type": "control_request",
            "request_id": request_id,
            "request": request,
        }

        await self.transport.write(json.dumps(control_request) + "\n")

        # Wait for response
        try:
            response = await asyncio.wait_for(future, timeout=60.0)
            result = response.get("response", {})
            return result if isinstance(result, dict) else {}
        except asyncio.TimeoutError as e:
            self.pending_control_responses.pop(request_id, None)
            raise Exception(f"Control request timeout: {request.get('subtype')}") from e

    async def _handle_sdk_mcp_request(self, server_name: str, message: dict) -> dict:
        """Handle an MCP request for an SDK server.

        Args:
            server_name: Name of the SDK MCP server
            message: The JSONRPC message

        Returns:
            The response message
        """
        if server_name not in self.sdk_mcp_servers:
            return {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {
                    "code": -32601,
                    "message": f"Server '{server_name}' not found",
                },
            }

        server = self.sdk_mcp_servers[server_name]
        method = message.get("method")
        params = message.get("params", {})

        try:
            # Route to appropriate handler based on method
            if method == "tools/list":
                # Get the list_tools handler and call it
                handler = server.request_handlers.get("tools/list")
                if handler:
                    tools = await handler()
                    return {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "result": {"tools": [t.model_dump() for t in tools]},
                    }
            elif method == "tools/call":
                # Get the call_tool handler and call it
                handler = server.request_handlers.get("tools/call")
                if handler:
                    result = await handler(
                        params.get("name"), params.get("arguments", {})
                    )
                    return {"jsonrpc": "2.0", "id": message.get("id"), "result": result}

            # Method not found
            return {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32601, "message": f"Method '{method}' not found"},
            }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32603, "message": str(e)},
            }

    async def interrupt(self) -> None:
        """Send interrupt control request."""
        await self._send_control_request({"subtype": "interrupt"})

    async def set_permission_mode(self, mode: str) -> None:
        """Change permission mode."""
        await self._send_control_request(
            {
                "subtype": "set_permission_mode",
                "mode": mode,
            }
        )

    async def stream_input(self, stream: AsyncIterable[dict[str, Any]]) -> None:
        """Stream input messages to transport."""
        try:
            async for message in stream:
                if self._closed:
                    break
                await self.transport.write(json.dumps(message) + "\n")
            # After all messages sent, end input
            await self.transport.end_input()
        except Exception as e:
            logger.debug(f"Error streaming input: {e}")

    async def receive_messages(self) -> AsyncIterator[dict[str, Any]]:
        """Receive SDK messages (not control messages)."""
        while not self._closed:
            message = await self._message_queue.get()

            # Check for special messages
            if message.get("type") == "end":
                break
            elif message.get("type") == "error":
                raise Exception(message.get("error", "Unknown error"))

            yield message

    async def close(self) -> None:
        """Close the query and transport."""
        self._closed = True
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            # Wait for task to complete cancellation
            with suppress(asyncio.CancelledError):
                await self._read_task
        await self.transport.close()

    # Make Query an async iterator
    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        """Return async iterator for messages."""
        return self.receive_messages()

    async def __anext__(self) -> dict[str, Any]:
        """Get next message."""
        async for message in self.receive_messages():
            return message
        raise StopAsyncIteration
