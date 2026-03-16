#!/usr/bin/env bash
# Reinstall krate globally from the current working copy.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
pip install --force-reinstall -e "$REPO"
echo "krate installed from $REPO ($(krate --version 2>/dev/null || echo 'version unknown'))"
