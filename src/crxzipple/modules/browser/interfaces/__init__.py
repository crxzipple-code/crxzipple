"""Interface layer for the browser module."""

from .facade import BrowserInterfaceFacade
from .requests import (
    BrowserControlRequest,
    BrowserInterfaceRequest,
    BrowserPageActionRequest,
)
from .serializers import BrowserResultSerializer

__all__ = [
    "BrowserControlRequest",
    "BrowserInterfaceRequest",
    "BrowserPageActionRequest",
    "BrowserResultSerializer",
    "BrowserInterfaceFacade",
]

