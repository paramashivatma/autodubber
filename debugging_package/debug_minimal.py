#!/usr/bin/env python3
"""
Minimal debugging script - copy this with the core files
"""

import os
import sys

# Add the dubber directory to path
sys.path.append('dubber')

from zernio import Zernio
from dubber.utils import log

def test_publishing_step_by_step():
    """Test each step of publishing individually"""
    
    print("🧪 STEP 1: Test SDK Initialization")
    try:
        api_key = "sk_b72389ef5c8adebb1b2f6e43496ef424d170c3fa797ae3154452eb0cd53ac213"
        client = Zernio(api_key=api_key)
        print("✅ SDK initialization successful")
    except Exception as e:
        print(f"❌ SDK init failed: {e}")
        return
    
    print("\n🧪 STEP 2: Test Upload Token Generation")
    try:
        token_response = client.media.generate_upload_token()
        print(f"✅ Upload token: {token_response.uploadUrl}")
    except Exception as e:
        print(f"❌ Upload token failed: {e}")
    
    print("\n🧪 STEP 3: Test File Upload")
    test_file = "workspace/output.mp4"
    if os.path.exists(test_file):
        try:
            # This will likely fail due to size, but shows the process
            result = client.media.upload(test_file)
            print(f"✅ Upload result: {result}")
        except Exception as e:
            print(f"⚠️ Upload failed (expected for large files): {e}")
    else:
        print(f"❌ Test file not found: {test_file}")
    
    print("\n🧪 STEP 4: Test Post Creation")
    try:
        # Test with minimal data
        result = client.posts.create(
            content="Test post",
            platforms=[],
            publish_now=False
        )
        print(f"✅ Post creation: {result}")
    except Exception as e:
        print(f"❌ Post creation failed: {e}")

if __name__ == "__main__":
    test_publishing_step_by_step()
