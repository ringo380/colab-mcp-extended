# colab-mcp-extended

Extended Google Colab MCP server with multi-session, headless browser, and rich tool support.
Fork of https://github.com/googlecolab/colab-mcp

## Project Structure
- `src/colab_mcp/` - Main package
  - `__init__.py` - Entry point, server bootstrapping, middleware
  - `session.py` - ColabSession, proxy client, transport
  - `session_manager.py` - SessionManager for concurrent sessions
  - `websocket_server.py` - WebSocket server for Colab frontend
  - `browser/` - Browser backend abstraction (base, webbrowser, playwright)
  - `tools/` - MCP tool definitions (connection, execution, notebook, files)
- `pyproject.toml` - Build config (hatchling), entry point: `colab-mcp`

## Tech Stack
- Python 3.12+, fastmcp 2.14.5, mcp SDK, websockets, google-auth-oauthlib
- Optional: playwright (for headless mode, install with `pip install .[headless]`)

## Commands
- `pip install -e .` - Install in dev mode
- `pip install -e '.[headless]'` - Install with headless browser support
- `python -m colab_mcp` - Run server
- `colab-mcp --browser-profile /path/to/profile` - Run with persistent browser profile

## MCP Configuration
- Project-level MCP settings in `.claude/settings.local.json`
- Irrelevant MCPs (ga4, google-docs, railway, dropbox, browser plugins) disabled for this project
- Remote MCPs (Gmail, Calendar, Notion, HuggingFace) can only be disabled at account level on claude.ai
- Valid settings keys: `disabledMcpjsonServers`, `enabledMcpjsonServers`, `enabledPlugins`, `enableAllProjectMcpServers`
