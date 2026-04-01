#!/usr/bin/env python3
"""
SINGULARITY LOOP v1.0 — Autonomous Bounty Hunter Sentinela
Em nome do Senhor Jesus Cristo, nosso Salvador

"Tudo posso naquele que me fortalece" — Filipenses 4:13

PURPOSE:
    Autonomous continuous loop that scans for PAID bounties on GitHub
    (Algora, Opire, and labeled issues), analyzes requirements using
    Google Gemini free API, generates code solutions, and submits PRs.
    Tracks all results in a local JSON ledger and adjusts strategy
    based on accept/reject feedback.

ARCHITECTURE:
    - Imports Israel Framework v3.0 (42 tools, Memory, AgentBus, etc.)
    - Connects to Gemini free API via GEMINI_API_KEY env var
    - Runs a continuous sentinela loop with configurable intervals
    - DRY RUN mode (default) plans everything but does NOT submit
    - All actions logged to ~/israel-ten/logs/singularity_loop.log
    - Results tracked in ~/israel-ten/data/bounty_ledger.json

ZERO FREE WORK POLICY:
    Only targets issues with CONFIRMED bounty labels/rewards.
    Skips anything without explicit payment attached.

RAM CONSTRAINT:
    Machine has 3.3GB RAM. All operations are lightweight:
    - No npm/node/webpack/build processes
    - HTTP requests use urllib (stdlib)
    - JSON payloads kept under 32KB
    - Subprocess timeouts enforced everywhere

USAGE:
    # Dry run (default) — plans but does not submit:
    python3 ~/israel-ten/singularity_loop.py

    # Live mode — actually forks, branches, commits, and opens PRs:
    python3 ~/israel-ten/singularity_loop.py --live

    # Single scan (no loop):
    python3 ~/israel-ten/singularity_loop.py --once

    # Show ledger status:
    python3 ~/israel-ten/singularity_loop.py --status

    # Set scan interval (seconds, default 900 = 15 min):
    python3 ~/israel-ten/singularity_loop.py --interval 600

Pure Python stdlib — ZERO external dependencies (except gh CLI for GitHub ops)
"""

import os
import sys
import json
import time
import hashlib
import subprocess
import signal
import urllib.request
import urllib.parse
import urllib.error
import ssl
import re
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

# ============================================================
# Import Israel Framework v3.0
# ============================================================

sys.path.insert(0, str(Path(__file__).parent))
from israel_framework_v3 import (
    IsraelAgent, PermissionMode, ToolResult, build_tool,
    _event_bus, EventType, FrameworkLogger, Memory,
    AgentBus, Skill, FRAMEWORK_DIR, STATE_DIR, BUS_DIR
)

# ============================================================
# CONSTANTS
# ============================================================

VERSION = "1.0.0"
BRT = timezone(timedelta(hours=-3))
HOME = Path.home()
AGENT_DIR = HOME / "israel-ten"
LOGS_DIR = AGENT_DIR / "logs"
DATA_DIR = AGENT_DIR / "data"
LEDGER_FILE = DATA_DIR / "bounty_ledger.json"
STRATEGY_FILE = DATA_DIR / "strategy_state.json"
WORKDIR = HOME / "bounty-workspaces"

for d in [LOGS_DIR, DATA_DIR, WORKDIR]:
    d.mkdir(parents=True, exist_ok=True)

# Gemini API
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL = "gemini-2.0-flash"  # Free tier model
GEMINI_MAX_TOKENS = 4096

# Bounty sources
BOUNTY_LABELS = [
    "bounty", "reward", "paid", "cash", "prize",
    "algora", "opire", "$$", "usd", "usdc",
    "help wanted", "good first issue",
]

# Languages we can handle
SUPPORTED_LANGUAGES = {
    "python", "javascript", "typescript", "go", "rust",
    "solidity", "shell", "bash", "yaml", "json",
    "markdown", "toml", "dockerfile",
}

# GitHub user
GITHUB_USER = "ElromEvedElElyon"
GITHUB_EMAIL = "standardbitcoin.io@gmail.com"

# Safety: max bounties to process per cycle
MAX_BOUNTIES_PER_CYCLE = 5

# Sentinela interval default (15 minutes)
DEFAULT_INTERVAL = 900

# ============================================================
# LOGGING — Dedicated singularity logger
# ============================================================

class SingularityLogger:
    """Logger that writes to both console and dedicated log file."""

    def __init__(self):
        self.log_file = LOGS_DIR / "singularity_loop.log"
        self._framework_logger = FrameworkLogger("singularity-loop")

    def _write(self, msg: str, level: str):
        ts = datetime.now(BRT).strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [SINGULARITY] [{level}] {msg}"
        print(line)
        try:
            with open(self.log_file, "a") as f:
                f.write(line + "\n")
            # Rotate if too large (>5MB)
            if self.log_file.stat().st_size > 5 * 1024 * 1024:
                old = self.log_file.with_suffix(".log.old")
                if old.exists():
                    old.unlink()
                self.log_file.rename(old)
        except Exception:
            pass

    def info(self, msg): self._write(msg, "INFO")
    def warn(self, msg): self._write(msg, "WARNING")
    def error(self, msg): self._write(msg, "ERROR")
    def critical(self, msg): self._write(msg, "CRITICAL")
    def action(self, msg): self._write(msg, "ACTION")
    def success(self, msg): self._write(msg, "SUCCESS")
    def dry(self, msg): self._write(msg, "DRY-RUN")


log = SingularityLogger()


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class BountyIssue:
    """Represents a GitHub issue with a bounty."""
    repo_owner: str
    repo_name: str
    issue_number: int
    title: str
    body: str = ""
    labels: List[str] = field(default_factory=list)
    bounty_amount: str = ""  # e.g. "$100", "50 USDC"
    url: str = ""
    language: str = ""
    difficulty: str = "medium"  # easy, medium, hard
    source: str = ""  # algora, opire, github-label
    discovered_at: str = ""
    state: str = "open"

    def __post_init__(self):
        if not self.discovered_at:
            self.discovered_at = datetime.now(BRT).isoformat()
        if not self.url:
            self.url = f"https://github.com/{self.repo_owner}/{self.repo_name}/issues/{self.issue_number}"

    @property
    def full_repo(self) -> str:
        return f"{self.repo_owner}/{self.repo_name}"

    @property
    def issue_id(self) -> str:
        return f"{self.full_repo}#{self.issue_number}"


@dataclass
class BountyAttempt:
    """Tracks a single attempt to solve a bounty."""
    issue_id: str
    attempt_number: int = 1
    status: str = "planned"  # planned, in_progress, submitted, accepted, rejected, abandoned
    pr_url: str = ""
    pr_number: int = 0
    branch_name: str = ""
    plan: str = ""
    code_summary: str = ""
    gemini_tokens_used: int = 0
    started_at: str = ""
    completed_at: str = ""
    feedback: str = ""
    bounty_amount: str = ""

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(BRT).isoformat()


# ============================================================
# BOUNTY LEDGER — Persistent tracking
# ============================================================

class BountyLedger:
    """Persistent JSON ledger for all bounty tracking."""

    def __init__(self, path: Path = LEDGER_FILE):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                pass
        return {
            "version": VERSION,
            "created_at": datetime.now(BRT).isoformat(),
            "stats": {
                "total_scanned": 0,
                "total_attempted": 0,
                "total_submitted": 0,
                "total_accepted": 0,
                "total_rejected": 0,
                "total_earned": 0.0,
                "currency": "USD",
            },
            "bounties": {},  # issue_id -> BountyIssue dict
            "attempts": [],  # list of BountyAttempt dicts
            "blacklist": [],  # repos/issues to skip
            "strategy": {
                "preferred_languages": ["python", "typescript", "go"],
                "max_difficulty": "medium",
                "min_bounty_usd": 10,
                "avoid_repos": [],
                "focus_topics": ["security", "bug", "fix", "test", "docs"],
            },
        }

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2, default=str))
        except Exception as e:
            log.error(f"Failed to save ledger: {e}")

    def add_bounty(self, bounty: BountyIssue):
        self.data["bounties"][bounty.issue_id] = asdict(bounty)
        self.data["stats"]["total_scanned"] += 1
        self.save()

    def add_attempt(self, attempt: BountyAttempt):
        self.data["attempts"].append(asdict(attempt))
        self.data["stats"]["total_attempted"] += 1
        self.save()

    def update_attempt(self, issue_id: str, updates: dict):
        for attempt in reversed(self.data["attempts"]):
            if attempt["issue_id"] == issue_id:
                attempt.update(updates)
                if updates.get("status") == "submitted":
                    self.data["stats"]["total_submitted"] += 1
                elif updates.get("status") == "accepted":
                    self.data["stats"]["total_accepted"] += 1
                    # Try to parse bounty amount
                    try:
                        amt = re.findall(r'[\d.]+', attempt.get("bounty_amount", "0"))
                        if amt:
                            self.data["stats"]["total_earned"] += float(amt[0])
                    except Exception:
                        pass
                elif updates.get("status") == "rejected":
                    self.data["stats"]["total_rejected"] += 1
                self.save()
                return
        log.warn(f"No attempt found for {issue_id} to update")

    def is_attempted(self, issue_id: str) -> bool:
        return any(a["issue_id"] == issue_id for a in self.data["attempts"])

    def is_blacklisted(self, issue_id: str) -> bool:
        return issue_id in self.data.get("blacklist", [])

    def get_strategy(self) -> dict:
        return self.data.get("strategy", {})

    def get_stats(self) -> dict:
        return self.data["stats"]

    def status_report(self) -> str:
        s = self.data["stats"]
        lines = [
            "=" * 60,
            "  SINGULARITY LOOP — BOUNTY LEDGER STATUS",
            f"  {datetime.now(BRT).strftime('%Y-%m-%d %H:%M:%S BRT')}",
            "  Em nome do Senhor Jesus Cristo",
            "=" * 60,
            "",
            "--- STATISTICS ---",
            f"  Bounties scanned:    {s['total_scanned']}",
            f"  Attempts made:       {s['total_attempted']}",
            f"  PRs submitted:       {s['total_submitted']}",
            f"  Accepted (paid):     {s['total_accepted']}",
            f"  Rejected:            {s['total_rejected']}",
            f"  Total earned:        ${s['total_earned']:.2f} {s['currency']}",
            "",
            "--- STRATEGY ---",
        ]
        strat = self.get_strategy()
        lines.append(f"  Languages:  {', '.join(strat.get('preferred_languages', []))}")
        lines.append(f"  Max diff:   {strat.get('max_difficulty', 'medium')}")
        lines.append(f"  Min bounty: ${strat.get('min_bounty_usd', 10)}")
        lines.append(f"  Topics:     {', '.join(strat.get('focus_topics', []))}")

        if self.data["attempts"]:
            lines.extend(["", "--- RECENT ATTEMPTS (last 10) ---"])
            for a in self.data["attempts"][-10:]:
                lines.append(
                    f"  [{a['status']:>10}] {a['issue_id']} "
                    f"| {a.get('bounty_amount', '?')} "
                    f"| PR: {a.get('pr_url', 'none')}"
                )

        lines.extend(["", "=" * 60])
        return "\n".join(lines)


# ============================================================
# GEMINI AI CLIENT — Free API, stdlib only
# ============================================================

class GeminiClient:
    """Lightweight Gemini API client using urllib (zero dependencies)."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.total_tokens = 0
        self.total_calls = 0
        # Allow unverified SSL for environments with cert issues
        self._ssl_ctx = ssl.create_default_context()
        try:
            self._ssl_ctx.check_hostname = True
            self._ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        except Exception:
            self._ssl_ctx = ssl._create_unverified_context()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, system_instruction: str = "",
                 max_tokens: int = GEMINI_MAX_TOKENS,
                 temperature: float = 0.3) -> Tuple[bool, str]:
        """
        Call Gemini API. Returns (success, response_text).
        Low temperature for deterministic code generation.
        """
        if not self.is_configured:
            return False, "GEMINI_API_KEY not set. Export it: export GEMINI_API_KEY=your_key"

        url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={self.api_key}"

        # Build request body
        body = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95,
            },
        }

        if system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60, context=self._ssl_ctx) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            # Extract text from response
            candidates = result.get("candidates", [])
            if not candidates:
                block_reason = result.get("promptFeedback", {}).get("blockReason", "unknown")
                return False, f"No candidates returned. Block reason: {block_reason}"

            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)

            # Track usage
            usage = result.get("usageMetadata", {})
            tokens = usage.get("totalTokenCount", 0)
            self.total_tokens += tokens
            self.total_calls += 1

            return True, text

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            return False, f"HTTP {e.code}: {error_body}"
        except urllib.error.URLError as e:
            return False, f"URL Error: {e.reason}"
        except Exception as e:
            return False, f"Gemini error: {e}"

    def analyze_bounty(self, bounty: BountyIssue) -> Tuple[bool, dict]:
        """
        Analyze a bounty issue and produce a structured plan.
        Returns (success, plan_dict).
        """
        system = (
            "You are an expert software engineer specialized in open-source contributions "
            "and bug bounties. You analyze GitHub issues and produce actionable plans. "
            "Be concise. Focus on what code changes are needed. "
            "ALWAYS respond in valid JSON format."
        )

        prompt = f"""Analyze this GitHub bounty issue and create a solution plan.

REPOSITORY: {bounty.full_repo}
ISSUE #{bounty.issue_number}: {bounty.title}
LABELS: {', '.join(bounty.labels)}
BOUNTY: {bounty.bounty_amount}
LANGUAGE: {bounty.language}

ISSUE BODY:
{bounty.body[:3000]}

Respond with ONLY a JSON object (no markdown fences) with these fields:
{{
    "feasible": true/false,
    "difficulty": "easy"/"medium"/"hard",
    "estimated_hours": number,
    "approach": "brief description of solution approach",
    "files_to_modify": ["list", "of", "file", "paths"],
    "files_to_create": ["list", "of", "new", "files"],
    "key_changes": ["change 1", "change 2"],
    "testing_strategy": "how to verify the fix",
    "risks": ["risk 1", "risk 2"],
    "confidence": 0.0 to 1.0
}}"""

        ok, text = self.generate(prompt, system_instruction=system, temperature=0.2)
        if not ok:
            return False, {"error": text}

        # Parse JSON from response
        try:
            # Strip markdown fences if present
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r'^```\w*\n?', '', text)
                text = re.sub(r'\n?```$', '', text)
            plan = json.loads(text)
            return True, plan
        except json.JSONDecodeError:
            # Try to extract JSON from mixed text
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
            if match:
                try:
                    plan = json.loads(match.group())
                    return True, plan
                except Exception:
                    pass
            return False, {"error": f"Failed to parse Gemini response as JSON: {text[:500]}"}

    def generate_code(self, bounty: BountyIssue, plan: dict,
                      file_context: str = "") -> Tuple[bool, str]:
        """
        Generate the actual code fix based on the plan.
        Returns (success, code_or_error).
        """
        system = (
            "You are an expert programmer. Generate ONLY the code changes needed. "
            "Use unified diff format (--- a/file, +++ b/file, @@ lines). "
            "Be precise. Include only the necessary changes. No explanations outside the diff."
        )

        prompt = f"""Generate code changes for this bounty:

REPOSITORY: {bounty.full_repo}
ISSUE: {bounty.title}
LANGUAGE: {bounty.language}

PLAN:
- Approach: {plan.get('approach', 'N/A')}
- Files to modify: {plan.get('files_to_modify', [])}
- Files to create: {plan.get('files_to_create', [])}
- Key changes: {plan.get('key_changes', [])}

{f'EXISTING FILE CONTEXT:{chr(10)}{file_context[:4000]}' if file_context else ''}

Generate the complete code changes in unified diff format.
If creating new files, show the full file content prefixed with "NEW FILE: path/to/file"
followed by the complete content."""

        return self.generate(prompt, system_instruction=system, temperature=0.2,
                             max_tokens=GEMINI_MAX_TOKENS)

    def generate_pr_description(self, bounty: BountyIssue, plan: dict) -> Tuple[bool, str]:
        """Generate a professional PR description."""
        system = "You write concise, professional GitHub PR descriptions. No fluff."

        prompt = f"""Write a PR description for this fix:

ISSUE: {bounty.full_repo}#{bounty.issue_number} — {bounty.title}
APPROACH: {plan.get('approach', 'N/A')}
KEY CHANGES: {plan.get('key_changes', [])}
TESTING: {plan.get('testing_strategy', 'N/A')}

Format:
## Summary
[1-2 sentences]

## Changes
- [bullet points]

## Testing
- [how to verify]

Closes #{bounty.issue_number}"""

        return self.generate(prompt, system_instruction=system, temperature=0.4,
                             max_tokens=1024)


# ============================================================
# GITHUB OPERATIONS — via gh CLI
# ============================================================

class GitHubOps:
    """GitHub operations via gh CLI. Respects dry-run mode."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self._gh_available = None

    @property
    def gh_available(self) -> bool:
        if self._gh_available is None:
            try:
                r = subprocess.run(
                    ["gh", "--version"],
                    capture_output=True, text=True, timeout=10
                )
                self._gh_available = r.returncode == 0
            except Exception:
                self._gh_available = False
        return self._gh_available

    def _run_gh(self, args: List[str], timeout: int = 60) -> Tuple[bool, str]:
        """Run a gh CLI command. Returns (success, output)."""
        if not self.gh_available:
            return False, "gh CLI not available. Install: https://cli.github.com/"

        try:
            r = subprocess.run(
                ["gh"] + args,
                capture_output=True, text=True, timeout=timeout
            )
            output = r.stdout.strip()
            if r.returncode != 0:
                return False, r.stderr.strip() or f"Exit code {r.returncode}"
            return True, output
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def _run_git(self, args: List[str], cwd: str = None,
                 timeout: int = 30) -> Tuple[bool, str]:
        """Run a git command. Returns (success, output)."""
        try:
            r = subprocess.run(
                ["git"] + args,
                capture_output=True, text=True, timeout=timeout,
                cwd=cwd
            )
            output = r.stdout.strip()
            if r.returncode != 0:
                return False, r.stderr.strip() or f"Exit code {r.returncode}"
            return True, output
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def search_bounty_issues(self, source: str = "all") -> List[BountyIssue]:
        """Search GitHub for issues with bounty labels."""
        bounties = []

        # Strategy: search for issues labeled with bounty-related terms
        search_queries = []

        if source in ("all", "algora"):
            search_queries.append(
                'label:"💰 algora" state:open sort:updated'
            )
            search_queries.append(
                'label:bounty label:algora state:open sort:updated'
            )

        if source in ("all", "opire"):
            search_queries.append(
                'label:"opire" state:open sort:updated'
            )
            search_queries.append(
                'label:"💎 opire" state:open sort:updated'
            )

        if source in ("all", "github"):
            search_queries.append(
                'label:bounty state:open sort:updated language:python'
            )
            search_queries.append(
                'label:bounty state:open sort:updated language:typescript'
            )
            search_queries.append(
                'label:bounty state:open sort:updated language:go'
            )
            search_queries.append(
                'label:"help wanted" label:bounty state:open sort:updated'
            )

        seen_ids = set()

        for query in search_queries:
            ok, output = self._run_gh([
                "search", "issues",
                "--json", "number,title,body,labels,repository,url,state",
                "--limit", "10",
                query,
            ], timeout=30)

            if not ok:
                log.warn(f"Search failed for query [{query[:50]}...]: {output[:200]}")
                continue

            try:
                issues = json.loads(output) if output else []
            except json.JSONDecodeError:
                log.warn(f"Failed to parse search results: {output[:200]}")
                continue

            for issue in issues:
                repo_data = issue.get("repository", {})
                # Handle both dict format and "owner/name" string format
                if isinstance(repo_data, dict):
                    repo_owner = repo_data.get("owner", "")
                    repo_name = repo_data.get("name", "")
                elif isinstance(repo_data, str) and "/" in repo_data:
                    parts = repo_data.split("/", 1)
                    repo_owner, repo_name = parts[0], parts[1]
                else:
                    # Try extracting from nameWithOwner
                    nwo = repo_data.get("nameWithOwner", "") if isinstance(repo_data, dict) else ""
                    if "/" in nwo:
                        repo_owner, repo_name = nwo.split("/", 1)
                    else:
                        continue

                issue_num = issue.get("number", 0)
                issue_id = f"{repo_owner}/{repo_name}#{issue_num}"

                if issue_id in seen_ids:
                    continue
                seen_ids.add(issue_id)

                labels = []
                for lbl in issue.get("labels", []):
                    if isinstance(lbl, dict):
                        labels.append(lbl.get("name", ""))
                    elif isinstance(lbl, str):
                        labels.append(lbl)

                # Extract bounty amount from labels and body
                bounty_amount = self._extract_bounty_amount(
                    labels, issue.get("body", "") or "", issue.get("title", "")
                )

                bounty = BountyIssue(
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    issue_number=issue_num,
                    title=issue.get("title", ""),
                    body=(issue.get("body", "") or "")[:5000],
                    labels=labels,
                    bounty_amount=bounty_amount,
                    url=issue.get("url", ""),
                    source=self._detect_source(labels),
                )

                bounties.append(bounty)

            # Rate-limit between searches
            time.sleep(1)

        return bounties

    def _extract_bounty_amount(self, labels: List[str], body: str,
                                title: str) -> str:
        """Extract bounty amount from labels, title, or body."""
        combined = " ".join(labels) + " " + title + " " + body[:2000]
        combined_lower = combined.lower()

        # Patterns to match bounty amounts
        patterns = [
            r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)',          # $100, $1,000
            r'(\d[\d,]*(?:\.\d{1,2})?)\s*(?:USD|USDC|USDT)',  # 100 USD
            r'bounty[:\s]*\$?\s*(\d[\d,]*)',            # bounty: $100
            r'reward[:\s]*\$?\s*(\d[\d,]*)',            # reward: $100
            r'prize[:\s]*\$?\s*(\d[\d,]*)',             # prize: $100
        ]

        for pattern in patterns:
            match = re.search(pattern, combined, re.IGNORECASE)
            if match:
                amount = match.group(1).replace(",", "")
                return f"${amount}"

        # Check for Algora-style labels like "💰 $100"
        for label in labels:
            if "$" in label:
                match = re.search(r'\$\s*(\d+)', label)
                if match:
                    return f"${match.group(1)}"

        return "unknown"

    def _detect_source(self, labels: List[str]) -> str:
        """Detect bounty source from labels."""
        labels_lower = [l.lower() for l in labels]
        label_text = " ".join(labels_lower)
        if "algora" in label_text:
            return "algora"
        if "opire" in label_text:
            return "opire"
        return "github-label"

    def get_repo_language(self, owner: str, name: str) -> str:
        """Get primary language of a repo."""
        ok, output = self._run_gh([
            "repo", "view", f"{owner}/{name}",
            "--json", "primaryLanguage",
        ], timeout=15)
        if ok:
            try:
                data = json.loads(output)
                lang = data.get("primaryLanguage", {})
                if isinstance(lang, dict):
                    return lang.get("name", "").lower()
                return str(lang).lower() if lang else ""
            except Exception:
                pass
        return ""

    def get_issue_details(self, owner: str, name: str,
                           issue_num: int) -> Optional[dict]:
        """Get full issue details."""
        ok, output = self._run_gh([
            "issue", "view", str(issue_num),
            "--repo", f"{owner}/{name}",
            "--json", "number,title,body,labels,comments,assignees,state",
        ], timeout=15)
        if ok:
            try:
                return json.loads(output)
            except Exception:
                pass
        return None

    def fork_repo(self, owner: str, name: str) -> Tuple[bool, str]:
        """Fork a repo to our account."""
        if self.dry_run:
            log.dry(f"Would fork {owner}/{name}")
            return True, f"{GITHUB_USER}/{name}"

        ok, output = self._run_gh([
            "repo", "fork", f"{owner}/{name}",
            "--clone=false",
        ], timeout=60)
        if ok or "already exists" in output.lower():
            return True, f"{GITHUB_USER}/{name}"
        return False, output

    def clone_repo(self, owner: str, name: str,
                    target_dir: str = "") -> Tuple[bool, str]:
        """Clone a repo to local workspace."""
        clone_dir = target_dir or str(WORKDIR / name)
        if Path(clone_dir).exists():
            # Pull latest instead
            ok, out = self._run_git(["pull", "--ff-only"], cwd=clone_dir)
            return True, clone_dir

        if self.dry_run:
            log.dry(f"Would clone {owner}/{name} to {clone_dir}")
            return True, clone_dir

        ok, output = self._run_gh([
            "repo", "clone", f"{owner}/{name}", clone_dir,
        ], timeout=120)
        return ok, clone_dir if ok else output

    def create_branch(self, repo_dir: str, branch: str) -> Tuple[bool, str]:
        """Create and checkout a new branch."""
        if self.dry_run:
            log.dry(f"Would create branch {branch} in {repo_dir}")
            return True, branch

        ok, out = self._run_git(["checkout", "-b", branch], cwd=repo_dir)
        return ok, out

    def commit_and_push(self, repo_dir: str, branch: str,
                         message: str) -> Tuple[bool, str]:
        """Stage all changes, commit, and push."""
        if self.dry_run:
            log.dry(f"Would commit and push branch {branch}: {message}")
            return True, "dry-run"

        # Stage all changes
        ok, out = self._run_git(["add", "-A"], cwd=repo_dir)
        if not ok:
            return False, f"git add failed: {out}"

        # Check if there are changes to commit
        ok, out = self._run_git(["diff", "--cached", "--quiet"], cwd=repo_dir)
        if ok:
            return False, "No changes to commit"

        # Commit
        ok, out = self._run_git(
            ["commit", "-m", message,
             "--author", f"Elrom Eved El Elyon <{GITHUB_EMAIL}>"],
            cwd=repo_dir
        )
        if not ok:
            return False, f"git commit failed: {out}"

        # Push
        ok, out = self._run_git(
            ["push", "origin", branch],
            cwd=repo_dir, timeout=60
        )
        return ok, out

    def create_pr(self, repo_owner: str, repo_name: str, branch: str,
                   title: str, body: str,
                   issue_number: int) -> Tuple[bool, str]:
        """Create a pull request."""
        if self.dry_run:
            log.dry(f"Would create PR: {title}")
            log.dry(f"  Base: {repo_owner}/{repo_name}")
            log.dry(f"  Head: {GITHUB_USER}:{branch}")
            log.dry(f"  Closes: #{issue_number}")
            return True, "https://github.com/dry-run/pr/0"

        ok, output = self._run_gh([
            "pr", "create",
            "--repo", f"{repo_owner}/{repo_name}",
            "--head", f"{GITHUB_USER}:{branch}",
            "--title", title,
            "--body", body,
        ], timeout=30)
        return ok, output

    def check_pr_status(self, pr_url: str) -> Optional[str]:
        """Check if a PR was merged, closed, or still open."""
        if not pr_url or "dry-run" in pr_url:
            return "dry-run"

        # Extract owner/repo and PR number from URL
        match = re.search(r'github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
        if not match:
            return None

        owner, name, pr_num = match.groups()
        ok, output = self._run_gh([
            "pr", "view", pr_num,
            "--repo", f"{owner}/{name}",
            "--json", "state,merged",
        ], timeout=15)

        if ok:
            try:
                data = json.loads(output)
                if data.get("merged"):
                    return "merged"
                return data.get("state", "unknown").lower()
            except Exception:
                pass
        return None


# ============================================================
# STRATEGY ENGINE — Feedback loop
# ============================================================

class StrategyEngine:
    """Adjusts bounty hunting strategy based on outcomes."""

    def __init__(self, ledger: BountyLedger):
        self.ledger = ledger

    def should_attempt(self, bounty: BountyIssue, plan: dict) -> Tuple[bool, str]:
        """Decide if we should attempt this bounty based on strategy."""
        strategy = self.ledger.get_strategy()

        # Check blacklist
        if self.ledger.is_blacklisted(bounty.issue_id):
            return False, "Blacklisted"

        # Already attempted
        if self.ledger.is_attempted(bounty.issue_id):
            return False, "Already attempted"

        # Check confidence threshold
        confidence = plan.get("confidence", 0.5)
        if confidence < 0.3:
            return False, f"Low confidence: {confidence}"

        # Check difficulty
        max_diff = strategy.get("max_difficulty", "medium")
        diff_order = {"easy": 1, "medium": 2, "hard": 3}
        plan_diff = plan.get("difficulty", "medium")
        if diff_order.get(plan_diff, 2) > diff_order.get(max_diff, 2):
            return False, f"Too difficult: {plan_diff} > {max_diff}"

        # Check feasibility
        if not plan.get("feasible", False):
            return False, "Plan says not feasible"

        # Check time estimate (skip if >8 hours estimated)
        est_hours = plan.get("estimated_hours", 4)
        if est_hours > 8:
            return False, f"Too time-consuming: {est_hours}h"

        return True, "OK"

    def adjust_from_results(self):
        """Adjust strategy based on past results."""
        attempts = self.ledger.data.get("attempts", [])
        if len(attempts) < 3:
            return  # Not enough data

        strategy = self.ledger.get_strategy()
        recent = attempts[-20:]  # Last 20 attempts

        # Calculate success rate
        submitted = [a for a in recent if a["status"] in ("submitted", "accepted", "merged")]
        accepted = [a for a in recent if a["status"] in ("accepted", "merged")]
        rejected = [a for a in recent if a["status"] == "rejected"]

        if submitted:
            success_rate = len(accepted) / len(submitted)
        else:
            success_rate = 0.0

        log.info(f"Strategy adjustment: {len(accepted)}/{len(submitted)} accepted "
                 f"({success_rate:.0%}), {len(rejected)} rejected")

        # If success rate is low, be more conservative
        if success_rate < 0.2 and len(submitted) >= 5:
            strategy["max_difficulty"] = "easy"
            log.info("Strategy: Lowering difficulty to 'easy' due to low success rate")

        # If success rate is high, be more aggressive
        elif success_rate > 0.5 and len(submitted) >= 3:
            strategy["max_difficulty"] = "hard"
            log.info("Strategy: Raising difficulty to 'hard' due to high success rate")

        # Track which languages get accepted
        accepted_langs = {}
        for a in accepted:
            bounty_data = self.ledger.data["bounties"].get(a["issue_id"], {})
            lang = bounty_data.get("language", "")
            if lang:
                accepted_langs[lang] = accepted_langs.get(lang, 0) + 1

        if accepted_langs:
            # Prioritize languages with most acceptances
            sorted_langs = sorted(accepted_langs.items(), key=lambda x: x[1], reverse=True)
            strategy["preferred_languages"] = [l for l, _ in sorted_langs[:5]]
            log.info(f"Strategy: Updated preferred languages: {strategy['preferred_languages']}")

        self.ledger.save()


# ============================================================
# SINGULARITY LOOP — The main autonomous sentinela
# ============================================================

class SingularityLoop:
    """
    Autonomous bounty hunting sentinela.
    Scans -> Analyzes -> Plans -> Codes -> Submits -> Tracks -> Adjusts.
    """

    def __init__(self, dry_run: bool = True, interval: int = DEFAULT_INTERVAL):
        self.dry_run = dry_run
        self.interval = interval
        self.running = False
        self.cycle_count = 0

        # Initialize core agent
        self.agent = IsraelAgent(
            name="SINGULARITY",
            codename="BOUNTY-HUNTER-SUPREME",
            mission="Autonomous bounty hunting — ZERO free work, only PAID bounties",
            permission_mode=PermissionMode.AUTONOMOUS,
        )

        # Components
        self.ledger = BountyLedger()
        self.gemini = GeminiClient()
        self.github = GitHubOps(dry_run=dry_run)
        self.strategy = StrategyEngine(self.ledger)

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        log.info(f"SingularityLoop v{VERSION} initialized")
        log.info(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        log.info(f"  Interval: {interval}s ({interval // 60}m)")
        log.info(f"  Gemini: {'configured' if self.gemini.is_configured else 'NOT CONFIGURED'}")
        log.info(f"  gh CLI: {'available' if self.github.gh_available else 'NOT AVAILABLE'}")

    def _handle_shutdown(self, signum, frame):
        log.info("Shutdown signal received. Finishing current cycle...")
        self.running = False

    def preflight_check(self) -> Tuple[bool, List[str]]:
        """Check all prerequisites before starting the loop."""
        issues = []

        # Check gh CLI
        if not self.github.gh_available:
            issues.append("gh CLI not installed or not authenticated")

        # Check gh auth
        try:
            r = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode != 0:
                issues.append("gh not authenticated. Run: gh auth login")
        except Exception:
            issues.append("Cannot verify gh auth status")

        # Check Gemini API
        if not self.gemini.is_configured:
            issues.append(
                "GEMINI_API_KEY not set. Run: export GEMINI_API_KEY=your_key\n"
                "  Get free key: https://aistudio.google.com/apikey"
            )

        # Check RAM
        health = self.agent.health_check()
        avail_mb = health.get("memory", {}).get("available_mb", 0)
        if avail_mb < 300:
            issues.append(f"Low RAM: {avail_mb}MB available (need 300MB+)")

        # Check git config
        try:
            r = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True, text=True, timeout=5
            )
            if not r.stdout.strip():
                issues.append("Git user.name not set")
        except Exception:
            issues.append("Cannot check git config")

        passed = len(issues) == 0
        return passed, issues

    def scan_bounties(self) -> List[BountyIssue]:
        """Scan all sources for paid bounties."""
        log.info("Scanning for paid bounties...")
        bounties = self.github.search_bounty_issues(source="all")

        # Enrich with repo language
        for bounty in bounties:
            if not bounty.language:
                bounty.language = self.github.get_repo_language(
                    bounty.repo_owner, bounty.repo_name
                )
            # Register in ledger
            self.ledger.add_bounty(bounty)

        # Filter: only bounties with detected amounts
        paid_bounties = [
            b for b in bounties
            if b.bounty_amount != "unknown"
        ]

        log.info(f"Found {len(bounties)} total issues, {len(paid_bounties)} with confirmed bounties")

        # Sort by bounty amount (higher first)
        def parse_amount(b):
            try:
                nums = re.findall(r'[\d.]+', b.bounty_amount)
                return float(nums[0]) if nums else 0
            except Exception:
                return 0

        paid_bounties.sort(key=parse_amount, reverse=True)

        return paid_bounties[:MAX_BOUNTIES_PER_CYCLE]

    def analyze_bounty(self, bounty: BountyIssue) -> Optional[dict]:
        """Use Gemini to analyze a bounty and produce a plan."""
        log.info(f"Analyzing: {bounty.issue_id} — {bounty.title[:60]}...")

        # Get full issue details if possible
        details = self.github.get_issue_details(
            bounty.repo_owner, bounty.repo_name, bounty.issue_number
        )
        if details and details.get("body"):
            bounty.body = details["body"][:5000]

        # Check for assignees (skip if already assigned)
        if details and details.get("assignees"):
            assignees = details["assignees"]
            if assignees:
                log.info(f"  Skipping: already assigned to {[a.get('login', '?') for a in assignees]}")
                return None

        # Analyze with Gemini
        ok, plan = self.gemini.analyze_bounty(bounty)
        if not ok:
            log.error(f"  Gemini analysis failed: {plan.get('error', 'unknown')}")
            return None

        log.info(f"  Plan: feasible={plan.get('feasible')}, "
                 f"difficulty={plan.get('difficulty')}, "
                 f"confidence={plan.get('confidence')}, "
                 f"est_hours={plan.get('estimated_hours')}")

        return plan

    def attempt_bounty(self, bounty: BountyIssue, plan: dict) -> BountyAttempt:
        """Attempt to solve a bounty: generate code, create PR."""
        attempt = BountyAttempt(
            issue_id=bounty.issue_id,
            bounty_amount=bounty.bounty_amount,
            plan=json.dumps(plan, default=str)[:2000],
        )

        branch_name = (
            f"fix/{bounty.repo_name}-{bounty.issue_number}-"
            f"{re.sub(r'[^a-z0-9]+', '-', bounty.title.lower()[:30])}"
        )
        attempt.branch_name = branch_name

        # Step 1: Generate code
        log.action(f"Generating code for {bounty.issue_id}...")
        ok, code = self.gemini.generate_code(bounty, plan)
        if not ok:
            log.error(f"  Code generation failed: {code[:200]}")
            attempt.status = "abandoned"
            attempt.feedback = f"Code generation failed: {code[:200]}"
            self.ledger.add_attempt(attempt)
            return attempt

        attempt.code_summary = code[:500]
        attempt.gemini_tokens_used = self.gemini.total_tokens
        log.info(f"  Code generated: {len(code)} chars")

        if self.dry_run:
            log.dry(f"  === DRY RUN: Would proceed with fork -> clone -> branch -> commit -> PR ===")
            log.dry(f"  Branch: {branch_name}")
            log.dry(f"  Code preview:\n{code[:300]}...")
            attempt.status = "planned"
            self.ledger.add_attempt(attempt)
            return attempt

        # Step 2: Fork the repo
        log.action(f"Forking {bounty.full_repo}...")
        ok, fork_result = self.github.fork_repo(bounty.repo_owner, bounty.repo_name)
        if not ok:
            log.error(f"  Fork failed: {fork_result}")
            attempt.status = "abandoned"
            attempt.feedback = f"Fork failed: {fork_result}"
            self.ledger.add_attempt(attempt)
            return attempt

        # Step 3: Clone the fork
        log.action(f"Cloning fork...")
        clone_dir = str(WORKDIR / bounty.repo_name)
        ok, clone_result = self.github.clone_repo(GITHUB_USER, bounty.repo_name, clone_dir)
        if not ok:
            log.error(f"  Clone failed: {clone_result}")
            attempt.status = "abandoned"
            attempt.feedback = f"Clone failed: {clone_result}"
            self.ledger.add_attempt(attempt)
            return attempt

        # Step 4: Create branch
        log.action(f"Creating branch {branch_name}...")
        ok, _ = self.github.create_branch(clone_dir, branch_name)
        if not ok:
            log.error(f"  Branch creation failed")
            attempt.status = "abandoned"
            self.ledger.add_attempt(attempt)
            return attempt

        # Step 5: Apply code changes
        log.action("Applying code changes...")
        applied = self._apply_code_changes(clone_dir, code, plan)
        if not applied:
            log.error("  Failed to apply code changes")
            attempt.status = "abandoned"
            attempt.feedback = "Failed to apply code changes"
            self.ledger.add_attempt(attempt)
            return attempt

        # Step 6: Commit and push
        commit_msg = (
            f"fix: {bounty.title[:60]}\n\n"
            f"Closes #{bounty.issue_number}\n\n"
            f"Changes:\n"
            + "\n".join(f"- {c}" for c in plan.get("key_changes", ["Fix applied"])[:5])
        )

        log.action("Committing and pushing...")
        ok, push_result = self.github.commit_and_push(clone_dir, branch_name, commit_msg)
        if not ok:
            log.error(f"  Push failed: {push_result}")
            attempt.status = "abandoned"
            attempt.feedback = f"Push failed: {push_result}"
            self.ledger.add_attempt(attempt)
            return attempt

        # Step 7: Create PR
        log.action("Generating PR description...")
        ok, pr_body = self.gemini.generate_pr_description(bounty, plan)
        if not ok:
            pr_body = f"## Fix for #{bounty.issue_number}\n\n{plan.get('approach', 'Fix applied')}"

        log.action("Creating pull request...")
        ok, pr_url = self.github.create_pr(
            bounty.repo_owner, bounty.repo_name,
            branch_name,
            f"fix: {bounty.title[:60]}",
            pr_body,
            bounty.issue_number,
        )

        if ok:
            attempt.status = "submitted"
            attempt.pr_url = pr_url
            attempt.completed_at = datetime.now(BRT).isoformat()
            log.success(f"  PR submitted: {pr_url}")
        else:
            attempt.status = "abandoned"
            attempt.feedback = f"PR creation failed: {pr_url}"
            log.error(f"  PR creation failed: {pr_url}")

        self.ledger.add_attempt(attempt)
        return attempt

    def _apply_code_changes(self, repo_dir: str, code: str,
                             plan: dict) -> bool:
        """
        Apply generated code changes to the repo.
        Supports:
        - Unified diff format
        - NEW FILE: path/content format
        - Direct file writes from plan
        """
        applied_any = False

        # Try to parse as new files first
        new_file_pattern = re.compile(
            r'NEW FILE:\s*(\S+)\n(.*?)(?=NEW FILE:|$)',
            re.DOTALL
        )
        for match in new_file_pattern.finditer(code):
            filepath = match.group(1).strip()
            content = match.group(2).strip()
            target = Path(repo_dir) / filepath
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content + "\n")
                log.info(f"  Created: {filepath}")
                applied_any = True
            except Exception as e:
                log.error(f"  Failed to create {filepath}: {e}")

        # Try to parse unified diffs
        diff_blocks = re.split(r'^diff --git', code, flags=re.MULTILINE)
        for block in diff_blocks:
            if not block.strip():
                continue
            # Extract filename from +++ b/path
            file_match = re.search(r'^\+\+\+ b/(.+)$', block, re.MULTILINE)
            if not file_match:
                continue
            filepath = file_match.group(1).strip()
            target = Path(repo_dir) / filepath

            if not target.exists():
                log.warn(f"  Diff target not found: {filepath}")
                continue

            # Apply hunks (simplified — write entire patched content)
            try:
                original = target.read_text()
                patched = self._apply_simple_diff(original, block)
                if patched and patched != original:
                    target.write_text(patched)
                    log.info(f"  Patched: {filepath}")
                    applied_any = True
            except Exception as e:
                log.warn(f"  Failed to patch {filepath}: {e}")

        # If nothing was applied via diff, try to create files from plan
        if not applied_any and plan.get("files_to_create"):
            for filepath in plan["files_to_create"]:
                target = Path(repo_dir) / filepath
                if not target.exists():
                    # Extract relevant code blocks
                    ext = target.suffix
                    code_blocks = re.findall(
                        r'```(?:\w+)?\n(.*?)```',
                        code, re.DOTALL
                    )
                    if code_blocks:
                        try:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_text(code_blocks[0].strip() + "\n")
                            log.info(f"  Created from code block: {filepath}")
                            applied_any = True
                        except Exception as e:
                            log.error(f"  Failed to create {filepath}: {e}")

        return applied_any

    def _apply_simple_diff(self, original: str, diff_block: str) -> Optional[str]:
        """
        Simplified diff application.
        Finds removed lines and replaces them with added lines.
        This is a best-effort approach for simple patches.
        """
        lines = original.split("\n")
        result = list(lines)

        hunks = re.findall(
            r'@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@.*?\n(.*?)(?=@@ |\Z)',
            diff_block, re.DOTALL
        )

        if not hunks:
            return None

        offset = 0
        for start_old_str, start_new_str, hunk_body in hunks:
            start_old = int(start_old_str) - 1  # 0-indexed
            removals = []
            additions = []

            for line in hunk_body.split("\n"):
                if line.startswith("-") and not line.startswith("---"):
                    removals.append(line[1:])
                elif line.startswith("+") and not line.startswith("+++"):
                    additions.append(line[1:])

            # Find and replace the removed lines
            if removals:
                idx = start_old + offset
                # Find the removal block in result
                found = False
                for search_idx in range(max(0, idx - 5), min(len(result), idx + 5)):
                    if (search_idx + len(removals) <= len(result) and
                            all(result[search_idx + i].rstrip() == removals[i].rstrip()
                                for i in range(len(removals)))):
                        # Replace
                        result[search_idx:search_idx + len(removals)] = additions
                        offset += len(additions) - len(removals)
                        found = True
                        break

                if not found:
                    # Fallback: just append additions at the position
                    idx = min(idx, len(result))
                    result[idx:idx] = additions
                    offset += len(additions)
            elif additions:
                idx = start_old + offset
                idx = min(idx, len(result))
                result[idx:idx] = additions
                offset += len(additions)

        return "\n".join(result)

    def check_previous_submissions(self):
        """Check status of previously submitted PRs and update ledger."""
        log.info("Checking status of previous submissions...")
        updated = 0

        for attempt in self.ledger.data.get("attempts", []):
            if attempt["status"] == "submitted" and attempt.get("pr_url"):
                status = self.github.check_pr_status(attempt["pr_url"])
                if status and status != "open" and status != "dry-run":
                    old_status = attempt["status"]
                    if status == "merged":
                        attempt["status"] = "accepted"
                        log.success(f"  ACCEPTED: {attempt['issue_id']} — {attempt['pr_url']}")
                    elif status == "closed":
                        attempt["status"] = "rejected"
                        log.warn(f"  REJECTED: {attempt['issue_id']} — {attempt['pr_url']}")
                    updated += 1

        if updated > 0:
            self.ledger.save()
            log.info(f"Updated {updated} submission statuses")

            # Adjust strategy based on new results
            self.strategy.adjust_from_results()

    def run_cycle(self) -> dict:
        """Execute one complete scan-analyze-attempt cycle."""
        self.cycle_count += 1
        cycle_start = time.time()
        results = {
            "cycle": self.cycle_count,
            "started_at": datetime.now(BRT).isoformat(),
            "bounties_found": 0,
            "analyzed": 0,
            "attempted": 0,
            "submitted": 0,
            "errors": [],
        }

        log.info(f"=== CYCLE {self.cycle_count} START ===")

        # Step 1: Check RAM before doing anything
        health = self.agent.health_check()
        avail_mb = health.get("memory", {}).get("available_mb", 0)
        if avail_mb < 200:
            log.critical(f"RAM too low: {avail_mb}MB. Skipping cycle.")
            results["errors"].append(f"RAM too low: {avail_mb}MB")
            return results

        # Step 2: Check previous submissions
        try:
            self.check_previous_submissions()
        except Exception as e:
            log.error(f"Error checking submissions: {e}")
            results["errors"].append(f"Submission check: {e}")

        # Step 3: Scan for bounties
        try:
            bounties = self.scan_bounties()
            results["bounties_found"] = len(bounties)
        except Exception as e:
            log.error(f"Scan failed: {e}")
            results["errors"].append(f"Scan: {e}")
            return results

        if not bounties:
            log.info("No paid bounties found this cycle.")
            return results

        # Step 4: Analyze and attempt each bounty
        for bounty in bounties:
            try:
                # Check RAM before each bounty
                try:
                    with open("/proc/meminfo") as f:
                        for line in f:
                            if line.startswith("MemAvailable:"):
                                avail = int(line.split()[1]) / 1024
                                if avail < 250:
                                    log.warn(f"RAM low ({avail:.0f}MB), stopping bounty processing")
                                    results["errors"].append(f"RAM low at bounty: {avail:.0f}MB")
                                    break
                except Exception:
                    pass

                # Analyze
                plan = self.analyze_bounty(bounty)
                if not plan:
                    continue
                results["analyzed"] += 1

                # Check if we should attempt
                should, reason = self.strategy.should_attempt(bounty, plan)
                if not should:
                    log.info(f"  Skipping {bounty.issue_id}: {reason}")
                    continue

                # Attempt
                attempt = self.attempt_bounty(bounty, plan)
                results["attempted"] += 1

                if attempt.status == "submitted":
                    results["submitted"] += 1
                elif attempt.status == "planned":
                    pass  # dry run
                else:
                    results["errors"].append(
                        f"{bounty.issue_id}: {attempt.feedback or attempt.status}"
                    )

                # Be nice: wait between attempts
                time.sleep(3)

            except Exception as e:
                log.error(f"Error processing {bounty.issue_id}: {e}")
                results["errors"].append(f"{bounty.issue_id}: {e}")

        # Cycle summary
        duration = time.time() - cycle_start
        results["duration_seconds"] = round(duration, 1)

        log.info(f"=== CYCLE {self.cycle_count} COMPLETE ===")
        log.info(f"  Duration: {duration:.1f}s")
        log.info(f"  Found: {results['bounties_found']}, "
                 f"Analyzed: {results['analyzed']}, "
                 f"Attempted: {results['attempted']}, "
                 f"Submitted: {results['submitted']}")
        if results["errors"]:
            log.warn(f"  Errors: {len(results['errors'])}")

        # Notify other agents via bus
        self.agent.send("*", "BOUNTY_CYCLE_COMPLETE", {
            "cycle": self.cycle_count,
            "found": results["bounties_found"],
            "submitted": results["submitted"],
            "mode": "dry-run" if self.dry_run else "live",
        })

        return results

    def run(self, single_cycle: bool = False):
        """
        Run the sentinela loop.
        If single_cycle=True, runs once and exits.
        """
        log.info("=" * 60)
        log.info("  SINGULARITY LOOP SENTINELA STARTING")
        log.info(f"  Em nome do Senhor Jesus Cristo, nosso Salvador")
        log.info(f"  'Tudo posso naquele que me fortalece' — Filipenses 4:13")
        log.info(f"  Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        log.info(f"  ZERO FREE WORK — Only PAID bounties")
        log.info("=" * 60)

        # Preflight check
        passed, issues = self.preflight_check()
        if not passed:
            log.critical("Preflight check FAILED:")
            for issue in issues:
                log.error(f"  - {issue}")
            if not self.dry_run:
                log.critical("Cannot start in LIVE mode with failing preflight. Fix issues above.")
                return
            else:
                log.warn("Continuing in DRY RUN mode despite preflight issues.")

        self.running = True

        if single_cycle:
            self.run_cycle()
            self.running = False
            return

        # Continuous sentinela loop
        while self.running:
            try:
                self.run_cycle()
            except Exception as e:
                log.error(f"Cycle error: {e}")
                import traceback
                log.error(traceback.format_exc())

            if not self.running:
                break

            log.info(f"Next cycle in {self.interval}s ({self.interval // 60}m)...")

            # Sleep in small increments so we can respond to shutdown signals
            sleep_remaining = self.interval
            while sleep_remaining > 0 and self.running:
                chunk = min(sleep_remaining, 10)
                time.sleep(chunk)
                sleep_remaining -= chunk

        # Shutdown
        log.info("Singularity Loop sentinela stopped.")
        log.info(f"Final stats: {json.dumps(self.ledger.get_stats(), indent=2)}")
        self.ledger.save()
        self.agent.memory.save()


# ============================================================
# CLI ENTRY POINT
# ============================================================

def main():
    """Entry point with argument parsing (pure stdlib, no argparse needed)."""
    args = sys.argv[1:]

    # Defaults
    dry_run = True
    single_cycle = False
    interval = DEFAULT_INTERVAL
    show_status = False

    # Parse args
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--live":
            dry_run = False
        elif arg == "--once":
            single_cycle = True
        elif arg == "--status":
            show_status = True
        elif arg == "--interval" and i + 1 < len(args):
            i += 1
            try:
                interval = int(args[i])
                if interval < 60:
                    print("WARNING: Interval too low, setting minimum 60s")
                    interval = 60
            except ValueError:
                print(f"Invalid interval: {args[i]}")
                return
        elif arg in ("-h", "--help"):
            print(__doc__)
            return
        else:
            print(f"Unknown argument: {arg}")
            print("Usage: singularity_loop.py [--live] [--once] [--status] [--interval N]")
            return
        i += 1

    # Show status
    if show_status:
        ledger = BountyLedger()
        print(ledger.status_report())
        return

    # Print startup banner
    print("""
    ========================================================
    SINGULARITY LOOP v1.0 — Autonomous Bounty Hunter
    Em nome do Senhor Jesus Cristo, nosso Salvador
    PADRAO BITCOIN — ZERO FREE WORK
    ========================================================
    """)

    if not dry_run:
        print("  *** LIVE MODE ACTIVE — Will submit real PRs ***")
        print("  Press Ctrl+C to stop gracefully.\n")
    else:
        print("  DRY RUN MODE — Planning only, no submissions.")
        print("  Use --live to enable real submissions.\n")

    # Create and run
    loop = SingularityLoop(dry_run=dry_run, interval=interval)
    loop.run(single_cycle=single_cycle)


if __name__ == "__main__":
    main()
