"""Test the sheet logger with dummy data."""
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dubber.sheet_logger import quick_update_from_publish_result

# Dummy test data
test_results = {
    "youtube": {
        "post_id": "test123abc",
        "url": "https://youtube.com/shorts/test123abc"
    },
    "instagram": {
        "post_id": "test456def",
        "url": "https://instagram.com/p/test456def"
    },
    "tiktok": {
        "post_id": "test789ghi",
        "url": "https://tiktok.com/@user/video/test789ghi"
    },
    "facebook": {
        "post_id": "test111jkl",
        "url": "https://facebook.com/test111jkl"
    },
    "twitter": {
        "post_id": "test222mno",
        "url": "https://twitter.com/user/status/test222mno"
    },
    "threads": {
        "post_id": "test333pqr",
        "url": "https://threads.net/@user/post/test333pqr"
    },
    "bluesky": {
        "post_id": "test444stu",
        "url": "https://bsky.app/profile/user/post/test444stu"
    }
}

print("=" * 60)
print("TESTING SHEET LOGGER")
print("=" * 60)

# Test the update function
success, msg = quick_update_from_publish_result(
    video_title="TEST_C Paramashivatma dubguiv4gui.mp4",
    publish_results=test_results,
    duration="00:44",
    source_lang="ta",
    target_lang="gu",
)

print(f"\nResult: {msg}")
print(f"Success: {success}")

if success:
    print("\n✅ Sheet logger test PASSED")
    print("Check your 'AutoDubQueue' Google Sheet for the new row")
else:
    print("\n❌ Sheet logger test FAILED")
    print("Error:", msg)
