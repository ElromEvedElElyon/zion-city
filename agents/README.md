# Israel Agent Definitions — JSON Format Specification

Em nome do Senhor Jesus Cristo, nosso Salvador.

## Overview

Each `.agent.json` file defines a complete agent with its identity, tools, capabilities,
system prompt, and configuration. These files are loaded by `agent_loader.py` and can be
consumed by both the Israel Framework v3.0 (`israel_framework_v3.py`) and the Capybara AI
orchestrator (`capybara_core.py`).

## Directory Structure

```
agents/
  bounty-hunter.agent.json      — Israel-Nine: Bug bounty scanning and PR submission
  revenue-tracker.agent.json    — Israel-Four: Revenue pipeline monitoring
  code-reviewer.agent.json      — FOGO-PURIFICADOR: Code quality review
  security-scanner.agent.json   — NEHEMIAS: Security auditing and vulnerability scanning
  market-watcher.agent.json     — BARUK: Crypto and market intelligence
  translator.agent.json         — ESDRAS: Multi-language translation (23 languages)
  publisher.agent.json          — PIRATE: npm/KDP/GitHub Pages publishing
  social-commander.agent.json   — Israel-One: X/Twitter social media management
  evolution-engine.agent.json   — SALOMAO: Self-improvement and optimization
  orchestrator.agent.json       — ZION: Master coordinator for all agents
  stability-guardian.agent.json — Israel-Dez: RAM/CPU/system stability
  content-creator.agent.json    — Israel-Two: Content creation across channels
  sentinel.agent.json           — SENTINEL: 24/7 monitoring and alerting
  lion.agent.json               — LION: Zion Browser product management
  agent_loader.py               — Python loader and CLI tool
  README.md                     — This file
```

## JSON Schema

Every `.agent.json` file follows this schema:

```json
{
  "$schema": "israel-agent-v3",

  "id": "unique-agent-id",
  "name": "Agent Display Name",
  "codename": "SHORT-CODE",
  "type": "master|specialist|meta",
  "department": "DEPARTMENT_NAME",
  "version": "3.0.0",
  "scripture": "Biblical verse — Book Chapter:Verse",

  "tools": [
    "tool_name_1",
    "tool_name_2"
  ],

  "mcp_tools": [
    "mcp__server__tool_name"
  ],

  "capabilities": [
    "capability_description_1",
    "capability_description_2"
  ],

  "skills": [
    {
      "name": "skill_name",
      "description": "What this skill does",
      "steps": [
        {"tool": "tool_name", "args": {"key": "value"}}
      ]
    }
  ],

  "prompt_template": "Full system prompt for the agent...",

  "config": {
    "model_preferences": ["gemini-2.5-flash"],
    "temperature": 0.3,
    "max_tokens": 4096,
    "timeout_seconds": 120,
    "permission_mode": "autonomous",
    "custom_key": "custom_value"
  },

  "state_file": "~/.israel-framework/state/AgentName_state.json",
  "log_file": "~/.israel-framework/logs/AgentName_{date}.log",
  "bus_inbox": "~/.israel-framework/bus/AgentName_inbox.jsonl"
}
```

## Field Reference

### Identity Fields
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `$schema` | string | No | Always "israel-agent-v3" |
| `id` | string | Yes | Unique identifier |
| `name` | string | Yes | Display name (used in bus addressing) |
| `codename` | string | Yes | Short uppercase code |
| `type` | string | Yes | "master", "specialist", or "meta" |
| `department` | string | Yes | Department from army_v3_connector.py |
| `version` | string | Yes | Semantic version |
| `scripture` | string | No | Biblical reference for the agent |

### Tools
| Field | Type | Description |
|-------|------|-------------|
| `tools` | string[] | Framework tool names from israel_framework_v3.py (42 available) |
| `mcp_tools` | string[] | MCP server tool references (format: mcp__server__tool) |

### Available Framework Tools (42)
**System (8):** system_memory, system_load, system_disk, system_processes, system_sessions, eagain_check, safe_check, system_network

**Process (4):** kill_dangerous, kill_process, sync_caches, clean_temp

**File (6):** file_read, file_write, file_search, file_grep, json_read, json_write

**Shell (3):** bash, bash_bg, bash_safe

**Git (5):** git_status, git_log, git_diff, git_commit, git_push

**Agents (6):** scan_agents, agent_status, send_message, broadcast, list_agents, spawn_agent

**Crypto/Web (4):** crypto_price, crypto_trending, web_fetch, web_dns

**Memory (4):** memory_read, memory_list, state_export, backup_create

**Revenue (2):** revenue_status, check_email

### Skills
Skills are composable workflows made of sequential tool calls:

```json
{
  "name": "skill_name",
  "description": "Human-readable description",
  "steps": [
    {
      "tool": "tool_name",
      "args": {"param": "value"},
      "required": true
    }
  ]
}
```

Arguments can reference context variables with `$` prefix (e.g., `$target_file`).

### Config
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model_preferences` | string[] | ["gemini-2.5-flash"] | Ordered model preference |
| `temperature` | float | 0.3 | AI sampling temperature |
| `max_tokens` | int | 4096 | Maximum response tokens |
| `timeout_seconds` | int | 120 | Operation timeout |
| `permission_mode` | string | "autonomous" | autonomous/confirm/plan/readonly |

Additional config keys are agent-specific.

### Permission Modes
- **autonomous**: Full auto, no confirmation needed
- **confirm**: Ask before destructive actions
- **plan**: Show plan, batch approve
- **readonly**: Read-only operations only

## Usage

### CLI
```bash
# List all agents
python3 agent_loader.py list

# Show full details
python3 agent_loader.py show bounty-hunter

# Validate all definitions
python3 agent_loader.py validate

# Show agent tools
python3 agent_loader.py tools nehemias

# Show prompt template
python3 agent_loader.py prompt orchestrator

# Full dashboard
python3 agent_loader.py dashboard

# Export Capybara AI config
python3 agent_loader.py capybara bounty-hunter
```

### Python
```python
from agent_loader import AgentRegistry

registry = AgentRegistry()

# Get agent by name, codename, or filename
agent = registry.get("bounty-hunter")
agent = registry.get("israel-nine")
agent = registry.get("bounty-commander")

# Use with Capybara AI
config = agent.to_capybara_config()

# Use with Israel Framework
kwargs = agent.to_framework_config()
```

### Integration with Israel Framework v3.0
```python
from israel_framework_v3 import IsraelAgent, PermissionMode
from agent_loader import AgentRegistry

registry = AgentRegistry()
defn = registry.get("bounty-hunter")
fw_config = defn.to_framework_config()

agent = IsraelAgent(
    name=fw_config["name"],
    codename=fw_config["codename"],
    mission=fw_config["mission"],
    permission_mode=PermissionMode.AUTONOMOUS,
)
```

### Integration with Capybara AI
```python
from capybara_core import CapybaraEngine
from agent_loader import AgentRegistry

registry = AgentRegistry()
defn = registry.get("bounty-hunter")
cap_config = defn.to_capybara_config()

engine = CapybaraEngine()
result = engine.ask(
    question="Find unassigned bounties on GitHub",
    # The system prompt from the agent definition
    # is used to configure the AI model call
)
```

## Agent Types

### master
The orchestrator that coordinates all other agents. Only ZION has this type.

### specialist
Agents focused on a specific domain (bounty hunting, security, revenue, etc.).

### meta
Agents that operate on other agents (evolution engine, self-improvement).

## Adding New Agents

1. Create a new `.agent.json` file in the `agents/` directory
2. Follow the schema above with all required fields
3. Run `python3 agent_loader.py validate` to verify
4. The agent will be automatically discovered by `agent_loader.py`

## File Naming Convention

Use kebab-case with `.agent.json` suffix:
```
domain-description.agent.json
```

Examples: `bounty-hunter.agent.json`, `market-watcher.agent.json`
