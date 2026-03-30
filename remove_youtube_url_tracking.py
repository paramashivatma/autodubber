#!/usr/bin/env python3
"""Remove YouTube URL tracking to reduce overhead and delays"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def remove_youtube_url_tracking():
    """Remove YouTube URL and Post IDs tracking to simplify sheet"""
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
        
        # Get current data
        all_values = worksheet.get_all_values()
        
        # Clear and rebuild with simplified headers (no YouTube URL, no Post IDs)
        worksheet.clear()
        
        # Simplified headers (removed YouTube URL and Post IDs)
        simplified_headers = [
            "Video Title", "Status", "Attempts", "Duration",
            "Source Lang", "Target Lang", "Platforms", "Timestamp"
        ]
        worksheet.append_row(simplified_headers)
        
        # Add back Row 2 data without YouTube URL and Post IDs
        if len(all_values) > 1:
            row_2_data = all_values[1]  # Current row 2
            simplified_row_2 = [
                row_2_data[0],  # Video Title
                row_2_data[1],  # Status
                row_2_data[2],  # Attempts
                row_2_data[4],  # Duration (skip YouTube URL)
                row_2_data[5],  # Source Lang
                row_2_data[6],  # Target Lang
                row_2_data[7],  # Platforms
                row_2_data[9]   # Timestamp (skip Post IDs)
            ]
            worksheet.append_row(simplified_row_2)
        
        print("✅ Removed YouTube URL and Post IDs tracking:")
        print("  - Simplified headers (no YouTube URL, no Post IDs)")
        print("  - Reduced overhead and potential delays")
        print("  - Sheet now focuses on core tracking only")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    remove_youtube_url_tracking()
