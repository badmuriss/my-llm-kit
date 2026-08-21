#!/usr/bin/env bash
# Print ScrapingDog credit usage without exposing account secrets.
# Output: "used/limit remaining=N concurrency=M pack=P".
# SCRAPINGDOG_ACCOUNT_FIXTURE=<json path> parses that file instead of calling /account.
# Exit 2 when the key is missing (and no fixture is given), 3 when the response cannot be parsed.

set -u

fixture="${SCRAPINGDOG_ACCOUNT_FIXTURE:-}"
if [[ -n "$fixture" ]]; then
  payload="$(cat "$fixture")" || exit 3
else
  if [[ -z "${SCRAPINGDOG_API_KEY:-}" ]]; then
    echo "SCRAPINGDOG_API_KEY missing" >&2
    exit 2
  fi
  payload="$(curl -sS --max-time 30 -G "https://api.scrapingdog.com/account" \
    --data-urlencode "api_key=${SCRAPINGDOG_API_KEY}")" || exit 3
fi

ACCOUNT_PAYLOAD="$payload" python3 - <<'PY'
import json
import os
import sys

try:
    data = json.loads(os.environ["ACCOUNT_PAYLOAD"])
except ValueError as exc:
    print(f"unparseable /account response: {exc}", file=sys.stderr)
    sys.exit(3)


def pick(*names, default=None):
    for name in names:
        if name in data and data[name] not in (None, ""):
            return data[name]
    return default


used = int(pick("requestUsed", "request_used", default=0))
limit = int(pick("requestLimit", "request_limit", default=0))
concurrency = pick("concurrencyLimit", "concurrency_limit", "concurrency", default="?")
pack = pick("pack", "plan", default="?")
print(f"{used}/{limit} remaining={limit - used} concurrency={concurrency} pack={pack}")
PY
