#!/usr/bin/env python3
"""
Example demonstrating keepalive behavior with ClaudeSDKClient.

The Claude process stays alive between queries within a session, allowing for:
- Multi-turn conversations with context retention
- Efficient resource usage (no subprocess restart overhead)
- Session state preservation across multiple queries

Usage:
    python examples/keepalive.py
"""

import asyncio

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)


def display_message(msg):
    """Display message content."""
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                print(f"Claude: {block.text}")
    elif isinstance(msg, ResultMessage):
        print(f"[Response complete, session: {msg.session_id}]")


async def example_keepalive_session():
    """Demonstrate keepalive behavior with multi-turn conversation.

    The Claude process stays alive between queries. Each query maintains
    context from previous interactions in the same session.
    """
    print("=== Keepalive Session Example ===")
    print("The Claude process will stay alive between all queries below.\n")

    # keepalive=True is the default behavior for ClaudeSDKClient
    options = ClaudeAgentOptions(
        keepalive=True,  # This is the default
        system_prompt="You are a helpful assistant. Remember what I tell you.",
    )

    async with ClaudeSDKClient(options=options) as client:
        # Query 1: Set up context
        print("Query 1: Setting up context")
        print("User: My name is Alice and I love Python programming.")
        await client.query("My name is Alice and I love Python programming.")
        async for msg in client.receive_response():
            display_message(msg)
        print()

        # Query 2: Reference previous context (session keeps context)
        print("Query 2: Referencing previous context (same session)")
        print("User: What's my name and what do I like?")
        await client.query("What's my name and what do I like?")
        async for msg in client.receive_response():
            display_message(msg)
        print()

        # Query 3: Additional query in same session
        print("Query 3: Another query in same session")
        print("User: Can you suggest a Python project for me?")
        await client.query(
            "Can you suggest a Python project for me based on my interests?"
        )
        async for msg in client.receive_response():
            display_message(msg)
        print()

        print("[Session complete - process will now close]")


async def example_long_running_session():
    """Demonstrate a long-running session with multiple interactions.

    This shows how the process stays alive for extended periods,
    handling multiple queries without restarting.
    """
    print("=== Long Running Session Example ===")
    print("The Claude process stays alive for all interactions.\n")

    async with ClaudeSDKClient() as client:
        questions = [
            "What is 2 + 2?",
            "Now multiply that by 10.",
            "Divide the result by 5.",
            "What's the square root of that?",
        ]

        for i, question in enumerate(questions, 1):
            print(f"\nQuery {i}:")
            print(f"User: {question}")
            await client.query(question)

            async for msg in client.receive_response():
                display_message(msg)

        print("\n[All queries complete in single session]")


async def example_explicit_disconnect():
    """Demonstrate explicit session control without context manager.

    Shows how to manually connect and disconnect while keeping
    the process alive between operations.
    """
    print("=== Explicit Session Control Example ===")
    print("Manual connect/disconnect with keepalive behavior.\n")

    client = ClaudeSDKClient()

    try:
        # Connect starts the Claude process
        await client.connect()
        print("[Claude process started]")

        # First query
        print("\nUser: Hello! I'm testing the SDK.")
        await client.query("Hello! I'm testing the SDK.")
        async for msg in client.receive_response():
            display_message(msg)

        # Wait a bit - process stays alive
        print("\n[Waiting 2 seconds - process still alive]")
        await asyncio.sleep(2)

        # Second query - still in same session
        print("\nUser: Are you still there?")
        await client.query("Are you still there?")
        async for msg in client.receive_response():
            display_message(msg)

    finally:
        # Disconnect closes the Claude process
        await client.disconnect()
        print("\n[Claude process closed via disconnect()]")


async def main():
    """Run all keepalive examples."""
    print("=" * 60)
    print("Claude Agent SDK - Keepalive Examples")
    print("=" * 60)
    print()
    print("These examples demonstrate how the Claude process stays alive")
    print("between queries within a session, enabling efficient multi-turn")
    print("conversations.\n")
    print("=" * 60)
    print()

    await example_keepalive_session()
    print("\n" + "-" * 60 + "\n")

    await example_long_running_session()
    print("\n" + "-" * 60 + "\n")

    await example_explicit_disconnect()


if __name__ == "__main__":
    asyncio.run(main())
