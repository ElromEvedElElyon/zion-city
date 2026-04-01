#!/usr/bin/env python3
"""
ISRAEL AGENT LOADER — Load agent definitions from JSON files
Em nome do Senhor Jesus Cristo, nosso Salvador

Loads .agent.json files from the agents/ directory and integrates them
with the Israel Framework v3.0 and Capybara AI orchestrator.

Usage:
    python3 agent_loader.py list                — List all agent definitions
    python3 agent_loader.py show <agent>        — Show agent details
    python3 agent_loader.py validate            — Validate all agent JSONs
    python3 agent_loader.py launch <agent>      — Launch agent with framework
    python3 agent_loader.py tools <agent>       — List agent tools
    python3 agent_loader.py prompt <agent>      — Show agent prompt template
    python3 agent_loader.py dashboard           — Full agent dashboard
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

BRT = timezone(timedelta(hours=-3))
AGENTS_DIR = Path(__file__).parent
REQUIRED_FIELDS = ["id", "name", "codename", "type", "department", "version",
                   "tools", "capabilities", "prompt_template", "config"]


class AgentDefinition:
    """Parsed agent definition from JSON."""

    def __init__(self, data: dict, filepath: Path):
        self.data = data
        self.filepath = filepath
        self.id = data.get("id", "unknown")
        self.name = data.get("name", "Unknown")
        self.codename = data.get("codename", "UNKNOWN")
        self.agent_type = data.get("type", "specialist")
        self.department = data.get("department", "OPERATIONS")
        self.version = data.get("version", "3.0.0")
        self.scripture = data.get("scripture", "")
        self.tools = data.get("tools", [])
        self.mcp_tools = data.get("mcp_tools", [])
        self.capabilities = data.get("capabilities", [])
        self.skills = data.get("skills", [])
        self.prompt_template = data.get("prompt_template", "")
        self.config = data.get("config", {})
        self.state_file = data.get("state_file", "")
        self.log_file = data.get("log_file", "")
        self.bus_inbox = data.get("bus_inbox", "")

    def validate(self) -> tuple:
        """Validate agent definition. Returns (valid, errors)."""
        errors = []
        for field in REQUIRED_FIELDS:
            if field not in self.data:
                errors.append(f"Missing required field: {field}")
        if not self.tools:
            errors.append("No tools defined")
        if not self.capabilities:
            errors.append("No capabilities defined")
        if not self.prompt_template:
            errors.append("No prompt_template defined")
        if len(self.prompt_template) < 100:
            errors.append("prompt_template too short (< 100 chars)")
        return (len(errors) == 0, errors)

    def summary(self) -> str:
        """One-line summary."""
        return (f"{self.name:18s} [{self.codename:18s}] "
                f"T:{len(self.tools):>2} MCP:{len(self.mcp_tools):>2} "
                f"C:{len(self.capabilities):>2} S:{len(self.skills):>2} "
                f"| {self.department}")

    def detail(self) -> str:
        """Full detail view."""
        lines = [
            f"{'=' * 70}",
            f"  AGENT: {self.name} ({self.codename})",
            f"  Type: {self.agent_type} | Dept: {self.department} | v{self.version}",
            f"  File: {self.filepath}",
            f"  Scripture: {self.scripture}",
            f"{'=' * 70}",
            "",
            f"--- TOOLS ({len(self.tools)} framework + {len(self.mcp_tools)} MCP) ---",
        ]
        for t in self.tools:
            lines.append(f"  - {t}")
        if self.mcp_tools:
            lines.append(f"\n--- MCP TOOLS ({len(self.mcp_tools)}) ---")
            for t in self.mcp_tools:
                lines.append(f"  - {t}")

        lines.append(f"\n--- CAPABILITIES ({len(self.capabilities)}) ---")
        for c in self.capabilities:
            lines.append(f"  - {c}")

        lines.append(f"\n--- SKILLS ({len(self.skills)}) ---")
        for s in self.skills:
            steps_count = len(s.get("steps", []))
            lines.append(f"  - {s['name']}: {s.get('description', '')} ({steps_count} steps)")

        lines.append(f"\n--- CONFIG ---")
        for k, v in self.config.items():
            val_str = str(v)
            if len(val_str) > 60:
                val_str = val_str[:57] + "..."
            lines.append(f"  {k}: {val_str}")

        lines.append(f"\n--- PROMPT ({len(self.prompt_template)} chars) ---")
        lines.append(self.prompt_template[:500] + "..." if len(self.prompt_template) > 500 else self.prompt_template)

        return "\n".join(lines)

    def to_framework_config(self) -> dict:
        """Convert to IsraelAgent constructor kwargs."""
        return {
            "name": self.name,
            "codename": self.codename,
            "mission": self.prompt_template[:200],
            "permission_mode": self.config.get("permission_mode", "autonomous"),
        }

    def to_capybara_config(self) -> dict:
        """Convert to Capybara AI engine configuration."""
        return {
            "agent_id": self.id,
            "agent_name": self.name,
            "system_prompt": self.prompt_template,
            "model_preferences": self.config.get("model_preferences", ["gemini-2.5-flash"]),
            "temperature": self.config.get("temperature", 0.3),
            "max_tokens": self.config.get("max_tokens", 4096),
            "tools": self.tools + self.mcp_tools,
            "capabilities": self.capabilities,
        }


class AgentRegistry:
    """Registry of all agent definitions."""

    def __init__(self, agents_dir: Path = AGENTS_DIR):
        self.agents_dir = agents_dir
        self.agents: Dict[str, AgentDefinition] = {}
        self._load_all()

    def _load_all(self):
        """Load all .agent.json files."""
        for filepath in sorted(self.agents_dir.glob("*.agent.json")):
            try:
                data = json.loads(filepath.read_text())
                agent = AgentDefinition(data, filepath)
                # Index by multiple keys for easy lookup
                key = filepath.stem.replace(".agent", "")
                self.agents[key] = agent
                self.agents[agent.name.lower()] = agent
                self.agents[agent.codename.lower()] = agent
            except Exception as e:
                print(f"  [ERROR] Failed to load {filepath.name}: {e}")

    def get(self, name: str) -> Optional[AgentDefinition]:
        """Get agent by name, codename, or file stem."""
        return self.agents.get(name.lower())

    def list_all(self) -> List[AgentDefinition]:
        """List all unique agents (deduplicated)."""
        seen_ids = set()
        result = []
        for agent in self.agents.values():
            if agent.id not in seen_ids:
                seen_ids.add(agent.id)
                result.append(agent)
        return sorted(result, key=lambda a: a.name)

    def validate_all(self) -> dict:
        """Validate all agents. Returns summary."""
        results = {"valid": 0, "invalid": 0, "errors": {}}
        for agent in self.list_all():
            valid, errors = agent.validate()
            if valid:
                results["valid"] += 1
            else:
                results["invalid"] += 1
                results["errors"][agent.name] = errors
        return results

    def dashboard(self) -> str:
        """Generate full dashboard."""
        agents = self.list_all()
        total_tools = sum(len(a.tools) for a in agents)
        total_mcp = sum(len(a.mcp_tools) for a in agents)
        total_caps = sum(len(a.capabilities) for a in agents)
        total_skills = sum(len(a.skills) for a in agents)

        lines = [
            f"{'=' * 75}",
            f"  ISRAEL AGENT REGISTRY — DASHBOARD",
            f"  {datetime.now(BRT).strftime('%Y-%m-%d %H:%M:%S BRT')}",
            f"  Em nome do Senhor Jesus Cristo",
            f"{'=' * 75}",
            "",
            f"  Agents loaded: {len(agents)}",
            f"  Total tools: {total_tools} framework + {total_mcp} MCP = {total_tools + total_mcp}",
            f"  Total capabilities: {total_caps}",
            f"  Total skills: {total_skills}",
            "",
            f"--- AGENTS ---",
        ]

        for agent in agents:
            valid, _ = agent.validate()
            status = "OK" if valid else "!!"
            lines.append(f"  [{status}] {agent.summary()}")

        # Department breakdown
        depts = {}
        for agent in agents:
            depts.setdefault(agent.department, []).append(agent.name)

        lines.append(f"\n--- DEPARTMENTS ({len(depts)}) ---")
        for dept, names in sorted(depts.items()):
            lines.append(f"  {dept}: {', '.join(names)}")

        # Type breakdown
        types = {}
        for agent in agents:
            types.setdefault(agent.agent_type, []).append(agent.name)

        lines.append(f"\n--- TYPES ---")
        for t, names in sorted(types.items()):
            lines.append(f"  {t}: {', '.join(names)}")

        # Validation
        val = self.validate_all()
        lines.append(f"\n--- VALIDATION ---")
        lines.append(f"  Valid: {val['valid']} | Invalid: {val['invalid']}")
        if val["errors"]:
            for name, errs in val["errors"].items():
                for err in errs:
                    lines.append(f"  [!!] {name}: {err}")

        lines.extend(["", "=" * 75])
        return "\n".join(lines)


def main():
    registry = AgentRegistry()

    if len(sys.argv) < 2:
        print(f"\nISRAEL AGENT LOADER — JSON Agent Definitions")
        print(f"Em nome do Senhor Jesus Cristo\n")
        print(f"Commands:")
        print(f"  list              — List all agent definitions")
        print(f"  show <agent>      — Show agent details")
        print(f"  validate          — Validate all agent JSONs")
        print(f"  tools <agent>     — List agent tools")
        print(f"  prompt <agent>    — Show agent prompt template")
        print(f"  dashboard         — Full agent dashboard")
        print(f"  capybara <agent>  — Export Capybara AI config")
        print(f"\nAgents directory: {AGENTS_DIR}")
        print(f"Loaded: {len(registry.list_all())} agents")
        return

    cmd = sys.argv[1]

    if cmd == "list":
        print(f"\n--- AGENT DEFINITIONS ({len(registry.list_all())}) ---\n")
        for agent in registry.list_all():
            print(f"  {agent.summary()}")
        print()

    elif cmd == "show":
        if len(sys.argv) < 3:
            print("Usage: agent_loader.py show <agent-name>")
            return
        agent = registry.get(sys.argv[2])
        if agent:
            print(agent.detail())
        else:
            print(f"Agent not found: {sys.argv[2]}")
            print(f"Available: {', '.join(a.name for a in registry.list_all())}")

    elif cmd == "validate":
        result = registry.validate_all()
        print(f"\n--- VALIDATION RESULTS ---")
        print(f"  Valid: {result['valid']} | Invalid: {result['invalid']}")
        if result["errors"]:
            for name, errs in result["errors"].items():
                print(f"\n  [!!] {name}:")
                for err in errs:
                    print(f"       - {err}")
        else:
            print(f"  All agents passed validation.")
        print()

    elif cmd == "tools":
        if len(sys.argv) < 3:
            print("Usage: agent_loader.py tools <agent-name>")
            return
        agent = registry.get(sys.argv[2])
        if agent:
            print(f"\n--- Tools for {agent.name} ({agent.codename}) ---")
            print(f"\nFramework tools ({len(agent.tools)}):")
            for t in agent.tools:
                print(f"  - {t}")
            if agent.mcp_tools:
                print(f"\nMCP tools ({len(agent.mcp_tools)}):")
                for t in agent.mcp_tools:
                    print(f"  - {t}")
            print(f"\nTotal: {len(agent.tools) + len(agent.mcp_tools)}")
        else:
            print(f"Agent not found: {sys.argv[2]}")

    elif cmd == "prompt":
        if len(sys.argv) < 3:
            print("Usage: agent_loader.py prompt <agent-name>")
            return
        agent = registry.get(sys.argv[2])
        if agent:
            print(f"\n--- Prompt Template: {agent.name} ---\n")
            print(agent.prompt_template)
        else:
            print(f"Agent not found: {sys.argv[2]}")

    elif cmd == "dashboard":
        print(registry.dashboard())

    elif cmd == "capybara":
        if len(sys.argv) < 3:
            print("Usage: agent_loader.py capybara <agent-name>")
            return
        agent = registry.get(sys.argv[2])
        if agent:
            config = agent.to_capybara_config()
            print(json.dumps(config, indent=2))
        else:
            print(f"Agent not found: {sys.argv[2]}")

    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
