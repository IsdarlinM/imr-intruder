from __future__ import annotations

import argparse
import os
import winreg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["add", "remove"])
    parser.add_argument("directory")
    args = parser.parse_args()

    target = os.path.normcase(os.path.normpath(os.path.expandvars(args.directory)))
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_READ | winreg.KEY_SET_VALUE,
    )
    try:
        try:
            current, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, value_type = "", winreg.REG_EXPAND_SZ
        parts = [part.strip() for part in current.split(";") if part.strip()]
        normalized = [os.path.normcase(os.path.normpath(os.path.expandvars(part))) for part in parts]
        if args.action == "add" and target not in normalized:
            parts.append(args.directory)
        elif args.action == "remove":
            parts = [part for part, norm in zip(parts, normalized) if norm != target]
        winreg.SetValueEx(key, "Path", 0, value_type, ";".join(parts))
    finally:
        winreg.CloseKey(key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
