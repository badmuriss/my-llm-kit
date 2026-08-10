#!/usr/bin/env bash

set -u

if [[ -n "${SCRAPINGDOG_API_KEY:-}" ]]; then
  printf '%s\n' current
  exit 0
fi

if command -v bash >/dev/null 2>&1 \
  && bash -ic '[[ -n "${SCRAPINGDOG_API_KEY:-}" ]]' >/dev/null 2>&1; then
  printf '%s\n' interactive
  exit 0
fi

printf '%s\n' missing
exit 1
