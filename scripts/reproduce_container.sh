#!/usr/bin/env bash
set -euo pipefail

docker compose build
docker compose run --rm runtime-test
docker compose run --rm benchmark

if [[ "${AFFORDANCE_WOT_PROOF:-0}" == "1" ]]; then
  docker compose --profile wot-proof build
  docker compose --profile wot-proof run --rm wot-conformance
fi
