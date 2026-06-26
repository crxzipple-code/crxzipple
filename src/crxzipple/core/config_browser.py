from __future__ import annotations

from crxzipple.core.config_browser_loader import (
    ensure_default_user_browser_profile_settings,
    load_browser_profile_settings,
    load_browser_proxy_base_urls,
)
from crxzipple.core.config_browser_models import (
    DEFAULT_BROWSER_DEFAULT_PROFILE_NAME,
    DEFAULT_BROWSER_PROFILE_COLOR,
    DEFAULT_BROWSER_USER_CDP_URL,
    DEFAULT_BROWSER_USER_PROFILE_NAME,
    BrowserProfileSettings,
    BrowserProxyEndpointSettings,
)

__all__ = [
    "BrowserProfileSettings",
    "BrowserProxyEndpointSettings",
    "DEFAULT_BROWSER_DEFAULT_PROFILE_NAME",
    "DEFAULT_BROWSER_PROFILE_COLOR",
    "DEFAULT_BROWSER_USER_CDP_URL",
    "DEFAULT_BROWSER_USER_PROFILE_NAME",
    "ensure_default_user_browser_profile_settings",
    "load_browser_profile_settings",
    "load_browser_proxy_base_urls",
]
