from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version

from . import __version__
from .paths import ensure_paths

DEFAULT_REPOSITORY = "IsdarlinM/imr-intruder"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 300 * 1024 * 1024
MAX_ARCHIVE_FILES = 5000


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    latest: str
    available: bool
    source: str
    archive_url: str
    release_url: str


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"imr-intruder/{__version__}",
    }
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("IMR_INTRUDER_GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(url: str, token: str | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=20, follow_redirects=True, headers=_headers(token)) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected GitHub API response.")
    return data


def check_update(
    repository: str = DEFAULT_REPOSITORY,
    channel: str = "release",
    token: str | None = None,
) -> UpdateInfo:
    channel = channel.lower()
    if channel == "release":
        try:
            data = _request_json(
                f"https://api.github.com/repos/{repository}/releases/latest", token
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return check_update(repository, "main", token)
            raise
        tag = str(data.get("tag_name", "")).lstrip("v")
        archive_url = str(data.get("zipball_url", ""))
        release_url = str(data.get("html_url", ""))
        source = "release"
    elif channel == "main":
        data = _request_json(f"https://api.github.com/repos/{repository}/commits/main", token)
        tag = str(data.get("sha", ""))[:12]
        archive_url = f"https://api.github.com/repos/{repository}/zipball/main"
        release_url = str(data.get("html_url", ""))
        source = "main"
    else:
        raise ValueError("Update channel must be release or main.")

    if not tag or not archive_url:
        raise ValueError("GitHub did not return a valid update archive.")
    if channel == "release":
        try:
            available = Version(tag) > Version(__version__)
        except InvalidVersion as exc:
            raise ValueError(f"Invalid release version: {tag}") from exc
    else:
        state = ensure_paths().state / "installed_main_commit"
        installed = state.read_text(encoding="utf-8").strip() if state.exists() else ""
        available = installed != tag
    return UpdateInfo(__version__, tag, available, source, archive_url, release_url)


def _safe_extract(data: bytes, destination: Path) -> Path:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("Update archive exceeds the maximum download size.")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_FILES:
            raise ValueError("Update archive contains too many files.")
        total = sum(info.file_size for info in infos)
        if total > MAX_EXTRACTED_BYTES:
            raise ValueError("Update archive expands beyond the safety limit.")
        root_resolved = destination.resolve()
        top_levels: set[str] = set()
        for info in infos:
            name = info.filename.replace("\\", "/")
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe path in update archive: {name}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"Symlink entries are not allowed: {name}")
            target = (destination / path).resolve()
            if root_resolved not in target.parents and target != root_resolved:
                raise ValueError(f"Archive path escapes destination: {name}")
            if path.parts:
                top_levels.add(path.parts[0])
        archive.extractall(destination)
    if len(top_levels) != 1:
        raise ValueError("Update archive must contain exactly one project root.")
    project_root = destination / next(iter(top_levels))
    if not (project_root / "pyproject.toml").is_file():
        raise ValueError("Update archive does not contain pyproject.toml.")
    return project_root


def _download(url: str, token: str | None = None) -> tuple[bytes, str]:
    hasher = hashlib.sha256()
    buffer = io.BytesIO()
    with httpx.Client(timeout=60, follow_redirects=True, headers=_headers(token)) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                buffer.write(chunk)
                hasher.update(chunk)
                if buffer.tell() > MAX_ARCHIVE_BYTES:
                    raise ValueError("Update archive exceeds the maximum download size.")
    return buffer.getvalue(), hasher.hexdigest()


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PIP_TARGET",
        "PIP_PREFIX",
        "PIP_REQUIRE_VIRTUALENV",
    ):
        env.pop(key, None)
    return env


def install_update(
    info: UpdateInfo,
    *,
    token: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        return {
            "installed": False,
            "dry_run": True,
            "latest": info.latest,
            "url": info.archive_url,
        }
    data, digest = _download(info.archive_url, token)
    with tempfile.TemporaryDirectory(prefix="imr-intruder-update-") as temporary:
        project_root = _safe_extract(data, Path(temporary))
        version_file = project_root / "src" / "imr_intruder" / "__init__.py"
        if not version_file.is_file():
            raise ValueError("Update archive does not contain the package version file.")
        match = re.search(
            r'__version__\s*=\s*["\']([^"\']+)',
            version_file.read_text(encoding="utf-8"),
        )
        if not match:
            raise ValueError("Unable to determine the version in the update archive.")
        archive_version = match.group(1)
        if info.source == "release" and Version(archive_version) != Version(info.latest):
            raise ValueError(
                f"Update archive version {archive_version} does not match release {info.latest}."
            )
        if os.name == "nt":
            installer = project_root / "install.cmd"
            if not installer.is_file():
                raise ValueError("Windows installer is missing from update archive.")
            command = [
                "cmd.exe",
                "/d",
                "/c",
                str(installer),
                "/SOURCE",
                str(project_root),
            ]
        else:
            installer = project_root / "install.sh"
            if not installer.is_file():
                raise ValueError("Linux installer is missing from update archive.")
            command = ["bash", str(installer), "--source", str(project_root)]
        completed = subprocess.run(command, env=_clean_env(), text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"Installer returned exit code {completed.returncode}.")
    if info.source == "main":
        marker = ensure_paths().state / "installed_main_commit"
        marker.write_text(info.latest + "\n", encoding="utf-8")
    return {"installed": True, "version": info.latest, "sha256": digest}
