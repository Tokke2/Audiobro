"""Hämta en Goodreads-token via en riktig webbläsare (Brave i första hand).

Goodreads skydd är ett test som en vanlig HTTP-klient
inte kan lösa, men en riktig Chromium-baserad webbläsare (Brave, Chromium,
Chrome, Edge) löser den på några sekunder och sparar resultatet i cookien
"Goodreads-token" (aws-waf-token). Den cookien går sedan att återanvända i appens egna
requests — samma sessionstyp som din vanliga surfning.

Så här går det till (helt lokalt, inget skickas någonstans):
  1. En tillfällig webbläsarprofil skapas.
  2. Webbläsaren startas headless och öppnar goodreads.com.
  3. Vi väntar tills profilen innehåller en Goodreads-token-cookie.
  4. Webbläsaren stängs och cookien returneras.

På användarens dator föredras Brave; i testmiljöer fungerar Chromium/Chrome.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Callable, Optional

TOKEN_NAME = "aws-waf-token"
GOODREADS = "https://www.goodreads.com/"

# (visningsnamn, linux-kommandon, macOS-sökvägar, Windows-sökvägar)
BROWSERS: list[tuple[str, list[str], list[str], list[str]]] = [
    (
        "Brave",
        ["brave", "brave-browser", "brave-browser-stable"],
        [
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "~/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ],
        [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
    ),
    (
        "Chromium",
        ["chromium", "chromium-browser"],
        ["/Applications/Chromium.app/Contents/MacOS/Chromium"],
        [r"C:\Program Files (x86)\Chromium\Application\chrome.exe"],
    ),
    (
        "Chrome",
        ["google-chrome", "google-chrome-stable"],
        ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
    ),
    (
        "Edge",
        ["microsoft-edge", "microsoft-edge-stable"],
        ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
        [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"],
    ),
]


def find_browser(executable: Optional[str] = None) -> Optional[tuple[str, str]]:
    """Hitta första tillgängliga webbläsare. Returnerar (namn, sökväg) eller None."""
    if executable:
        path = shutil.which(executable) or (os.path.expanduser(executable)
                                            if os.path.exists(os.path.expanduser(executable)) else None)
        if path:
            return (os.path.basename(path), path)
        return None
    for name, cmds, mac_paths, win_paths in BROWSERS:
        for cmd in cmds:
            path = shutil.which(cmd)
            if path:
                return (name, path)
        candidates = mac_paths if sys.platform == "darwin" else win_paths if os.name == "nt" else []
        for cand in candidates:
            exp = os.path.expanduser(cand)
            if os.path.exists(exp):
                return (name, exp)
    return None


def _cookie_db_path(profile_dir: str) -> Optional[str]:
    for sub in ("Default", "Profile 1", ""):
        p = os.path.join(profile_dir, sub, "Cookies") if sub else os.path.join(profile_dir, "Cookies")
        if os.path.exists(p):
            return p
    return None


def read_token_from_profile(profile_dir: str) -> str:
    """Läs Goodreads-token ur en Chromium-profil (kopierar filerna för att kringå lås)."""
    db = _cookie_db_path(profile_dir)
    if not db:
        return ""
    tmp = tempfile.mkdtemp(prefix="ags-cookies-")
    try:
        base = os.path.join(tmp, "Cookies")
        shutil.copy2(db, base)
        for suffix in ("-wal", "-shm", "-journal"):
            src = db + suffix
            if os.path.exists(src):
                shutil.copy2(src, base + suffix)
        con = sqlite3.connect(base)
        try:
            row = con.execute(
                "SELECT value, encrypted_value FROM cookies WHERE name = ?", (TOKEN_NAME,)
            ).fetchone()
        except sqlite3.Error:
            return ""
        finally:
            con.close()
        if not row:
            return ""
        value = row[0] or ""
        if not value and row[1]:
            enc = row[1]
            try:
                value = enc.decode("utf-8", errors="ignore")
            except Exception:
                value = ""
            # Chromiums Linux-fallback prefix "v10"/"v11" utan kryptering i headless-läge
            for prefix in (b"v10", b"v11"):
                if value.startswith(prefix.decode()):
                    value = value[3:]
        return value.strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _launch_args(executable: str, profile_dir: str, url: str, debug_port: int) -> list[str]:
    args = [
        executable,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-extensions",
        "--disable-background-networking",
        "--window-size=1280,900",
        "--remote-allow-origins=*",
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={profile_dir}",
    ]
    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
        args.insert(1, "--no-sandbox")
    args.append(url)
    return args


def _token_via_cdp(debug_port: int, url: str, deadline: float,
                   status: Callable[[str], None]) -> str:
    """Läs den avkrypterade cookien ur den körande webbläsaren via DevTools-protokollet."""
    import json

    import requests as _requests
    import websocket

    ws_url = None
    while time.monotonic() < deadline:
        try:
            targets = _requests.get(f"http://127.0.0.1:{debug_port}/json/list", timeout=3).json()
        except Exception:
            time.sleep(1)
            continue
        for t in targets:
            if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                ws_url = t["webSocketDebuggerUrl"]
                break
        if ws_url:
            break
        time.sleep(1)
    if not ws_url:
        return ""
    try:
        ws = websocket.create_connection(ws_url, timeout=5)
    except Exception:
        return ""
    msg_id = 0

    def call(method: str, params: Optional[dict] = None) -> dict:
        nonlocal msg_id
        msg_id += 1
        ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        ws.settimeout(5)
        while True:
            try:
                data = json.loads(ws.recv())
            except Exception:
                return {}
            if data.get("id") == msg_id:
                return data

    call("Network.enable")
    while time.monotonic() < deadline:
        resp = call("Network.getCookies", {"urls": [url]})
        for c in (resp.get("result") or {}).get("cookies", []):
            if c.get("name") == TOKEN_NAME and c.get("value"):
                status(f"Cookie uppläst via DevTools ({len(c['value'])} tecken).")
                ws.close()
                return c["value"]
        time.sleep(2)
    try:
        ws.close()
    except Exception:
        pass
    return ""


def fetch_waf_token(
    url: str = GOODREADS,
    executable: Optional[str] = None,
    timeout: float = 90.0,
    poll_interval: float = 1.5,
    on_status: Optional[Callable[[str], None]] = None,
) -> str:
    """Starta webbläsaren headless, öppna Goodreads, returnera cookien.

    Kastar RuntimeError om ingen webbläsare finns eller tiden räcker ut.
    """
    # Tydlig diagnos om websocket-client saknas — annars blir felet diffust timeout
    try:
        import importlib.util as _ilu
        if _ilu.find_spec("websocket") is None:
            raise RuntimeError(
                "Tillägg saknas: websocket-client är inte installerat.\n"
                "Det krävs för 'Lås upp via min webbläsare'.\n\n"
                "Fix: Öppna Audiobro → Inställningar → 'Kontrollera tillägg' → bocka i websocket-client → Installera.\n"
                "Eller kör i terminal: pip install websocket-client"
            )
    except RuntimeError:
        raise
    except Exception:
        pass
    found = find_browser(executable)
    if not found:
        raise RuntimeError(
            "Ingen Chromium-baserad webbläsare hittades (Brave/Chromium/Chrome/Edge). "
            "Installera en, eller klistra in Goodreads-token manuellt."
        )
    name, path = found
    status = on_status or (lambda s: None)
    status(f"Startar {name} headless för att öppna Goodreads …")
    profile_dir = tempfile.mkdtemp(prefix="ags-browser-")
    debug_port = 9222 + (os.getpid() % 500)
    proc = subprocess.Popen(
        _launch_args(path, profile_dir, url, debug_port),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    token = ""
    deadline = time.monotonic() + timeout
    try:
        # 1) DevTools ger den avkrypterade cookien (fungerar på alla OS)
        try:
            token = _token_via_cdp(debug_port, url, deadline, status)
        except Exception:
            token = ""
        # 2) reserv: läs profilen direkt (okrypterat på vissa Linux-setupar)
        while not token and time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            token = read_token_from_profile(profile_dir)
            if not token or len(token) <= 40:
                token = ""
                time.sleep(poll_interval)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)
    if not token or len(token) <= 40:
        raise RuntimeError(
            f"{name} hann inte öppna Goodreads inom {timeout:.0f} s. "
            "Prova igen, eller klistra in token manuellt från din vanliga webbläsare."
        )
    status(f"Hämtade Goodreads-token via {name} ({len(token)} tecken).")
    return token
