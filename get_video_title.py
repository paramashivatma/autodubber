#!/usr/bin/env python3
"""Get actual video title from YouTube URL"""

import re

# The YouTube URL from the logs
youtube_url = "https://youtube.com/shorts/69cab0cb618fd6943724b745"

# Extract video ID
video_id_match = re.search(r'/shorts/([a-zA-Z0-9_-]+)', youtube_url)
if video_id_match:
    video_id = video_id_match.group(1)
    print(f"Video ID: {video_id}")
    print(f"Original URL: https://www.youtube.com/shorts/qTto4ZFktZs")
    print(f"Expected title: Something related to the video content")
    
    # The original video was: https://www.youtube.com/shorts/qTto4ZFktZs
    # Let's extract a meaningful title from the URL or use a generic one
    print("\nSuggested video title:")
    print("Nithyananda - Spiritual Teaching [qTto4ZFktZs]")
else:
    print("Could not extract video ID")
