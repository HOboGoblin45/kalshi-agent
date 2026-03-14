#!/usr/bin/env bash
# validate.sh — Pre-deploy validation for the Kalshi AI Trading Agent
# Run this before deploying to ensure everything works.
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $desc"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}✗${NC} $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "═══════════════════════════════════════"
echo "  Kalshi Agent Validation"
echo "═══════════════════════════════════════"
echo ""

# ── 1. Module compilation ──
echo "Module compilation:"
for mod in modules/*.py; do
    check "$mod compiles" python3 -c "import py_compile; py_compile.compile('$mod', doraise=True)"
done
check "kalshi-agent.py compiles" python3 -c "import py_compile; py_compile.compile('kalshi-agent.py', doraise=True)"

# ── 2. Tests ──
echo ""
echo "Test suite:"
check "All tests pass" python3 -m pytest tests/ -q --tb=no

# ── 3. Critical imports ──
echo ""
echo "Module imports:"
check "modules.config" python3 -c "from modules.config import CFG, load_config"
check "modules.scoring" python3 -c "from modules.scoring import kelly, dynamic_min_edge"
check "modules.backtester" python3 -c "from modules.backtester import run_backtest, format_report"
check "modules.forward_backtest" python3 -c "from modules.forward_backtest import run_forward_backtest"
check "modules.arbitrage" python3 -c "from modules.arbitrage import find_quickflip_candidates, get_bankroll_tier"
check "modules.dashboard" python3 -c "from modules.dashboard import DashHandler"

# ── 4. Scoring sanity checks ──
echo ""
echo "Scoring sanity:"
check "dynamic_min_edge(50) > 20%" python3 -c "
from modules.scoring import dynamic_min_edge
assert dynamic_min_edge(50) > 20, f'Got {dynamic_min_edge(50)}'
"
check "dynamic_min_edge(10) > 100%" python3 -c "
from modules.scoring import dynamic_min_edge
assert dynamic_min_edge(10) > 100, f'Got {dynamic_min_edge(10)}'
"
check "kelly returns (int, float)" python3 -c "
from modules.scoring import kelly
c, cost = kelly(70, 50, 100, 10, 0.07)
assert isinstance(c, int) and isinstance(cost, float), f'Got {type(c)}, {type(cost)}'
"

# ── 5. Data files ──
echo ""
echo "Data files:"
if [ -f "kalshi-trades.json" ]; then
    check "kalshi-trades.json valid JSON" python3 -c "import json; json.load(open('kalshi-trades.json'))"
else
    echo -e "  ${YELLOW}⊘${NC} kalshi-trades.json not found (OK for fresh install)"
fi
if [ -f "kalshi-calibration.json" ]; then
    check "kalshi-calibration.json valid JSON" python3 -c "import json; json.load(open('kalshi-calibration.json'))"
else
    echo -e "  ${YELLOW}⊘${NC} kalshi-calibration.json not found (OK for fresh install)"
fi

# ── Summary ──
echo ""
echo "═══════════════════════════════════════"
TOTAL=$((PASS + FAIL))
if [ "$FAIL" -eq 0 ]; then
    echo -e "  ${GREEN}All $PASS checks passed${NC}"
else
    echo -e "  ${RED}$FAIL/$TOTAL checks failed${NC}"
fi
echo "═══════════════════════════════════════"
exit "$FAIL"
