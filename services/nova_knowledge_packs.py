from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Callable, Optional


def tokenize(query: str) -> list[str]:
    lowered = (query or "").lower()
    tokens = re.findall(r"[a-z0-9]{3,}", lowered)
    if "peims" in lowered and "peims" not in tokens:
        tokens.append("peims")
    return list(dict.fromkeys(tokens))[:25]


def kb_active_pack(active_pack_file: Path) -> Optional[str]:
    try:
        if active_pack_file.exists():
            name = active_pack_file.read_text(encoding="utf-8").strip()
            return name or None
    except Exception:
        pass
    return None


def kb_set_active(
    name: Optional[str],
    *,
    knowledge_root: Path,
    packs_dir: Path,
    active_pack_file: Path,
) -> str:
    knowledge_root.mkdir(parents=True, exist_ok=True)
    if not name:
        if active_pack_file.exists():
            active_pack_file.unlink(missing_ok=True)
        return "Knowledge pack disabled."
    (packs_dir / name).mkdir(parents=True, exist_ok=True)
    active_pack_file.write_text(name, encoding="utf-8")
    return f"Active knowledge pack: {name}"


def kb_list_packs(
    packs_dir: Path,
    *,
    kb_active_pack_fn: Callable[[], Optional[str]],
) -> str:
    packs_dir.mkdir(parents=True, exist_ok=True)
    packs = [path.name for path in packs_dir.iterdir() if path.is_dir()]
    packs.sort(key=str.lower)
    active = kb_active_pack_fn()
    lines: list[str] = []
    for pack in packs:
        mark = "*" if active and pack.lower() == active.lower() else " "
        lines.append(f"{mark} {pack}")
    if not lines:
        return "No knowledge packs yet. (You can add one with: kb add <zip_path> <pack_name>)"
    return "Knowledge packs:\n" + "\n".join(lines)


def kb_add_zip(
    zip_path: str,
    pack_name: str,
    *,
    packs_dir: Path,
    safe_path_fn: Callable[[str], Path],
) -> str:
    zip_file = safe_path_fn(zip_path) if not Path(zip_path).is_absolute() else Path(zip_path)
    if not zip_file.exists() or not zip_file.is_file():
        return f"Not a file: {zip_file}"

    destination = packs_dir / pack_name
    destination.mkdir(parents=True, exist_ok=True)

    allowed_exts = {".txt", ".md"}
    extracted = 0
    with zipfile.ZipFile(zip_file, "r") as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = Path(member.filename).name
            if Path(name).suffix.lower() not in allowed_exts:
                continue
            output_path = destination / name
            output_path.write_bytes(archive.read(member))
            extracted += 1

    if extracted == 0:
        return "No .txt/.md files found in zip. (For now, keep packs as txt/md; we can add PDF parsing later.)"
    return f"Added {extracted} file(s) to knowledge pack: {pack_name}"


def active_knowledge_root(
    packs_dir: Path,
    *,
    kb_active_pack_fn: Callable[[], Optional[str]],
) -> Optional[Path]:
    pack = kb_active_pack_fn()
    if not pack:
        return None
    root = packs_dir / pack
    if not root.exists() or not root.is_dir():
        return None
    return root


def kb_search(
    query: str,
    *,
    packs_dir: Path,
    kb_active_pack_fn: Callable[[], Optional[str]],
    tokenize_fn: Callable[[str], list[str]],
    max_files: int,
    max_chars: int,
) -> str:
    pack = kb_active_pack_fn()
    if not pack:
        return ""
    root = packs_dir / pack
    if not root.exists():
        return ""

    tokens = tokenize_fn(query)
    if not tokens:
        return ""

    candidates: list[tuple[int, Path, str]] = []
    allowed_exts = {".txt", ".md"}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in allowed_exts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        lowered = text.lower()
        score = sum(lowered.count(token) for token in tokens)
        if score > 0:
            candidates.append((score, path, text))

    if not candidates:
        return ""

    candidates.sort(key=lambda item: item[0], reverse=True)
    blocks: list[str] = []
    used = 0
    for score, path, text in candidates[:max_files]:
        lowered = text.lower()
        idx = 0
        for token in tokens:
            found_at = lowered.find(token)
            if found_at != -1:
                idx = found_at
                break
        start = max(0, idx - 250)
        end = min(len(text), idx + 950)
        snippet = text[start:end].strip().replace("\r\n", "\n")
        chunk = f"[FILE] {path.name} (score={score})\n{snippet}\n"
        if used + len(chunk) > max_chars:
            break
        blocks.append(chunk)
        used += len(chunk)

    if not blocks:
        return ""
    return f"REFERENCE (knowledge pack: {pack}):\n\n" + "\n---\n".join(blocks)


def read_text_safely(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except Exception:
        return ""

    for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            text = raw.decode(encoding)
            if "\x00" in text:
                continue
            if text.strip():
                return text
        except Exception:
            continue
    return ""


def extract_key_lines(text: str, *, max_lines: int = 2) -> list[str]:
    out: list[str] = []
    for raw in (text or "").splitlines():
        cleaned = re.sub(r"\s+", " ", (raw or "").strip().lstrip("-*•")).strip()
        if len(cleaned) < 20:
            continue
        if cleaned.lower().startswith("source:"):
            continue
        out.append(cleaned.rstrip("."))
        if len(out) >= max(1, int(max_lines)):
            break
    return out


def topic_tokens(text: str) -> list[str]:
    lowered = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]{3,}", lowered)
    stop_words = {
        "what", "when", "where", "which", "about", "could", "would", "should",
        "there", "their", "have", "your", "with", "from", "that", "this",
        "please", "tell", "more", "info", "information", "topic",
    }
    out: list[str] = []
    for token in tokens:
        if token in stop_words:
            continue
        if token not in out:
            out.append(token)
    return out[:12]


def extract_matching_lines(
    text: str,
    tokens: list[str],
    *,
    max_lines: int = 3,
) -> list[str]:
    if not tokens:
        return extract_key_lines(text, max_lines=max_lines)
    out: list[str] = []
    for raw in (text or "").splitlines():
        cleaned = re.sub(r"\s+", " ", (raw or "").strip().lstrip("-*•")).strip()
        if not cleaned or len(cleaned) < 14:
            continue
        lowered = cleaned.lower()
        score = sum(1 for token in tokens if token in lowered)
        if score <= 0:
            continue
        out.append(cleaned.rstrip("."))
        if len(out) >= max(1, int(max_lines)):
            break
    if out:
        return out
    return extract_key_lines(text, max_lines=max_lines)


def build_local_topic_digest_answer(
    query_text: str,
    *,
    packs_dir: Path,
    base_dir: Path,
    active_knowledge_root_fn: Callable[[], Optional[Path]],
    topic_tokens_fn: Callable[[str], list[str]],
    read_text_safely_fn: Callable[[Path], str],
    extract_matching_lines_fn: Callable[[str, list[str]], list[str]],
    max_files: int = 4,
    max_points: int = 10,
) -> str:
    query = (query_text or "").strip()
    if not query:
        return ""

    root = active_knowledge_root_fn()
    if root is None:
        return ""

    tokens = topic_tokens_fn(query)
    candidates = [path for path in root.glob("**/*.txt") if path.is_file()]
    if not candidates:
        return ""

    scored: list[tuple[int, Path, str]] = []
    for path in candidates:
        text = read_text_safely_fn(path)
        if not text:
            continue
        haystack = (path.name + " " + text[:5000]).lower()
        score = sum(2 if token in path.name.lower() else 1 for token in tokens if token in haystack)
        if score > 0:
            scored.append((score, path, text))

    if not scored:
        return ""

    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[: max(1, int(max_files))]

    try:
        pack_name = root.relative_to(packs_dir).as_posix()
    except Exception:
        pack_name = root.name

    lines = [f"I found relevant details in the active knowledge pack ({pack_name}):"]
    points = 0
    cited: set[str] = set()
    for _score, path, text in top:
        for key_line in extract_matching_lines_fn(text, tokens):
            lines.append(f"- {key_line}.")
            points += 1
            try:
                cited.add(str(path.relative_to(base_dir)).replace("\\", "/"))
            except Exception:
                cited.add(path.name)
            if points >= max(1, int(max_points)):
                break
        if points >= max(1, int(max_points)):
            break

    if points == 0:
        return ""

    for cited_path in sorted(cited):
        lines.append(f"[source: {cited_path}]")
    return "\n".join(lines)