#!/usr/bin/env python3
"""
Test all 7 platforms to verify the fix works for each one
"""

import os
from zernio import Zernio
from dubber.utils import PLATFORM_ACCOUNTS, PLATFORMS

def test_all_platforms():
    """Test publishing to all 7 platforms individually"""
    
    # Initialize SDK
    api_key = os.getenv("ZERNIO_API_KEY")
    if not api_key:
        print("❌ No ZERNIO_API_KEY found")
        return
        
    client = Zernio(api_key=api_key)
    print("✅ SDK initialized")
    
    # Test each platform individually
    for platform in PLATFORMS:
        account_id = PLATFORM_ACCOUNTS.get(platform)
        if not account_id:
            print(f"❌ {platform}: No account ID")
            continue
            
        print(f"\n🧪 Testing {platform}...")
        print(f"  Account ID: {account_id}")
        
        try:
            # Create platform-specific test
            test_platforms = [{"platform": platform, "accountId": account_id}]
            
            # Add platform-specific content if needed
            content = f"Test post for {platform} - please ignore"
            
            # Create the post
            post = client.posts.create(
                content=content,
                platforms=test_platforms,
                publish_now=True
            )
            
            print(f"  ✅ Post created: {type(post)}")
            
            # Parse response like our fixed code does
            if hasattr(post, 'post'):
                post_obj = post.post
                if hasattr(post_obj, 'platforms'):
                    published_platforms = post_obj.platforms
                    print(f"  📊 Platforms in response: {len(published_platforms)}")
                    
                    # Parse each platform result
                    for platform_info in published_platforms:
                        if hasattr(platform_info, 'platform'):
                            platform_name = platform_info.platform
                            post_id = getattr(platform_info, 'platformPostId', 'unknown')
                            status = getattr(platform_info, 'status', 'unknown')
                            
                            success = status == 'published' or (post_id and post_id != "unknown")
                            
                            print(f"  ✅ {platform_name}: {'SUCCESS' if success else 'FAILED'}")
                            print(f"     Post ID: {post_id}")
                            print(f"     Status: {status}")
                        else:
                            print(f"  ❌ Unknown platform info format: {type(platform_info)}")
                else:
                    print(f"  ❌ No platforms attribute on post object")
            else:
                print(f"  ❌ No post attribute on response")
                
        except Exception as e:
            print(f"  ❌ {platform} failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    print("🔍 Testing all 7 platforms...")
    print("=" * 50)
    test_all_platforms()
