#!/usr/bin/env python3
"""Example demonstrating canUseTool permission functionality."""

import asyncio
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    CanUseTool,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)


async def security_callback(
    tool_name: str, input_data: dict, context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """Example security callback that implements tool permission policy."""
    print(f"🔒 Permission check for tool: {tool_name}")
    print(f"   Input: {input_data}")

    # Example policy: deny dangerous bash commands
    if tool_name == "Bash":
        command = input_data.get("command", "")
        dangerous_patterns = ["rm -rf", "dd if=", "mkfs", "format", "del *"]

        if any(pattern in command for pattern in dangerous_patterns):
            print("❌ Denied: Command contains dangerous patterns")
            return PermissionResultDeny(
                message="Command blocked due to security policy",
                interrupt=True
            )

    # Example: Allow but modify file operations to add safety
    if tool_name in ["Write", "Edit"]:
        file_path = input_data.get("file_path", "")
        if file_path.startswith("/etc/") or file_path.startswith("/system/"):
            print("⚠️  Modified: Adding backup for system file operation")
            modified_input = input_data.copy()
            modified_input["backup"] = True
            return PermissionResultAllow(updated_input=modified_input)

    print("✅ Allowed")
    return PermissionResultAllow()


async def streaming_messages():
    """Generate streaming messages for testing."""
    yield {
        "type": "user",
        "message": {"role": "user", "content": "What is 2+2?"},
        "parent_tool_use_id": None,
        "session_id": "test_session"
    }


async def main():
    """Main example function."""
    print("🚀 Testing canUseTool functionality")

    try:
        # Create options with canUseTool callback
        options = ClaudeAgentOptions(
            can_use_tool=security_callback,
            permission_mode="default",  # This will be overridden to use stdio
        )

        print("📋 Options created with canUseTool callback")

        # Test with ClaudeSDKClient (streaming mode required for canUseTool)
        client = ClaudeSDKClient(options=options)

        print("🔌 Connecting to Claude with canUseTool enabled...")
        await client.connect(streaming_messages())

        print("✅ Connection successful!")
        print("🔒 canUseTool callback is now active and will intercept tool usage")

        # Note: In a real scenario, you would now interact with the client
        # and the security_callback would be invoked for each tool use

        await client.disconnect()
        print("✅ Disconnected successfully")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())