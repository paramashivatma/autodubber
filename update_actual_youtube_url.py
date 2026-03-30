#!/usr/bin/env python3
"""Update with actual YouTube URL from published.lock"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def update_actual_youtube_url():
    """Update sheet with actual YouTube URL from published.lock"""
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("No GOOGLE_SHEET_ID found")
        return
    
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if not os.path.exists(creds_path):
        print(f"Credentials not found: {creds_path}")
        return
    
    # Read the published.lock file to get actual YouTube post ID
    lock_file = os.path.join(os.path.dirname(__file__), "workspace", "published.lock")
    try:
        with open(lock_file, 'r') as f:
            published_data = json.load(f)
        
        youtube_post_id = published_data.get("youtube", {}).get("post_id", "")
        if not youtube_post_id:
            print("No YouTube post ID found in published.lock")
            return
        
        # Build the actual YouTube URL
        actual_youtube_url = f"https://youtube.com/shorts/{youtube_post_id}"
        print(f"Found actual YouTube URL: {actual_youtube_url}")
        
    except Exception as e:
        print(f"Error reading published.lock: {e}")
        return
    
    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly"
        ])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet("AutoDubQueue")
        
        # Update Row 2, Column D (YouTube URL) with actual URL
        worksheet.update("D2", [[actual_youtube_url]])
        
        # Also update Post IDs column with all platform IDs
        post_ids_str = f"yt:{youtube_post_id}"
        for platform, data in published_data.items():
            if platform != "youtube" and data.get("status") == "ok":
                post_id = data.get("post_id", "")
                if post_id:
                    post_ids_str += f",{platform[:2]}:{post_id}"
        
        # Update Row 2, Column I (Post IDs)
        worksheet.update("I2", [[post_ids_str]])
        
        print("✅ Updated Row 2 with actual published data:")
        print(f"  - YouTube URL: {actual_youtube_url}")
        print(f"  - Post IDs: {post_ids_str}")
        print("  - Video is now properly tracked with real URLs and IDs")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    update_actual_youtube_url()
