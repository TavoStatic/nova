import argparse
import json
import math
import re
import sqlite3
import time
from pathlib import Path
from typing import List, Tuple, Iterable, Optional

import requests

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nova_memory.sqlite"
POLICY_PATH = BASE_DIR / "policy.json"

OLLAMA_BASE = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"

STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "this", "what", "when", "where",
    "how", "have", "your", "you", "are", "was", "were", "will", "would", "could",
    "about", "into", "over", "under", "then", "than", "just", "also", "very",
}

def load_policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))

def connect():
        con = sqlite3.connect(DB_PATH)
        con.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            kind TEXT NOT NULL,
            source TEXT NOT NULL,
            user TEXT DEFAULT '',
            scope TEXT DEFAULT 'shared',
            text TEXT NOT NULL,
            vec BLOB NOT NULL
        )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_ts ON memories(ts)")
        # Ensure older DBs get a 'user' column if missing
        cols = [r[1] for r in con.execute("PRAGMA table_info(memories)").fetchall()]
        if 'user' not in cols:
                try:
                        con.execute("ALTER TABLE memories ADD COLUMN user TEXT DEFAULT ''")
                        con.commit()
                except Exception:
                        pass
        if 'scope' not in cols:
                try:
                        con.execute("ALTER TABLE memories ADD COLUMN scope TEXT DEFAULT 'shared'")
                        con.commit()
                except Exception:
                        pass
        con.commit()
        return con


def _normalize_scope(scope: str) -> str:
    s = str(scope or "shared").strip().lower()
    if s not in {"shared", "private", "hybrid"}:
        return "shared"
    return s


def _scope_where(scope: str, user: Optional[str]) -> tuple[str, tuple]:
    s = _normalize_scope(scope)
    u = str(user or "").strip()
    if s == "private":
        if not u:
            raise RuntimeError("private_scope_requires_user")
        return "(scope = 'private' AND user = ?)", (u,)
    if s == "shared":
        return "(scope = 'shared')", tuple()
    if u:
        return "(scope = 'shared' OR (scope = 'private' AND user = ?))", (u,)
    return "(scope = 'shared')", tuple()

def embed(text: str) -> List[float]:
    payload = {"model": EMBED_MODEL, "input": text}

    # Try the modern endpoint first
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/embed", json=payload, timeout=1800)
        if r.status_code == 200:
            data = r.json()
            vecs = data.get("embeddings")
            if isinstance(vecs, list) and len(vecs) > 0 and isinstance(vecs[0], list):
                return vecs[0]
    except Exception:
        pass

    # Fallback for older Ollama versions
    payload_old = {"model": EMBED_MODEL, "prompt": text}
    r2 = requests.post(f"{OLLAMA_BASE}/api/embeddings", json=payload_old, timeout=1800)
    r2.raise_for_status()
    data2 = r2.json()

    emb = data2.get("embedding")
    if emb is None:
        d0 = (data2.get("data") or [{}])[0]
        emb = d0.get("embedding")

    if not isinstance(emb, list):
        raise RuntimeError(f"Embeddings API returned unexpected payload keys={list(data2.keys())}")

    return emb

def vec_to_blob(v: List[float]) -> bytes:
    import array
    a = array.array("f", v)
    return a.tobytes()

def blob_to_vec(b: bytes) -> List[float]:
    import array
    a = array.array("f")
    a.frombytes(b)
    return list(a)

def vec_norm(v: List[float]) -> float:
    return math.sqrt(sum(x*x for x in v))

def cosine(a: List[float], b: List[float]) -> float:
    # manual cosine similarity (no numpy)
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def query_tokens(text: str) -> List[str]:
    toks = re.findall(r"[a-z0-9]{3,}", (text or "").lower())
    out = []
    for t in toks:
        if t in STOPWORDS:
            continue
        if t not in out:
            out.append(t)
    return out

def add_memory(kind: str, source: str, text: str, user: str = "", scope: str = "shared"):
    con = connect()
    try:
        scope_norm = _normalize_scope(scope)
        user_norm = str(user or "").strip()
        if scope_norm == "private" and not user_norm:
            raise RuntimeError("private_scope_requires_user")
        v = embed(text)
        con.execute(
            "INSERT INTO memories(ts, kind, source, user, scope, text, vec) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(time.time()), kind, source, user_norm, scope_norm, text, vec_to_blob(v)),
        )
        con.commit()
    finally:
        con.close()

def recall(query: str, top_k: int = 5, min_score: float = 0.25,
           exclude_sources: Optional[Iterable[str]] = None,
           user: Optional[str] = None,
           scope: str = "shared",
           debug: bool = False) -> List[Tuple[float, int, str, str, str, str]]:
    ex = set(s.lower() for s in (exclude_sources or []))

    con = connect()
    try:
        qv = embed(query)
        qn = vec_norm(qv)

        if debug:
            print(f"[DEBUG] query_emb_len={len(qv)} query_emb_norm={qn:.6f} model={EMBED_MODEL}")

        # If the embedding is invalid/zero, do NOT return random memories.
        if qn == 0.0 or len(qv) == 0:
            if debug:
                print("[DEBUG] query embedding is empty/zero; returning no memories.")
            return []

        # Pull newest first so ties prefer recent notes
        where_clause, where_args = _scope_where(scope, user)
        rows = con.execute(
            f"SELECT ts, kind, source, user, text, vec FROM memories WHERE {where_clause} ORDER BY ts DESC",
            where_args,
        ).fetchall()
        scored = []
        lexical_candidates = []
        q_words = query_tokens(query)
        for ts, kind, source, user_row, text, vecblob in rows:
            if source.lower() in ex:
                continue
            v = blob_to_vec(vecblob)
            vn = vec_norm(v)

            # Skip invalid stored vectors
            if vn == 0.0 or len(v) == 0:
                continue

            s = cosine(qv, v)

            if debug and len(scored) < 3:
                print(f"[DEBUG] sample_hit ts={ts} source={source} emb_len={len(v)} emb_norm={vn:.6f} score={s:.6f}")

            if s >= min_score:
                scored.append((s, ts, kind, source, user_row, text))

            # Keep a lightweight lexical candidate list for fallback when embedding recall misses.
            if q_words:
                low_text = text.lower()
                lex = 0
                unique_hits = 0
                for w in q_words:
                    c = low_text.count(w)
                    lex += c
                    if c > 0:
                        unique_hits += 1
                if lex > 0:
                    lexical_candidates.append((lex, unique_hits, ts, kind, source, user_row, text))

        # Sort by score desc, then recency desc
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        if scored:
            return scored[:top_k]

        # Fallback: lexical retrieval if semantic filtering produced no hits.
        # Use small normalized pseudo-scores so caller formatting remains stable.
        if lexical_candidates and len(q_words) >= 2:
            strong = [c for c in lexical_candidates if c[1] >= 2 and c[0] >= 2]
            strong.sort(key=lambda x: (x[1], x[0], x[2]), reverse=True)
            top = strong[:top_k]
            if not top:
                return []

            max_lex = max(c[0] for c in top) or 1
            fallback = []
            for lex, unique_hits, ts, kind, source, user_row, text in top:
                coverage = float(unique_hits) / float(max(2, len(q_words)))
                pseudo = min(0.35, max(min_score, min_score + coverage * 0.10 + min(0.05, float(lex) / float(max_lex) * 0.05)))
                fallback.append((pseudo, ts, kind, source, user_row, text))
            return fallback

        return []
    finally:
        con.close()


def recall_explain(query: str, top_k: int = 5, min_score: float = 0.25,
                   exclude_sources: Optional[Iterable[str]] = None,
                   user: Optional[str] = None,
                   scope: str = "shared") -> dict:
    ex = set(s.lower() for s in (exclude_sources or []))

    con = connect()
    try:
        qv = embed(query)
        qn = vec_norm(qv)
        q_words = query_tokens(query)
        where_clause, where_args = _scope_where(scope, user)
        rows = con.execute(
            f"SELECT ts, kind, source, user, text, vec FROM memories WHERE {where_clause} ORDER BY ts DESC",
            where_args,
        ).fetchall()
    finally:
        con.close()

    semantic_hits = []
    lexical_candidates = []

    for ts, kind, source, user_row, text, vecblob in rows:
        if source.lower() in ex:
            continue

        v = blob_to_vec(vecblob)
        vn = vec_norm(v)
        if qn > 0.0 and len(qv) > 0 and vn > 0.0 and len(v) > 0:
            s = cosine(qv, v)
            if s >= min_score:
                semantic_hits.append((s, ts, kind, source, user_row, text))

        if q_words:
            low_text = text.lower()
            lex = 0
            unique_hits = 0
            for w in q_words:
                c = low_text.count(w)
                lex += c
                if c > 0:
                    unique_hits += 1
            if lex > 0:
                lexical_candidates.append((lex, unique_hits, ts, kind, source, user_row, text))

    semantic_hits.sort(key=lambda x: (x[0], x[1]), reverse=True)

    mode = "semantic"
    selected = semantic_hits[:top_k]

    if not selected and lexical_candidates and len(q_words) >= 2:
        strong = [c for c in lexical_candidates if c[1] >= 2 and c[0] >= 2]
        strong.sort(key=lambda x: (x[1], x[0], x[2]), reverse=True)
        top = strong[:top_k]
        if top:
            mode = "lexical_fallback"
            max_lex = max(c[0] for c in top) or 1
            selected = []
            for lex, unique_hits, ts, kind, source, user_row, text in top:
                coverage = float(unique_hits) / float(max(2, len(q_words)))
                pseudo = min(0.35, max(min_score, min_score + coverage * 0.10 + min(0.05, float(lex) / float(max_lex) * 0.05)))
                selected.append((pseudo, ts, kind, source, user_row, text))

    items = []
    for score, ts, kind, source, user_row, text in selected:
        preview = " ".join((text or "").split())[:220]
        token_hits = 0
        if q_words:
            low_text = text.lower()
            token_hits = sum(1 for w in q_words if low_text.count(w) > 0)
        items.append({
            "score": round(float(score), 4),
            "ts": int(ts),
            "kind": str(kind),
            "source": str(source),
            "user": str(user_row),
            "token_hits": int(token_hits),
            "preview": preview,
        })

    return {
        "query": query,
        "mode": mode,
        "top_k": int(top_k),
        "min_score": float(min_score),
        "query_tokens": q_words,
        "results": items,
    }

def reset():
    if DB_PATH.exists():
        DB_PATH.unlink()


def stats(scope: str = "shared", user: Optional[str] = None) -> dict:
    con = connect()
    try:
        where_clause, where_args = _scope_where(scope, user)
        total = con.execute(f"SELECT COUNT(*) FROM memories WHERE {where_clause}", where_args).fetchone()[0]

        by_kind = {
            str(k): int(c)
            for k, c in con.execute(
                f"SELECT kind, COUNT(*) FROM memories WHERE {where_clause} GROUP BY kind ORDER BY COUNT(*) DESC",
                where_args,
            ).fetchall()
        }

        by_source = {
            str(s): int(c)
            for s, c in con.execute(
                f"SELECT source, COUNT(*) FROM memories WHERE {where_clause} GROUP BY source ORDER BY COUNT(*) DESC",
                where_args,
            ).fetchall()
        }

        oldest = con.execute(f"SELECT MIN(ts) FROM memories WHERE {where_clause}", where_args).fetchone()[0]
        newest = con.execute(f"SELECT MAX(ts) FROM memories WHERE {where_clause}", where_args).fetchone()[0]
    finally:
        con.close()

    return {
        "total": int(total or 0),
        "by_kind": by_kind,
        "by_source": by_source,
        "oldest_ts": int(oldest) if oldest else None,
        "newest_ts": int(newest) if newest else None,
    }

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add")
    a.add_argument("--kind", required=True)
    a.add_argument("--source", required=True)
    a.add_argument("--user", required=False, default="", help="Optional user id to scope the memory")
    a.add_argument("--scope", required=False, default="shared", choices=["shared", "private", "hybrid"], help="Memory scope")
    a.add_argument("--text", required=True)

    r = sub.add_parser("recall")
    r.add_argument("--query", required=True)
    r.add_argument("--topk", type=int, default=5)
    r.add_argument("--minscore", type=float, default=0.25)
    r.add_argument("--exclude-source", action="append", default=[],
                   help="Exclude a source (repeatable), e.g. --exclude-source voice")
    r.add_argument("--debug", action="store_true", help="Print embedding diagnostics")
    r.add_argument("--user", required=False, default="", help="Optional user id to scope recall")
    r.add_argument("--scope", required=False, default="shared", choices=["shared", "private", "hybrid"], help="Recall scope")

    sub.add_parser("reset")
    sub.add_parser("stats")
    s = sub.choices["stats"]
    s.add_argument("--user", required=False, default="", help="Optional user id for scoped stats")
    s.add_argument("--scope", required=False, default="shared", choices=["shared", "private", "hybrid"], help="Stats scope")

    a2 = sub.add_parser("audit")
    a2.add_argument("--query", required=True)
    a2.add_argument("--topk", type=int, default=5)
    a2.add_argument("--minscore", type=float, default=0.25)
    a2.add_argument("--exclude-source", action="append", default=[])
    a2.add_argument("--user", required=False, default="", help="Optional user id to scope audit")
    a2.add_argument("--scope", required=False, default="shared", choices=["shared", "private", "hybrid"], help="Audit scope")

    args = ap.parse_args()

    if args.cmd == "add":
        add_memory(args.kind, args.source, args.text, user=args.user, scope=args.scope)
        print("OK")
        return

    if args.cmd == "recall":
        hits = recall(
            args.query,
            args.topk,
            args.minscore,
            args.exclude_source,
            user=args.user or None,
            scope=args.scope,
            debug=args.debug,
        )
        if not hits:
            print("No memories.")
            return
        for score, ts, kind, source, user_row, text in hits:
            print(f"\n--- score={score:.3f} kind={kind} source={source} user={user_row} ts={ts} ---\n{text}\n")
        return

    if args.cmd == "reset":
        reset()
        print("OK")
        return

    if args.cmd == "stats":
        print(json.dumps(stats(scope=args.scope, user=args.user or None), indent=2))
        return

    if args.cmd == "audit":
        out = recall_explain(
            args.query,
            args.topk,
            args.minscore,
            args.exclude_source,
            user=args.user or None,
            scope=args.scope,
        )
        print(json.dumps(out, indent=2))
        return

if __name__ == "__main__":
    main()
