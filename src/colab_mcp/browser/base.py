from abc import ABC, abstractmethod


class BrowserBackend(ABC):
    """Abstract interface for browser backends that open and maintain Colab sessions."""

    @abstractmethod
    async def open(self, url: str) -> None:
        """Open the given URL in the browser."""

    @abstractmethod
    async def close(self) -> None:
        """Close the browser page/tab."""

    @abstractmethod
    async def is_alive(self) -> bool:
        """Check whether the browser page is still active."""

    @abstractmethod
    async def keepalive(self) -> None:
        """Perform a keepalive action to prevent Colab session timeout."""
