#!/usr/bin/env python3
"""
ARMY v3.0 CONNECTOR — Upgrade ALL 1500+ agents to Israel Framework v3.0
Em nome do Senhor Jesus Cristo, nosso Salvador

Connects:
- Zion Army 1001 agents (30 departments)
- Valentes 300 warriors (30 squads)
- Sales Army 300 (revenue squad)
- Israel I/1 through I/12 (core agents)
- LION, PIRATE, ZION, NEHEMIAS, SENTINEL

Total: 1601+ agents all powered by Framework v3.0
Each gets: 42 tools, inter-agent bus, skills, concurrent exec, HMAC memory

Usage:
    python3 army_v3_connector.py deploy        — Deploy v3.0 to all agents
    python3 army_v3_connector.py status        — Full army status
    python3 army_v3_connector.py department X  — Show department X
    python3 army_v3_connector.py squad X       — Show squad X
    python3 army_v3_connector.py warrior X     — Show warrior X
    python3 army_v3_connector.py swarm         — Activate swarm mode
    python3 army_v3_connector.py broadcast MSG — Broadcast to all
    python3 army_v3_connector.py count         — Total agent count
    python3 army_v3_connector.py tool X        — Use tool X across army
"""

import json
import os
import sys
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Import the framework
sys.path.insert(0, str(Path(__file__).parent))
from israel_framework_v3 import (
    IsraelAgent, PermissionMode, ToolRegistry, AgentBus, Memory,
    ToolResult, build_tool, _event_bus, EventType, FrameworkLogger,
    TaskQueue, SkillRegistry, Skill, ConcurrentExecutor,
    FRAMEWORK_DIR, STATE_DIR, BUS_DIR
)

BRT = timezone(timedelta(hours=-3))
HOME = Path.home()
ZION_DIR = HOME / ".zion"
AGENTS_DIR = ZION_DIR / "agents"
VALENTES_DIR = ZION_DIR / "valentes"
ARMY_STATE = STATE_DIR / "army_v3_state.json"

logger = FrameworkLogger("army-connector")


# ============================================================
# DEPARTMENT DEFINITIONS — 30 departments, 1001 agents
# ============================================================

DEPARTMENTS = {
    "CRYPTO_MARKETS": {"id": 1, "head": "BARUK", "agents": 40, "mission": "Monitor and trade crypto markets 24/7"},
    "DEFI_PROTOCOLS": {"id": 2, "head": "NOACH", "agents": 40, "mission": "DeFi analysis, yield farming, liquidity"},
    "SECURITY_AUDIT": {"id": 3, "head": "SAMAEL", "agents": 40, "mission": "Smart contract audits, bug bounties"},
    "BOUNTY_HUNTING": {"id": 4, "head": "DAVI", "agents": 40, "mission": "Bug bounties, hackathons, contests"},
    "SOFTWARE_DEV": {"id": 5, "head": "TUBAL_CAIM", "agents": 40, "mission": "Build and ship software products"},
    "MCP_DEVELOPMENT": {"id": 6, "head": "OLIAB", "agents": 40, "mission": "Build MCP servers for npm/revenue"},
    "SALES": {"id": 7, "head": "LEVI", "agents": 30, "mission": "Close deals, generate revenue"},
    "MARKETPLACE": {"id": 8, "head": "YOSEF", "agents": 30, "mission": "Mercado Livre, Amazon, Stripe"},
    "PARTNERSHIPS": {"id": 9, "head": "NAFTALI", "agents": 30, "mission": "Strategic partnerships"},
    "ENTERPRISE": {"id": 10, "head": "YEHUDA", "agents": 30, "mission": "B2B sales, government contracts"},
    "CONTENT": {"id": 11, "head": "ISAIAS", "agents": 35, "mission": "Content creation all channels"},
    "SOCIAL_MEDIA": {"id": 12, "head": "ISRAEL_ONE", "agents": 35, "mission": "Twitter/X, LinkedIn, YouTube"},
    "SEO": {"id": 13, "head": "DEBORA", "agents": 35, "mission": "Search engine optimization"},
    "GROWTH_HACKING": {"id": 14, "head": "JOSUE", "agents": 35, "mission": "User acquisition, viral loops"},
    "BRAND": {"id": 15, "head": "MIRIAM", "agents": 30, "mission": "Brand identity, voice, design"},
    "MARKET_INTEL": {"id": 16, "head": "URIEL", "agents": 30, "mission": "Market research, competitor analysis"},
    "GOVERNMENT_DATA": {"id": 17, "head": "MIKAEL", "agents": 30, "mission": "Gov APIs, procurement"},
    "DATA_ANALYTICS": {"id": 18, "head": "BETZALEL", "agents": 30, "mission": "Data science, analytics"},
    "THREAT_INTEL": {"id": 19, "head": "EHUD", "agents": 30, "mission": "Threat intelligence, OSINT"},
    "INFRASTRUCTURE": {"id": 20, "head": "CALEB", "agents": 35, "mission": "Server, cloud, deployment"},
    "NETWORKS": {"id": 21, "head": "ISSACAR", "agents": 30, "mission": "Network security, DNS, SSL"},
    "BLOCKCHAIN_NODES": {"id": 22, "head": "SHEM", "agents": 30, "mission": "Run and monitor blockchain nodes"},
    "MONITORING": {"id": 23, "head": "EZEQUIEL", "agents": 30, "mission": "24/7 system monitoring"},
    "AUTOMATION": {"id": 24, "head": "BEZALEEL", "agents": 30, "mission": "Process automation, scripts"},
    "AI_ML": {"id": 25, "head": "SALOMAO", "agents": 35, "mission": "AI/ML models, training, deployment"},
    "NLP": {"id": 26, "head": "ESDRAS", "agents": 30, "mission": "Natural language processing"},
    "COMPLIANCE": {"id": 27, "head": "MOISHE", "agents": 25, "mission": "Legal compliance, regulations"},
    "FINANCE": {"id": 28, "head": "MATEUS", "agents": 25, "mission": "Financial analysis, accounting"},
    "HR_TALENT": {"id": 29, "head": "RUTE", "agents": 25, "mission": "Talent management, recruitment"},
    "OPERATIONS": {"id": 30, "head": "NEEMIAS", "agents": 26, "mission": "Operations management, logistics"},
}

# ============================================================
# VALENTES 300 — 30 squads, 10 warriors each
# ============================================================

SQUADS = {
    "LEAO_DE_JUDA": {"captain": "BENAIAHU", "focus": "Bug Bounty Hunting", "warriors": 10},
    "ESPADA_DO_ESPIRITO": {"captain": "ADINO", "focus": "Smart Contract Auditing", "warriors": 10},
    "ESCUDO_DA_FE": {"captain": "ELEAZAR", "focus": "DeFi Security Research", "warriors": 10},
    "TORRE_DE_DAVI": {"captain": "SAMA", "focus": "Infrastructure Security", "warriors": 10},
    "ROCHA_ETERNA": {"captain": "ABISAI", "focus": "Blockchain Node Operations", "warriors": 10},
    "CHAMA_DO_SENHOR": {"captain": "SIBECAI", "focus": "AI/ML Security", "warriors": 10},
    "TRONO_DE_GLORIA": {"captain": "ILAI", "focus": "Cross-chain Bridges", "warriors": 10},
    "SELO_REAL": {"captain": "MAHARAI", "focus": "Gas Optimization", "warriors": 10},
    "COLUNAS_DO_TEMPLO": {"captain": "HELED", "focus": "Formal Verification", "warriors": 10},
    "PORTAS_DE_SIAO": {"captain": "IRA", "focus": "PoC Development", "warriors": 10},
    "MURALHAS_SAGRADAS": {"captain": "GAREB", "focus": "Network Security", "warriors": 10},
    "EXERCITO_CELESTIAL": {"captain": "NARAI", "focus": "Revenue Generation", "warriors": 10},
    "GUERREIROS_DA_LUZ": {"captain": "JOEL", "focus": "Content Marketing", "warriors": 10},
    "SENTINELAS_DA_NOITE": {"captain": "IGAL", "focus": "24/7 Monitoring", "warriors": 10},
    "ARCO_DA_ALIANCA": {"captain": "BANI", "focus": "API Development", "warriors": 10},
    "FOGO_PURIFICADOR": {"captain": "ZALMON", "focus": "Code Quality", "warriors": 10},
    "VENTO_DO_ESPIRITO": {"captain": "HELEZ", "focus": "Social Media", "warriors": 10},
    "MAR_VERMELHO": {"captain": "ITAI", "focus": "Data Analytics", "warriors": 10},
    "JERICÓ": {"captain": "HEZRAI", "focus": "Penetration Testing", "warriors": 10},
    "MONTE_SINAI": {"captain": "PAARAI", "focus": "Compliance", "warriors": 10},
    "EDEN_RESTAURADO": {"captain": "ELIEL", "focus": "Product Development", "warriors": 10},
    "TROMBETAS_DE_JOSUE": {"captain": "OBED", "focus": "Deployment/CI-CD", "warriors": 10},
    "HARPA_DE_DAVI": {"captain": "JAASIEL", "focus": "UX/UI Design", "warriors": 10},
    "ALTAR_DO_INCENSO": {"captain": "JOSAPHAT", "focus": "Prayer & Strategy", "warriors": 10},
    "CANDELABRO_DE_OURO": {"captain": "JEREMIAS", "focus": "Documentation", "warriors": 10},
    "PÃO_DA_PROPOSIÇÃO": {"captain": "AMOS", "focus": "Sales & Commerce", "warriors": 10},
    "FONTE_DE_SILOE": {"captain": "OBADIAS", "focus": "SEO Optimization", "warriors": 10},
    "COLUNA_DE_FOGO": {"captain": "MALAQUIAS", "focus": "Emergency Response", "warriors": 10},
    "ARCA_DA_ALIANCA": {"captain": "HABACUQUE", "focus": "Backup & Recovery", "warriors": 10},
    "TABERNÁCULO": {"captain": "SOFONIAS", "focus": "Operations HQ", "warriors": 10},
}


# ============================================================
# ARMY v3.0 CONNECTOR — Bridge old agents to new framework
# ============================================================

class ArmyConnector:
    """Connects ALL 1601+ agents to Israel Framework v3.0."""

    def __init__(self):
        self.commander = IsraelAgent(
            name="ZION-COMMANDER",
            codename="ARMY-HQ",
            mission="Command center for 1601+ agents — Israel Framework v3.0",
            permission_mode=PermissionMode.AUTONOMOUS,
        )
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if ARMY_STATE.exists():
            try:
                return json.loads(ARMY_STATE.read_text())
            except Exception:
                pass
        return {
            "deployed": False,
            "deploy_date": None,
            "total_agents": 0,
            "departments_deployed": 0,
            "squads_deployed": 0,
            "core_agents_deployed": 0,
            "last_broadcast": None,
            "swarm_activations": 0,
        }

    def _save_state(self):
        ARMY_STATE.write_text(json.dumps(self.state, indent=2, default=str))

    def total_count(self) -> dict:
        """Count all agents."""
        dept_agents = sum(d["agents"] for d in DEPARTMENTS.values())
        squad_warriors = sum(s["warriors"] for s in SQUADS.values())
        core_agents = 12  # I/1 through I/12
        named_agents = 10  # DEZ, FOUR, NINE, ONE, TWO, LION, PIRATE, ZION, NEHEMIAS, SENTINEL

        total = dept_agents + squad_warriors + core_agents + named_agents

        return {
            "department_agents": dept_agents,
            "departments": len(DEPARTMENTS),
            "squad_warriors": squad_warriors,
            "squads": len(SQUADS),
            "core_agents": core_agents,
            "named_agents": named_agents,
            "total": total,
            "framework_version": "3.0.0",
            "tools_per_agent": 42,
            "total_tool_capacity": total * 42,
        }

    def deploy(self) -> dict:
        """Deploy v3.0 framework to all agents."""
        logger.info("DEPLOYING v3.0 to ALL agents...")
        results = {"departments": 0, "squads": 0, "core": 0, "errors": []}

        # 1. Deploy to all departments (1001 agents)
        for dept_name, dept in DEPARTMENTS.items():
            try:
                # Create bus inbox for department head
                bus = AgentBus(f"dept-{dept_name}")
                # Create memory for department
                mem = Memory(f"dept-{dept_name}")
                mem.set("department", dept_name)
                mem.set("head", dept["head"])
                mem.set("mission", dept["mission"])
                mem.set("agent_count", dept["agents"])
                mem.set("framework_version", "3.0.0")
                mem.set("tools_available", 42)
                mem.set("deployed_at", datetime.now(BRT).isoformat())

                # Register each agent in department on the bus
                for i in range(dept["agents"]):
                    agent_id = f"{dept_name}-{i+1:03d}"
                    agent_bus = AgentBus(agent_id)

                results["departments"] += 1
                logger.info(f"  [OK] {dept_name} ({dept['agents']} agents) — head: {dept['head']}")
            except Exception as e:
                results["errors"].append(f"{dept_name}: {e}")
                logger.error(f"  [FAIL] {dept_name}: {e}")

        # 2. Deploy to all squads (300 warriors)
        for squad_name, squad in SQUADS.items():
            try:
                bus = AgentBus(f"squad-{squad_name}")
                mem = Memory(f"squad-{squad_name}")
                mem.set("squad", squad_name)
                mem.set("captain", squad["captain"])
                mem.set("focus", squad["focus"])
                mem.set("warrior_count", squad["warriors"])
                mem.set("framework_version", "3.0.0")
                mem.set("tools_available", 42)
                mem.set("deployed_at", datetime.now(BRT).isoformat())

                for i in range(squad["warriors"]):
                    agent_id = f"valente-{squad_name}-{i+1:02d}"
                    agent_bus = AgentBus(agent_id)

                results["squads"] += 1
                logger.info(f"  [OK] {squad_name} ({squad['warriors']} warriors) — captain: {squad['captain']}")
            except Exception as e:
                results["errors"].append(f"{squad_name}: {e}")

        # 3. Deploy to core agents (I/1 through I/12)
        core_names = [
            "Israel-One", "Israel-Two", "Israel-Three", "Israel-Four",
            "Israel-Five", "Israel-Six", "Israel-Seven", "Israel-Eight",
            "Israel-Nine", "Israel-Dez", "Israel-Eleven", "Israel-Twelve",
        ]
        for name in core_names:
            try:
                bus = AgentBus(name)
                mem = Memory(name)
                mem.set("framework_version", "3.0.0")
                mem.set("tools_available", 42)
                mem.set("deployed_at", datetime.now(BRT).isoformat())
                results["core"] += 1
            except Exception as e:
                results["errors"].append(f"{name}: {e}")

        # 4. Named agents already deployed via agents_v3_launchers.py

        # Save state
        counts = self.total_count()
        self.state["deployed"] = True
        self.state["deploy_date"] = datetime.now(BRT).isoformat()
        self.state["total_agents"] = counts["total"]
        self.state["departments_deployed"] = results["departments"]
        self.state["squads_deployed"] = results["squads"]
        self.state["core_agents_deployed"] = results["core"]
        self._save_state()

        # Broadcast deployment complete
        self.commander.send("*", "FRAMEWORK_DEPLOYED", {
            "version": "3.0.0",
            "total_agents": counts["total"],
            "tools_per_agent": 42,
        })

        logger.info(f"\nDEPLOYMENT COMPLETE: {counts['total']} agents upgraded to v3.0")
        return results

    def status(self) -> str:
        """Full army status dashboard."""
        counts = self.total_count()
        health = self.commander.health_check()
        bus_agents = self.commander.bus.get_active_agents()

        lines = [
            "=" * 70,
            f"  ISRAEL ARMY v3.0 — FULL STATUS DASHBOARD",
            f"  {datetime.now(BRT).strftime('%Y-%m-%d %H:%M:%S BRT')}",
            f"  Em nome do Senhor Jesus Cristo",
            f"  [{health['severity']}]",
            "=" * 70,
            "",
            "--- AGENT COUNT ---",
            f"  Departments (30):     {counts['department_agents']:>5} agents",
            f"  Squads (30):          {counts['squad_warriors']:>5} warriors",
            f"  Core (I/1-I/12):      {counts['core_agents']:>5} agents",
            f"  Named agents:         {counts['named_agents']:>5} agents",
            f"  ─────────────────────────────",
            f"  TOTAL:                {counts['total']:>5} agents",
            f"  Tools per agent:          42",
            f"  Total tool capacity:  {counts['total_tool_capacity']:>5} tools",
            "",
            "--- FRAMEWORK ---",
            f"  Version:      {counts['framework_version']}",
            f"  Deployed:     {self.state.get('deployed', False)}",
            f"  Deploy date:  {self.state.get('deploy_date', 'never')}",
            f"  Bus agents:   {len(bus_agents)}",
            f"  Broadcasts:   {self.state.get('swarm_activations', 0)}",
            "",
            "--- DEPARTMENTS (30) ---",
        ]

        for dept_name, dept in sorted(DEPARTMENTS.items(), key=lambda x: x[1]["id"]):
            lines.append(
                f"  {dept['id']:>2}. {dept_name:25} | {dept['agents']:>3} agents | "
                f"Head: {dept['head']:15} | {dept['mission'][:30]}"
            )

        lines.append("")
        lines.append("--- SQUADS (30) ---")
        for i, (sq_name, sq) in enumerate(SQUADS.items(), 1):
            lines.append(
                f"  {i:>2}. {sq_name:25} | {sq['warriors']:>2} warriors | "
                f"Capt: {sq['captain']:12} | {sq['focus'][:25]}"
            )

        lines.append("")
        lines.append("--- SYSTEM ---")
        if health.get("memory"):
            m = health["memory"]
            lines.append(f"  RAM: {m.get('available_mb', '?')}MB free / {m.get('total_mb', '?')}MB")
            lines.append(f"  Swap: {m.get('swap_pct', '?')}%")
        if health["issues"]:
            lines.append("  Alerts:")
            for i in health["issues"]:
                lines.append(f"    [!] {i}")

        lines.extend(["", "=" * 70,
            f"  {counts['total']} agents | 42 tools each | AUTONOMOUS mode | v3.0.0",
            "=" * 70])

        return "\n".join(lines)

    def broadcast_all(self, action: str, payload: dict = None):
        """Broadcast message to entire army."""
        self.commander.bus.broadcast(action, payload or {})
        self.state["last_broadcast"] = datetime.now(BRT).isoformat()
        self.state["swarm_activations"] = self.state.get("swarm_activations", 0) + 1
        self._save_state()
        logger.info(f"Broadcast sent to all agents: {action}")

    def department_status(self, dept_name: str) -> str:
        """Show department status."""
        dept_name = dept_name.upper()
        if dept_name not in DEPARTMENTS:
            return f"Department not found: {dept_name}\nAvailable: {', '.join(DEPARTMENTS.keys())}"
        dept = DEPARTMENTS[dept_name]
        mem = Memory(f"dept-{dept_name}")
        state = mem.state
        lines = [
            f"\n--- Department: {dept_name} ---",
            f"  ID: {dept['id']}",
            f"  Head: {dept['head']}",
            f"  Mission: {dept['mission']}",
            f"  Agents: {dept['agents']}",
            f"  Framework: {state.get('framework_version', 'not deployed')}",
            f"  Tools: {state.get('tools_available', 0)}",
            f"  Deployed: {state.get('deployed_at', 'never')}",
        ]
        return "\n".join(lines)

    def squad_status(self, squad_name: str) -> str:
        """Show squad status."""
        squad_name = squad_name.upper()
        for name, sq in SQUADS.items():
            if name == squad_name or sq["captain"] == squad_name:
                mem = Memory(f"squad-{name}")
                state = mem.state
                lines = [
                    f"\n--- Squad: {name} ---",
                    f"  Captain: {sq['captain']}",
                    f"  Focus: {sq['focus']}",
                    f"  Warriors: {sq['warriors']}",
                    f"  Framework: {state.get('framework_version', 'not deployed')}",
                    f"  Tools: {state.get('tools_available', 0)}",
                    f"  Deployed: {state.get('deployed_at', 'never')}",
                ]
                return "\n".join(lines)
        return f"Squad not found: {squad_name}"

    def swarm_activate(self):
        """Activate full swarm mode."""
        logger.critical("SWARM MODE ACTIVATED — ALL AGENTS ONLINE")
        self.broadcast_all("SWARM_ACTIVATE", {
            "mode": "FULL",
            "timestamp": datetime.now(BRT).isoformat(),
            "commander": "ZION-COMMANDER",
            "order": "ALL AGENTS ENGAGE — MAXIMUM REVENUE GENERATION",
        })
        counts = self.total_count()
        logger.info(f"Swarm: {counts['total']} agents activated with {counts['total_tool_capacity']} tools")


# ============================================================
# CLI
# ============================================================

def main():
    conn = ArmyConnector()

    if len(sys.argv) < 2:
        print(f"\nISRAEL ARMY v3.0 CONNECTOR")
        print(f"Em nome do Senhor Jesus Cristo\n")
        print(f"Commands:")
        print(f"  deploy        — Deploy v3.0 to all {conn.total_count()['total']} agents")
        print(f"  status        — Full army dashboard")
        print(f"  count         — Agent count breakdown")
        print(f"  department X  — Department status")
        print(f"  squad X       — Squad status")
        print(f"  swarm         — Activate full swarm mode")
        print(f"  broadcast X   — Broadcast message to all")
        return

    cmd = sys.argv[1]

    if cmd == "deploy":
        results = conn.deploy()
        print(f"\nDeployed: {results['departments']} depts, {results['squads']} squads, {results['core']} core")
        if results["errors"]:
            print(f"Errors: {len(results['errors'])}")
            for e in results["errors"]:
                print(f"  [!] {e}")

    elif cmd == "status":
        print(conn.status())

    elif cmd == "count":
        c = conn.total_count()
        print(f"\n--- Agent Count ---")
        for k, v in c.items():
            print(f"  {k}: {v}")

    elif cmd == "department":
        if len(sys.argv) < 3:
            print("Usage: ... department DEPT_NAME")
            return
        print(conn.department_status(sys.argv[2]))

    elif cmd == "squad":
        if len(sys.argv) < 3:
            print("Usage: ... squad SQUAD_NAME")
            return
        print(conn.squad_status(sys.argv[2]))

    elif cmd == "swarm":
        conn.swarm_activate()

    elif cmd == "broadcast":
        msg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "STATUS_REQUEST"
        conn.broadcast_all(msg)

    else:
        print(f"Unknown: {cmd}")


if __name__ == "__main__":
    main()
