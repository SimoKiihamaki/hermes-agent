---
name: autodev
description: Autonomous coding agent with hierarchical multi-agent orchestration for code generation, debugging, and software development tasks
version: 10.0.0
metadata:
  hermes:
    tags: [coding, autonomous, multi-agent, hierarchical, rl-training, swebench]
    related_skills: [code-review, test-driven-development, systematic-debugging]
---

# AutoDev: Autonomous Coding Agent

## Overview

AutoDev is a sophisticated autonomous coding system that combines hierarchical multi-agent orchestration with reinforcement learning to solve complex software development tasks. It implements the Manager-Coder-Reviewer pattern with full Hermes integration via `delegate_task`.

## Project Location

```
~/Projects/autodev/
```

## Current Status

### Phase 9: Training Pipeline - COMPLETE (100%)

All components implemented and tested:
- Training Orchestrator (1,200 lines)
- SWEBench Runner (1,771 lines, 690 assertions, 33 tests)
- Metrics Dashboard (382 lines)
- Model Deployer (2,912 lines, 110 tests)
- Integration Tests (3,257 lines, 38/38 tests passing)

### Phase 10: Hierarchical Agent Pipeline - IN PROGRESS

Hierarchical infrastructure created with the following components:

## Key File Locations

### Phase 10 Hierarchical Infrastructure (`src/hierarchical/`)

```
src/hierarchical/
├── __init__.py              # Module exports (52 lines)
├── agent_pipeline.py        # Agent-to-Training Orchestrator bridge (444 lines)
├── hermes_integration.py    # Full Hermes delegate_task integration (486 lines)
├── coordination/
│   ├── __init__.py          # Coordination module exports
│   ├── task_router.py       # Dynamic agent assignment (20KB)
│   └── conflict_resolver.py # Multi-agent merge strategies (23KB)
└── memory/
    ├── __init__.py          # Memory module exports
    ├── agent_memory.py      # Persistent memory system (17KB)
    └── context_manager.py   # Context window management (18KB)
```

### Core Agent Framework (`src/agents/`)

```
src/agents/
├── base.py              # BaseAgent class with state machine
├── manager.py           # ManagerAgent for task decomposition
├── coder.py             # CoderAgent for implementation
├── reviewer.py          # ReviewerAgent for validation
├── communication.py     # Inter-agent messaging
└── states.py            # State machine definitions
```

### Training Pipeline (`src/training/`)

```
src/training/
├── orchestrator.py      # End-to-end training coordination
├── data_collector.py    # Execution trace collection
├── reward_calculator.py # Multi-component rewards
├── grpo_trainer.py      # TRL GRPO wrapper
├── model_registry.py    # Model version management
└── pipeline.py          # Training orchestration CLI
```

### Benchmark & Evaluation (`src/benchmark/`)

```
src/benchmark/
├── swe_bench_harness.py # SWE-bench evaluation harness
├── swebench_runner.py   # Model evaluation runner
├── verification.py      # Patch verification
└── reporting.py         # Result reporting
```

## Usage

### From Hermes (via autodev tool)

```python
# Execute a development task
autodev(
    task="Implement user authentication with JWT tokens",
    workspace="/path/to/project",
    context={"files": ["auth.py", "models.py"]}
)

# Via delegate_task for subagent
delegate_task(
    task="Add unit tests for the user service",
    toolset=["autodev", "filesystem"],
    ...
)
```

### Programmatic Usage

```python
from hierarchical import AgentPipeline, PipelineConfig
from hierarchical.hermes_integration import HermesIntegration, DelegateTaskConfig

# Create pipeline with learning enabled
config = PipelineConfig(
    enable_learning=True,
    enable_review=True,
    max_iterations=3
)
pipeline = AgentPipeline(config)
result = await pipeline.execute(task_spec)

# Or use Hermes integration directly
integration = HermesIntegration()
result = await integration.delegate_task(
    task_description="Refactor the database layer",
    project_path="/path/to/project"
)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Hermes Agent                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                   autodev Tool                               ││
│  │  - Task validation                                          ││
│  │  - Workspace setup                                          ││
│  │  - Result formatting                                        ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │               Hierarchical Agent Pipeline                    ││
│  │  ┌─────────┐   ┌─────────┐   ┌───────────┐                  ││
│  │  │ Manager │──▶│  Coder  │──▶│ Reviewer  │                  ││
│  │  │ (Plan)  │   │(Implement)│ │ (Validate)│                  ││
│  │  └─────────┘   └─────────┘   └───────────┘                  ││
│  │       │              │              │                        ││
│  │       ▼              ▼              ▼                        ││
│  │  ┌─────────────────────────────────────────────────────────┐││
│  │  │              Training Orchestrator                       │││
│  │  │  - Trace collection  - Reward calculation               │││
│  │  │  - GRPO training     - Model deployment                 │││
│  │  └─────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Target Metrics

| Metric | Current | Target |
|--------|---------|--------|
| SWE-bench Resolution Rate | 20% | 30%+ |
| Task Completion Time | ~5 min | < 5 min |
| Review Catch Rate | 85% | 90%+ |
| Training Pipeline Uptime | 99% | 99%+ |

## Documentation

- **Full Spec**: `~/Documents/Obsidian/Hermes/Knowledge/AutoDev/Hierarchical_Architecture_Spec.md`
- **Phase 10 Planning**: `~/Documents/Obsidian/Hermes/Knowledge/AutoDev/Phase10_Planning.md`
- **Phase 10 Agent Pipeline Spec**: `~/Documents/Obsidian/Hermes/Knowledge/AutoDev/Phase10_Agent_Pipeline_Spec.md`
- **Research Index**: `~/Documents/Obsidian/Hermes/Knowledge/AutoDev/INDEX.md`

## Prerequisites

1. Python 3.10+ with virtual environment
2. MCP servers configured (filesystem, git)
3. LLM API keys (OpenAI, Anthropic, or local)
4. Hermes agent with autodev toolset enabled

## Related Hermes Tools

- `autodev` - Main tool for task execution
- `autodev_delegate_handler` - Handler for subagent delegation
- `check_autodev_requirements` - Validate setup

## Tips

- Use `enable_learning=True` to collect traces for model improvement
- Enable `enable_review=True` for quality assurance on generated code
- Set appropriate `max_iterations` for complex tasks (default: 3)
- Check `timeout_seconds` for long-running tasks (default: 1800s)

---

*Last updated: 2026-03-24 (Phase 10 Kickoff - Hierarchical Agent Pipeline)*
