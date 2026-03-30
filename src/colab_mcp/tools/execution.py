"""MCP tools for code execution in Colab sessions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastmcp.tools.tool import Tool

if TYPE_CHECKING:
    from colab_mcp.session_manager import SessionManager


def get_execution_tools(session_manager: SessionManager) -> list[Tool]:
    """Create execution tools bound to the given SessionManager."""

    async def execute_code(
        code: str,
        session_id: str | None = None,
    ) -> str:
        """Execute Python code in a Colab session's kernel.

        Runs the given code in the active (or specified) session. The code is
        executed in a temporary cell and the output is returned.

        Args:
            code: Python code to execute.
            session_id: Target session ID. Uses active session if not specified.

        Returns:
            JSON with execution output, errors, and status.
        """
        session = session_manager.resolve_session(session_id)
        if not session.is_connected():
            return json.dumps({"error": f"Session {session.session_id} is not connected"})

        # Proxy to Colab's execute_code tool if available
        try:
            client = session.proxy_client.client_factory()
            result = await client.call_tool("execute_code", {"code": code})
            return json.dumps({"output": str(result), "session_id": session.session_id})
        except Exception as e:
            return json.dumps({"error": str(e), "session_id": session.session_id})

    async def interrupt_kernel(
        session_id: str | None = None,
    ) -> str:
        """Interrupt the currently running execution in a Colab session.

        Args:
            session_id: Target session ID. Uses active session if not specified.

        Returns:
            Confirmation message.
        """
        session = session_manager.resolve_session(session_id)
        if not session.is_connected():
            return json.dumps({"error": f"Session {session.session_id} is not connected"})

        try:
            client = session.proxy_client.client_factory()
            result = await client.call_tool("interrupt_execution", {})
            return json.dumps({"interrupted": True, "session_id": session.session_id})
        except Exception as e:
            return json.dumps({"error": str(e), "session_id": session.session_id})

    async def restart_kernel(
        session_id: str | None = None,
    ) -> str:
        """Restart the Python kernel in a Colab session.

        This clears all variables and state. Use when the kernel is stuck
        or you need a fresh environment.

        Args:
            session_id: Target session ID. Uses active session if not specified.

        Returns:
            Confirmation message.
        """
        session = session_manager.resolve_session(session_id)
        if not session.is_connected():
            return json.dumps({"error": f"Session {session.session_id} is not connected"})

        try:
            client = session.proxy_client.client_factory()
            result = await client.call_tool("restart_kernel", {})
            return json.dumps({"restarted": True, "session_id": session.session_id})
        except Exception as e:
            return json.dumps({"error": str(e), "session_id": session.session_id})

    return [
        Tool.from_function(
            fn=execute_code,
            name="execute_code",
            description=(
                "Execute Python code in a Colab session. Returns the output, "
                "including print statements, return values, and errors."
            ),
        ),
        Tool.from_function(
            fn=interrupt_kernel,
            name="interrupt_kernel",
            description="Interrupt the currently running code execution in a Colab session.",
        ),
        Tool.from_function(
            fn=restart_kernel,
            name="restart_kernel",
            description=(
                "Restart the Python kernel in a Colab session. "
                "Clears all variables and state."
            ),
        ),
    ]
