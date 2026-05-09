#!/usr/bin/env bash
# Fails fast with a clear hint when Docker Desktop’s containerd overlay store is broken
# (“failed to stat parent … overlayfs/snapshots/…”). Compose changes cannot fix that.

set -euo pipefail

echo "Checking whether Docker can create and run a container…"
if err=$(docker run --rm alpine:3.19 echo ok 2>&1); then
  echo "OK — Docker daemon can run containers."
  exit 0
fi

echo "FAILED:"
echo "$err"
echo ""
if echo "$err" | grep -qE 'overlayfs/snapshots|failed to stat parent'; then
  echo "Diagnosis: corrupted Docker Desktop disk / containerd snapshots."
  echo "Fix (pick one):"
  echo "  1. Docker Desktop → Settings → Troubleshoot → Clean/Purge data or Reset to factory defaults."
  echo "  2. Use another engine: OrbStack (orbstack.dev) — then run: docker compose up -d --build"
fi
exit 1
