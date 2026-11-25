"""Compatibility entry point for generating the demo."""
import sys
from machine_learning.training import pipeline

if __name__ == "__main__":
    pipeline.build()
else:
    sys.modules[__name__] = pipeline
