from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote, urlparse

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
    endpoint = str(cfg.get("stackexchange_api_endpoint") or "https://api.stackexchange.com/2.3/search/advanced").strip()
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
            return "No active web research session. Start with: web research <query>"

        max_results = max(1, min(40, int((policy_web_fn().get("research_max_results") or 8))))
        page = session_store.next_page(max_results)
        if page is None:
            return "No active web research session. Start with: web research <query>"
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
            lines.append(f"{remaining} more result(s) available. Type 'web continue' to keep going.")
        else:
            lines.append("End of cached research results.")

        lines.append("Tip: run 'web gather <url>' for any source above to fetch and summarize it fully.")
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

    domains = allow_domains[: max(1, min(domains_limit, len(allow_domains)))]
    all_hits: list[tuple[float, str, str]] = []
    for domain in domains:
        sitemap_urls = fetch_sitemap_urls_fn(domain, max(200, scan_pages_per_domain * 25))
        if sitemap_urls:
            all_hits.extend(scan_candidate_urls_for_query_fn(sitemap_urls, tokens, max(2, scan_pages_per_domain), min_score))

        seeds = seed_urls_for_domain_fn(domain, tokens, max(1, seeds_per_domain))
        for start_url in seeds:
            all_hits.extend(crawl_domain_for_query_fn(start_url, tokens, max(2, pages_per_domain), max(0, max_depth)))

    if not all_hits:
        return "No relevant pages found across allowlisted domains for that query."

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
        return "No relevant pages found across allowlisted domains for that query."

    lines = [f"Web research results (allowlisted crawl) for: {q}"]
    rank = page.start
    for score, url, snippet in page.rows:
        rank += 1
        lines.append(f"{rank}. [{score:.1f}] {url}")
        if snippet:
            lines.append(f"   {snippet[:220]}")

    remaining = session_store.remaining_count()
    if remaining > 0:
        lines.append(f"{remaining} more result(s) available. Type 'web continue' to keep going.")
    else:
        lines.append("No more results pending for this query.")

    lines.append("Tip: run 'web gather <url>' for any source above to fetch and summarize it fully.")
    return "\n".join(lines)
