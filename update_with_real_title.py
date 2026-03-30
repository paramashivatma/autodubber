#!/usr/bin/env python3
"""Update row 3 with the actual YouTube title from captions.json"""

import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def update_with_real_title():
    """Update row 3 with actual YouTube title"""
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("No GOOGLE_SHEET_ID found")
        return
    
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if not os.path.exists(creds_path):
        print(f"Credentials not found: {creds_path}")
        return
    
    # Read the actual YouTube title from captions.json
    captions_path = os.path.join(os.path.dirname(__file__), "workspace", "captions.json")
    try:
        with open(captions_path, 'r', encoding='utf-8') as f:
            captions = json.load(f)
        
        # Get the YouTube title
        youtube_title = captions.get("youtube", {}).get("title", "")
        if not youtube_title:
            print("No YouTube title found in captions.json")
            return
            
        print(f"Found actual YouTube title: {youtube_title}")
        
    except Exception as e:
        print(f"Error reading captions.json: {e}")
        return
    
    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly"
        ])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet("AutoDubQueue")
        
        # Update only Column A (Video Title) in row 3 with the actual title
        worksheet.update("A3", [[youtube_title]])
        
        print("✅ Updated Row 3 with actual YouTube title:")
        print(f"  - Video Title: {youtube_title}")
        print("  - All other fields remain unchanged")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    update_with_real_title()
