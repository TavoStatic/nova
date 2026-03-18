import requests
import uuid
import os

CHAT_API_URL = "http://127.0.0.1:8080/api/chat"
CHAT_LOGIN_URL = "http://127.0.0.1:8080/api/chat/login"
USER_ID = (os.environ.get("NOVA_USER_ID") or os.environ.get("NOVA_CHAT_USER") or os.environ.get("USERNAME") or "local-user").strip()
CHAT_USER = (os.environ.get("NOVA_CHAT_USER") or USER_ID).strip()
CHAT_PASS = (os.environ.get("NOVA_CHAT_PASS") or "").strip()


def ensure_chat_login(session: requests.Session) -> None:
    if not CHAT_PASS:
        return
    r = session.post(CHAT_LOGIN_URL, json={"username": CHAT_USER, "password": CHAT_PASS}, timeout=30)
    r.raise_for_status()
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(j.get("error") or "login_failed")


def main() -> None:
    session_id = uuid.uuid4().hex[:12]
    session = requests.Session()
    ensure_chat_login(session)
    print("Nova Chat (unified brain via /api/chat)")
    print("Type your message. Type 'q' to quit.\n")

    while True:
        msg = input("> ").strip()
        if not msg:
            continue
        if msg.lower() in {"q", "quit", "exit"}:
            break

        try:
            r = session.post(
                CHAT_API_URL,
                json={"message": msg, "session_id": session_id, "user_id": USER_ID},
                headers={"X-Nova-User-Id": USER_ID},
                timeout=120,
            )
            r.raise_for_status()
            j = r.json()
            sid = str(j.get("session_id") or "").strip()
            if sid:
                session_id = sid
            reply = str(j.get("reply") or j.get("error") or "(no reply)").strip()
            print(f"Nova: {reply}\n")
        except Exception as e:
            print(f"Nova: chat API error: {e}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
