"""The local AI: look at this computer, recommend a model that runs well on it, and download it.

Models run through Ollama (free, https://ollama.com). Scout only talks to Ollama's local API; it never
installs software itself. Downloads start only when the user presses the button in Settings.
"""
import asyncio
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

OLLAMA = "http://localhost:11434"

# Small models that are good at following a JSON format and read the markets' languages.
# Sizes are the download sizes from ollama.com.
CATALOG = [
    {"model": "qwen3.5:9b", "size_gb": 6.6, "note": "best judgement; needs a graphics card with 8 GB+ or a fast Mac"},
    {"model": "qwen3.5:4b", "size_gb": 3.4, "note": "good balance of speed and judgement"},
    {"model": "qwen3.5:2b", "size_gb": 2.7, "note": "about twice as fast, a bit less precise"},
    {"model": "qwen3.5:0.8b", "size_gb": 1.0, "note": "for weak or old computers; basic judgement"},
]
_by_name = {m["model"]: m for m in CATALOG}

pull_state: dict = {}  # the running or last download: model, status, completed, total, error, done


# --- This computer -----------------------------------------------------------------------------

def _ram_gb() -> float | None:
    try:
        if sys.platform == "win32":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullTotalPhys / 1024 ** 3
        if sys.platform == "darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout) / 1024 ** 3
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except Exception:
        return None


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=8,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:
        return ""


def _gpus() -> list[dict]:
    """[{name, vram_gb (None if unknown), kind}] for real graphics hardware."""
    gpus = []
    if shutil.which("nvidia-smi"):
        for line in _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]).splitlines():
            if "," in line:
                name, mem = line.rsplit(",", 1)
                gpus.append({"name": name.strip(), "vram_gb": round(float(mem) / 1024, 1), "kind": "nvidia"})
    if sys.platform == "darwin" and platform.machine() == "arm64":
        gpus.append({"name": "Apple Silicon", "vram_gb": None, "kind": "apple"})
    if sys.platform == "win32":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | Select-Object Name | ConvertTo-Json -Compress"])
        try:
            items = json.loads(out) if out.strip() else []
            items = items if isinstance(items, list) else [items]
        except ValueError:
            items = []
        for it in items:
            name = (it.get("Name") or "").strip()
            low = name.lower()
            if not name or any(w in low for w in ("virtual", "basic display", "remote", "parsec", "meta")):
                continue
            if any(g["name"] == name for g in gpus):
                continue
            kind = "nvidia" if "nvidia" in low else "amd" if ("amd" in low or "radeon" in low) else "intel" if "intel" in low else "other"
            gpus.append({"name": name, "vram_gb": None, "kind": kind})
    return gpus


def hardware() -> dict:
    ram = _ram_gb()
    gpus = _gpus()
    # Models go to OLLAMA_MODELS if set (it can be on another drive), else ~/.ollama/models.
    where = Path(os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama" / "models")
    while not where.exists() and where.parent != where:
        where = where.parent
    free = shutil.disk_usage(where).free / 1024 ** 3
    # Integrated graphics (Intel, most laptops) share memory and don't speed Ollama up much: count as CPU only.
    dedicated = [g for g in gpus if g["kind"] in ("nvidia", "amd", "apple")]
    return {
        "ram_gb": round(ram, 1) if ram else None,
        "cpu_threads": os.cpu_count(),
        "gpus": gpus,
        "dedicated_gpu": dedicated[0] if dedicated else None,
        "free_disk_gb": round(free, 1),
        "os": platform.system(),
    }


def recommend(hw: dict) -> dict:
    ram, gpu = hw["ram_gb"] or 8, hw["dedicated_gpu"]
    vram = (gpu or {}).get("vram_gb")
    if gpu and gpu["kind"] == "apple":
        pick, why = ("qwen3.5:9b", "Apple Silicon with plenty of memory") if ram >= 24 else \
                    ("qwen3.5:4b", "Apple Silicon") if ram >= 12 else ("qwen3.5:2b", "Apple Silicon with little memory")
    elif gpu and vram and vram >= 8:
        pick, why = "qwen3.5:9b", f"{gpu['name']} with {vram:g} GB"
    elif gpu and (vram or 0) >= 4:
        pick, why = "qwen3.5:4b", f"{gpu['name']} with {vram:g} GB"
    elif ram >= 12:
        pick, why = "qwen3.5:4b", f"no dedicated graphics card, {ram:.0f} GB memory: runs on the processor"
    elif ram >= 8:
        pick, why = "qwen3.5:2b", f"no dedicated graphics card and {ram:.0f} GB memory"
    else:
        pick, why = "qwen3.5:0.8b", f"only {ram:.0f} GB memory"
    choice = dict(_by_name[pick])
    choice["why"] = why
    choice["fits_disk"] = hw["free_disk_gb"] > choice["size_gb"] + 1
    return choice


# --- Ollama ------------------------------------------------------------------------------------

def ollama_path() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    guess = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(guess) if guess.exists() else None


async def status() -> dict:
    """Whether Ollama is installed/running and which models are downloaded."""
    running, models, version = False, [], None
    try:
        async with httpx.AsyncClient(timeout=3) as http:
            version = (await http.get(OLLAMA + "/api/version")).json().get("version")
            tags = (await http.get(OLLAMA + "/api/tags")).json().get("models", [])
            running = True
            models = [{"name": m["name"], "size_gb": round(m.get("size", 0) / 1024 ** 3, 1)}
                      for m in tags if "embed" not in m["name"]]
    except (httpx.HTTPError, ValueError):
        pass
    return {"installed": running or bool(ollama_path()), "running": running, "version": version, "models": models}


def start() -> bool:
    """Start Ollama in the background if it's installed but not running."""
    path = ollama_path()
    if not path:
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([path, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    return True


async def pull(model: str) -> None:
    """Download a model through Ollama, keeping progress in `pull_state` for the Settings screen."""
    pull_state.clear()
    pull_state.update(model=model, status="starting", completed=0, total=0, error=None, done=False)
    layers: dict[str, tuple[int, int]] = {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5)) as http:
            async with http.stream("POST", OLLAMA + "/api/pull", json={"model": model, "stream": True}) as r:
                if r.status_code >= 400:
                    raise RuntimeError((await r.aread()).decode()[:200])
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    msg = json.loads(line)
                    if msg.get("error"):
                        raise RuntimeError(msg["error"])
                    if msg.get("digest") and msg.get("total"):
                        layers[msg["digest"]] = (msg.get("completed", 0), msg["total"])
                    pull_state["status"] = msg.get("status", "")
                    pull_state["completed"] = sum(c for c, _ in layers.values())
                    pull_state["total"] = sum(t for _, t in layers.values())
        pull_state["status"] = "success"
    except asyncio.CancelledError:
        pull_state["error"] = "Download stopped"
        raise
    except Exception as e:
        pull_state["error"] = f"Download failed: {e}"
    finally:
        pull_state["done"] = True
