#!/usr/bin/env python3
"""
Minimal test to debug publishing stalling
"""

import os
from zernio import Zernio
from dubber.utils import PLATFORM_ACCOUNTS

def test_minimal_publish():
    """Test minimal publishing to find the stall"""
    
    # Initialize SDK
    api_key = os.getenv("ZERNIO_API_KEY")
    if not api_key:
        print("❌ No ZERNIO_API_KEY found")
        return
        
    client = Zernio(api_key=api_key)
    print("✅ SDK initialized")
    
    # Test 1: Check if we can get accounts
    try:
        accounts = client.accounts.list()
        print(f"✅ Got accounts: {type(accounts)}")
        
        # Check account IDs
        for platform, account_id in PLATFORM_ACCOUNTS.items():
            print(f"  {platform}: {account_id}")
            
    except Exception as e:
        print(f"❌ Account list failed: {e}")
        return
    
    # Test 2: Try minimal post creation (without actually posting)
    try:
        print("🧪 Testing minimal post creation...")
        
        # Use the exact format from official docs
        test_platforms = [
            {"platform": "twitter", "accountId": PLATFORM_ACCOUNTS["twitter"]}
        ]
        
        print(f"  Platforms: {test_platforms}")
        print(f"  Content: 'Test post - please ignore'")
        print(f"  Publish now: True")
        
        # This should work according to docs
        post = client.posts.create(
            content="Test post - please ignore",
            platforms=test_platforms,
            publish_now=True
        )
        
        print(f"✅ Post created: {type(post)}")
        print(f"  Post data: {post}")
        
        # Try to access platforms like the docs show
        if isinstance(post, dict):
            platforms = post.get('post', {}).get('platforms', [])
        elif hasattr(post, 'post'):
            post_obj = post.post
            if hasattr(post_obj, 'platforms'):
                platforms = post_obj.platforms
            else:
                platforms = []
        else:
            platforms = []
            
        print(f"  Published platforms: {len(platforms)}")
        
    except Exception as e:
        print(f"❌ Post creation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_minimal_publish()
