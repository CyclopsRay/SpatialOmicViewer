#!/usr/bin/env python
"""Run the viewer from source (no packaging). Usage: python run_dev.py [study.config]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sparcal_viewer.app import main

if __name__ == "__main__":
    raise SystemExit(main())
