#!/usr/bin/env python3
"""Check current Google Sheet content"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dubber.sheet_logger import _get_sheet_client

def check_sheet():
    client = _get_sheet_client()
    if not client:
        print("Failed to connect to Google Sheets")
        return
    
    worksheet = client.worksheet("AutoDubQueue")
    all_values = worksheet.get_all_values()
    
    print("Current Google Sheet content:")
    print("=" * 80)
    
    for i, row in enumerate(all_values, start=1):
        print(f"Row {i}: {row}")
    
    print("=" * 80)
    print(f"Total rows: {len(all_values)}")

if __name__ == "__main__":
    check_sheet()
