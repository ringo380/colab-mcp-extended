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

import argparse
import asyncio
import datetime
import logging
import tempfile
import sys

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.tool_injection import ToolInjectionMiddleware
from fastmcp.utilities import logging as fastmcp_logger

from colab_mcp.session_manager import SessionManager
from colab_mcp.tools.connection import get_connection_tools
from colab_mcp.tools.execution import get_execution_tools
from colab_mcp.tools.files import get_file_tools
from colab_mcp.tools.notebook import get_notebook_tools


mcp = FastMCP(name="ColabMCP")


class SessionProxyMiddleware(Middleware):
    """Routes proxied tool calls to the active session's proxy server."""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self._last_connected: dict[str, bool] = {}

    async def on_message(self, context: MiddlewareContext, call_next):
        # Track connection state changes across all sessions
        result = await call_next(context)

        for session in self.session_manager.sessions.values():
            was_connected = self._last_connected.get(session.session_id, False)
            is_connected = session.is_connected()
            if is_connected != was_connected:
                self._last_connected[session.session_id] = is_connected
                try:
                    await context.fastmcp_context.send_tool_list_changed()
                except Exception:
                    logging.debug("Could not send tool list changed notification", exc_info=True)
                break

        return result


def init_logger(logdir):
    log_filename = datetime.datetime.now().strftime(
        f"{logdir}/colab-mcp.%Y-%m-%d_%H-%M-%S.log"
    )
    logging.basicConfig(
        format="%(asctime)s %(levelname)s:%(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
        filename=log_filename,
        level=logging.INFO,
    )
    fastmcp_logger.get_logger("colab-mcp").info("logging to %s" % log_filename)


def parse_args(v):
    parser = argparse.ArgumentParser(
        description="ColabMCP is an MCP server that lets you interact with Colab."
    )
    parser.add_argument(
        "-l",
        "--log",
        help="if set, use this directory as a location for logfiles (if unset, will log to %s/colab-mcp-logs/)"
        % tempfile.gettempdir(),
        action="store",
        default=tempfile.mkdtemp(prefix="colab-mcp-logs-"),
    )
    parser.add_argument(
        "--browser-profile",
        help="Path to Chromium user data directory for persistent auth in headless mode.",
        action="store",
        default=None,
    )
    return parser.parse_args(v)


async def main_async():
    args = parse_args(sys.argv[1:])
    init_logger(args.log)

    session_manager = SessionManager()
    logging.info("Session manager initialized")

    # Register all tools
    all_tools = (
        get_connection_tools(session_manager)
        + get_execution_tools(session_manager)
        + get_notebook_tools(session_manager)
        + get_file_tools(session_manager)
    )
    mcp.add_middleware(SessionProxyMiddleware(session_manager))
    mcp.add_middleware(ToolInjectionMiddleware(tools=all_tools))

    # Start keepalive loop for headless sessions
    await session_manager.start_keepalive_loop()

    try:
        await mcp.run_async()
    finally:
        await session_manager.cleanup()


def main() -> None:
    asyncio.run(main_async())
