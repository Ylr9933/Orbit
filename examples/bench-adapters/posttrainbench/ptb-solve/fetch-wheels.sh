#!/bin/bash
# Download the wheels the Dockerfile installs from disk into wheels/.
#
# Run this once after cloning, before `docker build`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WHEELS="$SCRIPT_DIR/wheels"

# Mirror overrides for hosts where the defaults are slow or blocked:
#   PIP_INDEX_URL=https://pypi.org/simple ./fetch-wheels.sh
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
TORCH_MIRROR="${TORCH_MIRROR:-https://mirrors.aliyun.com/pytorch-wheels/cu130}"
TORCH_URL="${TORCH_URL:-https://download.pytorch.org/whl/cu130}"
TORCH_FILE="torch-2.13.0+cu130-cp312-cp312-manylinux_2_28_x86_64.whl"

mkdir -p "$WHEELS/vllm-deps"

echo "==> torch 2.13.0+cu130"
if [ -f "$WHEELS/$TORCH_FILE" ]; then
  echo "    already present, skipping"
else
  curl -fL -o "$WHEELS/$TORCH_FILE" "$TORCH_MIRROR/$TORCH_FILE" \
    || curl -fL -o "$WHEELS/$TORCH_FILE" "$TORCH_URL/$TORCH_FILE"
fi

echo "==> vllm and its dependencies"
pip download vllm --dest "$WHEELS/vllm-deps" --index-url "$PIP_INDEX_URL"
# pip pulls a second, non-cu130 torch for vllm's own requirement; drop it.
rm -f "$WHEELS/vllm-deps"/torch-2.13.0-cp312-*.whl

echo "==> done ($(du -sh "$WHEELS" | cut -f1))"
echo "    next: docker build -t orbit-local/ptb-solve:latest $SCRIPT_DIR"
