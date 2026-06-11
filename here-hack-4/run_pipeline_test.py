#!/usr/bin/env python3
import httpx
import json
import sys

print("🚀 Running PlaceIQ Pipeline Test")
print("=" * 60)

# 1. Check health
print("\n1️⃣  Testing backend health...")
try:
    client = httpx.Client(timeout=10)
    r = client.get('http://localhost:8080/api/health')
    print(f"   ✅ Backend health: {r.status_code}")
except Exception as e:
    print(f"   ❌ Backend health check failed: {e}")
    sys.exit(1)

# 2. Run pipeline
print("\n2️⃣  Running pipeline with 500 real Singapore places...")
print("   (This will take 3-5 minutes)...")
try:
    client = httpx.Client(timeout=600)
    r = client.post('http://localhost:8080/api/pipeline/run', json={})
    print(f"   Status code: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        records = data.get('records', [])
        print(f"   ✅ Pipeline completed successfully!")
        print(f"   📊 Total records returned: {len(records)}")
        
        # Show status breakdown
        status_counts = {}
        for record in records:
            status = record.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"\n3️⃣  Status Breakdown:")
        for status, count in sorted(status_counts.items()):
            print(f"   • {status}: {count}")
        
        # Show sample records
        print(f"\n4️⃣  Sample Records (First 5):")
        for i, record in enumerate(records[:5]):
            name = record.get('name', 'Unknown')
            status = record.get('status', '?')
            sources = record.get('source_count', 0)
            print(f"   {i+1}. {name}")
            print(f"      Status: {status} | Sources: {sources}")
            print(f"      Address: {record.get('address', 'N/A')}")
            print()
        
        # Check for closure detections
        closed = [r for r in records if r.get('status') == 'closed']
        if closed:
            print(f"🔴 Closure Detections ({len(closed)} found):")
            for record in closed[:3]:
                print(f"   • {record.get('name')} - Last active: {record.get('last_activity')}")
        
    else:
        print(f"   ❌ Pipeline failed: {r.status_code}")
        print(f"   Response: {r.text[:500]}")
        sys.exit(1)
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✨ Pipeline test completed!")
