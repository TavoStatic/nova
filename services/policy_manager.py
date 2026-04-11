from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse


WEB_RESEARCH_PRESETS = {
    "normal": {
        "research_domains_limit": 4,
        "research_pages_per_domain": 8,
        "research_scan_pages_per_domain": 12,
        "research_max_depth": 1,
        "research_seeds_per_domain": 8,
        "research_max_results": 8,
        "research_min_score": 3.0,
    },
    "max": {
        "research_domains_limit": 8,
        "research_pages_per_domain": 25,
        "research_scan_pages_per_domain": 60,
        "research_max_depth": 2,
        "research_seeds_per_domain": 20,
        "research_max_results": 20,
        "research_min_score": 1.5,
    },
}


SEARCH_PROVIDER_PRIORITY_DEFAULT = ["wikipedia", "stackexchange", "general_web"]
SEARCH_PROVIDER_PRIORITY_ALLOWED = set(SEARCH_PROVIDER_PRIORITY_DEFAULT)


class PolicyManager:
    """Encapsulates policy persistence, access control, and domain whitelisting."""

    def __init__(self, policy_file: Path, audit_log_file: Path, base_dir: Path) -> None:
        self.policy_file = policy_file
        self.audit_log_file = audit_log_file
        self.base_dir = base_dir
        self._policy_cache: dict | None = None

    def load_policy(self) -> dict:
        """Load and normalize policy from file, applying defaults."""
        try:
            data = json.loads(self.policy_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        if not isinstance(data, dict):
            data = {}

        data["allowed_root"] = str(Path(data.get("allowed_root", str(self.base_dir))).resolve())

        tools = data.get("tools_enabled") if isinstance(data.get("tools_enabled"), dict) else {}
        tools.setdefault("screen", False)
        tools.setdefault("camera", False)
        tools.setdefault("files", False)
        tools.setdefault("health", False)
        tools.setdefault("web", False)
        data["tools_enabled"] = tools

        models = data.get("models") if isinstance(data.get("models"), dict) else {}
        models.setdefault("chat", "llama3.1:8b")
        models.setdefault("vision", "qwen2.5vl:7b")
        models.setdefault("stt_size", "base")
        data["models"] = models

        memory = data.get("memory") if isinstance(data.get("memory"), dict) else {}
        memory.setdefault("enabled", False)
        memory.setdefault("mode", "B")
        memory.setdefault("scope", "private")
        memory.setdefault("top_k", 5)
        memory.setdefault("context_top_k", 3)
        memory.setdefault("min_score", 0.25)
        memory.setdefault("store_min_chars", 12)
        memory.setdefault("exclude_sources", [])
        memory.setdefault("store_include_patterns", [])
        memory.setdefault("store_exclude_patterns", [])
        data["memory"] = memory

        web = data.get("web") if isinstance(data.get("web"), dict) else {}
        web.setdefault("enabled", False)
        web.setdefault("search_provider", "html")
        web.setdefault("search_api_endpoint", "")
        web.setdefault("search_provider_priority", list(SEARCH_PROVIDER_PRIORITY_DEFAULT))
        web.setdefault("stackexchange_site", "stackoverflow")
        web.setdefault("stackexchange_api_endpoint", "https://api.stackexchange.com/2.3/search/advanced")
        web.setdefault("stackexchange_api_key_env", "STACKEXCHANGE_API_KEY")
        web.setdefault("allow_domains", [])
        web.setdefault("max_bytes", 20_000_000)
        web.setdefault("research_domains_limit", 4)
        web.setdefault("research_pages_per_domain", 8)
        web.setdefault("research_scan_pages_per_domain", 12)
        web.setdefault("research_max_depth", 1)
        web.setdefault("research_seeds_per_domain", 8)
        web.setdefault("research_max_results", 8)
        web.setdefault("research_min_score", 3.0)
        data["web"] = web

        patch = data.get("patch") if isinstance(data.get("patch"), dict) else {}
        patch.setdefault("enabled", True)
        patch.setdefault("allow_force", False)
        patch.setdefault("strict_manifest", True)
        patch.setdefault("behavioral_check", True)
        patch.setdefault("behavioral_check_timeout_sec", 600)
        data["patch"] = patch

        safety_envelope = data.get("safety_envelope") if isinstance(data.get("safety_envelope"), dict) else {}
        safety_envelope.setdefault("enabled", True)
        safety_envelope.setdefault("mode", "observe")
        safety_envelope.setdefault("replay_threshold", 1.0)
        safety_envelope.setdefault("replay_attempts", 2)
        safety_envelope.setdefault("novelty_min", 0.35)
        safety_envelope.setdefault("entropy_min", 2.8)
        safety_envelope.setdefault("diversity_min_messages", 3)
        safety_envelope.setdefault("human_veto_first_n", 3)
        safety_envelope.setdefault("auto_demote_threshold", 0.90)
        safety_envelope.setdefault("max_candidates_per_cycle", 3)
        safety_envelope.setdefault("full_regression_required", False)
        safety_envelope.setdefault("quarantine_root", str(self.base_dir / "runtime" / "test_sessions" / "quarantine"))
        safety_envelope.setdefault("pending_review_root", str(self.base_dir / "runtime" / "test_sessions" / "pending_review"))
        data["safety_envelope"] = safety_envelope

        kidney = data.get("kidney") if isinstance(data.get("kidney"), dict) else {}
        kidney.setdefault("enabled", True)
        kidney.setdefault("mode", "observe")
        kidney.setdefault("definition_max_age_days", 7)
        kidney.setdefault("definition_novelty_min", 0.4)
        kidney.setdefault("quarantine_max_age_hours", 48)
        kidney.setdefault("preview_max_age_days", 3)
        kidney.setdefault("snapshot_max_age_days", 30)
        kidney.setdefault("temp_max_age_days", 14)
        kidney.setdefault("temp_max_total_mb", 500)
        kidney.setdefault("protect_patterns", [])
        data["kidney"] = kidney

        self._policy_cache = data
        return data

    def _load_raw(self) -> dict:
        """Load with normalization applied."""
        return self.load_policy()

    def _save_raw(self, data: dict) -> None:
        """Persist policy to file."""
        try:
            self.policy_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8"
            )
            self._policy_cache = None
        except Exception:
            pass

    def record_change(self, action: str, target: str, result: str, details: str = "", user: str | None = None) -> None:
        """Log a policy change to audit log."""
        entry = {
            "ts": int(time.time()),
            "user": str(user or "unknown"),
            "action": str(action or "").strip(),
            "target": str(target or "").strip(),
            "result": str(result or "").strip(),
            "details": str(details or "").strip(),
        }
        try:
            self.audit_log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.audit_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_models(self) -> dict:
        """Get model policy section."""
        p = self.load_policy()
        return p.get("models") or {}

    def get_memory(self) -> dict:
        """Get memory policy section."""
        p = self.load_policy()
        return p.get("memory") or {}

    def get_tools_enabled(self) -> dict:
        """Get tools_enabled policy section."""
        p = self.load_policy()
        return p.get("tools_enabled") or {}

    def get_web(self) -> dict:
        """Get web policy section."""
        p = self.load_policy()
        return p.get("web") or {}

    def get_patch(self) -> dict:
        """Get patch policy section."""
        p = self.load_policy()
        return p.get("patch") or {}

    def is_web_enabled(self) -> bool:
        """Check if web tool is enabled by policy."""
        p = self.load_policy()
        return bool((p.get("tools_enabled") or {}).get("web")) and bool((p.get("web") or {}).get("enabled"))

    def host_allowed(self, host: str, allow_domains: list[str]) -> bool:
        """Check if host is in allowed domains list."""
        host = (host or "").lower()
        for d in allow_domains:
            d_lower = (d or "").lower().strip()
            if not d_lower:
                continue
            if host == d_lower or host.endswith("." + d_lower):
                return True
        return False

    def normalize_domain_input(self, value: str) -> str:
        """Normalize domain input (URL or bare domain) to lowercase hostname."""
        s = (value or "").strip().lower()
        if not s:
            return ""

        if not re.match(r"^[a-z][a-z0-9+.-]*://", s):
            s = "https://" + s

        try:
            p = urlparse(s)
            host = (p.hostname or "").strip().lower()
        except Exception:
            return ""

        if not host:
            return ""

        # Basic host validation: labels with letters/numbers/hyphen, separated by dots.
        if not re.match(
            r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$",
            host
        ):
            return ""

        return host

    def list_allowed_domains(self) -> str:
        """Return formatted list of allowed domains."""
        allow_domains = list(self.get_web().get("allow_domains") or [])
        if not allow_domains:
            return "No allowed domains are configured in policy.json."

        lines = ["Here are the domains I currently allow:"]
        for d in allow_domains:
            lines.append(f"- {d}")
        return "\n".join(lines)

    def allow_domain(self, value: str, user: str | None = None) -> str:
        """Add domain to whitelist."""
        host = self.normalize_domain_input(value)
        if not host:
            self.record_change("allow_domain", value, "failed", "invalid_domain_input", user)
            return "Usage: policy allow <domain-or-url>"

        data = self._load_raw()
        web = data.get("web") if isinstance(data.get("web"), dict) else {}
        allow_domains = list(web.get("allow_domains") or [])

        existing = {str(x).strip().lower() for x in allow_domains if str(x).strip()}
        if host in existing:
            self.record_change("allow_domain", host, "skipped", "already_allowed", user)
            return f"Domain already allowed: {host}"

        allow_domains.append(host)
        web["allow_domains"] = allow_domains
        data["web"] = web
        self._save_raw(data)
        self.record_change("allow_domain", host, "success", "added_to_allow_domains", user)

        return f"Added allowed domain: {host}\n{self.list_allowed_domains()}"

    def remove_domain(self, value: str, user: str | None = None) -> str:
        """Remove domain from whitelist."""
        host = self.normalize_domain_input(value)
        if not host:
            self.record_change("remove_domain", value, "failed", "invalid_domain_input", user)
            return "Usage: policy remove <domain-or-url>"

        data = self._load_raw()
        web = data.get("web") if isinstance(data.get("web"), dict) else {}
        allow_domains = list(web.get("allow_domains") or [])

        kept = []
        removed = False
        for d in allow_domains:
            dd = str(d).strip()
            if dd.lower() == host:
                removed = True
                continue
            kept.append(dd)

        if not removed:
            self.record_change("remove_domain", host, "skipped", "not_found", user)
            return f"Domain not found in allowlist: {host}"

        web["allow_domains"] = kept
        data["web"] = web
        self._save_raw(data)
        self.record_change("remove_domain", host, "success", "removed_from_allow_domains", user)
        return f"Removed allowed domain: {host}\n{self.list_allowed_domains()}"

    def set_web_mode(self, mode: str, user: str | None = None) -> str:
        m = (mode or "").strip().lower()
        if m in {"balanced", "default"}:
            m = "normal"
        if m in {"deep", "full", "maxinput"}:
            m = "max"

        if m not in WEB_RESEARCH_PRESETS:
            return "Usage: web mode <normal|max>"

        data = self._load_raw()
        web = data.get("web") if isinstance(data.get("web"), dict) else {}
        for key, value in WEB_RESEARCH_PRESETS[m].items():
            web[key] = value
        data["web"] = web
        self._save_raw(data)
        self.record_change("web_mode", m, "success", "updated_research_limits", user)
        return f"Web research mode set to {m}."

    def set_memory_scope(self, scope: str, user: str | None = None) -> str:
        value = (scope or "").strip().lower()
        aliases = {
            "per-user": "private",
            "user": "private",
            "global": "shared",
            "both": "hybrid",
        }
        value = aliases.get(value, value)
        if value not in {"private", "shared", "hybrid"}:
            return "Usage: memory scope <private|shared|hybrid>"

        data = self._load_raw()
        memory = data.get("memory") if isinstance(data.get("memory"), dict) else {}
        prev = str(memory.get("scope") or "private").strip().lower()
        memory["scope"] = value
        data["memory"] = memory
        self._save_raw(data)
        self.record_change("memory_scope", value, "success", f"from={prev}", user)
        return f"Memory scope set to {value}."

    def get_search_provider(self) -> str:
        provider = str((self.get_web().get("search_provider") or "html")).strip().lower()
        if provider not in {"html", "searxng", "brave"}:
            return "html"
        return provider

    def get_search_provider_priority(self) -> list[str]:
        raw = self.get_web().get("search_provider_priority")
        values = raw if isinstance(raw, list) else []
        aliases = {
            "wiki": "wikipedia",
            "stack-overflow": "stackexchange",
            "stackoverflow": "stackexchange",
            "web": "general_web",
            "general": "general_web",
            "web_research": "general_web",
        }
        seen: set[str] = set()
        normalized: list[str] = []
        for item in values:
            token = aliases.get(str(item or "").strip().lower(), str(item or "").strip().lower())
            if token not in SEARCH_PROVIDER_PRIORITY_ALLOWED or token in seen:
                continue
            seen.add(token)
            normalized.append(token)
        for token in SEARCH_PROVIDER_PRIORITY_DEFAULT:
            if token not in seen:
                normalized.append(token)
        return normalized

    def get_search_endpoint(self) -> str:
        return str((self.get_web().get("search_api_endpoint") or "")).strip()

    def set_search_provider(self, provider: str, user: str | None = None) -> str:
        p = (provider or "").strip().lower()
        if p in {"search", "web", "fallback", "default"}:
            p = "html"
        if p in {"searx", "searx-ng", "sxng"}:
            p = "searxng"
        if p in {"brave-search", "bravesearch"}:
            p = "brave"

        if p not in {"html", "searxng", "brave"}:
            return "Usage: search provider <html|searxng|brave>"

        data = self._load_raw()
        web = data.get("web") if isinstance(data.get("web"), dict) else {}
        tools = data.get("tools_enabled") if isinstance(data.get("tools_enabled"), dict) else {}
        prev = str(web.get("search_provider") or "html").strip().lower()
        web["search_provider"] = p
        # Operator intent: selecting a search provider should activate web path.
        web["enabled"] = True
        tools["web"] = True
        data["web"] = web
        data["tools_enabled"] = tools
        self._save_raw(data)
        self.record_change("search_provider", p, "success", f"from={prev}", user)

        endpoint = str(web.get("search_api_endpoint") or "").strip()
        if p == "searxng":
            if not endpoint:
                return (
                    "Search provider set to searxng and web enabled. "
                    "Configure web.search_api_endpoint in policy.json."
                )
            if endpoint.endswith(":8080/search"):
                return (
                    "Search provider set to searxng and web enabled. "
                    "Current endpoint is on Nova's own port (8080) and may return 404; set a real SearXNG endpoint."
                )
            return f"Search provider set to searxng and web enabled (endpoint: {endpoint})."

        if p == "brave":
            return (
                "Search provider set to brave and web enabled. "
                "Set BRAVE_SEARCH_API_KEY or configure web.search_api_key_env if needed."
            )

        return "Search provider set to html and web enabled."

    def set_search_provider_priority(self, priority: str | list[str], user: str | None = None) -> str:
        raw_items = priority if isinstance(priority, list) else re.split(r"[\r\n,]+", str(priority or ""))
        aliases = {
            "wiki": "wikipedia",
            "stack-overflow": "stackexchange",
            "stackoverflow": "stackexchange",
            "web": "general_web",
            "general": "general_web",
            "web_research": "general_web",
        }
        normalized: list[str] = []
        seen: set[str] = set()
        invalid: list[str] = []
        for item in raw_items:
            token = aliases.get(str(item or "").strip().lower(), str(item or "").strip().lower())
            if not token:
                continue
            if token not in SEARCH_PROVIDER_PRIORITY_ALLOWED:
                invalid.append(token)
                continue
            if token in seen:
                continue
            seen.add(token)
            normalized.append(token)

        if invalid or not normalized:
            return "Usage: search provider priority <wikipedia,stackexchange,general_web>"

        for token in SEARCH_PROVIDER_PRIORITY_DEFAULT:
            if token not in seen:
                normalized.append(token)

        data = self._load_raw()
        web = data.get("web") if isinstance(data.get("web"), dict) else {}
        prev = ",".join(self.get_search_provider_priority())
        web["search_provider_priority"] = normalized
        web["enabled"] = True
        data["web"] = web
        self._save_raw(data)
        self.record_change("search_provider_priority", ",".join(normalized), "success", f"from={prev}", user)
        return "Search provider priority set to " + ", ".join(normalized) + "."

    def set_search_endpoint(self, endpoint: str, user: str | None = None) -> str:
        raw = str(endpoint or "").strip()
        if not raw:
            return "Usage: search endpoint <http://host:port/search>"

        candidate = raw
        if "://" not in candidate:
            candidate = "http://" + candidate

        parsed = urlparse(candidate)
        if not str(parsed.scheme or "").strip().lower() in {"http", "https"}:
            return "Usage: search endpoint <http://host:port/search>"
        if not str(parsed.hostname or "").strip():
            return "Usage: search endpoint <http://host:port/search>"

        path = str(parsed.path or "").strip()
        if not path:
            path = "/search"
        normalized = parsed._replace(path=path, params="", query="", fragment="").geturl()

        data = self._load_raw()
        web = data.get("web") if isinstance(data.get("web"), dict) else {}
        prev = str(web.get("search_api_endpoint") or "").strip()
        web["search_api_endpoint"] = normalized
        web["enabled"] = True
        data["web"] = web
        self._save_raw(data)
        self.record_change("search_endpoint", normalized, "success", f"from={prev}", user)
        return f"Search endpoint set to {normalized}."

    def auto_repair_search_endpoint(self, endpoint: str, user: str | None = None) -> str:
        normalized = str(endpoint or "").strip()
        if not normalized:
            return ""

        data = self._load_raw()
        web = data.get("web") if isinstance(data.get("web"), dict) else {}
        prev = str(web.get("search_api_endpoint") or "").strip()
        if prev == normalized:
            return ""

        web["search_api_endpoint"] = normalized
        web["enabled"] = True
        data["web"] = web
        self._save_raw(data)
        self.record_change("search_endpoint_auto_repair", normalized, "success", f"from={prev}", user)
        return f"Search endpoint auto-repaired to {normalized}."

    def audit(self, limit: int = 20) -> str:
        """Return formatted recent policy changes."""
        n = max(1, min(200, int(limit or 20)))
        if not self.audit_log_file.exists():
            return "No policy audit entries yet."

        try:
            lines = [ln for ln in self.audit_log_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except Exception as e:
            return f"Failed to read policy audit log: {e}"

        if not lines:
            return "No policy audit entries yet."

        rows = []
        for ln in lines[-n:]:
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue

        if not rows:
            return "No parseable policy audit entries found."

        out = [f"Recent policy changes (last {len(rows)}):"]
        for r in rows:
            ts = int(r.get("ts") or 0)
            tstr = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "unknown-time"
            user = str(r.get("user") or "unknown")
            action = str(r.get("action") or "")
            target = str(r.get("target") or "")
            result = str(r.get("result") or "")
            details = str(r.get("details") or "")
            out.append(f"- {tstr} user={user} action={action} target={target} result={result} details={details}")

        return "\n".join(out)
