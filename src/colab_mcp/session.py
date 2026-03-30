# Copyright 2026 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Extended version: multi-session support with browser backend abstraction.

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import contextlib
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import secrets
from typing import TYPE_CHECKING

from fastmcp import FastMCP, Client
from fastmcp.client.transports import ClientTransport
from fastmcp.server.proxy import FastMCPProxy
from mcp.client.session import ClientSession

from colab_mcp.websocket_server import ColabWebSocketServer

if TYPE_CHECKING:
    from colab_mcp.browser.base import BrowserBackend

UI_CONNECTION_TIMEOUT = 60.0  # secs


class SessionStatus(Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class ColabTransport(ClientTransport):
    def __init__(self, wss: ColabWebSocketServer):
        self.wss = wss

    @contextlib.asynccontextmanager
    async def connect_session(self, **session_kwargs) -> AsyncIterator[ClientSession]:
        async with ClientSession(
            self.wss.read_stream, self.wss.write_stream, **session_kwargs
        ) as session:
            yield session

    def __repr__(self) -> str:
        return "<ColabTransport>"


class ColabProxyClient:
    def __init__(self, wss: ColabWebSocketServer):
        self.wss = wss
        self.stubbed_mcp_client = Client(FastMCP())
        self.proxy_mcp_client: Client | None = None
        self._exit_stack = AsyncExitStack()
        self._start_task = None

    def is_connected(self):
        return self.wss.connection_live.is_set() and self.proxy_mcp_client is not None

    async def await_proxy_connection(self, timeout: float = UI_CONNECTION_TIMEOUT) -> bool:
        try:
            await asyncio.wait_for(
                asyncio.gather(self.wss.connection_live.wait(), self._start_task),
                timeout=timeout,
            )
            return True
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return False

    def client_factory(self):
        if self.is_connected():
            return self.proxy_mcp_client
        return self.stubbed_mcp_client

    async def _start_proxy_client(self):
        self.proxy_mcp_client = await self._exit_stack.enter_async_context(
            Client(ColabTransport(self.wss))
        )

    async def __aenter__(self):
        self._start_task = asyncio.create_task(self._start_proxy_client())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._start_task:
            self._start_task.cancel()
        await self._exit_stack.aclose()


@dataclass
class SessionInfo:
    """Serializable session metadata."""
    session_id: str
    notebook_id: str | None
    authuser: int
    status: str
    created_at: str


class ColabSession:
    """A single Colab notebook session with its own WSS + proxy client stack."""

    def __init__(
        self,
        session_id: str | None = None,
        notebook_id: str | None = None,
        authuser: int = 1,
    ):
        self.session_id = session_id or secrets.token_urlsafe(6)
        self.notebook_id = notebook_id
        self.authuser = authuser
        self.status = SessionStatus.DISCONNECTED
        self.created_at = datetime.now(timezone.utc)

        self._exit_stack = AsyncExitStack()
        self.wss: ColabWebSocketServer | None = None
        self.proxy_client: ColabProxyClient | None = None
        self.proxy_server: FastMCPProxy | None = None
        self.backend: BrowserBackend | None = None

    @property
    def info(self) -> SessionInfo:
        return SessionInfo(
            session_id=self.session_id,
            notebook_id=self.notebook_id,
            authuser=self.authuser,
            status=self.status.value,
            created_at=self.created_at.isoformat(),
        )

    def is_connected(self) -> bool:
        return self.proxy_client is not None and self.proxy_client.is_connected()

    async def start(self):
        """Initialize the WSS + proxy client stack."""
        self.status = SessionStatus.CONNECTING
        self.wss = await self._exit_stack.enter_async_context(ColabWebSocketServer())
        self.proxy_client = await self._exit_stack.enter_async_context(
            ColabProxyClient(self.wss)
        )
        self.proxy_server = FastMCPProxy(
            client_factory=self.proxy_client.client_factory,
            instructions=f"Colab session {self.session_id} "
            f"(notebook: {self.notebook_id or 'scratchpad'})",
        )

    async def await_connection(self, timeout: float = UI_CONNECTION_TIMEOUT):
        """Wait for the browser frontend to connect via WebSocket."""
        if self.proxy_client:
            await self.proxy_client.await_proxy_connection(timeout=timeout)
        if self.is_connected():
            self.status = SessionStatus.CONNECTED
        else:
            self.status = SessionStatus.DISCONNECTED

    def get_colab_url(self) -> str:
        """Build the Colab URL with proxy connection parameters."""
        from colab_mcp.websocket_server import COLAB, SCRATCH_PATH

        if self.notebook_id:
            path = f"/drive/{self.notebook_id}"
        else:
            path = SCRATCH_PATH

        token = self.wss.token if self.wss else ""
        port = self.wss.port if self.wss else 0
        return f"{COLAB}{path}?authuser={self.authuser}#mcpProxyToken={token}&mcpProxyPort={port}"

    async def cleanup(self):
        """Tear down all resources."""
        self.status = SessionStatus.DISCONNECTED
        if self.backend:
            await self.backend.close()
            self.backend = None
        await self._exit_stack.aclose()
