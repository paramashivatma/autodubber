#!/usr/bin/env python3
"""Fix YouTube URL placeholder to show pending status"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def fix_youtube_url():
    """Update YouTube URL to show pending status instead of 404 placeholder"""
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("No GOOGLE_SHEET_ID found")
        return
    
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if not os.path.exists(creds_path):
        print(f"Credentials not found: {creds_path}")
        return
    
    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly"
        ])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet("AutoDubQueue")
        
        # Update YouTube URL to show pending status
        pending_url = "Pending - Will be updated after successful publish"
        
        # Update Row 2, Column D (YouTube URL)
        worksheet.update("D2", [[pending_url]])
        
        print("✅ Updated YouTube URL:")
        print(f"  - Old: https://youtube.com/shorts/NEW_VIDEO_ID (404)")
        print(f"  - New: {pending_url}")
        print("  - This will be updated with the actual URL after the video is published")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fix_youtube_url()
