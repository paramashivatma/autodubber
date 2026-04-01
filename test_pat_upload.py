#!/usr/bin/env python3
"""Test upload_large with Vercel Personal Access Token"""

import os
import sys
sys.path.append('dubber')

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from zernio import Zernio

def test_upload_large_with_pat():
    print("🧪 Testing upload_large with Vercel Personal Access Token...")
    
    try:
        client = Zernio(api_key="sk_b72389ef5c8adebb1b2f6e43496ef424d170c3fa797ae3154452eb0cd53ac213", timeout=120.0)
        print("✅ Client created")
        
        # Get VERCEL_BLOB_TOKEN from .env (should be PAT now)
        vercel_token = os.environ.get('VERCEL_BLOB_TOKEN')
        if not vercel_token:
            print("❌ VERCEL_BLOB_TOKEN not found in environment")
            return
        
        print(f"🔑 Using Vercel PAT: {vercel_token[:20]}...")
        
        # Test file
        test_file = "workspace/source.mp4"
        if os.path.exists(test_file):
            file_size = os.path.getsize(test_file)
            print(f"📁 Testing with: {test_file} ({file_size/1024/1024:.1f} MB)")
            
            try:
                uploaded = client.media.upload_large(test_file, vercel_token=vercel_token)
                print("✅ Upload succeeded!")
                print("type:", type(uploaded))
                print("repr:", uploaded)
                # If it's a list/tuple, show first element too
                if isinstance(uploaded, (list, tuple)) and uploaded:
                    print("first type:", type(uploaded[0]))
                    print("first repr:", uploaded[0])
                for obj in ([uploaded[0]] if isinstance(uploaded, (list, tuple)) and uploaded else [uploaded]):
                    for meth in ("model_dump", "dict", "json"):
                        if hasattr(obj, meth):
                            print(meth, "=>", getattr(obj, meth)())
                            break
                
                print("\n🎉 SUCCESS! Look for the HTTPS URL field above - that's what goes in media_urls=[...]")
                
            except Exception as e:
                print(f"❌ Upload failed: {e}")
                print(f"Error type: {type(e)}")
                import traceback
                traceback.print_exc()
        else:
            print(f"❌ Test file not found: {test_file}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_upload_large_with_pat()
