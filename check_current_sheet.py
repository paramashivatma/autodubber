#!/usr/bin/env python3
"""Check current Google Sheet content"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def check_sheet():
    """Check current Google Sheet content"""
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
        
        all_values = worksheet.get_all_values()
        
        print("Current Google Sheet content:")
        print("=" * 120)
        
        for i, row in enumerate(all_values, start=1):
            print(f"Row {i}: {row}")
        
        print("=" * 120)
        print(f"Total rows: {len(all_values)}")
        
        # Check YouTube URL
        if len(all_values) >= 4:
            row_4 = all_values[3] if len(all_values) > 3 else []
            if len(row_4) > 3:
                youtube_url = row_4[3]
                print(f"\nRow 4 YouTube URL: {youtube_url}")
                if "404" in youtube_url or not youtube_url:
                    print("❌ YouTube URL is 404 or empty!")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_sheet()
