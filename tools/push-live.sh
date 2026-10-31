#!/usr/bin/env bash
# Retry only transient publication failures; reuse the already generated commit.
set -euo pipefail
remote=${1:?Usage: push-live.sh remote-name}
push_log=$(mktemp)
trap 'rm -f "$push_log"' EXIT

for attempt in 1 2 3; do
  if git push -q -f "$remote" HEAD:refs/heads/live-data >"$push_log" 2>&1; then
    cat "$push_log"
    echo "live-data branch published (attempt $attempt)"
    exit 0
  else
    status=$?
  fi
  cat "$push_log"
  # Authentication, branch policy and other permanent errors must remain failures.
  if [ "$attempt" -eq 3 ] || ! grep -Eqi \
    'Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout|HTTP 5[0-9]{2}|error: 5[0-9]{2}|timed out|Connection reset|Could not resolve host|Failed to connect' "$push_log"; then
    echo "::error::live-data publication failed after $attempt attempt(s)."
    exit "$status"
  fi
  delay=$((attempt * 10))
  echo "::warning::Temporary publication failure; retrying in ${delay}s ($attempt/3)."
  sleep "$delay"
done
