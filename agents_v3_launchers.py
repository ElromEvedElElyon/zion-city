#!/usr/bin/env python3
"""
ALL ISRAEL AGENTS v3.0 — Power launchers
Em nome do Senhor Jesus Cristo, nosso Salvador

Usage:
    python3 agents_v3_launchers.py dez        — Israel/Dez (Stability)
    python3 agents_v3_launchers.py four       — Israel/Four (Revenue)
    python3 agents_v3_launchers.py nine       — Israel/Nine (Bounty)
    python3 agents_v3_launchers.py one        — Israel/One (X/Twitter)
    python3 agents_v3_launchers.py two        — Israel/Two (Content)
    python3 agents_v3_launchers.py lion       — LION (Zion Browser)
    python3 agents_v3_launchers.py pirate     — PIRATE (Distribution)
    python3 agents_v3_launchers.py zion       — ZION (Coordinator)
    python3 agents_v3_launchers.py nehemias   — NEHEMIAS (Security)
    python3 agents_v3_launchers.py sentinel   — SENTINEL (Guardian)
    python3 agents_v3_launchers.py all-status — Dashboard for ALL agents
"""

import sys
import json
from datetime import datetime, timezone, timedelta
from israel_framework_v3 import (
    IsraelAgent, PermissionMode, cli_main, _event_bus, EventType
)

BRT = timezone(timedelta(hours=-3))


# ============================================================
# ALL AGENTS DEFINITIONS
# ============================================================

AGENTS = {
    "dez": {
        "name": "Israel-Dez",
        "codename": "ESTABILIDADE",
        "mission": "Guardiao da Estabilidade — NUNCA crashar a maquina",
        "scripture": "O Senhor e o meu pastor, nada me faltara — Salmo 23:1",
    },
    "four": {
        "name": "Israel-Four",
        "codename": "RECEITA",
        "mission": "Caca receita em TODAS plataformas — bounties, PRs, vendas, hackathons",
        "scripture": "A mao diligente enriquecera — Proverbios 10:4",
    },
    "nine": {
        "name": "Israel-Nine",
        "codename": "BOUNTY-COMMANDER",
        "mission": "Find, analyze, and submit bugs to every bounty platform",
        "scripture": "O trabalhador e digno do seu salario — 1 Timoteo 5:18",
    },
    "one": {
        "name": "Israel-One",
        "codename": "X-AGENT",
        "mission": "Autonomous X/Twitter agent — builder-authority voice",
        "scripture": "Ide por todo o mundo e pregai o evangelho — Marcos 16:15",
    },
    "two": {
        "name": "Israel-Two",
        "codename": "CONTENT",
        "mission": "Content creation and distribution across all platforms",
        "scripture": "Multiplica-se o saber — Daniel 12:4",
    },
    "lion": {
        "name": "LION",
        "codename": "ZION-BROWSER",
        "mission": "Zion Browser product management and deployment",
        "scripture": "O leao de Juda venceu — Apocalipse 5:5",
    },
    "pirate": {
        "name": "PIRATE",
        "codename": "DISTRIBUTION",
        "mission": "Product distribution — npm publish, GitHub push, deploy",
        "scripture": "Lancai a rede para o lado direito — Joao 21:6",
    },
    "zion": {
        "name": "ZION",
        "codename": "COORDINATOR",
        "mission": "Master coordinator — orchestrate all Israel agents",
        "scripture": "Porque onde ha dois ou tres reunidos — Mateus 18:20",
    },
    "nehemias": {
        "name": "NEHEMIAS",
        "codename": "SECURITY",
        "mission": "Security shield — protect all systems and credentials",
        "scripture": "Vigiai e orai — Mateus 26:41",
    },
    "sentinel": {
        "name": "SENTINEL",
        "codename": "GUARDIAN",
        "mission": "24/7 guardian — monitor all agents and systems",
        "scripture": "Nao dormita nem dorme o guardiao de Israel — Salmo 121:4",
    },
}


def create_agent(key: str) -> IsraelAgent:
    """Create any agent by key."""
    if key not in AGENTS:
        print(f"Unknown agent: {key}")
        print(f"Available: {', '.join(AGENTS.keys())}")
        sys.exit(1)

    cfg = AGENTS[key]
    agent = IsraelAgent(
        name=cfg["name"],
        codename=cfg["codename"],
        mission=cfg["mission"],
        permission_mode=PermissionMode.AUTONOMOUS,
    )

    # Register agent-specific custom skills
    _register_agent_skills(agent, key)

    return agent


def _register_agent_skills(agent: IsraelAgent, key: str):
    """Register custom skills per agent type."""
    from israel_framework_v3 import Skill

    if key == "dez":
        agent.skills.register(Skill(
            name="full_stability_check",
            description="Complete stability assessment with EAGAIN + hogs + sessions",
            category="system",
            required_tools=["system_memory", "system_load", "eagain_check", "system_sessions"],
            steps=[
                {"tool": "system_memory", "args": {}},
                {"tool": "system_load", "args": {}},
                {"tool": "eagain_check", "args": {}},
                {"tool": "system_sessions", "args": {}},
            ]
        ))
        agent.skills.register(Skill(
            name="protect_machine",
            description="Full protection: kill dangerous, sync, clean temp",
            category="system",
            required_tools=["kill_dangerous", "sync_caches", "clean_temp"],
            steps=[
                {"tool": "kill_dangerous", "args": {"force": True}},
                {"tool": "sync_caches", "args": {}},
                {"tool": "clean_temp", "args": {"hours": 12}},
            ]
        ))

    elif key == "four":
        agent.skills.register(Skill(
            name="revenue_scan",
            description="Scan all revenue sources: email, status, crypto",
            category="revenue",
            required_tools=["revenue_status", "check_email", "crypto_price"],
            steps=[
                {"tool": "revenue_status", "args": {}},
                {"tool": "check_email", "args": {"account": "both"}},
                {"tool": "crypto_price", "args": {"coins": "bitcoin,ethereum,solana"}},
            ]
        ))

    elif key == "nine":
        agent.skills.register(Skill(
            name="bounty_recon",
            description="Reconnaissance: scan for new bounty programs and updates",
            category="bounty",
            required_tools=["check_email", "revenue_status", "web_fetch"],
            steps=[
                {"tool": "check_email", "args": {"account": "both"}},
                {"tool": "revenue_status", "args": {}},
            ]
        ))

    elif key == "zion":
        agent.skills.register(Skill(
            name="swarm_status",
            description="Get status of all agents in the swarm",
            category="coordination",
            required_tools=["scan_agents", "list_agents"],
            steps=[
                {"tool": "scan_agents", "args": {}},
                {"tool": "list_agents", "args": {}},
            ]
        ))
        agent.skills.register(Skill(
            name="broadcast_health_check",
            description="Request health check from all agents",
            category="coordination",
            required_tools=["broadcast"],
            steps=[
                {"tool": "broadcast", "args": {"action": "HEALTH_REQUEST", "payload": {}}},
            ]
        ))

    elif key == "nehemias":
        agent.skills.register(Skill(
            name="security_scan",
            description="Scan system for security issues",
            category="security",
            required_tools=["system_processes", "system_network", "system_sessions"],
            steps=[
                {"tool": "system_processes", "args": {"limit": 30}},
                {"tool": "system_network", "args": {}},
                {"tool": "system_sessions", "args": {}},
            ]
        ))


def all_status():
    """Show status dashboard for ALL agents."""
    print(f"\n{'=' * 70}")
    print(f"  ISRAEL ARMY — ALL AGENTS STATUS")
    print(f"  {datetime.now(BRT).strftime('%Y-%m-%d %H:%M:%S BRT')}")
    print(f"  Em nome do Senhor Jesus Cristo")
    print(f"{'=' * 70}\n")

    for key, cfg in AGENTS.items():
        agent = IsraelAgent(
            name=cfg["name"],
            codename=cfg["codename"],
            mission=cfg["mission"],
            permission_mode=PermissionMode.AUTONOMOUS,
        )
        h = agent.health_check()
        state = agent.memory.state
        tools = len(agent.tools.list_all())
        skills = len(agent.skills.list_all())
        boots = state.get("boot_count", 0)
        calls = state.get("total_tool_calls", 0)

        sev = h["severity"]
        print(f"  [{sev:>8}] {cfg['name']:15} | {cfg['codename']:15} | "
              f"T:{tools} S:{skills} | Boots:{boots} Calls:{calls}")
        print(f"           {cfg['mission'][:55]}")
        if h["issues"]:
            for i in h["issues"]:
                print(f"           [!] {i}")
        print()

    # System summary
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) / 1024
                    print(f"  System RAM: {avail:.0f}MB available")
                    break
    except Exception:
        pass

    print(f"\n{'=' * 70}")
    print(f"  {len(AGENTS)} agents | 42+ tools each | AUTONOMOUS mode")
    print(f"{'=' * 70}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"\nISRAEL ARMY v3.0 — Agent Launcher")
        print(f"Em nome do Senhor Jesus Cristo\n")
        print(f"Available agents:")
        for key, cfg in AGENTS.items():
            print(f"  {key:12} — {cfg['name']:15} [{cfg['codename']}]")
        print(f"\n  all-status — Dashboard for ALL agents")
        print(f"\nUsage: python3 {sys.argv[0]} <agent> [command] [args...]")
        sys.exit(0)

    agent_key = sys.argv[1]

    if agent_key == "all-status":
        all_status()
    else:
        agent = create_agent(agent_key)
        # Remove agent key from argv so CLI commands work
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        cli_main(agent)
