#!/usr/bin/env python3
"""Run the no-fast-math comparison using the same 50-candidate runner."""

import run_2mm_dmxapi_50 as runner


if __name__ == "__main__":
    runner.CONFIGS = (runner.ROOT / "configs" / "2mm_dmxapi_50_fast_math_off.json",)
    raise SystemExit(runner.main())
