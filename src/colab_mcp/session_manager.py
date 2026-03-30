from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from colab_mcp.browser.webbrowser_backend import WebbrowserBackend
from colab_mcp.session import ColabSession, SessionInfo, SessionStatus

if TYPE_CHECKING:
    from colab_mcp.browser.base import BrowserBackend


class SessionManager:
    """Manages multiple concurrent Colab notebook sessions."""

    def __init__(self, default_browser_profile: str | None = None):
        self.sessions: dict[str, ColabSession] = {}
        self.active_session_id: str | None = None
        self.default_browser_profile = default_browser_profile
        self._keepalive_task: asyncio.Task | None = None

    async def create_session(
        self,
        notebook_id: str | None = None,
        authuser: int = 1,
        headless: bool = False,
        browser_profile: str | None = None,
    ) -> ColabSession:
        """Create and start a new Colab session.

        Args:
            notebook_id: Google Drive file ID, or None for scratchpad.
            authuser: Google account index (0=primary, 1=secondary, etc.).
            headless: If True, use Playwright headless browser.
            browser_profile: Path to Chromium user data dir for persistent auth.
                             Falls back to default_browser_profile from CLI.

        Returns:
            The created ColabSession.
        """
        # Use explicit browser_profile, fall back to CLI default
        effective_profile = browser_profile or self.default_browser_profile

        session = ColabSession(notebook_id=notebook_id, authuser=authuser)
        try:
            await session.start()

            backend = await self._create_backend(headless, effective_profile)
            session.backend = backend

            self.sessions[session.session_id] = session

            # First session becomes active by default
            if self.active_session_id is None:
                self.active_session_id = session.session_id

            url = session.get_colab_url()
            await backend.open(url)
            logging.info(
                f"Session {session.session_id} created "
                f"(notebook={notebook_id}, headless={headless})"
            )

            return session
        except Exception:
            self.sessions.pop(session.session_id, None)
            if self.active_session_id == session.session_id:
                self.active_session_id = None
            await session.cleanup()
            raise

    async def _create_backend(
        self, headless: bool, browser_profile: str | None
    ) -> BrowserBackend:
        if not headless:
            return WebbrowserBackend()

        try:
            from colab_mcp.browser.playwright_backend import PlaywrightBackend
        except ImportError:
            raise RuntimeError(
                "Playwright is required for headless mode. "
                "Install with: pip install 'colab-mcp-extended[headless]'"
            )
        return PlaywrightBackend(user_data_dir=browser_profile)

    def get_session(self, session_id: str) -> ColabSession:
        """Get a session by ID. Raises KeyError if not found."""
        return self.sessions[session_id]

    def get_active_session(self) -> ColabSession | None:
        """Get the currently active session."""
        if self.active_session_id and self.active_session_id in self.sessions:
            return self.sessions[self.active_session_id]
        return None

    def resolve_session(self, session_id: str | None = None) -> ColabSession:
        """Resolve a session by ID, falling back to active session."""
        if session_id:
            return self.get_session(session_id)
        session = self.get_active_session()
        if session is None:
            raise RuntimeError("No active session. Use open_session first.")
        return session

    async def close_session(self, session_id: str) -> None:
        """Close and remove a session."""
        if session_id not in self.sessions:
            raise KeyError(f"Session {session_id} not found")

        session = self.sessions[session_id]

        # Clean up resources before removing from tracking dict
        try:
            await session.cleanup()
        finally:
            self.sessions.pop(session_id, None)
            logging.info(f"Session {session_id} closed")

            # If we closed the active session, pick another or clear
            if self.active_session_id == session_id:
                if self.sessions:
                    self.active_session_id = next(iter(self.sessions))
                else:
                    self.active_session_id = None

    def set_active(self, session_id: str) -> None:
        """Set the active session."""
        if session_id not in self.sessions:
            raise KeyError(f"Session {session_id} not found")
        self.active_session_id = session_id

    def list_sessions(self) -> list[SessionInfo]:
        """Return metadata for all sessions."""
        result = []
        for session in self.sessions.values():
            # Update status based on live connection state
            if session.is_connected():
                session.status = SessionStatus.CONNECTED
            elif session.status == SessionStatus.CONNECTED:
                session.status = SessionStatus.DISCONNECTED
            result.append(session.info)
        return result

    async def start_keepalive_loop(self):
        """Start background keepalive loop for all Playwright-backed sessions."""
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def _keepalive_loop(self):
        """Periodically call keepalive on all sessions with Playwright backends."""
        while True:
            await asyncio.sleep(120)  # 2 minutes
            for session_id, session in list(self.sessions.items()):
                if session.backend is None:
                    continue
                try:
                    alive = await session.backend.is_alive()
                    if alive:
                        await session.backend.keepalive()
                    else:
                        logging.warning(
                            f"Session {session_id} browser is no longer alive"
                        )
                        session.status = SessionStatus.DISCONNECTED
                except Exception:
                    logging.exception(
                        f"Keepalive failed for session {session_id}"
                    )

    async def cleanup(self):
        """Shut down all sessions and background tasks."""
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None

        for session_id in list(self.sessions):
            try:
                await self.close_session(session_id)
            except Exception:
                logging.exception(f"Error closing session {session_id}")
