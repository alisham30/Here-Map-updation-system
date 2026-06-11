#!/usr/bin/env python3
"""Test PlaceIQ System with real data"""
import httpx
import json

print("📊 Testing PlaceIQ Singapore System")
print("=" * 60)

try:
    # Check health
    r = httpx.get('http://localhost:8080/api/health', timeout=5)
    print(f"✅ Backend Health: {r.status_code}")
    
    # Try pipeline
    print("\n🚀 Running pipeline with 500 real Singapore places...")
    print("   Processing with 10 agents (ACRA, STB, data.gov.sg, TripAdvisor, etc.)")
    print("   Estimated time: 3-5 minutes...")
    
    r = httpx.post('http://localhost:8080/pipeline/run', timeout=360)
    
    if r.status_code == 200:
        data = r.json()
        print(f"\n✅ Pipeline completed!")
        print(f"   Total results: {len(data) if isinstance(data, list) else 'N/A'}")
        
        if isinstance(data, list) and len(data) > 0:
            print(f"\n📍 Sample Results:")
            for i, place in enumerate(data[:3]):
                print(f"\n   [{i+1}] {place.get('name', 'Unknown')}")
                print(f"       Status: {place.get('status', 'N/A')}")
                print(f"       Confidence: {place.get('confidence_score', 'N/A')}")
                print(f"       Category: {place.get('category', 'N/A')}")
        else:
            print(f"   Response: {str(data)[:300]}")
    else:
        print(f"❌ Pipeline failed: {r.status_code}")
        print(f"   Response: {r.text[:500]}")
        
except httpx.ConnectError:
    print("❌ Cannot connect to backend")
    print("   Make sure backend is running on port 8080")
except Exception as e:
    print(f"❌ Error: {e}")
