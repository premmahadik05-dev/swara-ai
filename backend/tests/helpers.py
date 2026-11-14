from __future__ import annotations

import io
import wave

import numpy as np
from fastapi.testclient import TestClient


def make_wav(seconds: float = 1.0, sr: int = 16000, freq: float = 220.0, amp: float = 0.4, channels: int = 1) -> bytes:
    """Synthetic tone burst with syllable-like amplitude modulation (NOT speech - used for plumbing tests only)."""
    t = np.arange(int(seconds * sr)) / sr
    x = amp * np.sin(2 * np.pi * freq * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
    pcm = (x * 32767).astype("<i2")
    if channels == 2:
        pcm = np.repeat(pcm[:, None], 2, axis=1).reshape(-1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


KEY = "test-key-1234567890-SECRET"


OWNER = {"full_name": "Test Owner", "email": "owner@example.com", "password": "Correct-Horse-9!"}
STAFF = {"full_name": "Test Staff", "email": "staff@example.com", "password": "Another-Strong-7!"}


def register(c: TestClient, who: dict | None = None, **over):
    """Create an account through the real endpoint. When it signs the person in, remember the CSRF token for later writes."""
    who = who or OWNER
    body = {"full_name": who["full_name"], "email": who["email"], "password": who["password"], "confirm_password": who["password"], "accept_terms": True}
    body.update(over)
    r = c.post("/api/auth/signup", json=body)
    if r.status_code == 201 and r.json().get("csrf_token"):
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r


def login(c: TestClient, who: dict | None = None, remember: bool = False, **over):
    who = who or OWNER
    r = c.post("/api/auth/login", json={"email": who["email"], "password": who["password"], "remember": remember, **over})
    if r.status_code == 200:
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r


class AuthedClient(TestClient):
    """TestClient that signs the first account (the owner) in when entered, the way a person would on first run."""

    def __enter__(self):
        super().__enter__()
        r = register(self)
        assert r.status_code == 201, r.text
        return self


class SmtpSink:
    """A tiny SMTP server on 127.0.0.1 that records what it is sent. It is a stand-in for a mail provider:
    it proves our code speaks SMTP correctly (EHLO, AUTH, MAIL FROM, RCPT TO, DATA), NOT that a real provider delivers."""

    def __init__(self, require_auth: bool = False):
        import socket
        import threading

        self.messages: list[dict] = []
        self.auth_seen: list[str] = []
        self.require_auth = require_auth
        self._srv = socket.socket()
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(5)
        self.port = self._srv.getsockname()[1]
        self._stop = False
        self._t = threading.Thread(target=self._serve, daemon=True)
        self._t.start()

    def _serve(self):
        import threading
        self._srv.settimeout(0.2)
        while not self._stop:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                continue
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        f = conn.makefile("rwb")
        send = lambda s: (f.write((s + "\r\n").encode()), f.flush())  # noqa: E731
        send("220 sink ESMTP")
        mail_from, rcpts = "", []
        while True:
            line = f.readline()
            if not line:
                break
            cmd = line.decode(errors="replace").strip()
            up = cmd.upper()
            if up.startswith("EHLO"):
                f.write(b"250-sink\r\n250 AUTH PLAIN LOGIN\r\n"); f.flush()
            elif up.startswith("AUTH"):
                self.auth_seen.append(cmd)
                send("235 ok")
            elif up.startswith("MAIL FROM"):
                mail_from = cmd[10:].strip(); send("250 ok")
            elif up.startswith("RCPT TO"):
                rcpts.append(cmd[8:].strip()); send("250 ok")
            elif up == "DATA":
                send("354 go")
                data = []
                while True:
                    ln = f.readline()
                    if ln in (b".\r\n", b""):
                        break
                    data.append(ln.decode(errors="replace"))
                self.messages.append({"from": mail_from, "to": rcpts, "raw": "".join(data)})
                mail_from, rcpts = "", []
                send("250 queued")
            elif up == "QUIT":
                send("221 bye"); break
            else:
                send("250 ok")
        conn.close()

    def close(self):
        self._stop = True
        self._srv.close()

    @property
    def last_text(self) -> str:
        import email
        from email import policy
        m = email.message_from_string(self.messages[-1]["raw"], policy=policy.default)
        body = m.get_body(preferencelist=("plain",))
        return body.get_content() if body else ""

    def last_token(self) -> str:
        import re
        m = re.search(r"token=([A-Za-z0-9_\-]+)", self.last_text)
        assert m, self.last_text
        return m.group(1)
