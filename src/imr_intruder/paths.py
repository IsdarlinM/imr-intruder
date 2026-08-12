from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    home: Path
    config: Path
    state: Path
    data: Path
    cache: Path

    @property
    def sessions(self) -> Path:
        return self.data / "sessions"

    @property
    def workspaces(self) -> Path:
        return self.data / "workspaces"

    @property
    def history(self) -> Path:
        return self.data / "history"

    @property
    def macros(self) -> Path:
        return self.data / "macros"

    @property
    def web_state(self) -> Path:
        return self.state / "web.json"

    @property
    def web_log(self) -> Path:
        return self.state / "web.log"

    @property
    def web_pid(self) -> Path:
        return self.state / "web-child.json"


def _env_path(name: str, fallback: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else fallback


def get_paths() -> AppPaths:
    home = _env_path("IMR_INTRUDER_HOME", Path.home() / ".local" / "share" / "imr-intruder")
    config = _env_path("IMR_INTRUDER_CONFIG", Path.home() / ".config" / "imr-intruder")
    state = _env_path("IMR_INTRUDER_STATE", Path.home() / ".local" / "state" / "imr-intruder")
    data = _env_path("IMR_INTRUDER_DATA", home / "data")
    cache = _env_path("IMR_INTRUDER_CACHE", Path.home() / ".cache" / "imr-intruder")
    return AppPaths(home=home, config=config, state=state, data=data, cache=cache)


def ensure_paths() -> AppPaths:
    paths = get_paths()
    for directory in (
        paths.home,
        paths.config,
        paths.state,
        paths.data,
        paths.cache,
        paths.sessions,
        paths.workspaces,
        paths.history,
        paths.macros,
    ):
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:
            pass
    return paths
