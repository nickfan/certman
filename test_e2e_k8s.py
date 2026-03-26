#!/usr/bin/env python3
import httpx
import json
import time
import sys

base_url = "http://localhost:8000"

print("=== K8s E2E Test ===\n")

try:
    # Health check
    r = httpx.get(f"{base_url}/health", timeout=10)
    print(f"[1] Health check: {r.status_code}")
    
    # Submit job
    r = httpx.post(f"{base_url}/api/v1/certificates", 
                   json={"entry_name": "site-a"},
                   timeout=10)
    print(f"[2] Submit job (site-a): {r.status_code}")
    
    job_data = r.json()
    if "data" not in job_data or "job_id" not in job_data["data"]:
        print(f"    Error: {json.dumps(job_data, indent=2)}")
        sys.exit(1)
    
    job_id = job_data["data"]["job_id"]
    print(f"    Job ID: {job_id}")
    
    # Wait for worker
    print("[3] Waiting 5s for worker to process...")
    time.sleep(5)
    
    # Query job status
    r = httpx.get(f"{base_url}/api/v1/jobs/{job_id}", timeout=10)
    print(f"[4] Query job status: {r.status_code}")
    
    job_status = r.json()
    if "data" in job_status:
        data = job_status["data"]
        print(f"    Status: {data.get('status')}")
        print(f"    Type: {data.get('job_type')}")
        print(f"    Subject: {data.get('subject_id')}")
    else:
        print(f"    Error: {json.dumps(job_status, indent=2)}")
    
    print("\n[✓] Test complete!")
    
except Exception as e:
    print(f"[✗] Error: {e}")
    sys.exit(1)
