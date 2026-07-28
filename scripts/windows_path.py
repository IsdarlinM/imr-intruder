from __future__ import annotations

import argparse
import ctypes
import os
import winreg

ENVIRONMENT = r"Environment"
VARIABLES = ("IMR_INTRUDER_HOME", "IMR_INTRUDER_CONFIG", "IMR_INTRUDER_STATE", "IMR_INTRUDER_DATA", "IMR_INTRUDER_CACHE")


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


def broadcast() -> None:
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, ctypes.byref(result)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "remove"])
    parser.add_argument("bin")
    parser.add_argument("app_home")
    parser.add_argument("config")
    parser.add_argument("state")
    parser.add_argument("data")
    parser.add_argument("cache")
    args = parser.parse_args()

    current = read_environment().get("Path", "")
    parts = [part for part in current.split(";") if part and os.path.normcase(part) != os.path.normcase(args.bin)]
    if args.action == "install":
        write_value("Path", ";".join([args.bin, *parts]))
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
        write_value("Path", ";".join(parts))
        for name in VARIABLES:
            remove_value(name)
    broadcast()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
