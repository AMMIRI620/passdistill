#!/usr/bin/env python3
"""Repeat the no-fast-math experiment with configuration-aware system prompts."""

import run_2mm_dmxapi_50 as runner


if __name__ == "__main__":
    runner.CONFIGS = (runner.ROOT / "configs" / "2mm_dmxapi_50_fast_math_off_clean_prompt.json",)
    raise SystemExit(runner.main())
