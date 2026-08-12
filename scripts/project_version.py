from __future__ import annotations

import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
match = re.search(r'__version__\s*=\s*["\']([^"\']+)', path.read_text(encoding="utf-8"))
if not match:
    raise SystemExit("Unable to determine project version")
print(match.group(1))
