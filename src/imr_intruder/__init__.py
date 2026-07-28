"""imr-intruder: controlled HTTP request matrix for authorized testing."""

from .core import build_intruder_requests, run_requests

__version__ = "1.0.0"
__all__ = ["__version__", "build_intruder_requests", "run_requests"]
