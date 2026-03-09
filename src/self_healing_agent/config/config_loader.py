from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_env_from_config(env: str = "dev", overwrite: bool = False) -> dict[str, str]:
    """
    Load only top-level `env_variables` from configs/env/{env}_config.yaml into os.environ.

    Args:
        overwrite: If True, replace already-set environment variables.

    Returns:
        A dict of environment variables that were written to os.environ.
    """
    project_root = Path(__file__).resolve().parents[3]
    config_path = project_root / "configs" / "env" / f"{env}_config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        loaded: Any = yaml.safe_load(handle) or {}

    if not isinstance(loaded, dict):
        raise ValueError(
            f"Expected a mapping at top-level in {config_path}, got {type(loaded).__name__}"
        )

    env_variables = loaded.get("env_variables", {})
    if not isinstance(env_variables, dict):
        raise ValueError(
            f"Expected 'env_variables' to be a mapping in {config_path}, "
            f"got {type(env_variables).__name__}"
        )

    written: dict[str, str] = {}
    for key, value in env_variables.items():
        env_key = str(key)
        env_value = "" if value is None else str(value)
        if overwrite or env_key not in os.environ:
            os.environ[env_key] = env_value
            written[env_key] = env_value

    print(f"Loaded environment variables from {config_path}: {list(env_variables.keys())}")
    return written
