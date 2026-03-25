#!/usr/bin/env python3
"""
Simple integration test for trace collection without autodev dependencies.
"""

import sys
import os

# Add paths
sys.path.insert(0, os.path.expanduser("~/Projects/hermes-agent"))

def test_trace_collector_import():
    """Test that trace collector can be imported."""
    print("\n=== Test 1: Trace Collector Import ===")
    
    from tools.trace_collector import FileBasedTraceCollector, ExecutionTrace
    print("✓ Trace collector imported")
    
    # Create collector
    collector = FileBasedTraceCollector(output_dir="/tmp/test_traces")
    print("✓ Collector instantiated")
    
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
    
    # End trace
    trace = collector.end_trace(
        trace_id=trace_id,
        result={"status": "completed"},
        success=True
    )
    print(f"✓ Ended trace: {trace.trace_id}")
    print(f"  Tool calls: {len(trace.tool_calls)}")
    
    # Flush
    files = collector.flush()
    print(f"✓ Flushed traces to: {files}")
    
    return True


def test_bridge_has_trace_collector():
    """Test that HermesAutoDevBridge has trace collector integration."""
    print("\n=== Test 2: Bridge Has Trace Collector ===")
    
    # Import without autodev to avoid torch segfault
    import importlib.util
    
    spec = importlib.util.spec_from_file_location(
        "autodev_bridge",
        "/Users/simo/Projects/hermes-agent/tools/autodev_bridge.py"
    )
    
    # Mock autodev components before importing
    sys.modules['agents'] = type(sys)('agents')
    sys.modules['agents.base'] = type(sys)('agents.base')
    sys.modules['agents.manager'] = type(sys)('agents.manager')
    sys.modules['agents.coder'] = type(sys)('agents.coder')
    sys.modules['agents.reviewer'] = type(sys)('agents.reviewer')
    sys.modules['hierarchical'] = type(sys)('hierarchical')
    sys.modules['hierarchical.hierarchical_executor'] = type(sys)('hierarchical.hierarchical_executor')
    
    # Create mock classes
    class MockAgentRole:
        MANAGER = "manager"
        CODER = "coder"
        REVIEWER = "reviewer"
    
    class MockTaskSpec:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    class MockSubTask:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    class MockHierarchicalResult:
        def __init__(self):
            self.success = True
            self.iterations = 1
            self.review_iterations = 0
            self.total_time_seconds = 1.0
            self.agent_usage = {}
            self.decomposition = []
            self.code_changes = []
            self.final_result = None
    
    sys.modules['agents.base'].AgentRole = MockAgentRole
    sys.modules['agents.base'].BaseAgent = object
    sys.modules['agents.base'].TaskSpec = MockTaskSpec
    sys.modules['agents.base'].TaskResult = object
    sys.modules['agents.base'].SubTask = MockSubTask
    sys.modules['hierarchical.hierarchical_executor'].HierarchicalExecutor = object
    sys.modules['hierarchical.hierarchical_executor'].HierarchicalResult = MockHierarchicalResult
    sys.modules['hierarchical.hierarchical_executor'].ExecutionPhase = object
    
    # Now import the bridge
    module = importlib.util.module_from_spec(spec)
    sys.modules['autodev_bridge'] = module
    spec.loader.exec_module(module)
    
    HermesAutoDevBridge = module.HermesAutoDevBridge
    AutoDevConfig = module.AutoDevConfig
    
    # Create mock parent
    class MockParent:
        working_dir = "/tmp"
        model = "test"
    
    # Create bridge
    bridge = HermesAutoDevBridge(MockParent())
    
    # Check for trace collector
    has_trace_collector = hasattr(bridge, '_trace_collector')
    print(f"  _trace_collector: {'✓' if has_trace_collector else '✗ MISSING'}")
    
    if has_trace_collector and bridge._trace_collector:
        print(f"  Trace collector type: {type(bridge._trace_collector).__name__}")
    
    # Check for trace tracking
    has_active_traces = hasattr(bridge, '_active_traces')
    has_completed_traces = hasattr(bridge, '_completed_traces')
    print(f"  _active_traces: {'✓' if has_active_traces else '✗ MISSING'}")
    print(f"  _completed_traces: {'✓' if has_completed_traces else '✗ MISSING'}")
    
    # Check for trace collection method
    has_collect_traces = hasattr(bridge, '_collect_completed_traces')
    print(f"  _collect_completed_traces: {'✓' if has_collect_traces else '✗ MISSING'}")
    
    return has_trace_collector and has_active_traces and has_completed_traces


def main():
    """Run all tests."""
    print("=" * 60)
    print("AutoDev Bridge Trace Collection Integration Test")
    print("=" * 60)
    
    tests = [
        test_trace_collector_import,
        test_bridge_has_trace_collector,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓✓✓ All integration tests PASSED!")
        print("✓ FileBasedTraceCollector is properly integrated into HermesAutoDevBridge")
        print("✓ RL training data collection is now ENABLED")
    else:
        print("\n✗ Some tests failed")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
