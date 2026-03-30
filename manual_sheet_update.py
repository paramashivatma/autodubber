#!/usr/bin/env python3
"""Manually update Google Sheet for last processed video"""

import os
import sys
from datetime import datetime

# Add dubber to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dubber.sheet_logger import quick_update_from_publish_result

def main():
    """Manually update Google Sheet with last video data"""
    
    # Data from last video processing (from logs/output)
    video_title = "source.mp4"  # The video filename
    status = "done"
    attempts = 1
    youtube_url = "https://youtube.com/shorts/69cab0cb618fd6943724b745"  # From logs
    duration = "00:29"  # Approximate from logs
    source_lang = "en"  # From transcriber
    target_lang = "gu"  # Gujarati
    platforms = ["youtube", "instagram", "tiktok", "facebook", "twitter", "threads", "bluesky"]
    post_ids = {
        "youtube": {"post_id": "69cab0cb618fd6943724b745", "url": "https://youtube.com/shorts/69cab0cb618fd6943724b745"},
        "instagram": {"post_id": "69cab0cd420bfafbac7f7f0d", "url": ""},
        "tiktok": {"post_id": "69cab0cc3304bb41123dd370", "url": ""},
        "facebook": {"post_id": "69cab0cc3ff516397d7d4644", "url": ""},
        "twitter": {"post_id": "69cab0cc618fd6943724b780", "url": ""},
        "threads": {"post_id": "69cab0ca618fd6943724b70f", "url": ""},
        "bluesky": {"post_id": "69cab0cb3ff516397d7d462a", "url": ""}
    }
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print("Updating Google Sheet with last video data:")
    print(f"  Video Title: {video_title}")
    print(f"  Status: {status}")
    print(f"  YouTube URL: {youtube_url}")
    print(f"  Duration: {duration}")
    print(f"  Source Lang: {source_lang}")
    print(f"  Target Lang: {target_lang}")
    print(f"  Platforms: {', '.join(platforms)}")
    print(f"  Post IDs: {len(post_ids)} platforms")
    print()
    
    # Update the sheet
    success, message = quick_update_from_publish_result(
        video_title=video_title,
        publish_results=post_ids
    )
    
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")

if __name__ == "__main__":
    main()
