if [ "${PREFETCH_DATASET:-false}" = "true" ]; then
  uv run --no-sync python tools/prefetch_dataset.py "$CONFIG"
fi

