#!/bin/bash
#
# Verification script for T1.2: AutoDev Integration
# Checks all key integration points
#

echo "=========================================="
echo "T1.2 Integration Verification"
echo "=========================================="
echo ""

PASS=0
FAIL=0

# Function to check and report
check() {
    local description="$1"
    local command="$2"

    echo -n "Checking: $description ... "

    if eval "$command" > /dev/null 2>&1; then
        echo "✓ PASS"
        PASS=$((PASS + 1))
    else
        echo "✗ FAIL"
        FAIL=$((FAIL + 1))
    fi
}

# 1. Check files exist
echo "1. File Existence Checks"
echo "------------------------"
check "autodev_bridge.py exists" "test -f ~/Projects/hermes-agent/tools/autodev_bridge.py"
check "delegate_tool.py exists" "test -f ~/Projects/hermes-agent/tools/delegate_tool.py"
check "test_autodev_bridge.py exists" "test -f ~/Projects/hermes-agent/tools/test_autodev_bridge.py"
check "AUTODEV_INTEGRATION.md exists" "test -f ~/Projects/hermes-agent/tools/AUTODEV_INTEGRATION.md"
echo ""

# 2. Check Python syntax
echo "2. Syntax Validation"
echo "--------------------"
check "autodev_bridge.py syntax" "python3 -m py_compile ~/Projects/hermes-agent/tools/autodev_bridge.py"
check "delegate_tool.py syntax" "python3 -m py_compile ~/Projects/hermes-agent/tools/delegate_tool.py"
echo ""

# 3. Check key content in autodev_bridge.py
echo "3. AutoDev Bridge Content"
echo "-------------------------"
check "ROLE_MAPPING defined" "grep -q 'ROLE_MAPPING = {' ~/Projects/hermes-agent/tools/autodev_bridge.py"
check "Manager→plan mapping" "grep -q 'manager.*plan' ~/Projects/hermes-agent/tools/autodev_bridge.py"
check "Coder→implement mapping" "grep -q 'coder.*implement' ~/Projects/hermes-agent/tools/autodev_bridge.py"
check "Reviewer→review mapping" "grep -q 'reviewer.*review' ~/Projects/hermes-agent/tools/autodev_bridge.py"
check "HermesAutoDevBridge class" "grep -q 'class HermesAutoDevBridge' ~/Projects/hermes-agent/tools/autodev_bridge.py"
check "_HermesManagerWrapper class" "grep -q 'class _HermesManagerWrapper' ~/Projects/hermes-agent/tools/autodev_bridge.py"
check "_HermesCoderWrapper class" "grep -q 'class _HermesCoderWrapper' ~/Projects/hermes-agent/tools/autodev_bridge.py"
check "_HermesReviewerWrapper class" "grep -q 'class _HermesReviewerWrapper' ~/Projects/hermes-agent/tools/autodev_bridge.py"
echo ""

# 4. Check key content in delegate_tool.py
echo "4. Delegate Tool Content"
echo "------------------------"
check "task_type parameter" "grep -q 'task_type: Optional\[str\]' ~/Projects/hermes-agent/tools/delegate_tool.py"
check "_handle_autodev_delegation function" "grep -q 'def _handle_autodev_delegation' ~/Projects/hermes-agent/tools/delegate_tool.py"
check "autodev in schema" "grep -q '\"autodev\"' ~/Projects/hermes-agent/tools/delegate_tool.py"
check "task_type in schema" "grep -q '\"task_type\"' ~/Projects/hermes-agent/tools/delegate_tool.py"
check "autodev check in delegate_task" "grep -q 'if task_type == \"autodev\"' ~/Projects/hermes-agent/tools/delegate_tool.py"
check "asyncio import" "grep -q 'import asyncio' ~/Projects/hermes-agent/tools/delegate_tool.py"
echo ""

# 5. Check documentation
echo "5. Documentation"
echo "----------------"
check "Integration guide exists" "test -f ~/Projects/hermes-agent/tools/AUTODEV_INTEGRATION.md"
check "Quick reference exists" "test -f ~/Projects/hermes-agent/tools/AUTODEV_QUICKREF.md"
check "Examples exist" "test -f ~/Projects/hermes-agent/tools/example_autodev_usage.py"
check "Completion summary exists" "test -f ~/Projects/hermes-agent/T1.2_COMPLETION_SUMMARY.md"
echo ""

# Summary
echo "=========================================="
echo "Verification Summary"
echo "=========================================="
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo ""

if [ $FAIL -eq 0 ]; then
    echo "✓ All checks passed!"
    echo ""
    echo "Integration is complete and ready to use."
    echo ""
    echo "Quick start:"
    echo "  delegate_task(goal='...', task_type='autodev', parent_agent=agent)"
    echo ""
    exit 0
else
    echo "✗ Some checks failed"
    echo ""
    echo "Please review the failures above."
    exit 1
fi
