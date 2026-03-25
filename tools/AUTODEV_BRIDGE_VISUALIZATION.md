# AutoDev Bridge Integration - Visual Gap Analysis

## Current Architecture (What Exists)

```
┌─────────────────────────────────────────────────────────────┐
│                    HERMES AGENT                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  delegate_task(task_type="autodev")                   │ │
│  └────────────────────┬───────────────────────────────────┘ │
└───────────────────────┼─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              HERMES-AUTODEV BRIDGE                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  HermesAutoDevBridge                                   │ │
│  │  ├─ _executor: HierarchicalExecutor ✓                 │ │
│  │  ├─ _manager: _HermesManagerWrapper ✓                 │ │
│  │  ├─ _coder_pool: [_HermesCoderWrapper] ✓              │ │
│  │  └─ _reviewer_pool: [_HermesReviewerWrapper] ✓        │ │
│  │                                                        │ │
│  │  ✗ MISSING: _trace_collector                           │ │
│  │  ✗ MISSING: _training_bridge                           │ │
│  └────────────────────────────────────────────────────────┘ │
└───────────────────────┼─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              HIERARCHICAL EXECUTOR                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Manager → Coder(s) → Reviewer → Iterate              │ │
│  │                                                        │ │
│  │  Returns: HierarchicalResult                          │ │
│  │  ├─ success: bool ✓                                   │ │
│  │  ├─ iterations: int ✓                                 │ │
│  │  ├─ code_changes: List ✓                              │ │
│  │  └─ traces: List[Empty] ✗                             │ │
│  └────────────────────────────────────────────────────────┘ │
└───────────────────────┼─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    RESULT TO HERMES                          │
│  {                                                           │
│    "status": "completed",                                   │
│    "summary": "...",                                        │
│    "iterations": 2,                                         │
│    "traces": [] ← ALWAYS EMPTY! ✗                           │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘

✓ = Implemented and Working
✗ = Missing/Not Connected
```

---

## RL Training Infrastructure (What Exists But Not Connected)

```
┌─────────────────────────────────────────────────────────────┐
│          RL TRAINING INFRASTRUCTURE (DISCONNECTED)          │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  AgentTrainingBridge (EXISTS) ✓                       │ │
│  │  ├─ model_provider: ITrainedModelProvider             │ │
│  │  ├─ trace_collector: IAgentTraceCollector             │ │
│  │  └─ reward_calculator: RewardCalculator               │ │
│  │                                                        │ │
│  │  But NOT CONNECTED to HermesAutoDevBridge! ✗          │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  IAgentTraceCollector (INTERFACE EXISTS) ✓            │ │
│  │  ├─ start_trace()                                     │ │
│  │  ├─ record_tool_call()                                │ │
│  │  ├─ record_llm_call()                                 │ │
│  │  ├─ record_file_change()                              │ │
│  │  └─ end_trace()                                       │ │
│  │                                                        │ │
│  │  But NO IMPLEMENTATION! ✗                             │ │
│  │  (FileBasedTraceCollector provided in audit)          │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  RewardCalculator (EXISTS) ✓                          │ │
│  │  ├─ compute_reward(trace) → RewardComponents          │ │
│  │  └─ ...                                               │ │
│  │                                                        │ │
│  │  But NOT CONNECTED to bridge! ✗                       │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

✓ = Interface/Class Exists
✗ = Not Connected/Implemented
```

---

## Required Architecture (What We Need)

```
┌─────────────────────────────────────────────────────────────┐
│                    HERMES AGENT                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  delegate_task(task_type="autodev")                   │ │
│  └────────────────────┬───────────────────────────────────┘ │
└───────────────────────┼─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              HERMES-AUTODEV BRIDGE (FIXED)                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  HermesAutoDevBridge                                   │ │
│  │  ├─ _executor: HierarchicalExecutor ✓                 │ │
│  │  ├─ _manager: _HermesManagerWrapper ✓                 │ │
│  │  ├─ _coder_pool: [_HermesCoderWrapper] ✓              │ │
│  │  ├─ _reviewer_pool: [_HermesReviewerWrapper] ✓        │ │
│  │  │                                                    │ │
│  │  ├─ _trace_collector: FileBasedTraceCollector ← NEW ✓│ │
│  │  └─ _training_bridge: AgentTrainingBridge ← NEW ✓    │ │
│  └────────────────────────────────────────────────────────┘ │
└───────────────────────┼─────────────────────────────────────┘
                        │
        ┌───────────────┴──────────────┐
        │                              │
        ▼                              ▼
┌──────────────────┐        ┌─────────────────────┐
│  EXECUTION FLOW  │        │   TRACE COLLECTION  │
│                  │        │                     │
│  Manager         │───────▶│  start_trace()      │
│    ↓ (decompose) │        │  record_tool_call() │
│  Coder(s)        │───────▶│  record_llm_call()  │
│    ↓ (implement) │        │  record_file_change│
│  Reviewer        │───────▶│  end_trace()        │
│    ↓ (validate)  │        │         │           │
│  Iterate?        │        │         ▼           │
│    ↓ (repeat)    │        │  Flush to disk      │
│  Complete        │        └─────────────────────┘
└──────────────────┘                   │
        │                              │
        │                              ▼
        │                 ┌─────────────────────┐
        │                 │  TRAINING DATASET   │
        │                 │  ~/.autodev/traces/ │
        │                 │    ├─ trace1.jsonl  │
        │                 │    ├─ trace2.jsonl  │
        │                 │    └─ dataset.jsonl │
        │                 └─────────────────────┘
        │                              │
        └──────────────────────────────┼───────────────────┐
                                       │                   │
                                       ▼                   ▼
                          ┌──────────────────┐  ┌─────────────────┐
                          │ REWARD CALCULATOR│  │  RL TRAINING    │
                          │                  │  │  PIPELINE       │
                          │ compute_reward() │  │                 │
                          │       ↓          │  │  Train model    │
                          │  RewardComponents│  │  Evaluate       │
                          └──────────────────┘  │  Deploy         │
                                                └─────────────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────┐
                                              │ IMPROVED AGENTS │
                                              │  (Better models)│
                                              │  SWE-bench: 35% │
                                              │       ↓         │
                                              │  Target: 50%+   │
                                              └─────────────────┘
```

---

## Gap Analysis Summary

### What's There (But Not Connected)

| Component | Status | Location |
|-----------|--------|----------|
| IAgentTraceCollector | ✓ Interface | agent_training_bridge.py:94 |
| AgentTrainingBridge | ✓ Class | agent_training_bridge.py:146 |
| HierarchicalResult.traces | ✓ Field | hierarchical_executor.py:100 |
| FileBasedTraceCollector | ✓ Implementation (new) | trace_collector.py |

### What's Missing

| Component | Status | Impact |
|-----------|--------|--------|
| Trace collector in bridge | ✗ Not added | CRITICAL |
| Wrapper trace recording | ✗ Not implemented | CRITICAL |
| Reward calculation | ✗ Not connected | CRITICAL |
| Training pipeline | ✗ Not created | CRITICAL |
| Agent functionality | ⚠️ Stubs | MAJOR |

---

## Implementation Checklist

### Phase 1: Trace Collection (3-4 days)

- [ ] Add FileBasedTraceCollector to HermesAutoDevBridge.__init__
- [ ] Wrap _HermesManagerWrapper.decompose with trace recording
- [ ] Wrap _HermesCoderWrapper.execute with trace recording
- [ ] Wrap _HermesReviewerWrapper.review with trace recording
- [ ] Pass collected traces to HierarchicalResult
- [ ] Flush traces to disk after execution
- [ ] Test end-to-end trace collection
- [ ] Verify traces are complete and valid

### Phase 2: Reward Calculation (2-3 days)

- [ ] Connect AgentTrainingBridge to HermesAutoDevBridge
- [ ] Instantiate RewardCalculator with config
- [ ] Compute rewards after each execution
- [ ] Log reward signals
- [ ] Add reward metrics to results

### Phase 3: Training Pipeline (2-3 days)

- [ ] Create dataset export function
- [ ] Add data versioning
- [ ] Create train/val/test splits
- [ ] Run initial RL training experiments
- [ ] Evaluate on SWE-bench

---

## Code Changes Required

### 1. In `autodev_bridge.py`

```python
# Line 96-98: Add trace collector
from tools.trace_collector import FileBasedTraceCollector

class HermesAutoDevBridge:
    def __init__(self, parent_agent, config=None):
        self.parent_agent = parent_agent
        self.config = config or AutoDevConfig()
        self._executor: Optional[HierarchicalExecutor] = None
        
        # ADD THIS:
        self._trace_collector = FileBasedTraceCollector(
            output_dir="~/.autodev/traces"
        )
```

### 2. In wrapper classes

```python
# In _HermesCoderWrapper.execute
async def execute(self, subtask: SubTask) -> Any:
    # ADD THIS:
    trace_id = self._trace_collector.start_trace(
        agent_id=self.agent_id,
        task_id=subtask.subtask_id,
        role="coder"
    )
    
    # Execute with trace recording
    # ... existing code ...
    
    # ADD THIS:
    self._trace_collector.end_trace(trace_id, result)
    return result
```

### 3. In result conversion

```python
# In _convert_result
def _convert_result(self, result, start_time):
    # ... existing code ...
    
    # ADD THIS:
    traces = self._trace_collector.flush()
    
    return {
        # ... existing fields ...
        "traces": traces,  # Add traces
    }
```

---

## Effort Estimation

| Task | Effort | Priority |
|------|--------|----------|
| Add trace collector to bridge | 2 hours | CRITICAL |
| Wrap agent execution with traces | 4 hours | CRITICAL |
| Test trace collection | 2 hours | CRITICAL |
| Connect reward calculator | 3 hours | HIGH |
| Create training pipeline | 4 hours | HIGH |
| **Total Phase 1** | **3-4 days** | **CRITICAL** |

---

## Risk Assessment

### High Risk

1. **Trace quality**: Poor traces → poor RL models
   - **Mitigation**: Add trace validation
   
2. **Performance overhead**: Trace collection slows execution
   - **Mitigation**: Async writing, buffering

3. **Data privacy**: Traces may contain sensitive info
   - **Mitigation**: Sanitization, encryption

### Medium Risk

1. **Storage growth**: Traces consume disk space
   - **Mitigation**: Compression, rotation

2. **Integration bugs**: Trace collection breaks execution
   - **Mitigation**: Comprehensive testing

---

## Success Criteria

### Phase 1 Complete When:

- [ ] Traces collected for every execution
- [ ] Traces contain all tool calls, LLM calls, file changes
- [ ] Traces persisted to disk in JSONL format
- [ ] Can create training dataset from traces
- [ ] Test coverage > 80% for trace collection

### RL Training Ready When:

- [ ] 100+ traces collected
- [ ] Traces validated for quality
- [ ] Dataset exported
- [ ] Initial RL training runs
- [ ] SWE-bench improvement measured

---

**Bottom Line**: The infrastructure exists, just needs to be connected. A 3-4 day sprint can complete Phase 1 and unblock RL training.
