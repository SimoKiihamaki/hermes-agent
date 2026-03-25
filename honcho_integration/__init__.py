"""Honcho integration for AI-native memory.

This package is only active when honcho.enabled=true in config and
HONCHO_API_KEY is set. All honcho-ai imports are deferred to avoid
ImportError when the package is not installed.

Named ``honcho_integration`` (not ``honcho``) to avoid shadowing the
``honcho`` package installed by the ``honcho-ai`` SDK.
"""

from honcho_integration.client import (
    HonchoClientConfig,
    get_honcho_client,
    reset_honcho_client,
    resolve_config_path,
)
from honcho_integration.session import (
    HonchoSession,
    HonchoSessionManager,
)

__all__ = [
    "HonchoClientConfig",
    "get_honcho_client",
    "reset_honcho_client",
    "resolve_config_path",
    "HonchoSession",
    "HonchoSessionManager",
]
