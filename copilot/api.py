"""Compatibility entry point for the local API."""
import sys
from apps.api import main

sys.modules[__name__] = main
