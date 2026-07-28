from __future__ import annotations

import argparse
import ctypes
import os
import winreg


def normalize(value: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.expandvars(value.strip().strip('"'))))


def broadcast_environment_change() -> None:
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        0,
        "Environment",
        SMTO_ABORTIFHUNG,
        5000,
        ctypes.byref(result),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["add", "remove"])
    parser.add_argument("directory")
    args = parser.parse_args()

    target = normalize(args.directory)
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_READ | winreg.KEY_SET_VALUE,
    ) as key:
        try:
            current, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, value_type = "", winreg.REG_EXPAND_SZ

        parts = [part.strip() for part in current.split(";") if part.strip()]
        normalized = [normalize(part) for part in parts]
        if args.action == "add" and target not in normalized:
            parts.append(args.directory)
        elif args.action == "remove":
            parts = [part for part, norm in zip(parts, normalized) if norm != target]

        updated = ";".join(parts)
        if len(updated) >= 32767:
            raise SystemExit("[ERROR] The user PATH would exceed the Windows limit.")
        winreg.SetValueEx(key, "Path", 0, value_type, updated)

    broadcast_environment_change()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
