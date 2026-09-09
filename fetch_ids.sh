#!/usr/bin/env bash
# Batch-resolve fullnames (t1_xxx / t3_xxx) to full objects via Arctic Shift.
# Usage: ./fetch_ids.sh <kind: posts|comments> <ids-file: one bare id per line> <outfile.jsonl>
set -euo pipefail

KIND="$1"
IDS_FILE="$2"
OUT="$3"
BATCH=100

API="https://arctic-shift.photon-reddit.com/api/${KIND}/ids"
: > "$OUT"

total=$(wc -l < "$IDS_FILE")
n=0
while read -r -a chunk; do
  ids=$(printf '%s,' "${chunk[@]}"); ids="${ids%,}"
  body=$(curl -s --max-time 90 --retry 3 --retry-delay 5 --get \
    --data-urlencode "ids=${ids}" "$API")

  if ! echo "$body" | jq -e '.data | type == "array"' >/dev/null 2>&1; then
    echo "ERROR: $(echo "$body" | head -c 300)" >&2
    exit 1
  fi

  echo "$body" | jq -c '.data[]' >> "$OUT"
  n=$((n + ${#chunk[@]}))
  echo "  ${KIND}/ids: ${n}/${total} requested, $(wc -l < "$OUT") resolved" >&2
  sleep 1
done < <(xargs -n "$BATCH" < "$IDS_FILE")
