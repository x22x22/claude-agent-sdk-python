"""Test hooks functionality."""

import anyio
import pytest

from claude_code_sdk import (
    HookCallbackMatcher,
    HookJSONOutput,
    PostToolUseHookInput,
    PreToolUseHookInput,
    UserPromptSubmitHookInput,
    query,
)


def test_hook_types():
    """Test that hook types are properly defined."""

    async def _test():
        # Test PreToolUseHookInput
        pre_tool_input = PreToolUseHookInput(
            hook_event_name="PreToolUse",
            session_id="test-session",
            transcript_path="/tmp/test",
            cwd="/home/test",
            tool_name="Edit",
            tool_input={"file": "test.py", "content": "print('hello')"},
        )
        assert pre_tool_input.hook_event_name == "PreToolUse"
        assert pre_tool_input.tool_name == "Edit"

        # Test PostToolUseHookInput
        post_tool_input = PostToolUseHookInput(
            hook_event_name="PostToolUse",
            session_id="test-session",
            transcript_path="/tmp/test",
            cwd="/home/test",
            tool_name="Edit",
            tool_input={"file": "test.py", "content": "print('hello')"},
            tool_response={"success": True},
        )
        assert post_tool_input.hook_event_name == "PostToolUse"
        assert post_tool_input.tool_response == {"success": True}

        # Test HookJSONOutput
        output = HookJSONOutput(
            continue_=True,
            permission_decision="allow",
            reason="Test reason",
        )
        assert output.continue_ is True
        assert output.permission_decision == "allow"

    anyio.run(_test)


def test_hook_callback_matcher():
    """Test HookCallbackMatcher structure."""

    async def _test():
        async def test_hook(input_data, tool_use_id, options):
            return HookJSONOutput(permission_decision="allow")

        matcher = HookCallbackMatcher(matcher="Edit", hooks=[test_hook])

        assert matcher.matcher == "Edit"
        assert len(matcher.hooks) == 1
        assert callable(matcher.hooks[0])

    anyio.run(_test)


def test_query_with_hooks_requires_streaming():
    """Test that hooks require streaming mode."""

    async def _test():
        async def test_hook(input_data, tool_use_id, options):
            return HookJSONOutput(permission_decision="allow")

        hooks = {"PreToolUse": [HookCallbackMatcher(hooks=[test_hook])]}

        # Should raise error with string prompt
        with pytest.raises(ValueError, match="Hooks require streaming mode"):
            async for _ in query(prompt="test", hooks=hooks):
                pass

    anyio.run(_test)


def test_hook_callback_signature():
    """Test hook callback signature and execution."""

    async def _test():
        hook_called = False
        received_input = None
        received_tool_id = None
        received_options = None

        async def test_hook(
            input_data: PreToolUseHookInput, tool_use_id: str | None, options: dict
        ):
            nonlocal hook_called, received_input, received_tool_id, received_options
            hook_called = True
            received_input = input_data
            received_tool_id = tool_use_id
            received_options = options

            # Return a proper response
            return HookJSONOutput(permission_decision="allow", reason="Test hook executed")

        # Create a hook input to test with
        test_input = PreToolUseHookInput(
            hook_event_name="PreToolUse",
            session_id="test",
            transcript_path="/tmp/test",
            cwd="/tmp",
            tool_name="Edit",
            tool_input={"file": "test.py"},
        )

        # Call the hook directly to test signature
        result = await test_hook(test_input, "tool-123", {"signal": None})

        assert hook_called is True
        assert received_input == test_input
        assert received_tool_id == "tool-123"
        assert "signal" in received_options
        assert isinstance(result, HookJSONOutput)
        assert result.permission_decision == "allow"

    anyio.run(_test)


def test_multiple_hooks_in_matcher():
    """Test that multiple hooks can be added to a matcher."""

    async def _test():
        hook1_called = False
        hook2_called = False

        async def hook1(input_data, tool_use_id, options):
            nonlocal hook1_called
            hook1_called = True
            return HookJSONOutput(permission_decision="allow")

        async def hook2(input_data, tool_use_id, options):
            nonlocal hook2_called
            hook2_called = True
            return HookJSONOutput(permission_decision="allow")

        matcher = HookCallbackMatcher(matcher="Edit", hooks=[hook1, hook2])

        assert len(matcher.hooks) == 2

        # Test that both hooks are callable
        test_input = PreToolUseHookInput(
            hook_event_name="PreToolUse",
            session_id="test",
            transcript_path="/tmp/test",
            cwd="/tmp",
            tool_name="Edit",
            tool_input={},
        )

        await matcher.hooks[0](test_input, None, {})
        await matcher.hooks[1](test_input, None, {})

        assert hook1_called is True
        assert hook2_called is True

    anyio.run(_test)


def test_hook_output_fields():
    """Test all HookJSONOutput fields."""

    async def _test():
        output = HookJSONOutput(
            continue_=False,
            suppress_output=True,
            stop_reason="User requested stop",
            decision="block",
            system_message="System notification",
            permission_decision="deny",
            permission_decision_reason="Not allowed",
            reason="General reason",
            hook_specific_output={"custom": "data"},
        )

        assert output.continue_ is False
        assert output.suppress_output is True
        assert output.stop_reason == "User requested stop"
        assert output.decision == "block"
        assert output.system_message == "System notification"
        assert output.permission_decision == "deny"
        assert output.permission_decision_reason == "Not allowed"
        assert output.reason == "General reason"
        assert output.hook_specific_output == {"custom": "data"}

    anyio.run(_test)


def test_different_hook_events():
    """Test different hook event types."""

    async def _test():
        events_tested = set()

        async def generic_hook(input_data, tool_use_id, options):
            events_tested.add(input_data.hook_event_name)
            return HookJSONOutput()

        # Test UserPromptSubmitHookInput
        user_prompt_input = UserPromptSubmitHookInput(
            hook_event_name="UserPromptSubmit",
            session_id="test",
            transcript_path="/tmp/test",
            cwd="/tmp",
            prompt="Test prompt",
        )
        await generic_hook(user_prompt_input, None, {})

        assert "UserPromptSubmit" in events_tested
        assert user_prompt_input.prompt == "Test prompt"

    anyio.run(_test)
