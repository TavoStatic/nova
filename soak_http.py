#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass

import requests


@dataclass
class Counters:
    total: int = 0
    passed: int = 0
    failed: int = 0


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Nova HTTP soak runner")
    ap.add_argument("--base-url", default="http://127.0.0.1:8080", help="Nova HTTP base URL")
    ap.add_argument("--duration-sec", type=int, default=300, help="Total soak duration")
    ap.add_argument("--interval-sec", type=float, default=5.0, help="Interval between cycles")
    ap.add_argument("--session-id", default="soak-session", help="Chat session id")
    ap.add_argument("--control-user", default="", help="Optional control login username")
    ap.add_argument("--control-pass", default="", help="Optional control login password")
    ap.add_argument("--control-token", default="", help="Optional control token")
    return ap.parse_args()


def _ok(resp: requests.Response) -> bool:
    return 200 <= resp.status_code < 300


def _check(name: str, cond: bool, counters: Counters, details: str = "") -> None:
    counters.total += 1
    if cond:
        counters.passed += 1
        return
    counters.failed += 1
    print(f"[FAIL] {name} {details}".strip())


def main() -> int:
    args = parse_args()
    base = args.base_url.rstrip("/")
    sess = requests.Session()
    c = Counters()

    # Optional control-room login.
    if args.control_user and args.control_pass:
        r = sess.post(
            f"{base}/api/control/login",
            json={"username": args.control_user, "password": args.control_pass},
            timeout=10,
        )
        _check("control_login", _ok(r), c, f"status={r.status_code}")

    start = time.time()
    cycle = 0
    while time.time() - start < max(1, args.duration_sec):
        cycle += 1

        try:
            r = sess.get(f"{base}/api/health", timeout=10)
            ok = _ok(r)
            _check("health", ok, c, f"status={r.status_code}")

            r = sess.post(
                f"{base}/api/chat",
                json={"message": f"soak ping {cycle}", "session_id": args.session_id},
                timeout=25,
            )
            ok = _ok(r)
            body = {}
            if ok:
                try:
                    body = r.json()
                except Exception:
                    body = {}
            _check("chat", ok and bool((body.get("reply") or "").strip()), c, f"status={r.status_code}")

            r = sess.get(f"{base}/api/chat/history", params={"session_id": args.session_id}, timeout=10)
            ok = _ok(r)
            turns = []
            if ok:
                try:
                    turns = list((r.json() or {}).get("turns") or [])
                except Exception:
                    turns = []
            _check("history", ok and len(turns) >= 2, c, f"status={r.status_code} turns={len(turns)}")

            if args.control_token:
                headers = {"X-Nova-Control-Key": args.control_token}
                r = sess.get(f"{base}/api/control/status", headers=headers, timeout=10)
                ok = _ok(r)
                _check("control_status", ok, c, f"status={r.status_code}")

                r = sess.get(f"{base}/api/control/sessions", headers=headers, timeout=10)
                ok = _ok(r)
                count = -1
                if ok:
                    try:
                        count = len((r.json() or {}).get("sessions") or [])
                    except Exception:
                        count = -1
                _check("control_sessions", ok and count >= 0, c, f"status={r.status_code} sessions={count}")

                r = sess.post(
                    f"{base}/api/control/action",
                    headers={**headers, "Content-Type": "application/json"},
                    data=json.dumps({"action": "metrics"}),
                    timeout=10,
                )
                ok = _ok(r)
                _check("control_metrics", ok, c, f"status={r.status_code}")
        except Exception as e:
            c.total += 1
            c.failed += 1
            print(f"[FAIL] cycle_exception {e}")

        time.sleep(max(0.2, float(args.interval_sec)))

    print(f"Soak summary: total={c.total} passed={c.passed} failed={c.failed}")
    return 0 if c.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
