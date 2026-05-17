import unittest
from types import SimpleNamespace

from services.port_ownership import PORT_OWNERSHIP_SERVICE


class _Process:
    def __init__(self, *, name, exe, cmdline):
        self._name = name
        self._exe = exe
        self._cmdline = cmdline

    def name(self):
        return self._name

    def exe(self):
        return self._exe

    def cmdline(self):
        return list(self._cmdline)

    def status(self):
        return "running"

    def create_time(self):
        return 123.4


class _Psutil:
    CONN_LISTEN = "LISTEN"

    def __init__(self, connections, processes):
        self._connections = connections
        self._processes = processes

    def net_connections(self, kind="inet"):
        self.kind = kind
        return list(self._connections)

    def Process(self, pid):
        return self._processes[pid]


class TestPortOwnershipService(unittest.TestCase):
    def test_payload_reports_expected_ollama_listener_owner(self):
        conn = SimpleNamespace(
            status="LISTEN",
            laddr=SimpleNamespace(ip="127.0.0.1", port=11434),
            pid=10,
        )
        psutil_stub = _Psutil(
            [conn],
            {10: _Process(name="ollama.exe", exe="C:/Ollama/ollama.exe", cmdline=["ollama", "serve"])},
        )

        payload = PORT_OWNERSHIP_SERVICE.payload(psutil_module=psutil_stub)

        self.assertTrue(payload.get("ok"))
        port = (payload.get("ports") or {}).get("11434") or {}
        self.assertTrue(port.get("listening"))
        self.assertTrue(port.get("expected_owner_present"))
        self.assertEqual((port.get("owners") or [{}])[0].get("name"), "ollama.exe")

    def test_payload_marks_unexpected_expected_port_owner(self):
        conn = SimpleNamespace(
            status="LISTEN",
            laddr=SimpleNamespace(ip="127.0.0.1", port=11434),
            pid=20,
        )
        psutil_stub = _Psutil(
            [conn],
            {20: _Process(name="python.exe", exe="C:/Python/python.exe", cmdline=["python", "other.py"])},
        )

        payload = PORT_OWNERSHIP_SERVICE.payload(psutil_module=psutil_stub)

        self.assertFalse(payload.get("ok"))
        self.assertEqual(payload.get("status"), "watch")
        self.assertEqual(payload.get("issue_count"), 1)
        self.assertEqual(((payload.get("issues") or [{}])[0]).get("code"), "unexpected_port_owner")
        port = (payload.get("ports") or {}).get("11434") or {}
        self.assertFalse(port.get("expected_owner_present"))


if __name__ == "__main__":
    unittest.main()
