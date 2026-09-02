#!/usr/bin/env bash
# Smoke test — runs against the live stack (docker compose up first)
# Usage: bash scripts/smoke_test.sh [BASE_URL]

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

check() {
    local desc="$1"
    local url="$2"
    local expected_status="$3"

    actual=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    if [ "$actual" = "$expected_status" ]; then
        echo "  ✓  $desc ($actual)"
        PASS=$((PASS + 1))
    else
        echo "  ✗  $desc — expected $expected_status got $actual"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "RazorGuard ACE — Smoke Tests"
echo "Target: $BASE_URL"
echo "────────────────────────────────"

check "Liveness"          "$BASE_URL/health/live"  200
check "Readiness"         "$BASE_URL/health/ready" 200
check "Metrics endpoint"  "$BASE_URL/metrics"      200
check "Docs available"    "$BASE_URL/docs"         200

echo "────────────────────────────────"
echo "  Passed: $PASS   Failed: $FAIL"
echo ""

[ $FAIL -eq 0 ] && exit 0 || exit 1
