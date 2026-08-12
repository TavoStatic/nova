from __future__ import annotations

import hashlib
import html
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

from services.nova_web_contracts import STACKEXCHANGE_API_ENDPOINT_DEFAULT
from services.web_research_session import WebResearchSessionStore


def _provider_request_headers(token: str = "") -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Nova/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return headers


def _clean_html_text(value: str) -> str:
    text = html.unescape(str(value or "").strip())
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _prioritize_research_domains(domains: list[str], query_tokens: list[str]) -> list[str]:
    raw_terms = [str(token or "").strip().lower() for token in query_tokens if str(token or "").strip()]

    def _domain_score(domain: str) -> tuple[float, str]:
        low = str(domain or "").strip().lower()
        score = 0.0
        if any(term in {"tsds", "attendance", "ada", "submission", "reporting"} for term in raw_terms):
            if low == "tea.texas.gov" or low.endswith(".tea.texas.gov"):
                score += 16.0
            if "tsds.txschools.gov" in low:
                score += 14.0
            if "texasstudentdatasystem.org" in low:
                score += 12.0
            if low == "txschools.gov" or low.endswith(".txschools.gov"):
                score += 8.0
        score += sum(low.count(term) * 4.0 for term in raw_terms)
        return (-score, low)

    return sorted([str(item or "").strip() for item in domains if str(item or "").strip()], key=_domain_score)


def _query_seed_urls_for_domain(domain: str, query_tokens: list[str], max_candidates: int = 12) -> list[str]:
    base = f"https://{domain}"
    domain_low = str(domain or "").strip().lower()
    raw_terms = [str(token or "").strip().lower() for token in query_tokens if str(token or "").strip()]
    expanded_terms = list(raw_terms)
    if "attendance" in raw_terms:
        for term in ("ada", "reporting"):
            if term not in expanded_terms:
                expanded_terms.append(term)
    slugs: list[str] = []
    for term in expanded_terms:
        slug = re.sub(r"[^a-z0-9]+", "-", term).strip("-")
        if slug and slug not in slugs:
            slugs.append(slug)

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(url: str) -> None:
        clean = str(url or "").strip()
        if not clean or clean in seen:
            return
        seen.add(clean)
        candidates.append(clean)

    if domain_low == "tea.texas.gov" or domain_low.endswith(".tea.texas.gov"):
        _add(f"{base}/reports-and-data/data-submission")
        _add(f"{base}/reports-and-data")
        for slug in slugs[:4]:
            _add(f"{base}/reports-and-data/data-submission/{slug}")
            _add(f"{base}/reports-and-data/{slug}")
    elif "tsds.txschools.gov" in domain_low or "texasstudentdatasystem.org" in domain_low:
        _add(f"{base}/tsds")
        for slug in slugs[:4]:
            _add(f"{base}/{slug}")
            _add(f"{base}/resources/{slug}")
    elif domain_low == "txschools.gov" or domain_low.endswith(".txschools.gov"):
        _add(f"{base}/tsds")
        for slug in slugs[:4]:
            _add(f"{base}/{slug}")
    else:
        for slug in slugs[:4]:
            _add(f"{base}/{slug}")

    _add(f"{base}/")

    return candidates[: max(1, int(max_candidates or 1))]


def scan_candidate_urls_for_query(
    urls: list[str],
    query_tokens: list[str],
    max_pages: int,
    min_score: float = 3.0,
    *,
    requests_get_fn: Callable[..., Any],
    expand_research_terms_fn: Callable[[list[str]], list[str]],
    extract_text_from_html_content_fn: Callable[[str, int], str],
    score_research_hit_fn: Callable[..., float],
) -> list[tuple[float, str, str]]:
    terms = expand_research_terms_fn(query_tokens)

    def _url_candidate_score(u: str) -> float:
        low = (u or "").lower()
        parsed = urlparse(u)
        score = 0.0
        for term in terms:
            score += low.count(term) * 2.0
        for keyword in ("tsds", "attendance", "ada", "submission", "calendar", "timeline", "report", "student-data"):
            if keyword in low:
                score += 3.0
        if (parsed.path or "/") in {"", "/"}:
            score -= 2.0
        if re.search(r"\.(pdf|docx?|xlsx?|pptx?)($|\?)", low):
            score -= 4.0
        return score

    ranked_urls = sorted(urls, key=_url_candidate_score, reverse=True)
    hits: list[tuple[float, str, str]] = []
    scanned = 0

    for url in ranked_urls:
        if scanned >= max_pages:
            break
        try:
            response = requests_get_fn(url, headers={"User-Agent": "Nova/1.0"}, timeout=20)
            raise_for_status = getattr(response, "raise_for_status", None)
            if callable(raise_for_status):
                raise_for_status()
        except Exception:
            continue

        headers = getattr(response, "headers", {}) or {}
        ctype = str(headers.get("Content-Type") or "").lower() if hasattr(headers, "get") else ""
        scanned += 1

        if "html" in ctype:
            text = extract_text_from_html_content_fn(str(getattr(response, "text", "") or ""), 5000)
            score = score_research_hit_fn(url, text, terms, primary_tokens=query_tokens)
            if score >= min_score:
                hits.append((score, url, text[:900]))
        else:
            score = score_research_hit_fn(url, "", terms, primary_tokens=query_tokens)
            if score >= min_score:
                snippet = f"Non-HTML source ({ctype or 'unknown'}). Use web gather <url> to fetch and inspect."
                hits.append((score, url, snippet))

    return hits


def extract_urls(text: str) -> list[str]:
    seen = set()
    out = []
    for match in re.findall(r"https?://[^\s)>\]]+", text or "", flags=re.I):
        url = match.rstrip(".,;:")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def decode_search_href(href: str) -> str:
    candidate = (href or "").strip()
    if not candidate:
        return ""
    if candidate.startswith("/l/?"):
        params = parse_qs(urlparse("https://duckduckgo.com" + candidate).query)
        return unquote((params.get("uddg") or [""])[0])
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    return ""


def extract_text_from_path(path: Path, max_chars: int = 2000) -> str:
    try:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".log"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            return re.sub(r"\s+", " ", text).strip()[:max_chars]
        if suffix in {".html", ".htm"}:
            return extract_text_from_html_content(
                path.read_text(encoding="utf-8", errors="ignore"),
                max_chars=max_chars,
            )
        return ""
    except Exception:
        return ""


def extract_text_from_html_content(raw_html: str, max_chars: int = 2000) -> str:
    raw = raw_html or ""
    raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()[:max_chars]


def extract_same_host_links(raw_html: str, base_url: str, host: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', raw_html or "", flags=re.I):
        href = (href or "").strip()
        if not href or href.startswith("#"):
            continue
        if href.startswith("javascript:") or href.startswith("mailto:"):
            continue

        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            continue
        if parsed.hostname.lower() != str(host or "").lower():
            continue

        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            clean += f"?{parsed.query}"
        if clean in seen:
            continue
        seen.add(clean)
        links.append(clean)
    return links


def expand_research_terms(tokens: list[str]) -> list[str]:
    terms = {token for token in tokens if token}
    if "reporting" in terms:
        terms.update({"submission", "report"})
    if "attendance" in terms:
        terms.update({"ada", "attendance", "reporting"})
    if "timeline" in terms:
        terms.update({"calendar", "deadline", "dates"})
    return list(terms)


def score_research_hit(
    url: str,
    text: str,
    terms: list[str],
    primary_tokens: Optional[list[str]] = None,
) -> float:
    low_url = (url or "").lower()
    low_text = (text or "").lower()
    primary_tokens = [token for token in (primary_tokens or []) if token]
    parsed = urlparse(url or "")

    unique_text_hits = sum(1 for token in terms if token in low_text)
    unique_url_hits = sum(1 for token in terms if token in low_url)
    total_text_hits = sum(low_text.count(token) for token in terms)
    total_url_hits = sum(low_url.count(token) for token in terms)

    boost_patterns = ["tsds", "attendance", "ada", "submission", "calendar", "timeline", "report", "student-data"]
    path_boost = sum(1 for token in boost_patterns if token in low_url)

    score = (
        unique_text_hits * 4.0
        + unique_url_hits * 6.0
        + min(30.0, float(total_text_hits) * 0.25)
        + min(20.0, float(total_url_hits) * 0.75)
        + path_boost * 1.5
    )
    if primary_tokens and not any(token in low_text or token in low_url for token in primary_tokens):
        score -= 8.0
    if (parsed.path or "/") in {"", "/"} and primary_tokens and not any(token in low_text or token in low_url for token in primary_tokens):
        score -= 12.0
    return score


def crawl_domain_for_query(
    start_url: str,
    query_tokens: list[str],
    max_pages: int,
    max_depth: int,
    *,
    requests_get_fn: Callable[..., Any],
    expand_research_terms_fn: Callable[[list[str]], list[str]],
    extract_text_from_html_content_fn: Callable[[str, int], str],
    score_research_hit_fn: Callable[..., float],
    extract_same_host_links_fn: Callable[[str, str, str], list[str]],
) -> list[tuple[float, str, str]]:
    parsed = urlparse(start_url)
    host = parsed.hostname or ""
    if not host:
        return []

    terms = expand_research_terms_fn(query_tokens)
    queue: list[tuple[str, int]] = [(start_url, 0)]
    seen = {start_url}
    fetched = 0
    hits: list[tuple[float, str, str]] = []

    while queue and fetched < max_pages:
        url, depth = queue.pop(0)
        try:
            response = requests_get_fn(url, headers={"User-Agent": "Nova/1.0"}, timeout=25)
            response.raise_for_status()
        except Exception:
            continue

        fetched += 1
        content_type = str((getattr(response, "headers", {}) or {}).get("Content-Type") or "").lower()
        if "html" not in content_type:
            continue

        raw = str(getattr(response, "text", "") or "")
        text = extract_text_from_html_content_fn(raw, 5000)
        score = score_research_hit_fn(url, text, terms, primary_tokens=query_tokens)
        if score >= 3.0:
            hits.append((score, url, text[:900]))

        if depth >= max_depth:
            continue
        for next_url in extract_same_host_links_fn(raw, url, host):
            if next_url in seen:
                continue
            seen.add(next_url)
            queue.append((next_url, depth + 1))

    return hits


def seed_urls_for_domain(
    domain: str,
    query_tokens: list[str],
    max_seed: int = 30,
    *,
    fetch_sitemap_urls_fn: Callable[[str, int], list[str]],
    expand_research_terms_fn: Callable[[list[str]], list[str]],
) -> list[str]:
    seeds = [f"https://{domain}/"]
    candidates = fetch_sitemap_urls_fn(domain, max_seed * 3)
    if not candidates:
        return seeds

    terms = expand_research_terms_fn(query_tokens)
    scored: list[tuple[int, str]] = []
    for url in candidates:
        low = url.lower()
        score = sum(low.count(term) for term in terms)
        for token in ("tsds", "attendance", "ada", "submission", "calendar", "timeline", "report"):
            if token in low:
                score += 2
        if score > 0:
            scored.append((score, url))

    scored.sort(key=lambda item: item[0], reverse=True)
    for _score, url in scored[:max_seed]:
        if url not in seeds:
            seeds.append(url)

    if len(seeds) < (max_seed + 1):
        for url in candidates:
            if url in seeds:
                continue
            seeds.append(url)
            if len(seeds) >= (max_seed + 1):
                break
    return seeds


def looks_like_code_discovery_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    if not low:
        return False
    code_markers = (
        "github",
        "repo",
        "repository",
        "source code",
        "implementation",
        "example repo",
        "code example",
        "sample project",
        "issue",
        "codebase",
        "api docs",
        "documentation",
        "sdk",
        "package",
        "module",
        "library",
        "pull request",
        "public repo",
        "open source",
        "function ",
        "class ",
    )
    return any(marker in low for marker in code_markers)


def host_label(url: str) -> str:
    try:
        return (urlparse(url).hostname or "source").lower()
    except Exception:
        return "source"


def summary_from_gather_output(raw: str) -> str:
    txt = (raw or "").strip()
    if not txt:
        return ""
    match = re.search(r"Summary snippet:\s*(.+)$", txt, flags=re.I | re.S)
    if match:
        txt = match.group(1).strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt[:280].strip()


def is_weak_grounded_snippet(value: str) -> bool:
    low = (value or "").strip().lower()
    if not low:
        return True
    weak_markers = (
        "you need to enable javascript",
        "welcome to texas education agency",
        "skip to main content",
        "cookie",
        "privacy policy",
        "all rights reserved",
    )
    return any(marker in low for marker in weak_markers)


def build_grounded_answer(
    query_text: str,
    *,
    max_sources: int = 2,
    tool_web_research_fn: Callable[[str], str],
    tool_web_gather_fn: Callable[[str], str],
) -> str:
    research = tool_web_research_fn(query_text)
    if not isinstance(research, str) or not research.strip():
        return ""

    urls = extract_urls(research)
    if not urls:
        return ""

    snippets: list[tuple[str, str]] = []
    for url in urls[: max(1, int(max_sources))]:
        gathered = tool_web_gather_fn(url)
        snippet = summary_from_gather_output(gathered if isinstance(gathered, str) else "")
        if snippet and not is_weak_grounded_snippet(snippet):
            snippets.append((url, snippet))

    if not snippets:
        return ""

    lines = ["I found sourced information from allowlisted references:"]
    for _url, snippet in snippets:
        lines.append(f"- {snippet}")

    cited_hosts: list[str] = []
    for url, _snippet in snippets:
        host = host_label(url)
        if host not in cited_hosts:
            cited_hosts.append(host)
    for host in cited_hosts:
        lines.append(f"[source: {host}]")

    return "\n".join(lines)


def fetch_sitemap_urls(
    domain: str,
    limit: int = 80,
    *,
    requests_get_fn: Callable[..., Any],
    host_allowed_fn: Callable[[str, list[str]], bool],
) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    seen_sitemaps: set[str] = set()
    queue = [f"https://{domain}/sitemap.xml", f"https://{domain}/sitemap_index.xml"]

    while queue and len(urls) < limit:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)

        try:
            response = requests_get_fn(sitemap_url, headers={"User-Agent": "Nova/1.0"}, timeout=20)
            if int(getattr(response, "status_code", 0) or 0) != 200:
                continue
            body = str(getattr(response, "text", "") or "")
            locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", body, flags=re.I)
            for raw_url in locs:
                raw_url = html.unescape((raw_url or "").strip())
                parsed = urlparse(raw_url)
                if parsed.scheme not in ("http", "https"):
                    continue
                if not parsed.hostname:
                    continue
                if not host_allowed_fn(parsed.hostname, [domain]):
                    continue

                clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if parsed.query:
                    clean += f"?{parsed.query}"

                if Path(parsed.path).suffix.lower() == ".xml":
                    if clean not in seen_sitemaps:
                        queue.append(clean)
                    continue

                if clean in seen:
                    continue
                seen.add(clean)
                urls.append(clean)
                if len(urls) >= limit:
                    break
        except Exception:
            continue

    return urls


def tool_web_fetch(
    url: str,
    *,
    explain_missing_fn: Callable[[str, list[str]], str],
    policy_tools_enabled_fn: Callable[[], dict],
    web_fetch_fn: Callable[[str], dict],
    web_allowlist_message_fn: Callable[[str], str],
) -> str:
    missing = explain_missing_fn("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled_fn().get("web", False):
        return "Web tool disabled by policy."

    out = web_fetch_fn(url)
    if not out.get("ok"):
        err = out.get("error", "unknown error")
        if isinstance(err, str) and "not allowed" in err.lower():
            return web_allowlist_message_fn(url)
        return f"[FAIL] {err}"

    return f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)"


def tool_wikipedia_lookup(
    query: str,
    *,
    explain_missing_fn: Callable[[str, list[str]], str],
    policy_tools_enabled_fn: Callable[[], dict],
    web_enabled_fn: Callable[[], bool],
    requests_get_fn: Callable[..., Any],
) -> str:
    missing = explain_missing_fn("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled_fn().get("web", False):
        return "Web tool disabled by policy."
    if not web_enabled_fn():
        return "Web tool disabled by policy."

    q = str(query or "").strip()
    if not q:
        return "Usage: wikipedia <topic>"

    try:
        search_resp = requests_get_fn(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": q,
                "format": "json",
                "utf8": 1,
                "srlimit": 3,
            },
            headers=_provider_request_headers(),
            timeout=20,
        )
        search_resp.raise_for_status()
        search_data = search_resp.json()
    except Exception as exc:
        return f"[FAIL] Wikipedia lookup unavailable: {exc}"

    matches = ((search_data.get("query") or {}).get("search") or []) if isinstance(search_data, dict) else []
    if not matches:
        return f"No Wikipedia results found for: {q}"

    title = str((matches[0] or {}).get("title") or q).strip() or q
    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'), safe=':_()')}"
    try:
        summary_resp = requests_get_fn(summary_url, headers=_provider_request_headers(), timeout=20)
        summary_resp.raise_for_status()
        summary_data = summary_resp.json()
    except Exception as exc:
        return f"[FAIL] Wikipedia summary unavailable: {exc}"

    display_title = str(summary_data.get("title") or title).strip() or title
    extract = str(summary_data.get("extract") or "").strip()
    page_url = str((((summary_data.get("content_urls") or {}).get("desktop") or {}).get("page") or "")).strip()
    if not page_url:
        page_url = f"https://en.wikipedia.org/wiki/{quote(display_title.replace(' ', '_'))}"

    lines = [f"Wikipedia summary for: {display_title}", page_url]
    if extract:
        lines.append(extract)

    related = []
    for item in matches[1:3]:
        related_title = str((item or {}).get("title") or "").strip()
        if not related_title:
            continue
        related.append((related_title, f"https://en.wikipedia.org/wiki/{quote(related_title.replace(' ', '_'))}"))
    if related:
        lines.append("Related pages:")
        for index, (related_title, related_url) in enumerate(related, start=1):
            lines.append(f"{index}. {related_title}")
            lines.append(f"   {related_url}")
    return "\n".join(lines)


def tool_stackexchange_search(
    query: str,
    *,
    explain_missing_fn: Callable[[str, list[str]], str],
    policy_tools_enabled_fn: Callable[[], dict],
    web_enabled_fn: Callable[[], bool],
    policy_web_fn: Callable[[], dict],
    requests_get_fn: Callable[..., Any],
    env: dict[str, str],
) -> str:
    missing = explain_missing_fn("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled_fn().get("web", False):
        return "Web tool disabled by policy."
    if not web_enabled_fn():
        return "Web tool disabled by policy."

    q = str(query or "").strip()
    if not q:
        return "Usage: stackexchange <query>"

    cfg = policy_web_fn()
    endpoint = str(cfg.get("stackexchange_api_endpoint") or STACKEXCHANGE_API_ENDPOINT_DEFAULT).strip()
    site = str(cfg.get("stackexchange_site") or "stackoverflow").strip() or "stackoverflow"
    key_env = str(cfg.get("stackexchange_api_key_env") or "STACKEXCHANGE_API_KEY").strip() or "STACKEXCHANGE_API_KEY"
    api_key = str(env.get(key_env) or "").strip()
    params = {
        "order": "desc",
        "sort": "relevance",
        "site": site,
        "q": q,
        "pagesize": 5,
        "accepted": "True",
    }
    if api_key:
        params["key"] = api_key

    try:
        resp = requests_get_fn(endpoint, params=params, headers=_provider_request_headers(), timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return f"[FAIL] StackExchange search unavailable: {exc}"

    items = data.get("items") if isinstance(data, dict) else []
    if not items:
        return f"No StackExchange results found for: {q}"

    lines = [f"StackExchange results for: {q} (site={site})"]
    for index, item in enumerate(items[:5], start=1):
        title = _clean_html_text(item.get("title") or "")
        link = str(item.get("link") or "").strip()
        score = int(item.get("score") or 0)
        answer_count = int(item.get("answer_count") or 0)
        answered = bool(item.get("is_answered"))
        tags = [str(tag or "").strip() for tag in (item.get("tags") or []) if str(tag or "").strip()][:4]
        if title:
            lines.append(f"{index}. {title}")
        if link:
            lines.append(f"   {link}")
        meta = [f"score={score}", f"answers={answer_count}", f"answered={answered}"]
        if tags:
            meta.append("tags=" + ", ".join(tags))
        lines.append(f"   {' | '.join(meta)}")
    return "\n".join(lines)


def tool_web_search(
    query: str,
    *,
    explain_missing_fn: Callable[[str, list[str]], str],
    policy_tools_enabled_fn: Callable[[], dict],
    web_enabled_fn: Callable[[], bool],
    policy_web_fn: Callable[[], dict],
    host_allowed_fn: Callable[[str, list[str]], bool],
    decode_search_href_fn: Callable[[str], str],
    probe_search_endpoint_fn: Callable[..., dict],
    web_allowlist_message_fn: Callable[[str], str],
    requests_get_fn: Callable[..., Any],
) -> str:
    missing = explain_missing_fn("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled_fn().get("web", False):
        return "Web tool disabled by policy."
    if not web_enabled_fn():
        return "Web tool disabled by policy."

    cfg = policy_web_fn()
    allow_domains = cfg.get("allow_domains") or []
    if not allow_domains:
        return "Web search unavailable: no allow_domains configured in policy."

    q = str(query or "").strip()
    if not q:
        return "Usage: web search <query>"

    def _search_via_api(query_text: str, domains: list[str], max_results: int = 5) -> tuple[list[tuple[str, str]], Optional[str]]:
        provider = str(cfg.get("search_provider") or "").strip().lower()
        if provider not in {"brave", "searxng"}:
            return ([], None)

        scoped_query = query_text + " " + " ".join(f"site:{domain}" for domain in domains[:8])

        if provider == "brave":
            key_env = str(cfg.get("search_api_key_env") or "BRAVE_SEARCH_API_KEY").strip() or "BRAVE_SEARCH_API_KEY"
            api_key = str(os.environ.get(key_env) or "").strip()
            if not api_key:
                return ([], f"missing_api_key_env:{key_env}")

            endpoint = str(cfg.get("search_api_endpoint") or "https://api.search.brave.com/res/v1/web/search").strip()
            try:
                resp = requests_get_fn(
                    endpoint,
                    params={"q": scoped_query, "count": max(1, min(20, int(max_results)))},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key,
                        "User-Agent": "Nova/1.0",
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                return ([], f"api_error:{exc}")

            items = []
            for item in ((data.get("web") or {}).get("results") or []):
                url = str(item.get("url") or "").strip()
                title = str(item.get("title") or "").strip() or url
                if not url:
                    continue
                host = urlparse(url).hostname or ""
                if not host_allowed_fn(host, domains):
                    continue
                items.append((title, url))
                if len(items) >= max_results:
                    break
            return (items, None)

        endpoint_probe = probe_search_endpoint_fn(
            str(cfg.get("search_api_endpoint") or "http://127.0.0.1:8080/search").strip(),
            timeout=5.0,
            persist_repair=True,
        )
        if not bool(endpoint_probe.get("ok")):
            return ([], f"api_error:{endpoint_probe.get('note')}")
        endpoint = str(endpoint_probe.get("resolved_endpoint") or endpoint_probe.get("endpoint") or "http://127.0.0.1:8080/search").strip()
        try:
            resp = requests_get_fn(
                endpoint,
                params={"q": scoped_query, "format": "json"},
                headers={"Accept": "application/json", "User-Agent": "Nova/1.0"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return ([], f"api_error:{exc}")

        items = []
        for item in (data.get("results") or []):
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip() or url
            if not url:
                continue
            host = urlparse(url).hostname or ""
            if not host_allowed_fn(host, domains):
                continue
            items.append((title, url))
            if len(items) >= max_results:
                break
        return (items, None)

    def _local_search_backend_message(api_err: object) -> str:
        endpoint = str(cfg.get("search_api_endpoint") or "http://127.0.0.1:8080/search").strip()
        err_text = str(api_err or "").strip()
        endpoint_low = endpoint.lower()
        is_local = any(host in endpoint_low for host in ("127.0.0.1", "localhost"))
        if not is_local:
            return ""
        if any(token in err_text.lower() for token in ("404", "not found", "connection refused", "failed to establish a new connection", "max retries exceeded")):
            return (
                "[FAIL] Local web search backend is unavailable. The configured searxng service at "
                f"{endpoint} did not respond correctly. If it runs in Docker, start that service first. "
                "For now, try 'web research <query>' or fetch a specific URL with 'web <url>'."
            )
        return ""

    def _search_via_html(query_text: str, domains: list[str], max_results: int = 5) -> tuple[list[tuple[str, str]], Optional[str]]:
        scoped_query = query_text + " " + " ".join(f"site:{domain}" for domain in domains[:6])
        try:
            resp = requests_get_fn(
                "https://duckduckgo.com/html/",
                params={"q": scoped_query},
                headers={"User-Agent": "Nova/1.0"},
                timeout=30,
            )
            resp.raise_for_status()
            page = resp.text
        except Exception as exc:
            return ([], f"html_error:{exc}")

        hrefs = re.findall(r'href=["\']([^"\']+)["\']', page, flags=re.I)
        direct_urls = re.findall(r"https?://[^\s\"'<>]+", page)
        seen: set[str] = set()
        urls: list[tuple[str, str]] = []
        for href in hrefs:
            url = decode_search_href_fn(href)
            if not url:
                continue
            host = urlparse(url).hostname or ""
            if not host_allowed_fn(host, domains):
                continue
            if url in seen:
                continue
            seen.add(url)
            urls.append((url, url))
            if len(urls) >= max_results:
                break

        if len(urls) < max_results:
            for url in direct_urls:
                host = urlparse(url).hostname or ""
                if not host_allowed_fn(host, domains):
                    continue
                if url in seen:
                    continue
                seen.add(url)
                urls.append((url, url))
                if len(urls) >= max_results:
                    break
        return (urls, None)

    provider = str(cfg.get("search_provider") or "").strip().lower()
    rows, api_err = _search_via_api(q, allow_domains, max_results=5)
    provider_used = f"api:{provider}" if rows else "html"
    if not rows:
        rows, html_err = _search_via_html(q, allow_domains, max_results=5)
        if not rows and api_err:
            backend_msg = _local_search_backend_message(api_err)
            if backend_msg:
                return backend_msg
            if "404" in str(api_err).lower() or "not found" in str(api_err).lower():
                return (
                    "[FAIL] Web search service returned 404. Try a different phrase, use 'web research <query>', "
                    "or fetch a specific URL with 'web <url>'."
                )
            return f"[FAIL] Web search unavailable. API reason={api_err}; HTML fallback failed={html_err}"

    if not rows:
        return "No allowlisted web results found for that query.\n\n" + web_allowlist_message_fn(query)

    lines = [f"Web results (allowlisted, provider={provider_used}):"]
    for index, (title, url) in enumerate(rows, start=1):
        if title and title != url:
            lines.append(f"{index}. {title}")
            lines.append(f"   {url}")
        else:
            lines.append(f"{index}. {url}")
    lines.append("Tip: run 'web gather <url>' to fetch and summarize one result.")
    return "\n".join(lines)


def tool_web_gather(
    url: str,
    *,
    explain_missing_fn: Callable[[str, list[str]], str],
    policy_tools_enabled_fn: Callable[[], dict],
    web_fetch_fn: Callable[[str], dict],
    web_allowlist_message_fn: Callable[[str], str],
    extract_text_from_path_fn: Callable[[Path, int], str],
) -> str:
    missing = explain_missing_fn("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled_fn().get("web", False):
        return "Web tool disabled by policy."

    out = web_fetch_fn(url)
    if not out.get("ok"):
        err = out.get("error", "unknown error")
        if isinstance(err, str) and "not allowed" in err.lower():
            return web_allowlist_message_fn(url)
        return f"[FAIL] {err}"

    path = Path(out["path"])
    snippet = extract_text_from_path_fn(path, 2200)
    if snippet:
        return (
            f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)\n"
            f"Summary snippet:\n{snippet}"
        )

    content_type = str(out.get("content_type") or "").lower()
    if "html" in content_type:
        return (
            f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)\n"
            "I could access the page, but I couldn't extract readable content. "
            "It may be JavaScript-heavy/dynamic, and I do not run a browser renderer in this path."
        )

    return f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)"


NO_ACTIVE_WEB_RESEARCH_SESSION = "No active web research session. Start with: web research <query>"
NO_RELEVANT_ALLOWLISTED_PAGES = "No relevant pages found across allowlisted domains for that query."
WEB_CONTINUE_AVAILABLE_SUFFIX = "more result(s) available. Type 'web continue' to keep going."
WEB_GATHER_TIP = "Tip: run 'web gather <url>' for any source above to fetch and summarize it fully."


def tool_web_research(
    query: str,
    *,
    continue_mode: bool = False,
    explain_missing_fn: Callable[[str, list[str]], str],
    policy_tools_enabled_fn: Callable[[], dict],
    web_enabled_fn: Callable[[], bool],
    policy_web_fn: Callable[[], dict],
    tokenize_fn: Callable[[str], list[str]],
    fetch_sitemap_urls_fn: Callable[[str, int], list[str]],
    scan_candidate_urls_for_query_fn: Callable[[list[str], list[str], int, float], list[tuple[float, str, str]]],
    seed_urls_for_domain_fn: Callable[[str, list[str], int], list[str]],
    crawl_domain_for_query_fn: Callable[[str, list[str], int, int], list[tuple[float, str, str]]],
    session_store: WebResearchSessionStore,
) -> str:
    missing = explain_missing_fn("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled_fn().get("web", False):
        return "Web tool disabled by policy."
    if not web_enabled_fn():
        return "Web tool disabled by policy."

    cfg = policy_web_fn()
    allow_domains = cfg.get("allow_domains") or []
    if not allow_domains:
        return "Web research unavailable: no allow_domains configured in policy."

    q = str(query or "").strip()
    if continue_mode:
        if not session_store.has_results():
            return NO_ACTIVE_WEB_RESEARCH_SESSION

        max_results = max(1, min(40, int((policy_web_fn().get("research_max_results") or 8))))
        page = session_store.next_page(max_results)
        if page is None:
            return NO_ACTIVE_WEB_RESEARCH_SESSION
        if not page.rows and page.start >= page.total:
            return "No more cached research results. Start a new search with: web research <query>"

        lines = [f"Web research results (continued) for: {session_store.query}"]
        rank = page.start
        for score, url, snippet in page.rows:
            rank += 1
            lines.append(f"{rank}. [{score:.1f}] {url}")
            if snippet:
                lines.append(f"   {snippet[:220]}")

        remaining = session_store.remaining_count()
        if remaining > 0:
            lines.append(f"{remaining} {WEB_CONTINUE_AVAILABLE_SUFFIX}")
        else:
            lines.append("End of cached research results.")

        lines.append(WEB_GATHER_TIP)
        return "\n".join(lines)

    if not q:
        return "Usage: web research <query>"

    tokens = tokenize_fn(q)
    if not tokens:
        return "Query too short for web research."

    domains_limit = max(1, min(12, int(cfg.get("research_domains_limit") or 4)))
    pages_per_domain = max(2, min(50, int(cfg.get("research_pages_per_domain") or 8)))
    max_depth = max(0, min(3, int(cfg.get("research_max_depth") or 1)))
    max_results = max(1, min(40, int(cfg.get("research_max_results") or 8)))
    seeds_per_domain = max(1, min(40, int(cfg.get("research_seeds_per_domain") or 8)))
    scan_pages_per_domain = max(2, min(200, int(cfg.get("research_scan_pages_per_domain") or 12)))
    min_score = max(0.0, min(10.0, float(cfg.get("research_min_score") or 3.0)))
    domain_timeout_sec = max(0.5, min(15.0, float(cfg.get("research_domain_timeout_sec") or 5.0)))

    domains = _prioritize_research_domains(
        allow_domains[: max(1, min(domains_limit, len(allow_domains)))],
        tokens,
    )
    all_hits: list[tuple[float, str, str]] = []
    unique_urls: set[str] = set()

    def _extend_hits(rows: list[tuple[float, str, str]]) -> None:
        if not rows:
            return
        all_hits.extend(rows)
        for _score, url, _snippet in rows:
            if url:
                unique_urls.add(str(url))

    direct_fetch_limit = 3

    for domain in domains:
        domain_started = time.perf_counter()
        unique_before = len(unique_urls)
        query_seed_urls = _query_seed_urls_for_domain(domain, tokens, max_candidates=max(6, seeds_per_domain))
        if query_seed_urls:
            _extend_hits(
                scan_candidate_urls_for_query_fn(
                    query_seed_urls,
                    tokens,
                    max(2, min(direct_fetch_limit, len(query_seed_urls))),
                    min_score,
                )
            )
        if len(unique_urls) > unique_before:
            break
        if (time.perf_counter() - domain_started) >= domain_timeout_sec:
            continue

        sitemap_urls = fetch_sitemap_urls_fn(domain, max(200, scan_pages_per_domain * 25))
        if sitemap_urls:
            _extend_hits(scan_candidate_urls_for_query_fn(sitemap_urls, tokens, max(2, scan_pages_per_domain), min_score))
        if len(unique_urls) > unique_before:
            break
        if (time.perf_counter() - domain_started) >= domain_timeout_sec:
            continue

        seeds = seed_urls_for_domain_fn(domain, tokens, max(1, seeds_per_domain))
        for start_url in seeds:
            _extend_hits(crawl_domain_for_query_fn(start_url, tokens, max(2, pages_per_domain), max(0, max_depth)))
            if len(unique_urls) >= max_results:
                break
            if (time.perf_counter() - domain_started) >= domain_timeout_sec:
                break
        if len(unique_urls) >= max_results:
            break

    if not all_hits:
        return NO_RELEVANT_ALLOWLISTED_PAGES

    all_hits.sort(key=lambda item: item[0], reverse=True)
    used: set[str] = set()
    ordered: list[tuple[float, str, str]] = []
    for score, url, snippet in all_hits:
        if url in used:
            continue
        used.add(url)
        ordered.append((score, url, snippet))

    session_store.set_results(q, ordered)

    page = session_store.next_page(max_results)
    if page is None:
        return NO_RELEVANT_ALLOWLISTED_PAGES

    lines = [f"Web research results (allowlisted crawl) for: {q}"]
    rank = page.start
    for score, url, snippet in page.rows:
        rank += 1
        lines.append(f"{rank}. [{score:.1f}] {url}")
        if snippet:
            lines.append(f"   {snippet[:220]}")

    remaining = session_store.remaining_count()
    if remaining > 0:
        lines.append(f"{remaining} {WEB_CONTINUE_AVAILABLE_SUFFIX}")
    else:
        lines.append("No more results pending for this query.")

    lines.append(WEB_GATHER_TIP)
    return "\n".join(lines)


def web_search(
    query: str,
    save_dir: Path,
    *,
    requests_post_fn: Callable[..., Any],
    max_results: int = 5,
) -> dict:
    save_dir.mkdir(parents=True, exist_ok=True)
    try:
        response = requests_post_fn(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            timeout=30,
            headers={"User-Agent": "Nova/1.0"},
        )
    except Exception as exc:
        return {"ok": False, "error": f"Search request failed: {exc}"}

    try:
        response.raise_for_status()
        text = response.text or ""
        entries: list[tuple[str, str]] = []
        for match in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.I | re.S):
            href = match.group(1)
            title_html = match.group(2)
            title = re.sub(r"<.*?>", "", title_html).strip()
            entries.append((title, href))
            if len(entries) >= int(max_results):
                break

        ts = time.strftime("%Y%m%d_%H%M%S")
        digest = hashlib.sha256(str(query or "").encode("utf-8")).hexdigest()[:12]
        out_path = save_dir / f"search_{ts}_{digest}.txt"
        with out_path.open("w", encoding="utf-8") as handle:
            handle.write(f"Search results for: {query}\n\n")
            for index, (title, href) in enumerate(entries, start=1):
                handle.write(f"{index}. {title}\n   {href}\n\n")

        return {"ok": True, "query": query, "path": str(out_path), "bytes": int(out_path.stat().st_size)}
    except Exception as exc:
        return {"ok": False, "error": f"Parsing error: {exc}"}


def tool_search(
    query: str,
    *,
    explain_missing_fn: Callable[[str, list[str]], str],
    policy_tools_enabled_fn: Callable[[], dict],
    web_search_fn: Callable[[str, Path, int], dict],
    web_cache_dir: Path,
) -> str:
    missing = explain_missing_fn("web_fetch", ["web_access"])
    if missing:
        return missing
    if not policy_tools_enabled_fn().get("web", False):
        return "Web tool disabled by policy."

    out = web_search_fn(query, web_cache_dir, 5)
    if not out.get("ok"):
        return f"[FAIL] {out.get('error', 'unknown error')}"
    return f"[OK] Saved: {out['path']} (text, {out['bytes']} bytes)"
