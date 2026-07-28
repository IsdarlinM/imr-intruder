from pathlib import Path

from imr_intruder import build_intruder_requests, run_requests


base_request = {
    "method": "POST",
    "url": "https://httpbin.org/post",
    "data": {
        "username": "authorized-lab-user",
        "test_value": "{{VALUE}}",
    },
    "timeout": 15,
    "verify_tls": True,
    "follow_redirects": False,
    "columns": [
        {
            "name": "location",
            "source": "header",
            "key": "Location",
            "default": "-",
        }
    ],
}

requests_cfg = build_intruder_requests(
    base_request,
    ["alpha", "beta", "gamma"],
)

run_requests(
    requests_cfg=requests_cfg,
    workers=2,
    delay_ms=100,
    csv_path=Path("results.csv"),
    live=True,
)
