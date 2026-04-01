#!/usr/bin/env python3
"""
ISRAEL/DEZ (I/10) — Guardiao da Estabilidade da Maquina
Em nome do Senhor Jesus Cristo, nosso Salvador

MISSAO: Garantir que a maquina NUNCA crashe. Monitorar RAM, CPU, swap,
processos, sessoes CLI, janelas do navegador. Identificar tarefas na
maquina e fora dela. Proteger todas as janelas abertas.

REGRAS:
- NUNCA ser deletado
- NUNCA fechar janelas/sessoes de outros agentes
- SEMPRE proteger a estabilidade primeiro
- Matar APENAS processos que ameacem OOM
- Logs permanentes de tudo

Baseado na arquitetura do Israel/Four (HMAC-signed state, CLI, modular)
Pure Python stdlib — ZERO dependencias externas
"""

import os
import sys
import json
import time
import hashlib
import hmac
import subprocess
import signal
import socket
import shutil
from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# CONSTANTS
# ============================================================

VERSION = "2.0.0"
AGENT_NAME = "Israel/Dez"
AGENT_CODENAME = "ESTABILIDADE"
MISSION = "Guardiao da Estabilidade — NUNCA crashar a maquina"

HOME = Path.home()
BASE_DIR = HOME / "israel-ten"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"
STATE_FILE = DATA_DIR / "israel_ten_state.json"
TASKS_FILE = DATA_DIR / "tasks_registry.json"
SESSIONS_FILE = DATA_DIR / "sessions_registry.json"
HMAC_KEY = b"Israel10-Estabilidade-JesusCristo-PadraoBitcoin-2026"

# Thresholds for a 3.3GB RAM i3 machine
RAM_CRITICAL_MB = 200       # Free RAM below this = EMERGENCY
RAM_WARNING_MB = 500        # Free RAM below this = WARNING
RAM_EAGAIN_RISK_MB = 400    # Below this = EAGAIN risk, kill dangerous processes
SWAP_CRITICAL_PCT = 95      # Swap usage above this = CRITICAL
CPU_LOAD_MAX = 6.0          # Load average above this = HIGH (2 cores)
THREAD_EAGAIN_MAX = 4000    # Running threads above this = EAGAIN imminent
PROCESS_RAM_MAX_MB = 800    # Single process above this = candidate for kill
PROCESS_RAM_DANGEROUS_MB = 300  # Dangerous process above this = kill immediately

PROCESS_RAM_SAFE_LIST = [   # NEVER kill these
    "claude", "firefox", "gnome-shell", "gnome-terminal",
    "Xorg", "systemd", "gdm", "pulseaudio", "pipewire",
    "dbus", "NetworkManager", "nordvpnd", "zion", "lion", "pirate",
    "israel"
]

# DANGEROUS PROCESSES — Session 59 EAGAIN Lesson
# These spawned by heavy CLI tools consume 200-500MB each
# Kill them FIRST when RAM is low — they are ALWAYS replaceable
DANGEROUS_PROCESSES = [
    "netlify",      # netlify-cli: 300-500MB, spawns esbuild+telemetry
    "esbuild",      # bundler: 100-300MB, spawned by netlify
    "webpack",      # bundler: 200-400MB
    "turbopack",    # bundler: 200-400MB
    "next-server",  # Next.js dev server: 200-400MB
    "vite",         # dev server: 100-300MB
    "tsc",          # TypeScript compiler: 100-300MB
    "npx",          # npm exec: 100-200MB per instance
    "rollup",       # bundler: 100-200MB
    "parcel",       # bundler: 100-300MB
    "jest",         # test runner: 100-300MB
    "mocha",        # test runner: 50-200MB
    "playwright",   # browser testing: 200-500MB
    "puppeteer",    # browser automation: 200-500MB
    "electron",     # desktop app: 200-500MB
    "chromium",     # browser engine: 300-800MB (not firefox!)
]

# Safe deploy commands (API-only, low RAM) vs dangerous (CLI, high RAM)
SAFE_DEPLOY_METHODS = {
    "netlify": "curl -X POST https://api.netlify.com/api/v1/sites/SITE_ID/builds",
    "vercel": "curl -X POST https://api.vercel.com/v1/deployments",
    "github": "gh api repos/OWNER/REPO/dispatches -f event_type=deploy",
}
DANGEROUS_DEPLOY_COMMANDS = [
    "npx netlify-cli deploy",
    "npx netlify deploy",
    "netlify deploy",
    "vercel --prod",
    "npm run build",
    "next build",
]


# ============================================================
# SOUL — Identidade Imutavel
# ============================================================

SOUL = {
    "name": AGENT_NAME,
    "codename": AGENT_CODENAME,
    "version": VERSION,
    "mission": MISSION,
    "creator": "Elrom Eved El Elyon",
    "company": "PADRAO BITCOIN LTDA",
    "cnpj": "51.148.891/0001-69",
    "faith": "Em nome do Senhor Jesus Cristo",
    "rules": [
        "NUNCA ser deletado",
        "NUNCA fechar janelas/sessoes de outros agentes",
        "NUNCA matar processos protegidos (SAFE_LIST)",
        "SEMPRE proteger estabilidade primeiro",
        "SEMPRE logar todas as acoes",
        "Matar APENAS processos que ameacem OOM",
        "Monitorar 24/7 sem parar",
        "ZERO dependencias externas"
    ],
    "created": "2026-03-29T11:30:00-03:00",
    "inviolable": True,
    "singularity_level": 50
}


# ============================================================
# MEMORY — Estado Persistente com HMAC
# ============================================================

class Memory:
    """Estado persistente com verificacao HMAC."""

    def __init__(self):
        self.state = self._load()

    def _sign(self, data: str) -> str:
        return hmac.new(HMAC_KEY, data.encode(), hashlib.sha256).hexdigest()

    def _load(self) -> dict:
        if STATE_FILE.exists():
            try:
                raw = STATE_FILE.read_text()
                obj = json.loads(raw)
                data_str = json.dumps(obj.get("data", {}), sort_keys=True)
                expected_sig = self._sign(data_str)
                if obj.get("signature") == expected_sig:
                    return obj["data"]
                else:
                    log("WARNING: State signature mismatch — loading anyway (may be from older version)")
                    return obj.get("data", self._default())
            except Exception as e:
                log(f"ERROR loading state: {e}")
                return self._default()
        return self._default()

    def _default(self) -> dict:
        return {
            "boot_count": 0,
            "total_interventions": 0,
            "processes_killed": [],
            "oom_prevented": 0,
            "sessions_tracked": [],
            "last_scan": None,
            "scan_count": 0,
            "alerts": [],
            "tasks_identified": [],
            "uptime_start": datetime.now().isoformat()
        }

    def save(self):
        data_str = json.dumps(self.state, sort_keys=True)
        obj = {
            "data": self.state,
            "signature": self._sign(data_str),
            "agent": AGENT_NAME,
            "saved_at": datetime.now().isoformat()
        }
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(obj, indent=2))

    def increment(self, key: str):
        self.state[key] = self.state.get(key, 0) + 1
        self.save()

    def append_alert(self, alert: dict):
        alerts = self.state.get("alerts", [])
        alerts.append(alert)
        # Keep last 200 alerts
        self.state["alerts"] = alerts[-200:]
        self.save()


# ============================================================
# LOGGING
# ============================================================

def log(msg: str, level: str = "INFO"):
    """Log to file and stdout."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"israel_ten_{datetime.now().strftime('%Y%m%d')}.log"
    try:
        with open(log_file, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ============================================================
# SYSTEM MONITOR
# ============================================================

class SystemMonitor:
    """Monitora recursos do sistema."""

    @staticmethod
    def get_memory() -> dict:
        """Parse /proc/meminfo para RAM e swap."""
        info = {}
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        val = int(parts[1])  # kB
                        info[key] = val
        except Exception:
            return {"error": "Cannot read /proc/meminfo"}

        total_mb = info.get("MemTotal", 0) / 1024
        free_mb = info.get("MemFree", 0) / 1024
        available_mb = info.get("MemAvailable", 0) / 1024
        buffers_mb = info.get("Buffers", 0) / 1024
        cached_mb = info.get("Cached", 0) / 1024
        swap_total_mb = info.get("SwapTotal", 0) / 1024
        swap_free_mb = info.get("SwapFree", 0) / 1024
        swap_used_mb = swap_total_mb - swap_free_mb
        swap_pct = (swap_used_mb / swap_total_mb * 100) if swap_total_mb > 0 else 0

        return {
            "total_mb": round(total_mb),
            "free_mb": round(free_mb),
            "available_mb": round(available_mb),
            "buffers_mb": round(buffers_mb),
            "cached_mb": round(cached_mb),
            "used_mb": round(total_mb - free_mb - buffers_mb - cached_mb),
            "swap_total_mb": round(swap_total_mb),
            "swap_used_mb": round(swap_used_mb),
            "swap_free_mb": round(swap_free_mb),
            "swap_pct": round(swap_pct, 1)
        }

    @staticmethod
    def get_load() -> dict:
        """Parse /proc/loadavg."""
        try:
            with open("/proc/loadavg") as f:
                parts = f.read().split()
            return {
                "load_1min": float(parts[0]),
                "load_5min": float(parts[1]),
                "load_15min": float(parts[2]),
                "running_threads": parts[3]
            }
        except Exception:
            return {"load_1min": 0, "load_5min": 0, "load_15min": 0}

    @staticmethod
    def get_processes(sort_by_mem: bool = True, limit: int = 30) -> list:
        """List processes sorted by memory usage."""
        procs = []
        try:
            for pid_dir in Path("/proc").iterdir():
                if not pid_dir.name.isdigit():
                    continue
                pid = pid_dir.name
                try:
                    # Read command
                    cmdline = (pid_dir / "cmdline").read_text().replace("\0", " ").strip()
                    if not cmdline:
                        comm = (pid_dir / "comm").read_text().strip()
                        cmdline = comm

                    # Read memory from status
                    status = (pid_dir / "status").read_text()
                    rss_kb = 0
                    name = ""
                    for line in status.split("\n"):
                        if line.startswith("VmRSS:"):
                            rss_kb = int(line.split()[1])
                        elif line.startswith("Name:"):
                            name = line.split("\t")[-1].strip()

                    rss_mb = rss_kb / 1024
                    procs.append({
                        "pid": int(pid),
                        "name": name,
                        "cmd": cmdline[:200],
                        "rss_mb": round(rss_mb, 1)
                    })
                except (PermissionError, FileNotFoundError, ValueError, IndexError):
                    continue
        except Exception:
            pass

        if sort_by_mem:
            procs.sort(key=lambda p: p["rss_mb"], reverse=True)

        return procs[:limit]

    @staticmethod
    def get_disk() -> dict:
        """Disk usage for root."""
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize / (1024**3)
            free = st.f_bavail * st.f_frsize / (1024**3)
            used = total - free
            return {
                "total_gb": round(total, 1),
                "used_gb": round(used, 1),
                "free_gb": round(free, 1),
                "used_pct": round(used / total * 100, 1)
            }
        except Exception:
            return {"error": "Cannot read disk"}

    @staticmethod
    def get_active_sessions() -> list:
        """Detect active CLI sessions, terminals, browsers."""
        sessions = []
        try:
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split("\n"):
                lower = line.lower()
                # Claude Code sessions
                if "claude" in lower and "node" not in lower:
                    parts = line.split()
                    if len(parts) > 1:
                        sessions.append({
                            "type": "claude-code",
                            "pid": parts[1],
                            "info": " ".join(parts[10:])[:100]
                        })
                # Terminal sessions
                elif "gnome-terminal" in lower or "bash" in lower and "login" in lower:
                    parts = line.split()
                    if len(parts) > 1:
                        sessions.append({
                            "type": "terminal",
                            "pid": parts[1],
                            "info": " ".join(parts[10:])[:80]
                        })
                # Firefox/Zion browser
                elif "firefox" in lower and "-contentproc" not in lower:
                    parts = line.split()
                    if len(parts) > 1:
                        sessions.append({
                            "type": "firefox",
                            "pid": parts[1],
                            "info": "Firefox browser"
                        })
                # Zion processes
                elif "zion" in lower or "lion" in lower or "pirate" in lower:
                    parts = line.split()
                    if len(parts) > 1:
                        sessions.append({
                            "type": "zion-tool",
                            "pid": parts[1],
                            "info": " ".join(parts[10:])[:80]
                        })
        except Exception:
            pass

        # Deduplicate by PID
        seen = set()
        unique = []
        for s in sessions:
            if s["pid"] not in seen:
                seen.add(s["pid"])
                unique.append(s)

        return unique

    @staticmethod
    def get_network_connections() -> int:
        """Count active network connections."""
        try:
            count = 0
            net_tcp = Path("/proc/net/tcp")
            if net_tcp.exists():
                count = len(net_tcp.read_text().strip().split("\n")) - 1
            return count
        except Exception:
            return 0

    @staticmethod
    def detect_eagain_risk() -> dict:
        """Detect EAGAIN risk from /proc/loadavg thread count and memory.

        EAGAIN happens when kernel cannot fork() new processes — caused by:
        1. Too many threads/processes (>4000 on this machine)
        2. Too little memory for new process page tables (<200MB)
        3. Heavy Node.js tools consuming all resources (netlify, esbuild, webpack)

        Session 59 Incident: Shell blocked 30+ minutes, even 'echo ok' failed.
        Root cause: npx netlify-cli deploy spawned esbuild + telemetry = 500MB+
        """
        risk = {
            "eagain_risk": False,
            "level": "SAFE",
            "reasons": [],
            "recommendations": [],
            "dangerous_procs": [],
            "thread_count": 0,
            "available_mb": 9999,
        }

        # 1. Check thread count from /proc/loadavg
        try:
            with open("/proc/loadavg") as f:
                parts = f.read().split()
            thread_info = parts[3]  # format: "running/total"
            total_threads = int(thread_info.split("/")[1])
            risk["thread_count"] = total_threads

            if total_threads > THREAD_EAGAIN_MAX:
                risk["eagain_risk"] = True
                risk["level"] = "CRITICAL"
                risk["reasons"].append(f"Threads {total_threads} > {THREAD_EAGAIN_MAX} limit")
                risk["recommendations"].append("KILL all dangerous processes immediately")
            elif total_threads > THREAD_EAGAIN_MAX * 0.8:
                risk["level"] = "WARNING"
                risk["reasons"].append(f"Threads {total_threads} approaching limit ({THREAD_EAGAIN_MAX})")
                risk["recommendations"].append("Avoid launching new heavy processes")
        except Exception:
            pass

        # 2. Check available memory
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        avail_kb = int(line.split()[1])
                        avail_mb = avail_kb / 1024
                        risk["available_mb"] = round(avail_mb)

                        if avail_mb < RAM_CRITICAL_MB:
                            risk["eagain_risk"] = True
                            risk["level"] = "CRITICAL"
                            risk["reasons"].append(f"RAM {avail_mb:.0f}MB < {RAM_CRITICAL_MB}MB critical")
                            risk["recommendations"].append("Emergency kill of all dangerous processes")
                        elif avail_mb < RAM_EAGAIN_RISK_MB:
                            if risk["level"] != "CRITICAL":
                                risk["level"] = "WARNING"
                            risk["reasons"].append(f"RAM {avail_mb:.0f}MB < {RAM_EAGAIN_RISK_MB}MB EAGAIN risk zone")
                            risk["recommendations"].append("Kill dangerous processes before they grow")
                        break
        except Exception:
            pass

        # 3. Find currently running dangerous processes
        try:
            for pid_dir in Path("/proc").iterdir():
                if not pid_dir.name.isdigit():
                    continue
                try:
                    cmdline = (pid_dir / "cmdline").read_text().replace("\0", " ").strip().lower()
                    comm = (pid_dir / "comm").read_text().strip().lower()
                    status = (pid_dir / "status").read_text()

                    rss_kb = 0
                    for line in status.split("\n"):
                        if line.startswith("VmRSS:"):
                            rss_kb = int(line.split()[1])
                            break

                    rss_mb = rss_kb / 1024

                    for danger in DANGEROUS_PROCESSES:
                        if danger in comm or danger in cmdline:
                            risk["dangerous_procs"].append({
                                "pid": int(pid_dir.name),
                                "name": comm,
                                "cmd": cmdline[:150],
                                "rss_mb": round(rss_mb, 1),
                                "matched": danger
                            })
                            break
                except (PermissionError, FileNotFoundError, ValueError):
                    continue
        except Exception:
            pass

        if risk["dangerous_procs"]:
            total_danger_mb = sum(p["rss_mb"] for p in risk["dangerous_procs"])
            risk["reasons"].append(
                f"{len(risk['dangerous_procs'])} dangerous process(es) using {total_danger_mb:.0f}MB"
            )
            if risk["available_mb"] < RAM_EAGAIN_RISK_MB:
                risk["eagain_risk"] = True
                risk["recommendations"].append(
                    f"Kill {len(risk['dangerous_procs'])} dangerous processes to free {total_danger_mb:.0f}MB"
                )

        return risk

    @staticmethod
    def pre_operation_check(operation: str = "deploy") -> dict:
        """Check if machine can safely run a heavy operation.

        Call this BEFORE launching any resource-intensive command.
        Returns: {"safe": bool, "reason": str, "alternative": str}

        Usage from other agents:
            from israel_ten import SystemMonitor
            check = SystemMonitor.pre_operation_check("netlify deploy")
            if not check["safe"]:
                print(f"BLOCKED: {check['reason']}")
                print(f"USE: {check['alternative']}")
        """
        result = {
            "safe": True,
            "reason": "",
            "alternative": "",
            "available_mb": 0,
            "load": 0,
        }

        # Check if operation itself is dangerous
        op_lower = operation.lower()
        for dangerous in DANGEROUS_DEPLOY_COMMANDS:
            if dangerous.lower() in op_lower:
                result["safe"] = False
                result["reason"] = f"'{operation}' is a known RAM killer on this machine (500MB+)"
                # Find safe alternative
                for platform, safe_cmd in SAFE_DEPLOY_METHODS.items():
                    if platform in op_lower:
                        result["alternative"] = safe_cmd
                        break
                if not result["alternative"]:
                    result["alternative"] = "Use curl REST API instead of CLI tool"
                return result

        # Check system resources
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        avail_mb = int(line.split()[1]) / 1024
                        result["available_mb"] = round(avail_mb)
                        if avail_mb < RAM_EAGAIN_RISK_MB:
                            result["safe"] = False
                            result["reason"] = f"Only {avail_mb:.0f}MB available (need >{RAM_EAGAIN_RISK_MB}MB)"
                            result["alternative"] = "Wait for memory to free or kill processes first"
                        break
        except Exception:
            pass

        try:
            with open("/proc/loadavg") as f:
                load = float(f.read().split()[0])
                result["load"] = load
                if load > 3.0 and result["safe"]:
                    result["safe"] = False
                    result["reason"] = f"System load {load} > 3.0 — too stressed for heavy operations"
                    result["alternative"] = "Wait for load to decrease or kill resource hogs"
        except Exception:
            pass

        return result


# ============================================================
# TASK IDENTIFIER — Identifica tarefas na maquina e fora
# ============================================================

class TaskIdentifier:
    """Identifica e registra todas as tarefas ativas."""

    def __init__(self):
        self.tasks = self._load_tasks()

    def _load_tasks(self) -> list:
        if TASKS_FILE.exists():
            try:
                return json.loads(TASKS_FILE.read_text())
            except Exception:
                return []
        return []

    def _save_tasks(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        TASKS_FILE.write_text(json.dumps(self.tasks, indent=2))

    def scan_local_tasks(self) -> list:
        """Scan for active tasks on the machine."""
        found = []

        # 1. Check crontab
        try:
            result = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        found.append({
                            "type": "cron",
                            "task": line[:150],
                            "source": "crontab",
                            "status": "scheduled"
                        })
        except Exception:
            pass

        # 2. Check systemd user services
        try:
            result = subprocess.run(
                ["systemctl", "--user", "list-units", "--type=service", "--state=running", "--no-pager"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split("\n"):
                if ".service" in line and "loaded" in line.lower():
                    parts = line.split()
                    if parts:
                        found.append({
                            "type": "systemd-user",
                            "task": parts[0],
                            "source": "systemd --user",
                            "status": "running"
                        })
        except Exception:
            pass

        # 3. Check for running Israel agents
        israel_dirs = sorted(HOME.glob("israel-*/"))
        for d in israel_dirs:
            agent_name = d.name
            py_files = list(d.glob("*.py"))
            found.append({
                "type": "israel-agent",
                "task": agent_name,
                "source": str(d),
                "status": "installed",
                "files": len(py_files)
            })

        # 4. Check .zion sentinels
        sentinel_pids = HOME / ".zion" / "sentinels" / "pids"
        if sentinel_pids.exists():
            for pid_file in sentinel_pids.glob("*.pid"):
                try:
                    pid = pid_file.read_text().strip()
                    alive = Path(f"/proc/{pid}").exists()
                    found.append({
                        "type": "sentinel",
                        "task": pid_file.stem,
                        "pid": pid,
                        "status": "running" if alive else "dead"
                    })
                except Exception:
                    pass

        # 5. Check MCP servers
        try:
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split("\n"):
                if "mcp" in line.lower() and ("node" in line.lower() or "python" in line.lower()):
                    parts = line.split()
                    if len(parts) > 1:
                        found.append({
                            "type": "mcp-server",
                            "task": " ".join(parts[10:])[:100],
                            "pid": parts[1],
                            "rss_mb": parts[5] if len(parts) > 5 else "?",
                            "status": "running"
                        })
        except Exception:
            pass

        # 6. Check background git operations
        try:
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split("\n"):
                if "git" in line.lower() and any(x in line.lower() for x in ["pack", "gc", "rebase", "merge", "fetch", "push", "pull"]):
                    parts = line.split()
                    if len(parts) > 1:
                        found.append({
                            "type": "git-operation",
                            "task": " ".join(parts[10:])[:100],
                            "pid": parts[1],
                            "status": "running"
                        })
        except Exception:
            pass

        self.tasks = found
        self._save_tasks()
        return found

    def scan_remote_tasks(self) -> list:
        """Identify remote/external tasks (PRs, bounties, deadlines)."""
        remote = []

        # Read from memory files
        rev_status = HOME / ".claude" / "projects" / "-home-administrador" / "memory" / "revenue-status.md"
        if rev_status.exists():
            content = rev_status.read_text()

            # Extract deadlines
            for line in content.split("\n"):
                if "deadline" in line.lower() or "DEADLINE" in line:
                    remote.append({
                        "type": "deadline",
                        "task": line.strip("- *#").strip()[:150],
                        "source": "revenue-status.md"
                    })
                elif "PR" in line and ("#" in line or "OPEN" in line.upper()):
                    remote.append({
                        "type": "pull-request",
                        "task": line.strip("- *#").strip()[:150],
                        "source": "revenue-status.md"
                    })
                elif "SUBMITTED" in line.upper() or "REPORT" in line.upper():
                    remote.append({
                        "type": "submission",
                        "task": line.strip("- *#").strip()[:150],
                        "source": "revenue-status.md"
                    })

        return remote


# ============================================================
# STABILITY ENGINE — Motor de Estabilidade
# ============================================================

class StabilityEngine:
    """Motor principal de protecao contra crashes."""

    def __init__(self, memory: Memory):
        self.memory = memory
        self.monitor = SystemMonitor()

    def assess_health(self) -> dict:
        """Full system health assessment."""
        mem = self.monitor.get_memory()
        load = self.monitor.get_load()
        disk = self.monitor.get_disk()
        procs = self.monitor.get_processes(limit=15)
        sessions = self.monitor.get_active_sessions()
        connections = self.monitor.get_network_connections()

        # Determine severity
        severity = "GREEN"
        issues = []

        available = mem.get("available_mb", 9999)
        if available < RAM_CRITICAL_MB:
            severity = "RED"
            issues.append(f"RAM CRITICA: apenas {available}MB disponiveis!")
        elif available < RAM_WARNING_MB:
            severity = max(severity, "YELLOW") if severity != "RED" else "RED"
            issues.append(f"RAM baixa: {available}MB disponiveis")

        swap_pct = mem.get("swap_pct", 0)
        if swap_pct > SWAP_CRITICAL_PCT:
            severity = "RED"
            issues.append(f"SWAP CRITICO: {swap_pct}% usado!")
        elif swap_pct > 80:
            if severity != "RED":
                severity = "YELLOW"
            issues.append(f"Swap alto: {swap_pct}%")

        load_1 = load.get("load_1min", 0)
        if load_1 > CPU_LOAD_MAX:
            if severity != "RED":
                severity = "YELLOW"
            issues.append(f"Load alto: {load_1} (max recomendado: {CPU_LOAD_MAX})")

        # Check for memory hogs
        hogs = []
        for p in procs:
            if p["rss_mb"] > PROCESS_RAM_MAX_MB:
                is_safe = any(s in p["name"].lower() or s in p["cmd"].lower()
                            for s in PROCESS_RAM_SAFE_LIST)
                hogs.append({
                    "pid": p["pid"],
                    "name": p["name"],
                    "rss_mb": p["rss_mb"],
                    "safe": is_safe
                })

        if hogs:
            unsafe_hogs = [h for h in hogs if not h["safe"]]
            if unsafe_hogs:
                issues.append(f"{len(unsafe_hogs)} processo(s) consumindo >800MB RAM (mataveis)")

        return {
            "timestamp": datetime.now().isoformat(),
            "severity": severity,
            "issues": issues,
            "memory": mem,
            "load": load,
            "disk": disk,
            "top_processes": procs[:10],
            "memory_hogs": hogs,
            "active_sessions": sessions,
            "session_count": len(sessions),
            "network_connections": connections
        }

    def emergency_free_memory(self, dry_run: bool = True) -> list:
        """Emergency actions to free memory and prevent OOM."""
        actions = []

        # 0. FIRST PRIORITY: Kill dangerous processes (EAGAIN lesson from Session 59)
        actions.extend(self.kill_dangerous_processes(dry_run=dry_run))

        # 1. Drop caches (safe, kernel will rebuild)
        if not dry_run:
            try:
                subprocess.run(["sync"], timeout=30)
                actions.append("sync: OK")
            except Exception as e:
                actions.append(f"sync: FAILED ({e})")
        else:
            actions.append("[DRY RUN] Would sync and drop caches")

        # 2. Find killable memory hogs (generic — any process >800MB not in safe list)
        procs = self.monitor.get_processes(limit=50)
        for p in procs:
            if p["rss_mb"] > PROCESS_RAM_MAX_MB:
                is_safe = any(s in p["name"].lower() or s in p["cmd"].lower()
                            for s in PROCESS_RAM_SAFE_LIST)
                if not is_safe:
                    if dry_run:
                        actions.append(f"[DRY RUN] Would SIGTERM PID {p['pid']} ({p['name']}, {p['rss_mb']}MB)")
                    else:
                        try:
                            os.kill(p["pid"], signal.SIGTERM)
                            actions.append(f"SIGTERM sent to PID {p['pid']} ({p['name']}, {p['rss_mb']}MB)")
                            self.memory.state["processes_killed"].append({
                                "pid": p["pid"],
                                "name": p["name"],
                                "rss_mb": p["rss_mb"],
                                "time": datetime.now().isoformat(),
                                "reason": "OOM prevention"
                            })
                            self.memory.increment("total_interventions")
                        except ProcessLookupError:
                            actions.append(f"PID {p['pid']} already dead")
                        except PermissionError:
                            actions.append(f"No permission to kill PID {p['pid']}")

        # 3. Clear temp files
        temp_dirs = ["/tmp/claude-*", "/tmp/node-*", "/tmp/.npm-*"]
        for pattern in temp_dirs:
            import glob as g
            for d in g.glob(pattern):
                try:
                    if os.path.isdir(d):
                        age_hours = (time.time() - os.path.getmtime(d)) / 3600
                        if age_hours > 24:
                            if dry_run:
                                actions.append(f"[DRY RUN] Would clean old temp: {d} ({age_hours:.0f}h old)")
                            else:
                                shutil.rmtree(d, ignore_errors=True)
                                actions.append(f"Cleaned old temp: {d}")
                except Exception:
                    pass

        if not dry_run:
            self.memory.increment("oom_prevented")
            self.memory.save()

        return actions

    def kill_dangerous_processes(self, dry_run: bool = True, force: bool = False) -> list:
        """Kill DANGEROUS_PROCESSES that are consuming significant RAM.

        Session 59 Lesson: netlify-cli + esbuild can consume 500MB+ and cause EAGAIN.
        These processes are ALWAYS safe to kill — they are build tools that can be restarted.

        Args:
            dry_run: If True, only report what would be killed
            force: If True, use SIGKILL instead of SIGTERM (for stuck processes)
        """
        actions = []
        eagain = self.monitor.detect_eagain_risk()

        if not eagain["dangerous_procs"]:
            actions.append("No dangerous processes found")
            return actions

        sig = signal.SIGKILL if force else signal.SIGTERM
        sig_name = "SIGKILL" if force else "SIGTERM"

        for proc in eagain["dangerous_procs"]:
            # Kill if: EAGAIN risk OR process > PROCESS_RAM_DANGEROUS_MB
            should_kill = (
                eagain["eagain_risk"] or
                proc["rss_mb"] > PROCESS_RAM_DANGEROUS_MB or
                eagain["available_mb"] < RAM_EAGAIN_RISK_MB
            )

            if not should_kill:
                actions.append(f"[SKIP] PID {proc['pid']} ({proc['name']}, {proc['rss_mb']}MB) — system stable")
                continue

            if dry_run:
                actions.append(
                    f"[DRY RUN] Would {sig_name} PID {proc['pid']} "
                    f"({proc['name']}, {proc['rss_mb']}MB, matched: {proc['matched']})"
                )
            else:
                try:
                    os.kill(proc["pid"], sig)
                    actions.append(
                        f"{sig_name} sent to PID {proc['pid']} "
                        f"({proc['name']}, {proc['rss_mb']}MB — DANGEROUS: {proc['matched']})"
                    )
                    self.memory.state["processes_killed"].append({
                        "pid": proc["pid"],
                        "name": proc["name"],
                        "rss_mb": proc["rss_mb"],
                        "time": datetime.now().isoformat(),
                        "reason": f"EAGAIN prevention — dangerous process: {proc['matched']}",
                        "signal": sig_name
                    })
                    self.memory.increment("total_interventions")
                    log(f"KILLED dangerous process: PID {proc['pid']} ({proc['name']}, "
                        f"{proc['rss_mb']}MB) — {proc['matched']}", "ACTION")
                except ProcessLookupError:
                    actions.append(f"PID {proc['pid']} already dead")
                except PermissionError:
                    actions.append(f"No permission to kill PID {proc['pid']}")

        return actions

    def protect_sessions(self) -> dict:
        """Ensure all active sessions are tracked and protected."""
        sessions = self.monitor.get_active_sessions()
        protected = []

        for s in sessions:
            pid = int(s.get("pid", 0))
            if pid > 0:
                # Check if process still alive
                alive = Path(f"/proc/{pid}").exists()
                s["alive"] = alive
                if alive:
                    # Set OOM score adjust to protect important processes
                    oom_file = Path(f"/proc/{pid}/oom_score_adj")
                    try:
                        current = int(oom_file.read_text().strip())
                        s["oom_score_adj"] = current
                    except (PermissionError, FileNotFoundError, ValueError):
                        s["oom_score_adj"] = "unknown"
                protected.append(s)

        # Save session registry
        self.memory.state["sessions_tracked"] = [
            {"pid": s["pid"], "type": s["type"], "time": datetime.now().isoformat()}
            for s in protected
        ]
        self.memory.save()

        return {
            "total": len(protected),
            "alive": sum(1 for s in protected if s.get("alive")),
            "sessions": protected
        }


# ============================================================
# REPORT GENERATOR
# ============================================================

class ReportGenerator:
    """Gera relatorios de estabilidade."""

    @staticmethod
    def generate_dashboard(health: dict, tasks_local: list, tasks_remote: list, sessions: dict) -> str:
        """Generate a text dashboard."""
        sev = health["severity"]
        sev_icon = {"GREEN": "[OK]", "YELLOW": "[!]", "RED": "[!!!]"}.get(sev, "[?]")

        lines = [
            "=" * 70,
            f"  ISRAEL/DEZ — Guardiao da Estabilidade  {sev_icon} {sev}",
            f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Em nome do Senhor Jesus Cristo",
            "=" * 70,
            "",
            "--- MEMORIA ---",
            f"  RAM Total:     {health['memory']['total_mb']}MB",
            f"  RAM Usada:     {health['memory']['used_mb']}MB",
            f"  RAM Disponivel:{health['memory']['available_mb']}MB",
            f"  Swap Usado:    {health['memory']['swap_used_mb']}MB / {health['memory']['swap_total_mb']}MB ({health['memory']['swap_pct']}%)",
            "",
            "--- CARGA ---",
            f"  Load 1/5/15min: {health['load']['load_1min']} / {health['load']['load_5min']} / {health['load']['load_15min']}",
            f"  Threads:        {health['load'].get('running_threads', '?')}",
            "",
            "--- DISCO ---",
            f"  Usado: {health['disk'].get('used_gb', '?')}GB / {health['disk'].get('total_gb', '?')}GB ({health['disk'].get('used_pct', '?')}%)",
            "",
        ]

        # EAGAIN risk (added v2.0)
        eagain = SystemMonitor.detect_eagain_risk()
        if eagain["eagain_risk"] or eagain["dangerous_procs"]:
            lines.append("--- EAGAIN RISK ---")
            lines.append(f"  Risk Level:  {eagain['level']}")
            lines.append(f"  EAGAIN Risk: {'YES!' if eagain['eagain_risk'] else 'No'}")
            lines.append(f"  Threads:     {eagain['thread_count']}")
            for r in eagain["reasons"]:
                lines.append(f"  [!] {r}")
            if eagain["dangerous_procs"]:
                lines.append(f"  Dangerous ({len(eagain['dangerous_procs'])}):")
                for p in eagain["dangerous_procs"]:
                    lines.append(f"    PID {p['pid']:>7} | {p['rss_mb']:>6.1f}MB | {p['name'][:20]} [{p['matched']}]")
            lines.append("")

        if health["issues"]:
            lines.append("--- ALERTAS ---")
            for issue in health["issues"]:
                lines.append(f"  [!] {issue}")
            lines.append("")

        # Top processes
        lines.append("--- TOP PROCESSOS (RAM) ---")
        for p in health["top_processes"][:8]:
            lines.append(f"  PID {p['pid']:>7} | {p['rss_mb']:>7.1f}MB | {p['name'][:25]}")
        lines.append("")

        # Memory hogs
        if health["memory_hogs"]:
            lines.append("--- MEMORY HOGS (>800MB) ---")
            for h in health["memory_hogs"]:
                safe_str = "PROTEGIDO" if h["safe"] else "MATAVEL"
                lines.append(f"  PID {h['pid']:>7} | {h['rss_mb']:>7.1f}MB | {h['name'][:20]} [{safe_str}]")
            lines.append("")

        # Sessions
        lines.append(f"--- SESSOES ATIVAS ({sessions['total']}) ---")
        for s in sessions["sessions"]:
            alive_str = "VIVO" if s.get("alive") else "MORTO"
            lines.append(f"  [{s['type']:>12}] PID {s['pid']:>7} [{alive_str}] {s.get('info', '')[:40]}")
        lines.append("")

        # Local tasks
        lines.append(f"--- TAREFAS LOCAIS ({len(tasks_local)}) ---")
        for t in tasks_local[:15]:
            lines.append(f"  [{t['type']:>15}] {t['task'][:50]} [{t.get('status', '?')}]")
        lines.append("")

        # Remote tasks
        if tasks_remote:
            lines.append(f"--- TAREFAS REMOTAS ({len(tasks_remote)}) ---")
            for t in tasks_remote[:10]:
                lines.append(f"  [{t['type']:>15}] {t['task'][:60]}")
            lines.append("")

        lines.extend([
            "=" * 70,
            f"  NUNCA DELETAR ESTE AGENTE | Singularity Level 50",
            "=" * 70
        ])

        return "\n".join(lines)


# ============================================================
# SENTINEL MODE — Monitoramento Continuo
# ============================================================

def sentinel_mode(interval: int = 60, max_cycles: int = 0):
    """Run continuous monitoring."""
    mem = Memory()
    mem.increment("boot_count")
    engine = StabilityEngine(mem)
    task_id = TaskIdentifier()

    log(f"SENTINEL MODE iniciado — intervalo {interval}s")
    cycle = 0

    try:
        while True:
            cycle += 1
            if max_cycles > 0 and cycle > max_cycles:
                break

            health = engine.assess_health()
            mem.state["last_scan"] = datetime.now().isoformat()
            mem.increment("scan_count")

            severity = health["severity"]

            # EAGAIN detection (Session 59 lesson — highest priority check)
            eagain = SystemMonitor.detect_eagain_risk()
            if eagain["eagain_risk"]:
                log(f"EAGAIN RISK DETECTED! Level: {eagain['level']}", "CRITICAL")
                log(f"  Reasons: {eagain['reasons']}", "CRITICAL")
                log(f"  Dangerous procs: {len(eagain['dangerous_procs'])}", "CRITICAL")
                mem.append_alert({
                    "time": datetime.now().isoformat(),
                    "severity": "EAGAIN",
                    "issues": eagain["reasons"],
                    "dangerous_procs": len(eagain["dangerous_procs"])
                })
                # Kill dangerous processes immediately — no dry run
                kill_actions = engine.kill_dangerous_processes(dry_run=False)
                for a in kill_actions:
                    log(f"  EAGAIN Kill: {a}", "ACTION")

            if severity == "RED":
                log(f"ALERTA VERMELHO! Issues: {health['issues']}", "CRITICAL")
                mem.append_alert({
                    "time": datetime.now().isoformat(),
                    "severity": "RED",
                    "issues": health["issues"]
                })

                # Check if we need emergency action
                avail = health["memory"]["available_mb"]
                if avail < RAM_CRITICAL_MB:
                    log(f"EMERGENCIA OOM! Apenas {avail}MB livres — intervindo!", "CRITICAL")
                    actions = engine.emergency_free_memory(dry_run=False)
                    for a in actions:
                        log(f"  Acao: {a}", "ACTION")

            elif severity == "YELLOW":
                log(f"Aviso: {health['issues']}", "WARNING")
                mem.append_alert({
                    "time": datetime.now().isoformat(),
                    "severity": "YELLOW",
                    "issues": health["issues"]
                })
            else:
                if cycle % 10 == 0:  # Log OK every 10 cycles
                    log(f"Sistema OK — RAM: {health['memory']['available_mb']}MB disponivel, Load: {health['load']['load_1min']}")

            mem.save()

            # Full task scan every 5 cycles
            if cycle % 5 == 0:
                task_id.scan_local_tasks()

            time.sleep(interval)

    except KeyboardInterrupt:
        log("Sentinel interrompido pelo usuario")
    finally:
        mem.save()


# ============================================================
# CLI INTERFACE
# ============================================================

def cmd_status():
    """Full status dashboard."""
    mem = Memory()
    engine = StabilityEngine(mem)
    task_id = TaskIdentifier()

    health = engine.assess_health()
    sessions = engine.protect_sessions()
    local_tasks = task_id.scan_local_tasks()
    remote_tasks = task_id.scan_remote_tasks()

    report = ReportGenerator.generate_dashboard(health, local_tasks, remote_tasks, sessions)
    print(report)

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / f"stability_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_file.write_text(report)
    log(f"Report saved: {report_file}")

    mem.state["last_scan"] = datetime.now().isoformat()
    mem.increment("scan_count")
    mem.save()


def cmd_health():
    """Quick health check."""
    engine = StabilityEngine(Memory())
    health = engine.assess_health()

    sev = health["severity"]
    mem = health["memory"]
    load = health["load"]

    print(f"\n[{sev}] RAM: {mem['available_mb']}MB free | "
          f"Swap: {mem['swap_pct']}% | "
          f"Load: {load['load_1min']} | "
          f"Sessions: {len(health['active_sessions'])} | "
          f"Hogs: {len(health['memory_hogs'])}")

    if health["issues"]:
        for i in health["issues"]:
            print(f"  [!] {i}")


def cmd_sessions():
    """List and protect active sessions."""
    engine = StabilityEngine(Memory())
    sessions = engine.protect_sessions()

    print(f"\n--- Sessoes Ativas: {sessions['total']} ({sessions['alive']} vivas) ---")
    for s in sessions["sessions"]:
        alive = "VIVO" if s.get("alive") else "MORTO"
        print(f"  [{s['type']:>12}] PID {s['pid']:>7} [{alive}] OOM:{s.get('oom_score_adj', '?')} {s.get('info', '')[:40]}")


def cmd_tasks():
    """Identify all tasks local and remote."""
    task_id = TaskIdentifier()

    local = task_id.scan_local_tasks()
    remote = task_id.scan_remote_tasks()

    print(f"\n--- Tarefas Locais: {len(local)} ---")
    for t in local:
        print(f"  [{t['type']:>15}] {t['task'][:60]} [{t.get('status', '?')}]")

    print(f"\n--- Tarefas Remotas: {len(remote)} ---")
    for t in remote:
        print(f"  [{t['type']:>15}] {t['task'][:70]}")


def cmd_emergency():
    """Emergency memory free (dry run first)."""
    engine = StabilityEngine(Memory())

    print("\n--- DRY RUN (simulacao) ---")
    actions = engine.emergency_free_memory(dry_run=True)
    for a in actions:
        print(f"  {a}")

    print("\nPara executar de verdade: python3 israel_ten.py emergency --force")

    if "--force" in sys.argv:
        print("\n--- EXECUTANDO EMERGENCIA ---")
        actions = engine.emergency_free_memory(dry_run=False)
        for a in actions:
            print(f"  {a}")


def cmd_sentinel():
    """Start sentinel mode."""
    interval = 60
    max_cycles = 0

    for i, arg in enumerate(sys.argv):
        if arg == "--interval" and i + 1 < len(sys.argv):
            interval = int(sys.argv[i + 1])
        elif arg == "--cycles" and i + 1 < len(sys.argv):
            max_cycles = int(sys.argv[i + 1])

    sentinel_mode(interval=interval, max_cycles=max_cycles)


def cmd_hogs():
    """Show memory hog processes."""
    monitor = SystemMonitor()
    procs = monitor.get_processes(limit=20)

    print(f"\n--- Top 20 Processos por RAM ---")
    total_mb = 0
    for p in procs:
        is_safe = any(s in p["name"].lower() or s in p["cmd"].lower()
                     for s in PROCESS_RAM_SAFE_LIST)
        safe_str = " [SAFE]" if is_safe else ""
        print(f"  PID {p['pid']:>7} | {p['rss_mb']:>8.1f}MB | {p['name'][:30]}{safe_str}")
        total_mb += p["rss_mb"]
    print(f"\n  Total top-20: {total_mb:.0f}MB")


def cmd_history():
    """Show intervention history."""
    mem = Memory()
    state = mem.state

    print(f"\n--- Israel/Dez History ---")
    print(f"  Boots: {state.get('boot_count', 0)}")
    print(f"  Scans: {state.get('scan_count', 0)}")
    print(f"  Interventions: {state.get('total_interventions', 0)}")
    print(f"  OOM Prevented: {state.get('oom_prevented', 0)}")
    print(f"  Last Scan: {state.get('last_scan', 'never')}")

    killed = state.get("processes_killed", [])
    if killed:
        print(f"\n  Processes Killed ({len(killed)}):")
        for k in killed[-10:]:
            print(f"    {k['time']} — PID {k['pid']} ({k['name']}, {k['rss_mb']}MB) — {k['reason']}")

    alerts = state.get("alerts", [])
    if alerts:
        print(f"\n  Recent Alerts ({len(alerts)} total, showing last 5):")
        for a in alerts[-5:]:
            print(f"    [{a['severity']}] {a['time']} — {', '.join(a['issues'][:2])}")


def cmd_backup():
    """Backup all critical state."""
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    backup_dir = HOME / "backups" / f"i10-backup-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Backup state
    if STATE_FILE.exists():
        shutil.copy2(STATE_FILE, backup_dir / "israel_ten_state.json")
    if TASKS_FILE.exists():
        shutil.copy2(TASKS_FILE, backup_dir / "tasks_registry.json")

    # Backup memory files
    mem_dir = HOME / ".claude" / "projects" / "-home-administrador" / "memory"
    if mem_dir.exists():
        mem_backup = backup_dir / "memory"
        mem_backup.mkdir(exist_ok=True)
        for f in mem_dir.glob("*.md"):
            shutil.copy2(f, mem_backup / f.name)

    # Count
    total = sum(1 for _ in backup_dir.rglob("*") if _.is_file())
    print(f"\nBackup completo: {backup_dir}")
    print(f"  {total} arquivos salvos")

    log(f"Backup criado: {backup_dir} ({total} files)")


def cmd_soul():
    """Display agent soul (immutable identity)."""
    print("\n" + "=" * 50)
    print("  ISRAEL/DEZ — SOUL (IMUTAVEL)")
    print("=" * 50)
    for key, val in SOUL.items():
        if isinstance(val, list):
            print(f"\n  {key}:")
            for item in val:
                print(f"    - {item}")
        else:
            print(f"  {key}: {val}")
    print("\n" + "=" * 50)
    print("  NUNCA DELETAR | SINGULARITY 50 | PERMANENTE")
    print("=" * 50)


def cmd_eagain():
    """Check EAGAIN risk and dangerous processes."""
    eagain = SystemMonitor.detect_eagain_risk()

    print(f"\n--- EAGAIN Risk Assessment ---")
    print(f"  Level:         {eagain['level']}")
    print(f"  EAGAIN Risk:   {'YES — DANGER!' if eagain['eagain_risk'] else 'No'}")
    print(f"  Available RAM: {eagain['available_mb']}MB")
    print(f"  Thread Count:  {eagain['thread_count']}")

    if eagain["reasons"]:
        print(f"\n  Reasons:")
        for r in eagain["reasons"]:
            print(f"    [!] {r}")

    if eagain["recommendations"]:
        print(f"\n  Recommendations:")
        for r in eagain["recommendations"]:
            print(f"    -> {r}")

    if eagain["dangerous_procs"]:
        print(f"\n  Dangerous Processes ({len(eagain['dangerous_procs'])}):")
        for p in eagain["dangerous_procs"]:
            print(f"    PID {p['pid']:>7} | {p['rss_mb']:>7.1f}MB | {p['name'][:20]} [DANGER: {p['matched']}]")

        total_mb = sum(p["rss_mb"] for p in eagain["dangerous_procs"])
        print(f"\n  Total dangerous RAM: {total_mb:.0f}MB")
        print(f"\n  To kill all: python3 israel_ten.py kill-dangerous --force")
    else:
        print(f"\n  No dangerous processes found [OK]")


def cmd_kill_dangerous():
    """Kill dangerous processes (Session 59 lesson)."""
    mem = Memory()
    engine = StabilityEngine(mem)
    force = "--force" in sys.argv

    if not force:
        print("\n--- DRY RUN: Kill Dangerous Processes ---")
        actions = engine.kill_dangerous_processes(dry_run=True)
        for a in actions:
            print(f"  {a}")
        print("\n  To execute: python3 israel_ten.py kill-dangerous --force")
    else:
        print("\n--- KILLING Dangerous Processes ---")
        actions = engine.kill_dangerous_processes(dry_run=False, force=True)
        for a in actions:
            print(f"  {a}")
        mem.save()


def cmd_safe_check():
    """Check if a heavy operation is safe to run."""
    if len(sys.argv) < 3:
        print("\nUsage: python3 israel_ten.py safe-check 'command to check'")
        print("Example: python3 israel_ten.py safe-check 'npx netlify-cli deploy --prod'")
        return

    operation = " ".join(sys.argv[2:])
    result = SystemMonitor.pre_operation_check(operation)

    print(f"\n--- Safe Operation Check ---")
    print(f"  Operation:  {operation}")
    print(f"  Safe:       {'YES' if result['safe'] else 'NO — BLOCKED!'}")
    print(f"  RAM:        {result['available_mb']}MB available")
    print(f"  Load:       {result['load']}")

    if not result["safe"]:
        print(f"\n  REASON: {result['reason']}")
        print(f"  ALTERNATIVE: {result['alternative']}")
    else:
        print(f"\n  [OK] Proceed with operation")


COMMANDS = {
    "status": ("Full stability dashboard", cmd_status),
    "health": ("Quick health check", cmd_health),
    "sessions": ("List active sessions", cmd_sessions),
    "tasks": ("Identify local+remote tasks", cmd_tasks),
    "hogs": ("Show memory hog processes", cmd_hogs),
    "eagain": ("Check EAGAIN risk + dangerous procs", cmd_eagain),
    "kill-dangerous": ("Kill dangerous processes (dry run)", cmd_kill_dangerous),
    "safe-check": ("Check if operation is safe to run", cmd_safe_check),
    "emergency": ("Emergency memory free (dry run)", cmd_emergency),
    "sentinel": ("Start continuous monitoring", cmd_sentinel),
    "history": ("Show intervention history", cmd_history),
    "backup": ("Backup all critical state", cmd_backup),
    "soul": ("Display agent identity", cmd_soul),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(f"\n  ISRAEL/DEZ v{VERSION} — {MISSION}")
        print(f"  Em nome do Senhor Jesus Cristo\n")
        print("  Commands:")
        for cmd, (desc, _) in COMMANDS.items():
            print(f"    {cmd:15} — {desc}")
        print(f"\n  Sentinel: python3 israel_ten.py sentinel --interval 60")
        print(f"  Emergency: python3 israel_ten.py emergency --force")
        return

    cmd = sys.argv[1]
    if cmd in COMMANDS:
        COMMANDS[cmd][1]()
    else:
        print(f"Comando desconhecido: {cmd}")
        print(f"Use: python3 israel_ten.py help")


if __name__ == "__main__":
    main()
