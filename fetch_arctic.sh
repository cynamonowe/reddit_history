#!/usr/bin/env bash
# Paginate a full author history out of the Arctic Shift API.
# Usage: ./fetch_arctic.sh <kind: posts|comments> <author> <outfile.jsonl>
set -euo pipefail

KIND="$1"
AUTHOR="$2"
OUT="$3"

API="https://arctic-shift.photon-reddit.com/api/${KIND}/search"
: > "$OUT"

after=1100000000
page=0
while :; do
  page=$((page + 1))
  body=$(curl -s --max-time 90 --retry 3 --retry-delay 5 \
    "${API}?author=${AUTHOR}&limit=100&sort=asc&after=${after}")

  # Bail out loudly if the API returned an error object instead of data.
  if ! echo "$body" | jq -e '.data | type == "array"' >/dev/null 2>&1; then
    echo "ERROR on page ${page}: $(echo "$body" | head -c 300)" >&2
    exit 1
  fi

  n=$(echo "$body" | jq '.data | length')
  echo "  ${KIND} page ${page}: ${n} rows (after=${after})" >&2
  [ "$n" -eq 0 ] && break

  echo "$body" | jq -c '.data[]' >> "$OUT"

  last=$(echo "$body" | jq '[.data[].created_utc] | max')
  # created_utc is inclusive on `after`, so step forward one second to avoid a loop.
  if [ "$last" -le "$after" ]; then break; fi
  after=$((last))

  [ "$n" -lt 100 ] && break
  sleep 1
done

echo "  ${KIND} total: $(wc -l < "$OUT") rows" >&2
