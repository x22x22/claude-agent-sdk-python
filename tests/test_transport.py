"""Tests for Claude SDK transport layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest

from claude_code_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
from claude_code_sdk.types import ClaudeCodeOptions


class TestSubprocessCLITransport:
    """Test subprocess transport implementation."""

    def test_find_cli_not_found(self):
        """Test CLI not found error."""
        from claude_code_sdk._errors import CLINotFoundError

        with (
            patch("shutil.which", return_value=None),
            patch("pathlib.Path.exists", return_value=False),
            pytest.raises(CLINotFoundError) as exc_info,
        ):
            SubprocessCLITransport(prompt="test", options=ClaudeCodeOptions())

        assert "Claude Code requires Node.js" in str(exc_info.value)

    def test_build_command_basic(self):
        """Test building basic CLI command."""
        transport = SubprocessCLITransport(
            prompt="Hello", options=ClaudeCodeOptions(), cli_path="/usr/bin/claude"
        )

        cmd = transport._build_command()
        assert cmd[0] == "/usr/bin/claude"
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--print" in cmd
        assert "Hello" in cmd

    def test_cli_path_accepts_pathlib_path(self):
        """Test that cli_path accepts pathlib.Path objects."""
        from pathlib import Path

        transport = SubprocessCLITransport(
            prompt="Hello",
            options=ClaudeCodeOptions(),
            cli_path=Path("/usr/bin/claude"),
        )

        assert transport._cli_path == "/usr/bin/claude"

    def test_build_command_with_options(self):
        """Test building CLI command with options."""
        transport = SubprocessCLITransport(
            prompt="test",
            options=ClaudeCodeOptions(
                system_prompt="Be helpful",
                allowed_tools=["Read", "Write"],
                disallowed_tools=["Bash"],
                model="claude-3-5-sonnet",
                permission_mode="acceptEdits",
                max_turns=5,
            ),
            cli_path="/usr/bin/claude",
        )

        cmd = transport._build_command()
        assert "--system-prompt" in cmd
        assert "Be helpful" in cmd
        assert "--allowedTools" in cmd
        assert "Read,Write" in cmd
        assert "--disallowedTools" in cmd
        assert "Bash" in cmd
        assert "--model" in cmd
        assert "claude-3-5-sonnet" in cmd
        assert "--permission-mode" in cmd
        assert "acceptEdits" in cmd
        assert "--max-turns" in cmd
        assert "5" in cmd

    def test_session_continuation(self):
        """Test session continuation options."""
        transport = SubprocessCLITransport(
            prompt="Continue from before",
            options=ClaudeCodeOptions(continue_conversation=True, resume="session-123"),
            cli_path="/usr/bin/claude",
        )

        cmd = transport._build_command()
        assert "--continue" in cmd
        assert "--resume" in cmd
        assert "session-123" in cmd

    def test_connect_disconnect(self):
        """Test connect and disconnect lifecycle."""

        async def _test():
            with patch("anyio.open_process") as mock_exec:
                mock_process = MagicMock()
                mock_process.returncode = None
                mock_process.terminate = MagicMock()
                mock_process.wait = AsyncMock()
                mock_process.stdout = MagicMock()
                mock_process.stderr = MagicMock()
                mock_exec.return_value = mock_process

                transport = SubprocessCLITransport(
                    prompt="test",
                    options=ClaudeCodeOptions(),
                    cli_path="/usr/bin/claude",
                )

                await transport.connect()
                assert transport._process is not None
                assert transport.is_connected()

                await transport.disconnect()
                mock_process.terminate.assert_called_once()

        anyio.run(_test)

    def test_receive_messages(self):
        """Test parsing messages from CLI output."""
        # This test is simplified to just test the parsing logic
        # The full async stream handling is tested in integration tests
        transport = SubprocessCLITransport(
            prompt="test", options=ClaudeCodeOptions(), cli_path="/usr/bin/claude"
        )

        # The actual message parsing is done by the client, not the transport
        # So we just verify the transport can be created and basic structure is correct
        assert transport._prompt == "test"
        assert transport._cli_path == "/usr/bin/claude"

    def test_bypass_permissions_disabled_error(self):
        """Test that bypassPermissions being disabled raises proper error."""
        from claude_code_sdk._errors import ProcessError
        from anyio.streams.text import TextReceiveStream
        from anyio import ClosedResourceError

        async def _test():
            with patch("anyio.open_process") as mock_exec:
                # Create a mock process that simulates the CLI behavior
                mock_process = MagicMock()
                mock_process.returncode = 0  # CLI exits successfully
                mock_process.wait = AsyncMock()
                
                # Create mock stdout/stderr streams
                mock_stdout_stream = AsyncMock()
                mock_stderr_stream = AsyncMock()
                
                # Simulate empty stdout (no JSON messages) followed by closed stream
                async def stdout_iter(self):
                    raise ClosedResourceError()
                    yield  # This won't be reached
                
                # Simulate stderr with the warning message
                async def stderr_iter(self):
                    yield "[ERROR] bypassPermissions mode is disabled by settings"
                    raise ClosedResourceError()
                
                type(mock_stdout_stream).__aiter__ = stdout_iter
                type(mock_stderr_stream).__aiter__ = stderr_iter
                
                mock_process.stdout = MagicMock()
                mock_process.stderr = MagicMock()
                mock_exec.return_value = mock_process

                # Patch TextReceiveStream to return our mocks
                with patch("claude_code_sdk._internal.transport.subprocess_cli.TextReceiveStream") as mock_text_stream:
                    mock_text_stream.side_effect = [mock_stdout_stream, mock_stderr_stream]
                    
                    transport = SubprocessCLITransport(
                        prompt="test",
                        options=ClaudeCodeOptions(permission_mode="bypassPermissions"),
                        cli_path="/usr/bin/claude",
                    )

                    await transport.connect()
                    
                    with pytest.raises(ProcessError) as exc_info:
                        # Consume all messages to trigger the error check
                        async for _ in transport.receive_messages():
                            pass
                    
                    assert "bypassPermissions mode is disabled" in str(exc_info.value)
                    assert "requires user input" in str(exc_info.value)
                    assert "acceptEdits" in str(exc_info.value)

        anyio.run(_test)

    def test_bypass_permissions_adds_debug_flag(self):
        """Test that bypassPermissions mode adds --debug flag to command."""
        transport = SubprocessCLITransport(
            prompt="test",
            options=ClaudeCodeOptions(permission_mode="bypassPermissions"),
            cli_path="/usr/bin/claude",
        )

        cmd = transport._build_command()
        assert "--debug" in cmd

    def test_bypass_permissions_root_user_error(self):
        """Test that running as root with bypassPermissions raises proper error."""
        from claude_code_sdk._errors import ProcessError
        from anyio import ClosedResourceError

        async def _test():
            with patch("anyio.open_process") as mock_exec:
                # Create a mock process that exits with code 1 (root user rejection)
                mock_process = MagicMock()
                mock_process.returncode = 1
                mock_process.wait = AsyncMock()
                
                # Create mock stdout/stderr streams
                mock_stdout_stream = AsyncMock()
                mock_stderr_stream = AsyncMock()
                
                # Simulate empty stdout
                async def stdout_iter(self):
                    raise ClosedResourceError()
                    yield  # Won't be reached
                
                # Simulate stderr with root user error
                async def stderr_iter(self):
                    yield "--dangerously-skip-permissions cannot be used with root/sudo privileges for security reasons"
                    raise ClosedResourceError()
                
                type(mock_stdout_stream).__aiter__ = stdout_iter
                type(mock_stderr_stream).__aiter__ = stderr_iter
                
                mock_process.stdout = MagicMock()
                mock_process.stderr = MagicMock()
                mock_exec.return_value = mock_process

                # Patch TextReceiveStream to return our mocks
                with patch("claude_code_sdk._internal.transport.subprocess_cli.TextReceiveStream") as mock_text_stream:
                    mock_text_stream.side_effect = [mock_stdout_stream, mock_stderr_stream]
                    
                    transport = SubprocessCLITransport(
                        prompt="test",
                        options=ClaudeCodeOptions(permission_mode="bypassPermissions"),
                        cli_path="/usr/bin/claude",
                    )

                    await transport.connect()
                    
                    with pytest.raises(ProcessError) as exc_info:
                        async for _ in transport.receive_messages():
                            pass
                    
                    assert "cannot be used when running as root/sudo" in str(exc_info.value)
                    assert "Run as a non-root user" in str(exc_info.value)

        anyio.run(_test)

    def test_bypass_permissions_no_output(self):
        """Test bypassPermissions mode that exits without any output."""
        from claude_code_sdk._errors import ProcessError
        from anyio import ClosedResourceError

        async def _test():
            with patch("anyio.open_process") as mock_exec:
                # Create a mock process that exits cleanly but produces no output
                mock_process = MagicMock()
                mock_process.returncode = 0  # Clean exit
                mock_process.wait = AsyncMock()
                
                # Create mock stdout/stderr streams that immediately close
                mock_stdout_stream = AsyncMock()
                mock_stderr_stream = AsyncMock()
                
                # Both streams immediately close without yielding anything
                async def empty_iter(self):
                    raise ClosedResourceError()
                    yield  # Won't be reached
                
                type(mock_stdout_stream).__aiter__ = empty_iter
                type(mock_stderr_stream).__aiter__ = empty_iter
                
                mock_process.stdout = MagicMock()
                mock_process.stderr = MagicMock()
                mock_exec.return_value = mock_process

                # Patch TextReceiveStream to return our mocks
                with patch("claude_code_sdk._internal.transport.subprocess_cli.TextReceiveStream") as mock_text_stream:
                    mock_text_stream.side_effect = [mock_stdout_stream, mock_stderr_stream]
                    
                    transport = SubprocessCLITransport(
                        prompt="test",
                        options=ClaudeCodeOptions(permission_mode="bypassPermissions"),
                        cli_path="/usr/bin/claude",
                    )

                    await transport.connect()
                    
                    with pytest.raises(ProcessError) as exc_info:
                        # This simulates the "no response" issue - the iterator completes
                        # without yielding any messages
                        async for _ in transport.receive_messages():
                            pass
                    
                    error_msg = str(exc_info.value)
                    assert "terminated without producing any output" in error_msg
                    assert "bypassPermissions mode" in error_msg
                    assert "Running as root/sudo" in error_msg
                    assert "acceptEdits" in error_msg

        anyio.run(_test)
