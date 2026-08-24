#!/usr/bin/env python3
"""Backward-compatible CLI for the independent quality engines."""
from pathlib import Path
import importlib.util

_spec=importlib.util.spec_from_file_location('quality_engine', Path(__file__).with_name('quality_engine.py'))
_mod=importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_mod)

# Keep public helpers available to existing callers.
luminance=_mod.luminance if hasattr(_mod,'luminance') else None

def main():
    _mod.main()

if __name__=='__main__': main()
