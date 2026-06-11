#!/usr/bin/env python3
"""
Quick test to verify Instagram API token is working
"""
import httpx
import json

# Credentials from .env
INSTAGRAM_APP_ID = "985157090619372"
INSTAGRAM_APP_SECRET = "3440120953cd22a28837126b81d777fb"
INSTAGRAM_CLIENT_TOKEN = "24b78b4102277cbc8ead2cd30dd92c0f"

INSTAGRAM_GRAPH_API = "https://graph.instagram.com/v18.0"

async def test_instagram_token():
    """Test if Instagram API token is valid"""
    async with httpx.AsyncClient() as client:
        # Test 1: Get app info (basic test)
        print("🧪 Testing Instagram API Token...")
        print(f"App ID: {INSTAGRAM_APP_ID}")
        print(f"Token: {INSTAGRAM_CLIENT_TOKEN[:20]}...")
        
        try:
            # Test endpoint - get app info
            url = f"{INSTAGRAM_GRAPH_API}/{INSTAGRAM_APP_ID}"
            params = {"access_token": INSTAGRAM_CLIENT_TOKEN}
            
            print(f"\n📡 Calling: {url}")
            resp = await client.get(url, params=params, timeout=10)
            
            print(f"Status Code: {resp.status_code}")
            print(f"Response: {resp.text[:200]}")
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"\n✅ SUCCESS! Instagram API is working!")
                print(f"App Name: {data.get('name', 'N/A')}")
                return True
            else:
                print(f"\n❌ API Error: {resp.status_code}")
                print(f"Details: {resp.text}")
                return False
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
            return False

if __name__ == "__main__":
    import asyncio
    result = asyncio.run(test_instagram_token())
    if result:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Tests failed - check credentials")
