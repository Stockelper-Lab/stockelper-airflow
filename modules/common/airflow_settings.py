from __future__ import annotations

import os
from typing import Any

from modules.common.logging_config import setup_logger

logger = setup_logger(__name__)


try:
    # Airflow runtime
    from airflow.models import Variable  # type: ignore
except Exception:  # noqa: BLE001
    Variable = None


def get_setting(key: str, default: str | None = None) -> str | None:
    """Get setting from Airflow Variables first, then fallback to env var.

    This enables configuration via:
    - Airflow Web UI → Admin → Variables
    - or OS environment variables for local/dev usage
    """

    if Variable is not None:
        try:
            value = Variable.get(key, default_var=default)
            if value is not None:
                return str(value)
        except Exception as exc:  # noqa: BLE001
            # Do not leak secrets; log only metadata.
            logger.warning("Variable.get failed for key=%s: %s", key, exc)

    return os.getenv(key, default)


def get_required_setting(key: str) -> str:
    value = get_setting(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Required setting is missing: {key} (Airflow Variable or env var)")
    return str(value)


def get_setting_json(key: str, default: Any | None = None) -> Any:
    """Get JSON setting from Airflow Variable if possible, else from env (string)."""
    if Variable is not None:
        try:
            return Variable.get(key, default_var=default, deserialize_json=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Variable.get(json) failed for key=%s: %s", key, exc)
            return default

    raw = os.getenv(key)
    if raw is None:
        return default
    # Best-effort: caller can json.loads if needed.
    return raw


