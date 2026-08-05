from __future__ import annotations

import argparse
import ctypes
import ntpath
import os
import winreg

ENVIRONMENT = r"Environment"
VARIABLES = (
    "IMR_INTRUDER_HOME",
    "IMR_INTRUDER_CONFIG",
    "IMR_INTRUDER_STATE",
    "IMR_INTRUDER_DATA",
    "IMR_INTRUDER_CACHE",
)


def read_environment() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, ENVIRONMENT, 0, winreg.KEY_READ)
    except FileNotFoundError:
        return values
    with key:
        index = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, index)
            except OSError:
                break
            values[name] = value
            index += 1
    return values


def write_value(name: str, value: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ENVIRONMENT) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)


def remove_value(name: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ENVIRONMENT) as key:
        try:
            winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass


def normalized_path(value: str) -> str:
    expanded = ntpath.expandvars(value.strip().strip('"'))
    return ntpath.normcase(ntpath.normpath(expanded))


def update_user_path(*, add: list[str], remove: list[str]) -> str:
    environment = read_environment()
    current = next(
        (value for name, value in environment.items() if name.casefold() == "path"),
        "",
    )
    remove_set = {normalized_path(value) for value in remove if value.strip()}
    ordered: list[str] = []
    seen: set[str] = set()

    for value in add:
        part = value.strip()
        if not part:
            continue
        normalized = normalized_path(part)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(part)

    for value in current.split(";"):
        part = value.strip()
        if not part:
            continue
        normalized = normalized_path(part)
        if normalized in remove_set or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(part)

    result = ";".join(ordered)
    write_value("Path", result)
    return result


def python_path_entries(executable: str) -> list[str]:
    home = ntpath.dirname(ntpath.normpath(executable.strip('"')))
    return [home, ntpath.join(home, "Scripts")]


def broadcast() -> None:
    """Best-effort environment refresh; Windows Server Core may not expose user32."""
    try:
        user32 = ctypes.windll.user32
    except (AttributeError, OSError):
        return
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_ulong()
    try:
        user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            ctypes.byref(result),
        )
    except OSError:
        return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)

    python = subparsers.add_parser("python")
    python.add_argument("executable")

    install = subparsers.add_parser("install")
    install.add_argument("bin")
    install.add_argument("app_home")
    install.add_argument("config")
    install.add_argument("state")
    install.add_argument("data")
    install.add_argument("cache")
    install.add_argument("--python-executable")

    remove = subparsers.add_parser("remove")
    remove.add_argument("bin")
    remove.add_argument("app_home")
    remove.add_argument("config")
    remove.add_argument("state")
    remove.add_argument("data")
    remove.add_argument("cache")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.action == "python":
        entries = python_path_entries(args.executable)
        update_user_path(add=entries, remove=[])
        broadcast()
        return 0

    if args.action == "install":
        python_entries = (
            python_path_entries(args.python_executable)
            if args.python_executable
            else []
        )
        update_user_path(add=[args.bin, *python_entries], remove=[args.bin])
        values = {
            "IMR_INTRUDER_HOME": args.app_home,
            "IMR_INTRUDER_CONFIG": args.config,
            "IMR_INTRUDER_STATE": args.state,
            "IMR_INTRUDER_DATA": args.data,
            "IMR_INTRUDER_CACHE": args.cache,
        }
        for name, value in values.items():
            write_value(name, value)
    else:
        # Uninstall only removes the application launcher. Python was installed
        # as a separate user runtime and remains available to the user.
        update_user_path(add=[], remove=[args.bin])
        for name in VARIABLES:
            remove_value(name)

    broadcast()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
