from __future__ import annotations
required = ['httpx','fastapi','uvicorn','jinja2','rich','packaging','websockets']
missing=[]
for name in required:
    try: __import__(name)
    except Exception: missing.append(name)
if missing:
    raise SystemExit('Missing dependencies: ' + ', '.join(missing))
