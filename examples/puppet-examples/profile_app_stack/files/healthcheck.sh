#!/bin/bash
# Application health check script
# Managed by Puppet — do not edit manually

set -euo pipefail

URL="${1:-http://localhost:8000/health}"
TIMEOUT=5
LOG="/var/log/myapp-api/healthcheck.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "${LOG}" 2>/dev/null || true
}

# Push metrics mode
if [[ "${1:-}" == "--push-metrics" ]]; then
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}:%{time_total}" --max-time "${TIMEOUT}" "${URL}" 2>/dev/null || echo "000:0")
    HTTP_CODE="${RESPONSE%%:*}"
    RESPONSE_TIME="${RESPONSE##*:}"

    cat <<METRICS | curl -s --max-time 5 --data-binary @- http://localhost:9091/metrics/job/app_health 2>/dev/null || true
app_health_status ${HTTP_CODE}
app_response_time_seconds ${RESPONSE_TIME}
METRICS
    exit 0
fi

# Standard health check
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time "${TIMEOUT}" "${URL}" 2>/dev/null || echo "000")

if [[ "${HTTP_CODE}" == "200" ]]; then
    log "OK: ${URL} returned ${HTTP_CODE}"
    exit 0
else
    log "FAIL: ${URL} returned ${HTTP_CODE}"
    exit 1
fi
