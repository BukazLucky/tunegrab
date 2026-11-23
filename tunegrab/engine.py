"""Tunegrab engine: components (yt-dlp + deno), download, MP3 conversion, tagging."""
from __future__ import annotations

import ctypes
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "Tunegrab"
VERSION = "1.0.0"
REPO = "BukazLucky/tunegrab"

DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME
BIN_DIR = DATA_DIR / "bin"
YTDLP = BIN_DIR / "yt-dlp.exe"
DENO = BIN_DIR / "deno.exe"
SETTINGS_FILE = DATA_DIR / "settings.json"

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_SUMS = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS"
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
DENO_SUM = DENO_URL + ".sha256sum"

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UA = {"User-Agent": f"{APP_NAME}/{VERSION}"}


class Cancelled(Exception):
    pass


LOG_FILE = DATA_DIR / "tunegrab.log"


def log(msg: str) -> None:
    """Append to the log file (kept under ~200 KB)."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 200_000:
            LOG_FILE.write_text(LOG_FILE.read_text(encoding="utf-8", errors="replace")[-100_000:], encoding="utf-8")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg.strip() + "\n")
    except Exception:
        pass


class FriendlyError(Exception):
    """Error with a translation key for the UI."""

    def __init__(self, key: str, detail: str = ""):
        super().__init__(detail or key)
        self.key = key
        self.detail = detail
        log(f"{key}: {detail}")


# ---------------------------------------------------------------- settings
def music_dir() -> Path:
    try:
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

        g = GUID(0x4BD8D571, 0x6D19, 0x48D3, (ctypes.c_ubyte * 8)(0xBE, 0x97, 0x42, 0x22, 0x20, 0x08, 0x0E, 0x43))
        p = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0:
            path = Path(p.value)
            ctypes.windll.ole32.CoTaskMemFree(p)
            return path
    except Exception:
        pass
    return Path.home() / "Music"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------- components
def components_ready() -> bool:
    return YTDLP.exists() and DENO.exists()


def _download(url: str, dest: Path, on_progress=None, cancel: threading.Event | None = None) -> None:
    req = urllib.request.Request(url, headers=UA)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancel and cancel.is_set():
                raise Cancelled()
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done, total)
    tmp.replace(dest)


def _fetch_text(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def install_components(on_progress=None, cancel=None) -> None:
    """Download yt-dlp.exe and deno.exe (official releases, checksum-verified).
    on_progress(fraction 0..1)."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    # rough weights: yt-dlp ~24 MB, deno ~43 MB
    w1, w2 = 0.36, 0.64

    def prog(base, weight):
        return lambda d, t: on_progress and t and on_progress(base + weight * d / t)

    if not YTDLP.exists():
        sums = _fetch_text(YTDLP_SUMS)
        m = re.search(r"([0-9a-fA-F]{64})\s+\*?yt-dlp\.exe\s*$", sums, re.M)
        tmp = BIN_DIR / "yt-dlp.download"
        _download(YTDLP_URL, tmp, prog(0, w1), cancel)
        if not m or _sha256(tmp) != m.group(1).lower():
            tmp.unlink(missing_ok=True)
            raise FriendlyError("err_checksum")
        tmp.replace(YTDLP)
    if on_progress:
        on_progress(w1)

    if not DENO.exists():
        expected = re.search(r"\b([0-9a-fA-F]{64})\b", _fetch_text(DENO_SUM))
        zpath = BIN_DIR / "deno.zip"
        _download(DENO_URL, zpath, prog(w1, w2), cancel)
        if not expected or _sha256(zpath) != expected.group(1).lower():
            zpath.unlink(missing_ok=True)
            raise FriendlyError("err_checksum")
        with zipfile.ZipFile(zpath) as z:
            with z.open("deno.exe") as src, open(DENO, "wb") as dst:
                shutil.copyfileobj(src, dst)
        zpath.unlink(missing_ok=True)
    if on_progress:
        on_progress(1.0)


_update_lock = threading.Lock()


def needs_update() -> bool:
    return time.time() - load_settings().get("last_update", 0) >= 86400


def update_ytdlp_locked() -> None:
    """Self-update yt-dlp. Caller must have acquired _update_lock; it is released here."""
    try:
        r = subprocess.run([str(YTDLP), "-U"], capture_output=True, timeout=180, creationflags=NO_WINDOW,
                           stdin=subprocess.DEVNULL)
        log("update: " + (r.stdout or b"").decode("utf-8", "replace").strip().replace("\n", " | ")[-300:])
        s = load_settings()
        s["last_update"] = time.time()
        save_settings(s)
    except Exception as e:
        log(f"update failed: {e}")
    finally:
        _update_lock.release()


def start_update(force: bool = False) -> bool:
    """Start a background update (daily unless forced). Takes the lock synchronously,
    so downloads started right after this call will wait for it."""
    if not force and not needs_update():
        return False
    if not _update_lock.acquire(blocking=False):
        return False
    threading.Thread(target=update_ytdlp_locked, daemon=True).start()
    return True


def latest_app_version() -> str | None:
    if REPO.startswith("OWNER/"):
        return None
    try:
        data = json.loads(_fetch_text(f"https://api.github.com/repos/{REPO}/releases/latest"))
        return (data.get("tag_name") or "").lstrip("v") or None
    except Exception:
        return None


# ---------------------------------------------------------------- links
URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.I)
BARE_YT_RE = re.compile(r"(?<![/\w.])(?:(?:www|m|music)\.)?(?:youtube\.com|youtu\.be)/[^\s<>\"'`]+", re.I)


def extract_links(text: str) -> list[str]:
    found = []
    for m in URL_RE.finditer(text):
        found.append((m.start(), m.group(0)))
    for m in BARE_YT_RE.finditer(text):
        found.append((m.start(), "https://" + m.group(0)))
    out, seen = [], set()
    for _, u in sorted(found):
        u = u.rstrip(").,;!?]}")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ---------------------------------------------------------------- yt-dlp calls
def _base_args() -> list[str]:
    return [str(YTDLP), "--ignore-config", "--no-playlist", "--color", "never",
            "--js-runtimes", f"deno:{DENO}", "--no-warnings"]


_procs: set = set()


def kill_all() -> None:
    """Kill running yt-dlp processes (Stop button / window closed)."""
    for p in list(_procs):
        try:
            p.kill()
        except Exception:
            pass


def _run_proc(args, cancel, on_line=None) -> tuple[int, str, str]:
    if cancel.is_set():
        raise Cancelled()
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    _procs.add(proc)
    err_chunks: list[bytes] = []
    t = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    t.start()
    out_lines = []
    try:
        for raw in proc.stdout:
            if cancel.is_set():
                proc.kill()
                raise Cancelled()
            line = raw.decode("utf-8", "replace").rstrip()
            out_lines.append(line)
            if on_line:
                on_line(line)
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
        _procs.discard(proc)
    t.join(timeout=5)
    if cancel.is_set():
        raise Cancelled()
    return proc.returncode, "\n".join(out_lines), b"".join(err_chunks).decode("utf-8", "replace")


def classify_error(text: str) -> str:
    t = text.lower()
    rules = [
        ("private video", "err_private"),
        ("confirm your age", "err_age"), ("age-restricted", "err_age"), ("inappropriate for some users", "err_age"),
        ("not a bot", "err_bot"), ("http error 429", "err_bot"), ("try again later", "err_bot"),
        ("rate-limit", "err_bot"), ("rate limit", "err_bot"),
        ("live event", "err_live"), ("is live", "err_live"), ("premieres in", "err_live"),
        ("unsupported url", "err_unsupported"), ("is not a valid url", "err_unsupported"),
        ("getaddrinfo", "err_network"), ("failed to resolve", "err_network"), ("timed out", "err_network"),
        ("connection", "err_network"), ("network is unreachable", "err_network"),
        ("video unavailable", "err_unavailable"), ("is unavailable", "err_unavailable"),
        ("http error 404", "err_unavailable"), ("http error 410", "err_unavailable"), ("has been removed", "err_unavailable"),
        ("not available", "err_unavailable"), ("does not exist", "err_unavailable"),
        ("members-only", "err_unavailable"), ("join this channel", "err_unavailable"),
    ]
    for needle, key in rules:
        if needle in t:
            return key
    return "err_generic"


def _last_error(stderr: str) -> str:
    lines = [l.strip() for l in stderr.splitlines() if l.strip()]
    errs = [l for l in lines if "ERROR" in l]
    return (errs or lines or [""])[-1].replace("ERROR: ", "")


@dataclass
class Item:
    url: str
    title: str
    vid: str = ""
    duration: float | None = None
    status: str = "st_waiting"
    params: dict = field(default_factory=dict)
    path: Path | None = None
    error: str = ""


def expand(url: str, cancel) -> list[Item]:
    """Turn a link (video or playlist) into a list of items."""
    code, out, err = _run_proc(_base_args() + ["--flat-playlist", "-J", url], cancel)
    if code != 0 or not out.strip():
        raise FriendlyError(classify_error(err), _last_error(err))
    data = json.loads(out)
    entries = data.get("entries") if data.get("_type") == "playlist" else [data]
    items = []
    for e in entries or []:
        if not e:
            continue
        live = e.get("live_status") in ("is_live", "is_upcoming") or e.get("is_live")
        u = e.get("webpage_url") or e.get("url") or url
        if e.get("ie_key") == "Youtube" or (e.get("id") and "youtube" in (e.get("extractor_key") or e.get("ie_key") or "").lower()):
            u = f"https://www.youtube.com/watch?v={e['id']}"
        it = Item(url=u, title=e.get("title") or u, vid=e.get("id") or "", duration=e.get("duration"))
        if live:
            it.status, it.error = "st_error", "err_live"
        items.append(it)
    return items


def safe_filename(name: str, limit: int = 150) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if name.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
        name = "_" + name
    return (name[:limit].rstrip(". ") or "audio")


def _split_artist_title(title: str):
    m = re.match(r"^\s*(.+?)\s+[-–—]\s+(.+?)\s*$", title)
    if not m:
        return None, title
    track = re.sub(r"\s*[\(\[](official|lyric|audio|video|music video|official video|official audio|lyrics|hd|4k|visualizer)[^\)\]]*[\)\]]", "", m.group(2), flags=re.I).strip()
    return m.group(1).strip(), track or m.group(2)


def describe(info: dict) -> tuple[str, str, str | None, str]:
    """Return (artist, title, album, filename_stem)."""
    title = info.get("title") or "audio"
    artist = info.get("artist") or ", ".join(info.get("artists") or []) or info.get("creator")
    track = info.get("track")
    if artist and track:
        stem = f"{artist} - {track}"
        return artist, track, info.get("album"), stem
    a2, t2 = _split_artist_title(title)
    if a2:
        return a2, t2, info.get("album"), title
    uploader = (info.get("uploader") or info.get("channel") or "").replace(" - Topic", "").strip()
    return uploader, title, info.get("album"), title


def download_item(item: Item, folder: Path, kbps: int, cancel, on_status) -> Path:
    """Full pipeline for one item. on_status(key, params)."""
    folder.mkdir(parents=True, exist_ok=True)
    quick = folder / (safe_filename(item.title) + ".mp3")
    if item.title != item.url and quick.exists():
        item.path = quick
        on_status("st_exists", {})
        return quick
    tmp = Path(tempfile.mkdtemp(prefix="tunegrab_"))
    try:
        on_status("st_fetching", {})
        args = _base_args() + [
            "-f", "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
            "--fixup", "never", "--write-info-json", "--write-thumbnail", "--no-mtime",
            "--match-filter", "!is_live", "--newline",
            "--progress-template",
            "download:TGPROG %(progress.downloaded_bytes)s %(progress.total_bytes)s %(progress.total_bytes_estimate)s",
            "-o", "media.%(ext)s", "-P", str(tmp), item.url,
        ]

        def on_line(line: str):
            if line.startswith("TGPROG"):
                parts = line.split()
                try:
                    done = float(parts[1])
                    total = float(parts[2]) if parts[2] not in ("NA", "None") else float(parts[3])
                    on_status("st_downloading", {"pct": max(0, min(100, int(done * 100 / total)))})
                except (ValueError, IndexError, ZeroDivisionError):
                    pass

        code, out, err = _run_proc(args, cancel, on_line)
        files = [p for p in tmp.iterdir() if p.is_file()]
        info_f = next((p for p in files if p.name.endswith(".info.json")), None)
        media = next((p for p in files if p.suffix.lower() not in (".json", ".webp", ".jpg", ".jpeg", ".png", ".part", ".ytdl")), None)
        if code != 0 or not media or not info_f:
            if "does not pass filter" in out + err:
                raise FriendlyError("err_live")
            raise FriendlyError(classify_error(err + out), _last_error(err))
        info = json.loads(info_f.read_text(encoding="utf-8"))
        thumb = next((p for p in files if p.suffix.lower() in (".webp", ".jpg", ".jpeg", ".png")), None)

        artist, title, album, stem = describe(info)
        dest = folder / (safe_filename(stem) + ".mp3")
        if dest.exists():
            item.path = dest
            on_status("st_exists", {})
            return dest

        dur = info.get("duration") or item.duration
        part = tmp / "out.mp3"
        convert_to_mp3(media, part, kbps, dur, cancel,
                       lambda pct: on_status("st_converting", {"pct": pct}))
        write_tags(part, artist, title, album, info, thumb)
        shutil.move(str(part), str(dest))
        item.path = dest
        on_status("st_done", {})
        return dest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- conversion
def convert_to_mp3(src: Path, dst: Path, kbps: int, duration, cancel, on_pct) -> None:
    import av

    try:
        inp = av.open(str(src))
    except Exception as e:
        raise FriendlyError("err_convert", str(e))
    try:
        ast = inp.streams.audio[0]
        if not duration and inp.duration:
            duration = inp.duration / 1_000_000
        rate = ast.rate if ast.rate in (32000, 44100, 48000) else 44100
        out = av.open(str(dst), "w", format="mp3")
        ost = out.add_stream("libmp3lame", rate=rate)
        ost.bit_rate = kbps * 1000
        ost.codec_context.layout = "stereo"
        res = av.AudioResampler(format="fltp", layout="stereo", rate=rate)
        last = -1
        for frame in inp.decode(ast):
            if cancel.is_set():
                raise Cancelled()
            t = frame.time
            frame.pts = None
            for rf in res.resample(frame):
                for pkt in ost.encode(rf):
                    out.mux(pkt)
            if duration and t is not None:
                pct = int(min(99, t * 100 / duration))
                if pct != last:
                    last = pct
                    on_pct(pct)
        for rf in res.resample(None):
            for pkt in ost.encode(rf):
                out.mux(pkt)
        for pkt in ost.encode(None):
            out.mux(pkt)
        out.close()
    except (Cancelled, FriendlyError):
        raise
    except Exception as e:
        raise FriendlyError("err_convert", str(e))
    finally:
        inp.close()


def _cover_jpeg(thumb: Path) -> bytes | None:
    try:
        from PIL import Image

        im = Image.open(thumb).convert("RGB")
        w, h = im.size
        if abs(w / h - 1) > 0.05:  # crop the centre square (album-art look)
            s = min(w, h)
            im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
        im.thumbnail((600, 600))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        return buf.getvalue()
    except Exception:
        return None


def write_tags(path: Path, artist, title, album, info: dict, thumb: Path | None) -> None:
    from mutagen.id3 import APIC, COMM, ID3, TALB, TDRC, TIT2, TPE1, ID3NoHeaderError

    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()
    if title:
        tags.add(TIT2(encoding=3, text=title))
    if artist:
        tags.add(TPE1(encoding=3, text=artist))
    if album:
        tags.add(TALB(encoding=3, text=album))
    year = info.get("release_year") or (info.get("upload_date") or "")[:4]
    if year:
        tags.add(TDRC(encoding=3, text=str(year)))
    if info.get("webpage_url"):
        tags.add(COMM(encoding=3, lang="eng", desc="Source", text=info["webpage_url"]))
    if thumb:
        data = _cover_jpeg(thumb)
        if data:
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=data))
    tags.save(str(path), v2_version=3)
