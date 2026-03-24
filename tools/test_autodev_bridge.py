#!/usr/bin/env python3
"""
Test script for AutoDev bridge integration.

Tests:
1. Bridge imports and initialization
2. Role mapping correctness
3. Hierarchical execution flow
4. Result aggregation
"""

import sys
import os

# Add paths
sys.path.insert(0, os.path.expanduser("~/Projects/hermes-agent"))
sys.path.insert(0, os.path.expanduser("~/Projects/autodev/src"))

import asyncio
import json


class MockParentAgent:
    """Mock parent agent for testing."""
    
    def __init__(self):
        self.working_dir = "/tmp/test"
        self.model = "test-model"
        self.base_url = "https://api.example.com"
        self.api_key = "test-key"


def test_bridge_imports():
    """Test that bridge imports correctly."""
    print("Test 1: Bridge imports...")
    
    try:
        from tools.autodev_bridge import (
            HermesAutoDevBridge,
            AutoDevConfig,
            ROLE_MAPPING,
            AUTODEV_AVAILABLE,
        )
        print("  ✓ Imports successful")
        print(f"  ✓ AUTODEV_AVAILABLE = {AUTODEV_AVAILABLE}")
        print(f"  ✓ ROLE_MAPPING = {ROLE_MAPPING}")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_role_mapping():
    """Test that role mapping is correct."""
    print("\nTest 2: Role mapping...")
    
    from tools.autodev_bridge import ROLE_MAPPING
    
    expected = {
        "manager": "plan",
        "coder": "implement",
        "reviewer": "review",
    }
    
    if ROLE_MAPPING == expected:
        print(f"  ✓ Role mapping correct: {ROLE_MAPPING}")
        return True
    else:
        print(f"  ✗ Role mapping incorrect")
        print(f"    Expected: {expected}")
        print(f"    Got: {ROLE_MAPPING}")
        return False


def test_delegate_task_schema():
    """Test that delegate_task schema includes task_type."""
    print("\nTest 3: delegate_task schema...")
    
    try:
        from tools.delegate_tool import DELEGATE_TASK_SCHEMA
        
        properties = DELEGATE_TASK_SCHEMA.get("parameters", {}).get("properties", {})
        
        if "task_type" in properties:
            task_type = properties["task_type"]
            print(f"  ✓ task_type parameter found")
            print(f"    Type: {task_type.get('type')}")
            print(f"    Enum: {task_type.get('enum')}")
            
            if "autodev" in task_type.get("enum", []):
                print(f"  ✓ 'autodev' type available")
                return True
            else:
                print(f"  ✗ 'autodev' not in enum")
                return False
        else:
            print(f"  ✗ task_type parameter not found in schema")
            return False
    except Exception as e:
        print(f"  ✗ Schema test failed: {e}")
        return False


async def test_bridge_execution():
    """Test bridge execution flow."""
    print("\nTest 4: Bridge execution...")
    
    try:
        from tools.autodev_bridge import (
            HermesAutoDevBridge,
            AutoDevConfig,
            AUTODEV_AVAILABLE,
        )
        
        if not AUTODEV_AVAILABLE:
            print("  ⚠ AutoDev not available - skipping execution test")
            print("  ℹ This is expected if autodev is not fully installed")
            return True
        
        # Create mock parent and config
        parent = MockParentAgent()
        config = AutoDevConfig(max_iterations=2)
        
        # Create bridge
        bridge = HermesAutoDevBridge(parent, config)
        
        # Execute simple task
        result = await bridge.execute(
            goal="Test hierarchical execution",
            context="This is a test"
        )
        
        print(f"  ✓ Execution completed")
        print(f"  ✓ Result keys: {list(result.keys())}")
        print(f"  ✓ Status: {result.get('status')}")
        print(f"  ✓ Autodev mode: {result.get('autodev_mode')}")
        
        return True
    except Exception as e:
        print(f"  ✗ Execution test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_delegate_tool_integration():
    """Test that delegate_task accepts task_type parameter."""
    print("\nTest 5: delegate_task integration...")
    
    try:
        from tools.delegate_tool import delegate_task, _handle_autodev_delegation
        
        # Check that handler function exists
        print(f"  ✓ _handle_autodev_delegation function exists")
        
        # Check signature
        import inspect
        sig = inspect.signature(delegate_task)
        params = list(sig.parameters.keys())
        
        if "task_type" in params:
            print(f"  ✓ task_type parameter in delegate_task signature")
            print(f"    Parameters: {params}")
            return True
        else:
            print(f"  ✗ task_type parameter not in signature")
            print(f"    Parameters: {params}")
            return False
    except Exception as e:
        print(f"  ✗ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("AutoDev Bridge Integration Tests")
    print("=" * 60)
    
    tests = [
        test_bridge_imports,
        test_role_mapping,
        test_delegate_task_schema,
        test_delegate_tool_integration,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"Test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    # Run async test
    try:
        result = asyncio.run(test_bridge_execution())
        results.append(result)
    except Exception as e:
        print(f"Async test crashed: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
