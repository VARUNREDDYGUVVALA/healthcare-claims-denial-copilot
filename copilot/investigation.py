"""Compatibility import for the original investigation module."""
import sys
from agentic_ai.workflows import investigation

sys.modules[__name__] = investigation
