"""YAML config reader.

Loads a YAML file (defaults to `project_config.yaml` at the repo root) into
a nested, attribute-accessible object, so callers can do either:

    config.logging.level
    config.logging.get("level")
    config.logging.get("timeout", 30)          # with a default
    config.get("logging", {}).get("level")     # dict-style throughout

Every nested mapping is wrapped the same way, so this works at any depth
(e.g. `config.database.pool.get("size")`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# repo root -- three levels up from this file (src/utils/config.py -> repo root)
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "project_config.yaml"


class ConfigReader:
    """Read-only, dict-like view over a mapping that also exposes each key
    as an attribute, recursively wrapping nested mappings (and mappings
    nested inside lists) the same way."""

    def __init__(self, data: dict[str, Any]):
        object.__setattr__(self, "_data", data)

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._data:
            return default
        return self._wrap(self._data[key])

    def to_dict(self) -> dict[str, Any]:
        """Return the underlying plain dict, unwrapped."""
        return self._data

    def __getattr__(self, key: str) -> Any:
        # only called when normal attribute lookup fails, so this never
        # shadows real attributes/methods like get() or to_dict()
        try:
            return self._wrap(self._data[key])
        except KeyError as exc:
            raise AttributeError(f"no config key '{key}'") from exc

    def __getitem__(self, key: str) -> Any:
        return self._wrap(self._data[key])

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        return f"ConfigReader({self._data!r})"

    @classmethod
    def _wrap(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return cls(value)
        if isinstance(value, list):
            return [cls._wrap(v) for v in value]
        return value


def load_config(path: str | Path | None = None) -> ConfigReader:
    """Load a YAML file into a ConfigReader.

    Resolution order for the path: the explicit `path` argument, then the
    `CONFIG_PATH` env var, then `project_config.yaml` at the repo root.
    """
    resolved = path or os.environ.get("CONFIG_PATH") or _DEFAULT_CONFIG_PATH
    config_path = Path(resolved)
    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        got = type(data).__name__
        raise ValueError(f"{config_path} must contain a top-level mapping, got {got}")
    return ConfigReader(data)


_config: ConfigReader | None = None


def get_config(path: str | Path | None = None) -> ConfigReader:
    """Module-level singleton, loaded lazily on first use and cached after
    that -- so merely importing this module never fails just because
    project_config.yaml isn't found yet (e.g. cwd differs in a test run)."""
    global _config
    if _config is None:
        _config = load_config(path)
    return _config


def __getattr__(name: str) -> Any:
    # PEP 562: lets `from utils.config import config` and
    # `config.config` both resolve to get_config() lazily, so the
    # common case (`config.logging.get("level")`) needs no extra call.
    if name == "config":
        return get_config()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def from_env(name: str):
    """Retrieve a configuration value from the environment variables."""
    return os.environ.get(name)