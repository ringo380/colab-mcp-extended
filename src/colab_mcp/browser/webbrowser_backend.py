import webbrowser

from colab_mcp.browser.base import BrowserBackend


class WebbrowserBackend(BrowserBackend):
    """Browser backend using Python's webbrowser module (opens default browser)."""

    async def open(self, url: str) -> None:
        webbrowser.open_new(url)

    async def close(self) -> None:
        pass  # Cannot programmatically close a webbrowser-opened tab

    async def is_alive(self) -> bool:
        return True  # Cannot determine — assume alive

    async def keepalive(self) -> None:
        pass  # User is responsible for keeping the tab open
