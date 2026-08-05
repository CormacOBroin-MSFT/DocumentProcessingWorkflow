#!/bin/bash

if [ -z "${BASH_VERSION:-}" ]; then
    exec /bin/bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/setup-analyzer.sh"

setup_analyzer "${1:-${AZURE_CONTENT_UNDERSTANDING_ENDPOINT:-}}" true