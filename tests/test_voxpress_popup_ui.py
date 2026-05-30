import importlib.machinery
import importlib.util
import json
import os
import socket
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "voxpress-popup-ui"


def install_gtk_stubs():
    names = ["cairo", "gi", "gi.repository"]
    original = {name: sys.modules.get(name) for name in names}

    cairo = types.ModuleType("cairo")
    cairo.Region = lambda *args, **kwargs: None

    gi = types.ModuleType("gi")
    gi.require_version = lambda *args, **kwargs: None

    repository = types.ModuleType("gi.repository")
    repository.Gdk = types.SimpleNamespace()
    repository.GdkX11 = types.SimpleNamespace()
    repository.GLib = types.SimpleNamespace()
    repository.Gtk = types.SimpleNamespace()

    sys.modules["cairo"] = cairo
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository
    return original


def restore_modules(original):
    for name, module in original.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def load_popup_module(runtime_dir):
    original_runtime = os.environ.get("XDG_RUNTIME_DIR")
    os.environ["XDG_RUNTIME_DIR"] = str(runtime_dir)
    original_modules = install_gtk_stubs()
    try:
        loader = importlib.machinery.SourceFileLoader("voxpress_popup_ui_test", str(SCRIPT))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        restore_modules(original_modules)
        if original_runtime is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = original_runtime
    return module


class FakePopupDaemon:
    def __init__(self, socket_path, compatible=False, protocol=None, commands=None):
        self.socket_path = Path(socket_path)
        self.compatible = compatible
        self.protocol = protocol
        self.commands = commands or []
        self.stop_event = threading.Event()
        self.server = None
        self.thread = None

    def start(self):
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.socket_path))
        self.server.listen(8)
        self.server.settimeout(0.05)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop_event.is_set():
            try:
                conn, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def handle(self, conn):
        with conn:
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            if not data:
                return
            message = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
            command = message.get("cmd")
            if self.compatible and command == "capabilities":
                payload = {
                    "ok": True,
                    "protocol": self.protocol,
                    "commands": self.commands,
                }
            elif self.compatible:
                payload = {"ok": True}
            elif command in {"recording", "transcribing", "ping"}:
                payload = {"ok": True}
            else:
                payload = {"ok": False, "error": "unknown command"}
            conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))

    def close(self):
        self.stop_event.set()
        if self.server:
            self.server.close()
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass


class VoxpressPopupUiTest(unittest.TestCase):
    def test_socket_request_replaces_old_daemon_without_capabilities(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            module = load_popup_module(tmpdir)
            old_daemon = FakePopupDaemon(module.SOCKET_PATH, compatible=False)
            new_daemon = FakePopupDaemon(
                module.SOCKET_PATH,
                compatible=True,
                protocol=module.DAEMON_PROTOCOL,
                commands=module.DAEMON_COMMANDS,
            )
            old_daemon.start()
            popen_calls = []

            def fake_popen(*args, **kwargs):
                popen_calls.append((args, kwargs))
                new_daemon.start()
                return object()

            original_popen = module.subprocess.Popen
            module.subprocess.Popen = fake_popen
            try:
                response = module.socket_request({"cmd": "saved-correction"})
            finally:
                module.subprocess.Popen = original_popen
                old_daemon.close()
                new_daemon.close()

            self.assertTrue(popen_calls)
            self.assertEqual(response, {"ok": True})


if __name__ == "__main__":
    unittest.main()
