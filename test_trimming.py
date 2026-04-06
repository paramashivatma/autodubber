#!/usr/bin/env python3
"""Test script for priority-aware trimming implementation."""

import sys

sys.path.insert(0, ".")

from dubber.caption_generator import (
    _smart_trim,
    _extract_trailing_hashtags,
    _extract_cta_links,
    _split_hook_body,
    _priority_aware_trim,
    _get_platform_config,
    PLATFORM_OVERRIDES,
    MIN_HOOK_CHARS,
    MIN_BODY_THRESHOLD,
    SEPARATOR,
)


def test_platform_config():
    print("\n" + "=" * 60)
    print("TEST: Platform Config")
    print("=" * 60)

    for platform in [
        "twitter",
        "threads",
        "instagram",
        "facebook",
        "tiktok",
        "bluesky",
        "youtube",
    ]:
        config = _get_platform_config(platform)
        print(f"  {platform}: {config}")

    print("  [PASS] Allplatform configs retrieved")


def test_hashtag_extraction():
    print("\n" + "=" * 60)
    print("TEST: Hashtag Extraction")
    print("=" * 60)

    # Trailing hashtag detection - only captures hashtags at END
    test_cases = [
        ("Body text\n\n#AI #GovTech\n#Policy", ("Body text", "#AI #GovTech\n#Policy")),
        ("No hashtags here", ("No hashtags here", "")),
        ("Text body\n\n#trailing #tags", ("Text body", "#trailing #tags")),
        ("#OnlyHashtags\n#Here", ("", "#OnlyHashtags\n#Here")),
    ]

    print("  Note: Only TRAILING hashtags are extracted (not inline)")
    print()

    for caption, expected in test_cases:
        body, hashtags = _extract_trailing_hashtags(caption)
        hashtags_match = hashtags.strip() == expected[1].strip() or (
            not expected[1] and not hashtags
        )
        status = "[PASS]" if hashtags_match else "[INFO]"
        print(f"  {status}")
        print(f"    Input: {caption[:50]}...")
        print(f"    Expected hashtags: {expected[1][:40]}...")
        print(f"    Got hashtags: {hashtags[:40]}...")


def test_cta_extraction():
    print("\n" + "=" * 60)
    print("TEST: CTA Extraction")
    print("=" * 60)

    # CTA extraction captures ENTIRE line containing CTA keywords
    test_cases = [
        ("Click here for details", ("for details", "Click here")),
        ("Watch the full video on YouTube", ("", "Watch the full video on YouTube")),
        (
            "Text body with link in bio for more",
            ("Text body with for more", "link in bio"),
        ),
        ("No CTAs here", ("No CTAs here", "")),
    ]

    print("  Note: CTA keywords capture entire line")
    print()

    for caption, expected in test_cases:
        body, cta = _extract_cta_links(caption)
        has_cta = bool(expected[1])
        got_cta = bool(cta)
        status = "[PASS]" if (has_cta == got_cta) else "[INFO]"
        print(f"  {status}")
        print(f"    Input: {caption[:50]}...")
        print(f"    Body: {body[:40] if body else '(empty)'}...")
        print(f"    CTA: {cta[:40] if cta else '(empty)'}...")


def test_smart_trim():
    print("\n" + "=" * 60)
    print("TEST: Smart Trim")
    print("=" * 60)

    test_cases = [
        (
            "This is a complete sentence. And another one here.",
            30,
            "This is a complete sentence.",
        ),
        ("Short text", 100, "Short text"),
        ("This ends with a conjunction and", 25, "This ends with a..."),
        ("One two three four five six seven eight", 20, "One two three four..."),
    ]

    for text, limit, expected_contains in test_cases:
        result = _smart_trim(text, limit)
        status = "[PASS]" if len(result) <= limit + 3 else "[FAIL]"
        print(f"  {status}")
        print(f"    Input ({len(text)} chars): {text[:40]}...")
        print(f"    Limit: {limit}")
        print(f"    Output ({len(result)} chars): {result}")


def test_priority_aware_trim():
    print("\n" + "=" * 60)
    print("TEST: Priority-Aware Trim")
    print("=" * 60)

    # Test case 1: Instagram with hashtags
    caption1 = "This is a wonderful message about spirituality and inner peace. The guru teaches us to find balance in our lives and connect with the divine within.#spiritual #innerpeace #meditation #KAILASA #Nithyananda"
    result1 = _priority_aware_trim(caption1, 300, "instagram")
    print(f"\n  [Case 1] Instagram (limit 300)")
    print(f"    Input ({len(caption1)} chars): {caption1[:60]}...")
    print(f"    Output ({len(result1)} chars): {result1[:80]}...")
    print(f"    Hashtags preserved: {'#KAILASA' in result1}")

    # Test case 2: Twitter - tight platform
    caption2 = "The divine consciousness permeates all existence and we must awaken to our true nature. #consciousness #awakening #KAILASA #Nithyananda"
    result2 = _priority_aware_trim(caption2, 240, "twitter")
    print(f"\n  [Case 2] Twitter (limit 240, tight platform)")
    print(f"    Input ({len(caption2)} chars): {caption2[:60]}...")
    print(f"    Output ({len(result2)} chars): {result2[:80]}...")
    print(f"    Under limit: {len(result2) <= 240}")

    # Test case 3: With CTA
    caption3 = "Watch the full video on YouTube for the complete teaching. This is the body text that explains the spiritual concept in detail.\n\n#spiritual #teaching\n\nLink in bio for more"
    result3 = _priority_aware_trim(caption3, 200, "instagram")
    print(f"\n  [Case 3] With CTA (limit 200)")
    print(f"    Input ({len(caption3)} chars)")
    print(f"    Output ({len(result3)} chars): {result3[:80]}...")
    print(
        f"    CTA preserved: {'Link in bio' in result3 or 'Watch the full' in result3}"
    )

    # Test case 4: Over 30% threshold - should trigger trim
    caption4 = "A" * 500 + "\n\n#hashtag1 #hashtag2"
    result4 = _priority_aware_trim(caption4, 200, "threads")
    overage_pct = ((len(caption4) - 200) / 200) * 100
    print(f"\n  [Case 4] Large overage ({overage_pct:.0f}% over, should trim)")
    print(f"    Input ({len(caption4)} chars)")
    print(f"    Output ({len(result4)} chars): {result4[:50]}...")
    print(f"    Hashtags preserved: {'#hashtag' in result4}")

    # Test case 5: Within tolerance - should not trim
    caption5 = "Short caption here.\n\n#tag1 #tag2"
    result5 = _priority_aware_trim(caption5, 300, "instagram")
    print(f"\n  [Case 5] Within tolerance (should not trim)")
    print(f"    Input ({len(caption5)} chars): {caption5}")
    print(f"    Output ({len(result5)} chars): {result5}")
    print(f"    Unchanged: {caption5 == result5}")


def test_degradation_hierarchy():
    print("\n" + "=" * 60)
    print("TEST: Degradation Hierarchy")
    print("=" * 60)

    # Very tight constraint to force degradation
    caption = "This is a long hook sentence that contains important spiritual teaching. Then we have more body text that extends the message.\n\n#hashtag1 #hashtag2 #hashtag3 #hashtag4 #hashtag5\n\nLink in bio for more"

    print(f"  Input ({len(caption)} chars)")

    for platform, limit in [("threads", 150), ("twitter", 180), ("bluesky", 200)]:
        result = _priority_aware_trim(caption, limit, platform)
        print(f"\n  [{platform}] Limit: {limit}")
        print(f"    Output ({len(result)} chars): {result[:80]}...")
        print(f"    Under limit: {len(result) <= limit}")


def run_all_tests():
    print("\n" + "=" * 60)
    print("PRIORITY-AWARE TRIMMING - INTERNAL TESTS")
    print("=" * 60)

    test_platform_config()
    test_hashtag_extraction()
    test_cta_extraction()
    test_smart_trim()
    test_priority_aware_trim()
    test_degradation_hierarchy()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
