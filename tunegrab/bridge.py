"""Browser -> app bridge: tunegrab:// links and a single running window.

The browser extension opens  tunegrab://add?url=<encoded video url>.
Windows starts Tunegrab.exe with that link as an argument. If Tunegrab is already
running, the new process hands the links to the running window over a localhost
socket (protected by a random token) and exits.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import socket
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import engine

PROTO = "tunegrab"
INSTANCE_FILE = engine.DATA_DIR / "instance.json"
MAX_MSG = 256 * 1024


def parse_args(argv: list[str]) -> list[str]:
    """Collect safe video links from command-line arguments (tunegrab:// links or plain URLs)."""
    urls: list[str] = []
    for a in argv:
        if a.lower().startswith(PROTO + ":"):
            for value in parse_qs(urlsplit(a).query).get("url", []):
                urls += engine.extract_links(value)
        else:
            urls += engine.extract_links(a)
    out, seen = [], set()
    for u in urls:
        if engine.is_safe_url(u) and u not in seen:
            seen.add(u)
            out.append(u)
    return out[:500]


def send_to_running(urls: list[str]) -> bool:
    """Give links to an already running Tunegrab. Returns True if it accepted them."""
    try:
        info = json.loads(INSTANCE_FILE.read_text(encoding="utf-8"))
        port, token = int(info["port"]), str(info["token"])
    except Exception:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
            s.sendall(json.dumps({"token": token, "urls": urls}).encode("utf-8") + b"\n")
            s.settimeout(3)
            return s.recv(16).startswith(b"ok")
    except OSError:
        return False


class Server:
    """Listens on 127.0.0.1 for links from new Tunegrab processes."""

    def __init__(self, on_urls):
        self.on_urls = on_urls
        self.token = secrets.token_hex(16)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        engine.DATA_DIR.mkdir(parents=True, exist_ok=True)
        INSTANCE_FILE.write_text(json.dumps({"port": self.port, "token": self.token, "pid": os.getpid()}),
                                 encoding="utf-8")
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        with conn:
            try:
                conn.settimeout(3)
                data = b""
                while b"\n" not in data and len(data) < MAX_MSG:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                msg = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
                if not hmac.compare_digest(str(msg.get("token", "")), self.token):
                    return
                urls = [u for u in msg.get("urls", []) if isinstance(u, str) and engine.is_safe_url(u)][:500]
                conn.sendall(b"ok\n")
                self.on_urls(urls)
            except Exception:
                return

    def close(self):
        try:
            self.sock.close()
            info = json.loads(INSTANCE_FILE.read_text(encoding="utf-8"))
            if info.get("pid") == os.getpid():
                INSTANCE_FILE.unlink(missing_ok=True)
        except Exception:
            pass


def register_protocol() -> None:
    """Register tunegrab:// for the current user (no admin rights needed)."""
    try:
        import winreg

        if getattr(sys, "frozen", False):
            command = f'"{sys.executable}" "%1"'
            icon = f'"{sys.executable}",0'
        else:
            pyw = Path(sys.executable).with_name("pythonw.exe")
            script = Path(__file__).resolve().parent.parent / "tunegrab.pyw"
            command = f'"{pyw}" "{script}" "%1"'
            icon = str(Path(__file__).resolve().parent.parent / "assets" / "icon.ico")
        base = r"Software\Classes\tunegrab"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Tunegrab")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\DefaultIcon") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, icon)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, command)
    except Exception as e:
        engine.log(f"protocol registration failed: {e}")
