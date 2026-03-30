"""MCP tools for managing Colab session connections."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from fastmcp.tools.tool import Tool

if TYPE_CHECKING:
    from colab_mcp.session_manager import SessionManager


def get_connection_tools(session_manager: SessionManager) -> list[Tool]:
    """Create connection management tools bound to the given SessionManager."""

    async def open_session(
        notebook_id: str | None = None,
        authuser: int = 1,
        headless: bool = False,
        browser_profile: str | None = None,
        ctx: Context = CurrentContext(),
    ) -> str:
        """Open a new Google Colab session and connect to it.

        Args:
            notebook_id: Google Drive file ID of the notebook to open.
                         If not provided, opens a blank scratchpad.
                         Get this from a Drive URL: drive.google.com/file/d/{THIS_PART}/...
            authuser: Google account index (default 1). Use 0 for primary, 1 for secondary.
            headless: If True, use headless browser automation (requires playwright).
                      If False (default), opens in your default browser.
            browser_profile: Path to Chromium user data dir for persistent auth.
                             Overrides the --browser-profile CLI default.

        Returns:
            JSON with session_id and connection status.
        """
        await ctx.report_progress(
            progress=1, total=3, message="Creating Colab session..."
        )

        session = await session_manager.create_session(
            notebook_id=notebook_id,
            authuser=authuser,
            headless=headless,
            browser_profile=browser_profile,
        )

        await ctx.report_progress(
            progress=2, total=3,
            message="Waiting for browser to connect to Colab (up to 60s)...",
        )

        # Wait for the frontend to connect
        await session.await_connection()

        if session.is_connected():
            await ctx.report_progress(
                progress=3, total=3, message="Colab session connected!"
            )
        else:
            await ctx.report_progress(
                progress=3, total=3,
                message="Timeout waiting for browser connection.",
            )

        return json.dumps({
            "session_id": session.session_id,
            "connected": session.is_connected(),
            "notebook_id": notebook_id,
            "message": (
                "Connected to Colab session"
                if session.is_connected()
                else "Waiting for browser to connect. The Colab tab should open shortly."
            ),
        })

    async def list_sessions() -> str:
        """List all active Colab sessions.

        Returns:
            JSON array of session info objects with session_id, notebook_id, status, created_at.
        """
        sessions = session_manager.list_sessions()
        active = session_manager.active_session_id
        result = []
        for s in sessions:
            entry = {
                "session_id": s.session_id,
                "notebook_id": s.notebook_id,
                "status": s.status,
                "created_at": s.created_at,
                "active": s.session_id == active,
            }
            result.append(entry)
        return json.dumps(result, indent=2)

    async def close_session(session_id: str) -> str:
        """Close a Colab session and release its resources.

        Args:
            session_id: The ID of the session to close.

        Returns:
            Confirmation message.
        """
        await session_manager.close_session(session_id)
        return json.dumps({"closed": session_id})

    async def switch_session(session_id: str) -> str:
        """Switch the active session. The active session receives proxied tool calls.

        Args:
            session_id: The ID of the session to make active.

        Returns:
            Confirmation with the new active session ID.
        """
        session_manager.set_active(session_id)
        session = session_manager.get_session(session_id)
        return json.dumps({
            "active_session_id": session_id,
            "notebook_id": session.notebook_id,
            "connected": session.is_connected(),
        })

    return [
        Tool.from_function(
            fn=open_session,
            name="open_session",
            description=(
                "Opens a new Google Colab session. Returns a session_id for managing "
                "multiple concurrent notebooks. Pass notebook_id to open a specific "
                "Drive notebook, or omit for a blank scratchpad. Set headless=True "
                "for automated browser sessions (requires playwright)."
            ),
        ),
        Tool.from_function(
            fn=list_sessions,
            name="list_sessions",
            description="List all active Colab sessions with their status and metadata.",
        ),
        Tool.from_function(
            fn=close_session,
            name="close_session",
            description="Close a Colab session and release its resources.",
        ),
        Tool.from_function(
            fn=switch_session,
            name="switch_session",
            description=(
                "Switch the active Colab session. The active session's notebook tools "
                "become available for use. Other sessions remain connected in the background."
            ),
        ),
    ]
