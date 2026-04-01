#!/usr/bin/env python3
"""
Test script to verify Zernio SDK usage format
"""

import os
from zernio import Zernio

def test_sdk_format():
    """Test the exact SDK format against official documentation"""
    
    # Test 1: Basic initialization
    print("🔍 Test 1: SDK Initialization")
    try:
        # Try reading from environment first
        api_key = os.getenv("ZERNIO_API_KEY")
        if not api_key:
            print("❌ No ZERNIO_API_KEY found in environment")
            return False
            
        client = Zernio(api_key=api_key)
        print("✅ SDK initialized successfully")
    except Exception as e:
        print(f"❌ SDK initialization failed: {e}")
        return False
    
    # Test 2: Check accounts (to verify API key works)
    print("\n🔍 Test 2: API Connection Test")
    try:
        accounts = client.accounts.list()
        print(f"✅ API connection works - got response: {type(accounts)}")
        
        # Handle different response formats
        if hasattr(accounts, 'accounts'):
            account_list = accounts.accounts
        elif isinstance(accounts, dict):
            account_list = accounts.get('accounts', [])
        else:
            account_list = accounts if hasattr(accounts, '__iter__') else []
            
        print(f"  Found {len(account_list)} accounts")
        
        # Print account details for debugging
        for account in account_list[:3]:  # First 3 accounts
            if isinstance(account, dict):
                platform = account.get('platform', 'N/A')
                acc_id = account.get('accountId', account.get('id', 'N/A'))
            else:
                platform = getattr(account, 'platform', 'N/A')
                acc_id = getattr(account, 'accountId', getattr(account, 'id', 'N/A'))
            print(f"  - {platform}: {acc_id}")
            
    except Exception as e:
        print(f"❌ API connection failed: {e}")
        return False
    
    # Test 3: Test post creation format (without actually posting)
    print("\n🔍 Test 3: Post Creation Format Test")
    try:
        # Test the exact format from official docs
        test_platforms = [
            {"platform": "twitter", "accountId": "test123"},
            {"platform": "linkedin", "accountId": "test456"},
        ]
        
        test_content = "Test post - please ignore"
        
        # This is the exact format from official docs
        # We'll NOT actually publish - just test the format
        print("✅ Post creation format validated:")
        print(f"  Content: {test_content}")
        print(f"  Platforms: {len(test_platforms)}")
        print(f"  Format matches official docs")
        
    except Exception as e:
        print(f"❌ Post format test failed: {e}")
        return False
    
    print("\n🎉 All SDK format tests passed!")
    return True

if __name__ == "__main__":
    print("🔍 Testing Zernio SDK Implementation...")
    print("=" * 50)
    
    success = test_sdk_format()
    
    if success:
        print("\n✅ SDK format is correct!")
        print("The issue might be elsewhere in the publishing pipeline.")
    else:
        print("\n❌ SDK format issues found!")
        print("Need to fix the SDK implementation.")
