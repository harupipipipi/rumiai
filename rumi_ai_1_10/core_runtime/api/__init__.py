"""
api パッケージ — PackAPIHandler のハンドラ Mixin 群

使い方:
    from .api import (
        PackHandlersMixin,
        ContainerHandlersMixin,
        ...
    )

    class PackAPIHandler(PackHandlersMixin, ..., BaseHTTPRequestHandler):
        ...
"""
import importlib

from .api_response import APIResponse
from .flow_handlers import FlowHandlersMixin
from .route_handlers import RouteHandlersMixin
from .control_panel_handlers import ControlPanelHandlersMixin
from .capability_graph_handlers import CapabilityGraphHandlersMixin
from .setup_handlers import SetupHandlersMixin
from .oauth_handlers import OAuthHandlersMixin
from .viewer_handlers import ViewerHandlersMixin
from .desktop_handlers import DesktopHandlersMixin
from .security import (
    AuthorityHandlersMixin,
    CapabilityGrantHandlersMixin,
    CapabilityInstallerHandlersMixin,
    NetworkHandlersMixin,
    PrivilegeHandlersMixin,
)
from .lifecycle import (
    PackHandlersMixin,
    PackLifecycleHandlersMixin,
    ContainerHandlersMixin,
    PipHandlersMixin,
)
from .store import (
    SecretsHandlersMixin,
    StoreHandlersMixin,
    StoreShareHandlersMixin,
    UnitHandlersMixin,
)

__all__ = [
    "APIResponse",
    "AuthorityHandlersMixin",
    "PackHandlersMixin",
    "ContainerHandlersMixin",
    "NetworkHandlersMixin",
    "CapabilityGrantHandlersMixin",
    "StoreShareHandlersMixin",
    "PrivilegeHandlersMixin",
    "CapabilityInstallerHandlersMixin",
    "PipHandlersMixin",
    "SecretsHandlersMixin",
    "StoreHandlersMixin",
    "UnitHandlersMixin",
    "FlowHandlersMixin",
    "RouteHandlersMixin",
    "PackLifecycleHandlersMixin",
    "ControlPanelHandlersMixin",
    "CapabilityGraphHandlersMixin",
    "SetupHandlersMixin",
    "OAuthHandlersMixin",
    "ViewerHandlersMixin",
    "DesktopHandlersMixin",
]

_LAZY_SUBMODULES = {
    "control_panel_handlers",
    "capability_graph_handlers",
    "desktop_handlers",
    "flow_handlers",
    "lifecycle",
    "oauth_handlers",
    "route_handlers",
    "secrets_handlers",
    "setup_handlers",
    "store",
    "viewer_handlers",
}


def __getattr__(name):
    if name in _LAZY_SUBMODULES:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
