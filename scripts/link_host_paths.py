from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: link_host_paths.py VENV_PYTHON")
    venv_python = Path(sys.argv[1])
    completed = subprocess.run(
        [str(venv_python), "-c", "import json,site; print(json.dumps(site.getsitepackages()))"],
        text=True,
        capture_output=True,
        check=True,
    )
    sites = json.loads(completed.stdout.strip())
    if not sites:
        raise SystemExit("Unable to determine virtualenv site-packages")
    host_paths = []
    for raw in sys.path:
        if not raw:
            continue
        path = Path(raw).resolve()
        if path.is_dir() and ("site-packages" in path.name or "dist-packages" in path.name):
            host_paths.append(str(path))
    if not host_paths:
        raise SystemExit("Host interpreter does not expose package paths")
    target = Path(sites[0]) / "_imr_intruder_host_dependencies.pth"
    target.write_text("\n".join(dict.fromkeys(host_paths)) + "\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
