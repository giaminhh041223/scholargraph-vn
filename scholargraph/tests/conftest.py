"""Pytest configuration and shared test fixtures for ScholarGraph VN."""

import sys
from pathlib import Path

# Đảm bảo src/ nằm trong sys.path khi chạy pytest trực tiếp
SRC_PATH = Path(__file__).resolve().parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
