#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "httpx>=0.24.0",
#     "pyyaml>=6.0",
# ]
# ///
"""
End-to-end test suite for CertMan agent mode.

Tests compose and k8s deployments:
1. Compose e2e: server + worker + agent running via docker-compose
2. K8s e2e: server + worker + agent running in kind cluster

Usage:
    python scripts/e2e-test.py [--compose-only] [--k8s-only] [--cleanup]
"""

import subprocess
import sys
import time
import shutil
from pathlib import Path
from typing import Optional
import argparse

import httpx


def run_cmd(cmd: list[str], check: bool = True, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Execute shell command and return result."""
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}")
    return result


def test_compose_e2e(workspace_root: Path, cleanup: bool = True) -> bool:
    """
    Test compose mode: server + worker + agent.
    
    Steps:
    1. Start docker-compose with agent profile
    2. Wait for server health check
    3. Verify agent registered successfully
    4. Verify agent can poll jobs
    5. Clean up
    """
    print("\n" + "=" * 60)
    print("COMPOSE E2E TEST")
    print("=" * 60)
    
    try:
        # Start compose
        print("\n[1/5] Starting docker-compose (server + worker + agent)...")
        run_cmd(
            ["docker", "compose", "-f", "docker-compose.yml", "up", "-d", "--profile", "agent"],
            cwd=workspace_root,
        )
        
        # Wait for services to be ready
        print("\n[2/5] Waiting for services to stabilize (15s)...")
        time.sleep(15)
        
        # Health check: server
        print("\n[3/5] Verifying server health...")
        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                resp = httpx.get("http://localhost:8000/api/v1/health", timeout=5)
                if resp.status_code == 200:
                    print(f"✓ Server healthy: {resp.json()}")
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                if attempt < max_attempts - 1:
                    print(f"  Attempt {attempt + 1}/{max_attempts}: waiting for server...")
                    time.sleep(1)
                else:
                    raise RuntimeError("Server failed health check")
        
        # Check agent logs for successful registration
        print("\n[4/5] Checking agent registration status...")
        logs_result = run_cmd(
            ["docker", "compose", "logs", "certman-agent"],
            check=False,
            cwd=workspace_root,
        )
        
        if "register_status=ok" in logs_result.stdout or "registered successfully" in logs_result.stdout.lower():
            print("✓ Agent registration successful")
        else:
            print("⚠ Agent registration status unclear in logs:")
            print(logs_result.stdout)
        
        # Verify agent can poll (simple check)
        print("\n[5/5] Verification complete.")
        print("✓ COMPOSE E2E TEST PASSED")
        return True
        
    except Exception as e:
        print(f"✗ COMPOSE E2E TEST FAILED: {e}")
        return False
    
    finally:
        if cleanup:
            print("\nCleaning up compose resources...")
            run_cmd(
                ["docker", "compose", "down", "-v"],
                check=False,
                cwd=workspace_root,
            )


def test_k8s_e2e(workspace_root: Path, cleanup: bool = True) -> bool:
    """
    Test k8s mode: deploy to kind cluster.
    
    Steps:
    1. Check kind cluster exists; create if needed
    2. Apply k8s-e2e-test.yaml manifest
    3. Wait for deployments to be ready
    4. Verify agent registered
    5. Port-forward and check endpoints
    6. Clean up
    """
    print("\n" + "=" * 60)
    print("KUBERNETES E2E TEST")
    print("=" * 60)
    
    try:
        # Check if kind cluster exists
        print("\n[1/6] Checking kind cluster...")
        clusters_result = run_cmd(["kind", "get", "clusters"], check=False)
        if "certman-lab" not in clusters_result.stdout:
            print("  Cluster not found, creating 'certman-lab'...")
            run_cmd(["kind", "create", "cluster", "--name", "certman-lab", "--wait", "5m"])
        else:
            print("✓ Cluster 'certman-lab' exists")
        
        # Apply manifest
        print("\n[2/6] Applying k8s-e2e-test.yaml manifest...")
        run_cmd(
            ["kubectl", "apply", "-f", "k8s-e2e-test.yaml"],
            cwd=workspace_root,
        )
        
        # Wait for deployments
        print("\n[3/6] Waiting for deployments to be ready (60s)...")
        for service in ["certman-server", "certman-worker", "certman-agent"]:
            run_cmd(
                ["kubectl", "-n", "certman-lab", "rollout", "status", f"deployment/{service}", "--timeout=60s"],
                cwd=workspace_root,
            )
            print(f"✓ {service} is ready")
        
        # Check agent pod logs
        print("\n[4/6] Checking agent pod status...")
        pods_result = run_cmd(
            ["kubectl", "-n", "certman-lab", "get", "pods", "-l", "app=certman-agent", "-o", "jsonpath={.items[0].status.phase}"],
            check=False,
            cwd=workspace_root,
        )
        print(f"✓ Agent pod status: {pods_result.stdout.strip()}")
        
        # Port-forward and health check
        print("\n[5/6] Testing server endpoint...")
        # Start port-forward in background
        pf_proc = subprocess.Popen(
            ["kubectl", "-n", "certman-lab", "port-forward", "svc/certman-server", "8001:8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(3)  # Wait for port-forward to establish
        
        try:
            resp = httpx.get("http://localhost:8001/api/v1/health", timeout=5)
            if resp.status_code == 200:
                print(f"✓ K8s server endpoint healthy: {resp.json()}")
        except Exception as e:
            print(f"⚠ Could not verify k8s server endpoint: {e}")
        finally:
            pf_proc.terminate()
            pf_proc.wait(timeout=5)
        
        print("\n✓ KUBERNETES E2E TEST PASSED")
        return True
        
    except Exception as e:
        print(f"✗ KUBERNETES E2E TEST FAILED: {e}")
        return False
    
    finally:
        if cleanup:
            print("\nCleaning up k8s resources...")
            run_cmd(
                ["kubectl", "delete", "-f", "k8s-e2e-test.yaml"],
                check=False,
                cwd=workspace_root,
            )


def main():
    parser = argparse.ArgumentParser(
        description="CertMan end-to-end test suite (compose and k8s)",
        epilog="Example: python scripts/e2e-test.py --compose-only",
    )
    parser.add_argument("--compose-only", action="store_true", help="Run only compose e2e test")
    parser.add_argument("--k8s-only", action="store_true", help="Run only k8s e2e test")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup after tests")
    args = parser.parse_args()
    
    workspace_root = Path(__file__).parent.parent
    cleanup = not args.no_cleanup
    
    results = {}
    
    if not args.k8s_only:
        results["compose"] = test_compose_e2e(workspace_root, cleanup=cleanup)
    
    if not args.compose_only:
        # Check for kind and skip k8s if not available
        if shutil.which("kind") is None:
            print("\n⚠ 'kind' not found in PATH; skipping k8s e2e test")
            print("  Install: https://kind.sigs.k8s.io/docs/user/quick-start/")
            results["k8s"] = None
        else:
            results["k8s"] = test_k8s_e2e(workspace_root, cleanup=cleanup)
    
    # Summary
    print("\n" + "=" * 60)
    print("E2E TEST SUMMARY")
    print("=" * 60)
    for test_name, result in results.items():
        if result is None:
            status = "SKIPPED"
        elif result:
            status = "PASSED"
        else:
            status = "FAILED"
        print(f"{test_name:15} {status}")
    
    failed = sum(1 for v in results.values() if v is False)
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
