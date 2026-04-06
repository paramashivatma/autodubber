#!/usr/bin/env python3
"""Dry run test - generates captions without publishing."""

import sys
import os

# Force UTF-8 encoding for stdout
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, ".")

from dubber.caption_generator import generate_all_captions
from dubber.utils import OPTIMAL_RANGES, PLATFORM_LIMITS, SHORT_MINIMUMS

# Mock vision data (simulating what Gemini would return)
mock_vision_data = {
    "main_topic": "Sudashiva teaches to be your own boss and fulfill your dreams",
    "core_conflict": "People waste their lives fulfilling others' dreams instead of their own",
    "provocative_angle": "Never bow down to anyone except Sudashiva - your life is meant for your dreams",
    "theme": "teaching",
}

# Simulated transcript (what would come from transcription)
mock_transcript = [
    {
        "text": "Never bow down to anybody other than Sudashiva. You fulfill your dream or somebody else will hire you to fulfill their dreams."
    },
    {
        "text": "Please understand, if you don't become your own boss, I am giving you spiritual advice, not social advice."
    },
    {"text": "It's a spiritual truth - bowing down only to him, nobody else."},
]


def print_separator(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def analyze_caption(platform, caption, original_len=None):
    """Analyze a caption and show if it would be trimmed."""
    opt_range = OPTIMAL_RANGES.get(platform)
    hard_limit = PLATFORM_LIMITS.get(platform, 2000)
    min_len = SHORT_MINIMUMS.get(platform, 80)

    if opt_range:
        opt_min, opt_max = opt_range
        overage_pct = (
            ((len(caption) - opt_max) / opt_max) * 100 if len(caption) > opt_max else 0
        )

        if len(caption) < opt_min:
            status = "[!] BELOW OPTIMAL"
        elif len(caption) > opt_max:
            if overage_pct >= 30:
                status = "[X] WOULD TRIM (>30% over)"
            else:
                status = "[OK] WITHIN TOLERANCE (<30% over)"
        else:
            status = "[OK] OPTIMAL"
    else:
        status = "[OK] NO OPTIMAL RANGE"

    print(f"\n{'-' * 70}")
    print(f"  {platform.upper()}")
    print(f"{'-' * 70}")
    print(f"  Length: {len(caption)} chars")
    print(f"  Optimal range: {opt_range}")
    print(f"  Hard limit: {hard_limit}")
    print(f"  Status: {status}")
    if len(caption) > opt_max if opt_range else False:
        print(f"  Overage: {overage_pct:.0f}%")
    print(f"\n  Caption preview:")
    print(f"  {caption[:120]}{'...' if len(caption) > 120 else ''}")
    print(f"  {'-' * 66}")
    if len(caption) > 120:
        print(f"  ...{caption[-120:]}")


def main():
    print_separator("DRY RUN - Caption Generation Test")
    print("\nThis test generates captions WITHOUT publishing.")
    print("Shows what would be trimmed based on current OPTIMAL_RANGES.\n")

    print(f"Current OPTIMAL_RANGES:")
    for platform, (min_val, max_val) in OPTIMAL_RANGES.items():
        print(f"  {platform:12} -> {min_val}-{max_val} chars")

    print_separator("Generating Captions...")

    try:
        captions = generate_all_captions(
            vision_data=mock_vision_data,
            segments=mock_transcript,
            target_language="gu",
            return_meta=False,
        )

        print_separator("Caption Analysis")

        for platform, data in captions.items():
            caption = data.get("caption", "") if isinstance(data, dict) else str(data)
            analyze_caption(platform, caption)

        print_separator("Summary")

        trim_count = 0
        keep_count = 0
        for platform, data in captions.items():
            caption = data.get("caption", "") if isinstance(data, dict) else str(data)
            opt_range = OPTIMAL_RANGES.get(platform)
            if opt_range:
                opt_max = opt_range[1]
                overage_pct = (
                    ((len(caption) - opt_max) / opt_max) * 100
                    if len(caption) > opt_max
                    else 0
                )
                if overage_pct >= 30:
                    trim_count += 1
                    print(
                        f"  [X] {platform}: {len(caption)} chars ({overage_pct:.0f}% over) - WOULD TRIM"
                    )
                elif len(caption) > opt_max:
                    keep_count += 1
                    print(
                        f"  [OK] {platform}: {len(caption)} chars ({overage_pct:.0f}% over) - KEPT"
                    )
                else:
                    keep_count += 1
                    print(f"  [OK] {platform}: {len(caption)} chars - OPTIMAL")

        print(f"\n  Result: {keep_count} kept, {trim_count} would be trimmed")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
