"""Example demonstrating how to use strict MCP config with Claude SDK.

This example shows how to use the strict_mcp_config option to ensure
only your programmatically specified MCP servers are used, ignoring
any global or project-level MCP configurations.
"""

from claude_code_sdk import ClaudeCodeSDK, ClaudeCodeOptions

async def main():
    # Create options with strict MCP config enabled
    # This ensures ONLY the MCP servers specified here will be used
    options = ClaudeCodeOptions(
        mcp_servers={
            "my-custom-server": {
                "command": "npx",
                "args": ["@modelcontextprotocol/server-memory"],
            }
        },
        strict_mcp_config=True,  # Ignore all file-based MCP configurations
    )
    
    # Create SDK instance
    sdk = ClaudeCodeSDK()
    
    # Query Claude with strict MCP config
    async with await sdk.query(
        "List the available MCP tools from the memory server", 
        options=options
    ) as session:
        async for message in session.stream():
            if message.type == "assistant":
                print(f"Claude: {message.message.content}")
            elif message.type == "result":
                print(f"\nResult: {message.subtype}")
                if message.result:
                    print(f"Final output: {message.result}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())