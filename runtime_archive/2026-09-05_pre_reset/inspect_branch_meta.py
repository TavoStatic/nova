import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree

for bid in ("branch_3175ae5e", "branch_882b7612"):
    b = work_tree.get_branch(bid)
    if not b:
        continue
    print("=" * 80)
    print("branch", bid, "|", b.title)
    print("status", getattr(getattr(b, "status", ""), "value", getattr(b, "status", "")))
    print("kind", getattr(b, "kind", ""))
    meta = getattr(b, "metadata", {}) or {}
    payload = getattr(b, "source_payload", {}) or {}
    print("meta_keys", sorted(meta.keys()))
    print("fingerprint", meta.get("fingerprint"))
    print("source", payload.get("source"), "class", payload.get("signal_class"))
    print("payload_fingerprint", payload.get("fingerprint"))
