#!/usr/bin/env python3
"""Quick start example for Claude Code SDK."""

import anyio

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ResultMessage,
    TextBlock,
    query,
)


async def basic_example():
    """Basic example - simple question."""
    print("=== Basic Example ===")

    async for message in query(prompt="What is 2 + 2?"):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
    print()


async def with_options_example():
    """Example with custom options."""
    print("=== With Options Example ===")

    options = ClaudeCodeOptions(
        system_prompt="You are a helpful assistant that explains things simply.",
        max_turns=1,
    )

    async for message in query(
        prompt="Explain what Python is in one sentence.", options=options
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
    print()


async def with_tools_example():
    """Example using tools."""
    print("=== With Tools Example ===")

    options = ClaudeCodeOptions(
        allowed_tools=["Read", "Write"],
        system_prompt="You are a helpful file assistant.",
    )

    async for message in query(
        prompt="Create a file called hello.txt with 'Hello, World!' in it",
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
        elif isinstance(message, ResultMessage) and message.total_cost_usd > 0:
            print(f"\nCost: ${message.total_cost_usd:.4f}")
    print()


async def with_strict_mcp_config_example():
    """Example using strict MCP configuration."""
    print("=== Strict MCP Config Example ===")

    # This ensures ONLY the MCP servers specified here will be used,
    # ignoring any global or project-level MCP configurations
    options = ClaudeCodeOptions(
        mcp_servers={
            "memory-server": {
                "command": "npx",
                "args": ["@modelcontextprotocol/server-memory"],
            }
        },
        strict_mcp_config=True,  # Ignore all file-based MCP configurations
    )

    async for message in query(
        prompt="List the available MCP tools from the memory server",
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
        elif isinstance(message, ResultMessage):
            print(f"\nResult: {message.subtype}")
    print()


async def main():
    """Run all examples."""
    await basic_example()
    await with_options_example()
    await with_tools_example()
    # Note: Uncomment the line below if you have MCP servers configured
    # await with_strict_mcp_config_example()


if __name__ == "__main__":
    anyio.run(main)
