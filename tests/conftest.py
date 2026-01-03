"""Pytest configuration for IR Floor Heating tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add custom_components to path for imports
custom_components_path = Path(__file__).parent.parent / "custom_components"
if str(custom_components_path) not in sys.path:
    sys.path.insert(0, str(custom_components_path))
