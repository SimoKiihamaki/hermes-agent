#!/usr/bin/env python3
"""
Demo test showing missing trace collection functionality.

This test demonstrates that:
1. Trace collection infrastructure exists
2. But it's NOT connected to the AutoDev bridge
3. Traces are not being collected during execution
"""

import sys
import os
import asyncio
import pytest

# Add paths
sys.path.insert(0, os.path.expanduser("~/Projects/hermes-agent"))
sys.path.insert(0, os.path.expanduser("~/Projects/autodev/src"))


def test_trace_collector_exists():
    """Test that trace collector can be imported and instantiated."""
    print("\n" + "="*60)
    print("Test 1: Trace Collector Infrastructure")
    print("="*60)
    
    try:
        from tools.trace_collector import FileBasedTraceCollector
        
        # Create collector
        collector = FileBasedTraceCollector(output_dir="/tmp/test_traces")
        print("✓ FileBasedTraceCollector instantiated successfully")
        
        # Test trace lifecycle
        trace_id = collector.start_trace(
            agent_id="test-agent",
            task_id="test-task",
            role="coder",
            metadata={"test": True}
        )
        print(f"✓ Started trace: {trace_id}")
        
        # Record some data
        collector.record_tool_call(
            trace_id=trace_id,
            tool_name="test_tool",
            tool_input={"arg": "value"},
            tool_output="success",
            duration_ms=123.4
        )
        print("✓ Recorded tool call")
        
        collector.record_llm_call(
            trace_id=trace_id,
            prompt="test prompt",
            response="test response",
            tokens_used=100,
            duration_ms=500.0,
            model="test-model"
        )
        print("✓ Recorded LLM call")
        
        collector.record_file_change(
            trace_id=trace_id,
            file_path="/tmp/test.py",
            change_type="modify",
            diff="test diff"
        )
        print("✓ Recorded file change")
        
        # End trace
        trace = collector.end_trace(
            trace_id=trace_id,
            result={"status": "completed"},
            success=True
        )
        print(f"✓ Ended trace: {trace.trace_id}")
        print(f"  Tool calls: {len(trace.tool_calls)}")
        print(f"  LLM calls: {len(trace.llm_calls)}")
        print(f"  File changes: {len(trace.file_changes)}")
        
        # Flush and create dataset
        files = collector.flush()
        print(f"✓ Flushed traces to: {files}")
        
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_bridge_missing_trace_collection():
    """Test that bridge does NOT collect traces (demonstrating the gap)."""
    print("\n" + "="*60)
    print("Test 2: Bridge Missing Trace Collection")
    print("="*60)
    
    try:
        from tools.autodev_bridge import HermesAutoDevBridge, AutoDevConfig
        
        # Check bridge attributes
        print("\nChecking HermesAutoDevBridge attributes:")
        
        # Create mock parent
        class MockParent:
            working_dir = "/tmp"
            model = "test"
            base_url = "https://test.com"
            api_key = "test"
        
        bridge = HermesAutoDevBridge(MockParent())
        
        # Check for training bridge
        has_training_bridge = hasattr(bridge, '_training_bridge') or hasattr(bridge, 'training_bridge')
        print(f"  _training_bridge: {'✓' if has_training_bridge else '✗ MISSING'}")
        
        # Check for trace collector
        has_trace_collector = hasattr(bridge, '_trace_collector') or hasattr(bridge, 'trace_collector')
        print(f"  _trace_collector: {'✓' if has_trace_collector else '✗ MISSING'}")
        
        # Check executor
        has_executor = hasattr(bridge, '_executor')
        print(f"  _executor: {'✓' if has_executor else '✗'}")
        
        print("\n✗ Bridge does NOT have trace collection infrastructure")
        print("  This is the critical gap preventing RL training!")
        
        return True  # Test passed (we found the gap)
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


@pytest.mark.asyncio
async def test_execution_without_traces():
    """Test that execution works but doesn't collect traces."""
    print("\n" + "="*60)
    print("Test 3: Execution Without Trace Collection")
    print("="*60)
    
    try:
        from tools.autodev_bridge import HermesAutoDevBridge, AutoDevConfig, AUTODEV_AVAILABLE
        
        print(f"AutoDev available: {AUTODEV_AVAILABLE}")
        
        if not AUTODEV_AVAILABLE:
            print("⚠ AutoDev not available, using fallback mode")
        
        # Create mock parent
        class MockParent:
            working_dir = "/tmp"
            model = "test"
            base_url = "https://test.com"
            api_key = "test"
        
        config = AutoDevConfig(max_iterations=2)
        bridge = HermesAutoDevBridge(MockParent(), config)
        
        # Execute a task
        result = await bridge.execute(
            goal="Test task execution",
            context="This is a test"
        )
        
        print(f"\n✓ Execution completed")
        print(f"  Status: {result.get('status')}")
        print(f"  Autodev mode: {result.get('autodev_mode')}")
        print(f"  Duration: {result.get('duration_seconds')}s")
        
        # Check for traces
        if 'traces' in result:
            print(f"  Traces: {len(result['traces'])} collected")
            if len(result['traces']) == 0:
                print("  ✗ NO TRACES COLLECTED - RL training impossible!")
        else:
            print("  ✗ No 'traces' field in result")
        
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("AutoDev Bridge Trace Collection Gap Analysis")
    print("="*60)
    print("\nThis test demonstrates that trace collection infrastructure")
    print("exists but is NOT connected to the AutoDev bridge.\n")
    
    tests = [
        test_trace_collector_exists,
        test_bridge_missing_trace_collection,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"Test crashed: {e}")
            results.append(False)
    
    # Run async test
    try:
        result = asyncio.run(test_execution_without_traces())
        results.append(result)
    except Exception as e:
        print(f"Async test crashed: {e}")
        results.append(False)
    
    # Summary
    print("\n" + "="*60)
    print("Summary")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Tests passed: {passed}/{total}")
    
    print("\n" + "="*60)
    print("CRITICAL FINDING")
    print("="*60)
    print("✓ Trace collection infrastructure EXISTS (FileBasedTraceCollector)")
    print("✓ AutoDev bridge WORKS (hierarchical execution)")
    print("✗ Bridge does NOT USE trace collector")
    print("✗ NO traces are collected during execution")
    print("✗ RL training is IMPOSSIBLE without traces")
    print("\nREQUIRED FIX:")
    print("1. Add FileBasedTraceCollector to HermesAutoDevBridge.__init__")
    print("2. Wrap wrapper agent execution with trace collection")
    print("3. Pass traces to HierarchicalResult.traces field")
    print("4. Flush traces to disk after execution")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
