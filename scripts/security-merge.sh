#!/bin/bash
#
# Security Merge Shell Wrapper
# Quick interface to the Python merge preparation script
#
# Usage:
#   ./scripts/security-merge.sh [--dry-run] [--phase N] [--plan] [--verify]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Colors
RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
CYAN='\033[96m'
RESET='\033[0m'

echo -e "${CYAN}================================${RESET}"
echo -e "${CYAN}Security Merge Preparation${RESET}"
echo -e "${CYAN}================================${RESET}"
echo ""

# Parse arguments
DRY_RUN=""
PHASE=""
ACTION=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run|-n)
            DRY_RUN="--dry-run"
            shift
            ;;
        --phase|-p)
            PHASE="--phase $2"
            shift 2
            ;;
        --plan)
            ACTION="--plan"
            shift
            ;;
        --verify|-v)
            ACTION="--verify-ssrf"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run, -n      Show what would be done without making changes"
            echo "  --phase N, -p N    Run only phase N"
            echo "  --plan             Generate and print the merge plan"
            echo "  --verify, -v       Verify SSRF protection is working"
            echo "  --help, -h         Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${RESET}"
            exit 1
            ;;
    esac
done

# Run the Python script
python3 scripts/security_merge_prep.py $DRY_RUN $PHASE $ACTION
