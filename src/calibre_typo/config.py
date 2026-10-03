from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENV_PREFIX = "CALIBRE_TYPO_"

_PACKAGE_DIR = Path(__file__).resolve().parent
_BUNDLED_PLUGIN = _PACKAGE_DIR / "koplugin" / "calibretypo.koplugin"
_SOURCE_PLUGIN = _PACKAGE_DIR.parents[1] / "koreader" / "calibretypo.koplugin"


def _default_plugin_dir() -> Path:
    # Bundled in wheels, at the repo root in a source checkout
    return _BUNDLED_PLUGIN if _BUNDLED_PLUGIN.is_dir() else _SOURCE_PLUGIN


@dataclass(frozen=True)
class Settings:
    library_dir: Path
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8090
    public_url: str | None = None
    plugin_dir: Path = _default_plugin_dir()

    @property
    def database_path(self) -> Path:
        return self.data_dir / "calibre-typo.db"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        def get(name: str, default: str | None = None) -> str | None:
            return env.get(ENV_PREFIX + name, default)

        return cls(
            library_dir=Path(get("LIBRARY", "/calibre-library")),
            data_dir=Path(get("DATA", "/data")),
            host=get("HOST", "127.0.0.1"),
            port=int(get("PORT", "8090")),
            public_url=(get("PUBLIC_URL") or "").rstrip("/") or None,
            plugin_dir=Path(get("PLUGIN_DIR") or _default_plugin_dir()),
        )
