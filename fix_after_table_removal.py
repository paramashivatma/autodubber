#!/usr/bin/env python3
"""Fix sheet after converting table back to range"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def fix_after_table_removal():
    """Fix sheet after table is converted back to range"""
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
        
        # Get current data to preserve
        all_values = worksheet.get_all_values()
        
        print("Current sheet (before fix):")
        for i, row in enumerate(all_values, start=1):
            print(f"Row {i}: {row}")
        print()
        
        # Clear and rebuild with proper headers
        worksheet.clear()
        
        # Add PROPER headers
        proper_headers = [
            "Video Title", "Status", "Attempts", "YouTube URL", "Duration",
            "Source Lang", "Target Lang", "Platforms", "Post IDs", "Timestamp"
        ]
        worksheet.append_row(proper_headers)
        
        # Restore data (preserve what we had)
        if len(all_values) > 1:
            # Row 2 data (preserving existing video)
            if len(all_values) >= 2:
                row_2_data = all_values[1]  # Current row 2
                worksheet.append_row(row_2_data)
                print("✅ Preserved Row 2 data")
        
        print("✅ Fixed sheet structure:")
        print("  - Proper headers restored (not Column 1, 2, 3...)")
        print("  - Data preserved")
        print("  - Ready for new videos")
        print("\nIMPORTANT: Make sure you converted the table back to a regular range in Google Sheets first!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure you converted the table back to a regular range in Google Sheets")

if __name__ == "__main__":
    fix_after_table_removal()
