#!/bin/bash
# Redis health check and sentinel notification script
# Managed by Puppet — do not edit manually

set -euo pipefail

REDIS_CLI="/usr/bin/redis-cli"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
LOG_FILE="/var/log/redis/health-check.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "${LOG_FILE}"
}

check_redis() {
    local auth_args=""
    if [[ -n "${REDIS_PASSWORD}" ]]; then
        auth_args="-a ${REDIS_PASSWORD} --no-auth-warning"
    fi

    if ${REDIS_CLI} -p "${REDIS_PORT}" ${auth_args} ping | grep -q PONG; then
        log "INFO: Redis is responding on port ${REDIS_PORT}"
        return 0
    else
        log "ERROR: Redis is not responding on port ${REDIS_PORT}"
        return 1
    fi
}

# Sentinel notification handler
if [[ "${1:-}" == "sentinel" ]]; then
    event_type="${2:-unknown}"
    log "SENTINEL EVENT: ${event_type} — ${*}"
    exit 0
fi

check_redis
