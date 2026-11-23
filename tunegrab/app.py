"""Tunegrab — window."""
from __future__ import annotations

import ctypes
import json
import locale
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import engine

# ------------------------------------------------------------------ look
ACCENT = ("#6D5DF6", "#7C6CFF")
ACCENT_HOVER = ("#5A49E8", "#6A59F0")
BG = ("#F5F4FA", "#121117")
CARD = ("#FFFFFF", "#1C1B22")
FIELD = ("#F7F6FC", "#16151B")
BORDER = ("#E3E1EE", "#2B2934")
SEG = ("#EEECF6", "#24222C")
SEL = ("#D9D3FF", "#40378A")
TEXT = ("#1B1A22", "#EDECF3")
MUTED = ("#6E6C7A", "#9896A6")
OK = ("#178A55", "#3DD68C")
ERR = ("#C93C3C", "#FF6B6B")
STOP = ("#D64545", "#E05252")
STOP_HOVER = ("#B93636", "#C94444")

QUALITIES = [("q_best", 320), ("q_good", 192), ("q_small", 128)]
LANGS = ["en", "es", "pt", "de", "fr", "it", "pl", "tr", "uk", "ru", "zh"]


def resource(*parts) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


# ------------------------------------------------------------------ i18n
class I18n:
    def __init__(self):
        self.tables = {}
        for code in LANGS:
            p = resource("tunegrab", "locales", f"{code}.json")
            try:
                self.tables[code] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        self.code = "en"

    def available(self):
        return [c for c in LANGS if c in self.tables]

    def name(self, code):
        return self.tables.get(code, {}).get("_language", code)

    def __call__(self, key, **kw):
        s = self.tables.get(self.code, {}).get(key) or self.tables.get("en", {}).get(key) or key
        try:
            return s.format(**kw)
        except Exception:
            return s


def system_language() -> str:
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        name = locale.windows_locale.get(lid, "en")
    except Exception:
        name = (locale.getlocale()[0] or "en")
    return name.split("_")[0].lower()


def font(size=13, weight="normal"):
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


def short(text: str, n: int = 64) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


# ------------------------------------------------------------------ queue row
class Row(ctk.CTkFrame):
    def __init__(self, master, app, title):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.path = None
        self.key, self.params = "st_waiting", {}
        self.grid_columnconfigure(0, weight=1)
        self.title = ctk.CTkLabel(self, text=short(title), font=font(13), text_color=TEXT, anchor="w")
        self.title.grid(row=0, column=0, sticky="ew", padx=(4, 8))
        self.status = ctk.CTkLabel(self, text="", font=font(12), text_color=MUTED, anchor="e")
        self.status.grid(row=0, column=1, sticky="e")
        self.btn = ctk.CTkButton(self, text="", width=78, height=24, font=font(12),
                                 fg_color="transparent", border_width=1, border_color=BORDER,
                                 text_color=TEXT, hover_color=BORDER, command=self.reveal)
        self.bar = ctk.CTkProgressBar(self, height=4, progress_color=ACCENT, fg_color=BORDER)
        self.bar.set(0)
        self.bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=(2, 8))
        self.render()

    def set_title(self, title):
        self.title.configure(text=short(title))

    def set(self, key, params=None, error_key=None):
        self.key, self.params = key, params or {}
        self.error_key = error_key
        pct = self.params.get("pct")
        if key == "st_downloading":
            self.bar.set((pct or 0) / 100 * 0.8)
        elif key == "st_converting":
            self.bar.set(0.8 + (pct or 0) / 100 * 0.2)
        elif key in ("st_done", "st_exists"):
            self.bar.set(1)
        self.render()

    def render(self):
        t = self.app.t
        if self.key == "st_error":
            self.status.configure(text=t(getattr(self, "error_key", None) or "err_generic"), text_color=ERR)
            self.bar.configure(progress_color=ERR)
            self.bar.set(1)
        elif self.key in ("st_done", "st_exists"):
            self.status.configure(text="✓ " + t(self.key), text_color=OK)
            self.bar.configure(progress_color=OK)
        elif self.key == "st_cancelled":
            self.status.configure(text=t(self.key), text_color=MUTED)
        else:
            self.status.configure(text=t(self.key, **self.params), text_color=MUTED)
        if self.path and self.key in ("st_done", "st_exists"):
            self.btn.configure(text=t("show"))
            self.btn.grid(row=0, column=2, padx=(8, 4))
        else:
            self.btn.grid_forget()

    def reveal(self):
        if self.path and Path(self.path).exists():
            subprocess.Popen(["explorer", "/select,", str(self.path)])


# ------------------------------------------------------------------ app
class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        ctk.set_appearance_mode("system")
        self.t = I18n()
        self.s = engine.load_settings()
        lang = self.s.get("lang") or system_language()
        self.t.code = lang if lang in self.t.tables else "en"

        self.ui_q: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.rows: list[Row] = []
        self.last_clip = None
        self.last_clip_check = 0.0
        self.tried_update = False
        self.new_version = None

        self.folder = Path(self.s.get("folder") or engine.music_dir() / "Tunegrab")
        q = self.s.get("quality", 320)
        self.quality = q if q in (320, 192, 128) else 320

        self.title("Tunegrab")
        self.geometry("640x760")
        self.minsize(540, 620)
        try:
            self.iconbitmap(str(resource("assets", "icon.ico")))
        except Exception:
            pass

        self.build()
        self.texts()
        self.bind_all("<Control-KeyPress>", self.ctrl_keys, add="+")
        self.bind("<FocusIn>", lambda e: self.after(150, self.check_clipboard))
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(60, self.pump)
        self.after(400, self.watch_input)
        if engine.components_ready():
            self.after(300, self.startup_tasks)
        else:
            self.show_setup()

    # ---------------- layout
    def build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        px = 22

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=px, pady=(18, 10))
        head.grid_columnconfigure(1, weight=1)
        try:
            from PIL import Image
            img = Image.open(resource("assets", "logo.png"))
            self.logo = ctk.CTkImage(img, img, size=(44, 44))
            ctk.CTkLabel(head, image=self.logo, text="").grid(row=0, column=0, rowspan=2, padx=(0, 12))
        except Exception:
            pass
        ctk.CTkLabel(head, text="Tunegrab", font=font(24, "bold"), text_color=TEXT, anchor="w").grid(row=0, column=1, sticky="w")
        self.tagline = ctk.CTkLabel(head, font=font(12), text_color=MUTED, anchor="w")
        self.tagline.grid(row=1, column=1, sticky="w")
        codes = self.t.available()
        self.lang_names = {self.t.name(c): c for c in codes}
        self.lang_menu = ctk.CTkOptionMenu(head, values=list(self.lang_names), width=130, height=30,
                                           font=font(12), dropdown_font=font(12),
                                           fg_color=CARD, button_color=CARD, button_hover_color=BORDER,
                                           text_color=TEXT, command=self.change_lang)
        self.lang_menu.set(self.t.name(self.t.code))
        self.lang_menu.grid(row=0, column=2, rowspan=2, sticky="e")

        # input card
        card = self.card(1)
        card.grid_columnconfigure(0, weight=1)
        self.box = ctk.CTkTextbox(card, height=118, font=font(13), fg_color=FIELD, border_width=1,
                                  border_color=BORDER, text_color=TEXT, wrap="none", corner_radius=10)
        self.box.grid(row=0, column=0, columnspan=4, sticky="ew", padx=14, pady=(14, 8))
        self.hint = ctk.CTkLabel(self.box, font=font(13), text_color=MUTED, justify="left", anchor="nw",
                                 fg_color=FIELD)
        self.hint.place(x=12, y=8)
        self.hint.bind("<Button-1>", lambda e: self.box.focus_set())
        self.box.bind("<Button-3>", lambda e: self.paste())
        self.paste_btn = ctk.CTkButton(card, width=110, height=32, font=font(13, "bold"),
                                       fg_color="transparent", border_width=2, border_color=ACCENT,
                                       text_color=ACCENT, hover_color=BORDER, command=self.paste)
        self.paste_btn.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 14))
        self.clear_btn = ctk.CTkButton(card, width=90, height=32, font=font(13), fg_color="transparent",
                                       text_color=MUTED, hover_color=BORDER, command=self.clear)
        self.clear_btn.grid(row=1, column=0, sticky="w", padx=(132, 0), pady=(0, 14))
        self.count = ctk.CTkLabel(card, text="", font=font(12), text_color=MUTED)
        self.count.grid(row=1, column=3, sticky="e", padx=14, pady=(0, 14))

        # options card
        opt = self.card(2)
        opt.grid_columnconfigure(1, weight=1)
        self.q_label = ctk.CTkLabel(opt, font=font(13), text_color=MUTED, anchor="w", width=100)
        self.q_label.grid(row=0, column=0, sticky="w", padx=(14, 6), pady=(12, 6))
        self.q_seg = ctk.CTkSegmentedButton(opt, font=font(12, "bold"), height=30, selected_color=SEL,
                                            selected_hover_color=SEL, fg_color=SEG,
                                            unselected_color=SEG, unselected_hover_color=BORDER,
                                            text_color=(TEXT[0], TEXT[1]), command=self.set_quality)
        self.q_seg.grid(row=0, column=1, columnspan=2, sticky="w", pady=(12, 6))
        self.f_label = ctk.CTkLabel(opt, font=font(13), text_color=MUTED, anchor="w", width=100)
        self.f_label.grid(row=1, column=0, sticky="w", padx=(14, 6), pady=(6, 12))
        self.f_path = ctk.CTkLabel(opt, font=font(13), text_color=TEXT, anchor="w", cursor="hand2")
        self.f_path.grid(row=1, column=1, sticky="ew", pady=(6, 12))
        self.f_path.bind("<Button-1>", lambda e: self.open_folder())
        self.f_btn = ctk.CTkButton(opt, width=100, height=30, font=font(12), fg_color="transparent",
                                   border_width=1, border_color=BORDER, text_color=TEXT,
                                   hover_color=BORDER, command=self.pick_folder)
        self.f_btn.grid(row=1, column=2, sticky="e", padx=14, pady=(6, 12))

        # main button + status
        act = ctk.CTkFrame(self, fg_color="transparent")
        act.grid(row=3, column=0, sticky="ew", padx=px, pady=(4, 6))
        act.grid_columnconfigure(0, weight=1)
        self.go = ctk.CTkButton(act, height=48, corner_radius=12, font=font(16, "bold"),
                                fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.start_or_stop)
        self.go.grid(row=0, column=0, sticky="ew")
        self.status = ctk.CTkLabel(act, text="", font=font(12), text_color=MUTED, wraplength=560)
        self.status.grid(row=1, column=0, pady=(6, 0))

        # queue
        qcard = self.card(4, sticky="nsew")
        qcard.grid_columnconfigure(0, weight=1)
        qcard.grid_rowconfigure(0, weight=1)
        self.list = ctk.CTkScrollableFrame(qcard, fg_color="transparent", scrollbar_button_color=BORDER,
                                           scrollbar_button_hover_color=MUTED)
        self.list.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.list.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(self.list, font=font(13), text_color=MUTED)
        self.empty.grid(row=0, column=0, pady=40)

        # footer
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=5, column=0, sticky="ew", padx=px, pady=(2, 12))
        foot.grid_columnconfigure(0, weight=1)
        self.legal = ctk.CTkLabel(foot, font=font(11), text_color=MUTED, anchor="w")
        self.legal.grid(row=0, column=0, sticky="w")
        self.open_btn = self.link(foot, self.open_folder)
        self.open_btn.grid(row=0, column=1, padx=(8, 0))
        self.help_btn = self.link(foot, lambda: webbrowser.open(f"https://github.com/{engine.REPO}#readme"))
        self.help_btn.grid(row=0, column=2, padx=(8, 0))
        self.banner = ctk.CTkButton(self, height=30, font=font(12, "bold"), fg_color=OK, hover_color=OK,
                                    text_color="#FFFFFF", command=self.open_release)

    def card(self, row, sticky="ew"):
        f = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        f.grid(row=row, column=0, sticky=sticky, padx=22, pady=6)
        return f

    def link(self, master, cmd):
        return ctk.CTkButton(master, width=10, height=24, font=font(12, "bold"), fg_color="transparent",
                             text_color=ACCENT, hover_color=BORDER, command=cmd)

    def texts(self):
        t = self.t
        self.tagline.configure(text=t("tagline"))
        self.lang_menu.set(t.name(t.code))
        self.hint.configure(text=t("input_hint"))
        self.paste_btn.configure(text=t("paste"))
        self.clear_btn.configure(text=t("clear"))
        self.q_label.configure(text=t("quality"))
        labels = [t(k) for k, _ in QUALITIES]
        self.q_seg.configure(values=labels)
        self.q_seg.set(labels[[v for _, v in QUALITIES].index(self.quality)])
        self.f_label.configure(text=t("save_to"))
        self.f_btn.configure(text=t("change"))
        self.f_path.configure(text=self.short_path())
        self.go.configure(text=t("stop") if self.busy else t("download"))
        self.empty.configure(text=t("empty_queue"))
        self.legal.configure(text=t("legal"))
        self.open_btn.configure(text=t("open_folder"))
        self.help_btn.configure(text=t("help"))
        if self.new_version:
            self.banner.configure(text=t("new_version", v=self.new_version))
        for r in self.rows:
            r.render()
        self.update_count()
        if hasattr(self, "setup"):
            self.setup_texts()

    def short_path(self):
        p = str(self.folder)
        return p if len(p) <= 46 else "…" + p[-45:]

    # ---------------- input helpers
    def ctrl_keys(self, e):
        if e.keysym.lower() in ("v", "c", "x", "a"):
            return None  # Latin layout: Tk handles it
        w = e.widget
        events = {86: "<<Paste>>", 67: "<<Copy>>", 88: "<<Cut>>"}
        if e.keycode in events:
            w.event_generate(events[e.keycode])
            return "break"
        if e.keycode == 65:
            try:
                w.tag_add("sel", "1.0", "end")
            except Exception:
                try:
                    w.select_range(0, "end")
                except Exception:
                    pass
            return "break"
        return None

    def text(self):
        return self.box.get("1.0", "end").strip()

    def paste(self):
        try:
            clip = self.clipboard_get()
        except Exception:
            clip = ""
        links = engine.extract_links(clip)
        if not links:
            self.say(self.t("no_links"))
            return
        self.add_links(links)
        self.last_clip = clip

    def add_links(self, links):
        current = engine.extract_links(self.text())
        new = [l for l in links if l not in current]
        if new:
            cur = self.text()
            self.box.delete("1.0", "end")
            self.box.insert("1.0", (cur + "\n" if cur else "") + "\n".join(new))
        self.update_count()

    def clear(self):
        self.box.delete("1.0", "end")
        self.update_count()

    def check_clipboard(self):
        if self.busy or hasattr(self, "setup") or time.time() - self.last_clip_check < 1:
            return
        self.last_clip_check = time.time()
        try:
            clip = self.clipboard_get()
        except Exception:
            return
        if clip == self.last_clip:
            return
        links = engine.extract_links(clip)
        if links and not self.text():
            self.last_clip = clip
            self.add_links(links)
            self.say(self.t("from_clipboard"))

    def watch_input(self):
        self.update_count()
        self.after(400, self.watch_input)

    def update_count(self):
        txt = self.text()
        if txt:
            self.hint.place_forget()
        else:
            self.hint.place(x=12, y=8)
        n = len(engine.extract_links(txt))
        self.count.configure(text=self.t("links_count", n=n) if n else "")

    def say(self, msg, color=MUTED):
        self.status.configure(text=msg, text_color=color)

    # ---------------- options
    def set_quality(self, label):
        labels = [self.t(k) for k, _ in QUALITIES]
        if label in labels:
            self.quality = QUALITIES[labels.index(label)][1]
            self.save()

    def change_lang(self, name):
        self.t.code = self.lang_names.get(name, "en")
        self.save()
        self.texts()

    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=str(self.folder), parent=self)
        if d:
            self.folder = Path(d)
            self.f_path.configure(text=self.short_path())
            self.save()

    def open_folder(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.folder))

    def save(self):
        s = engine.load_settings()
        s.update({"folder": str(self.folder), "quality": self.quality, "lang": self.t.code})
        engine.save_settings(s)

    # ---------------- thread -> UI
    def ui(self, fn, *a, **kw):
        self.ui_q.put((fn, a, kw))

    def pump(self):
        try:
            for _ in range(200):
                fn, a, kw = self.ui_q.get_nowait()
                fn(*a, **kw)
        except queue.Empty:
            pass
        self.after(60, self.pump)

    # ---------------- setup (first launch)
    def show_setup(self):
        self.setup = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.setup.place(relx=0, rely=0, relwidth=1, relheight=1)
        box = ctk.CTkFrame(self.setup, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER)
        box.place(relx=0.5, rely=0.45, anchor="center", relwidth=0.84)
        box.grid_columnconfigure(0, weight=1)
        if hasattr(self, "logo"):
            ctk.CTkLabel(box, image=self.logo, text="").grid(row=0, column=0, pady=(24, 6))
        self.su_title = ctk.CTkLabel(box, font=font(20, "bold"), text_color=TEXT)
        self.su_title.grid(row=1, column=0, pady=(0, 6))
        self.su_text = ctk.CTkLabel(box, font=font(13), text_color=MUTED, wraplength=440, justify="center")
        self.su_text.grid(row=2, column=0, padx=24)
        self.su_bar = ctk.CTkProgressBar(box, height=8, progress_color=ACCENT, fg_color=BORDER)
        self.su_bar.set(0)
        self.su_bar.grid(row=3, column=0, sticky="ew", padx=40, pady=(18, 6))
        self.su_pct = ctk.CTkLabel(box, text="0%", font=font(12), text_color=MUTED)
        self.su_pct.grid(row=4, column=0)
        self.su_retry = ctk.CTkButton(box, height=36, font=font(13, "bold"), fg_color=ACCENT,
                                      hover_color=ACCENT_HOVER, command=self.run_setup)
        ctk.CTkLabel(box, text="", height=12).grid(row=6, column=0)
        self.setup_texts()
        self.run_setup()

    def setup_texts(self):
        self.su_title.configure(text=self.t("setup_title"))
        self.su_text.configure(text=self.t("setup_text"))
        self.su_retry.configure(text=self.t("try_again"))

    def run_setup(self):
        self.su_retry.grid_forget()
        self.su_text.configure(text=self.t("setup_text"), text_color=MUTED)

        def prog(f):
            self.ui(lambda: (self.su_bar.set(f), self.su_pct.configure(text=f"{int(f * 100)}%")))

        def work():
            try:
                engine.install_components(prog, self.cancel)
                self.ui(self.setup_done)
            except engine.Cancelled:
                pass
            except Exception as e:
                key = e.key if isinstance(e, engine.FriendlyError) else "setup_failed"
                self.ui(self.setup_failed, key)

        threading.Thread(target=work, daemon=True).start()

    def setup_failed(self, key):
        self.su_text.configure(text=self.t(key), text_color=ERR)
        self.su_retry.grid(row=5, column=0, pady=(12, 0))

    def setup_done(self):
        self.setup.destroy()
        del self.setup
        engine.save_settings({**engine.load_settings(), "last_update": time.time()})
        self.startup_tasks()

    def startup_tasks(self):
        self.check_clipboard()
        engine.start_update()

        def bg():
            v = engine.latest_app_version()
            if v and tuple(map(int, v.split(".")[:3])) > tuple(map(int, engine.VERSION.split("."))):
                self.ui(self.show_banner, v)

        threading.Thread(target=bg, daemon=True).start()

    def show_banner(self, v):
        self.new_version = v
        self.banner.configure(text=self.t("new_version", v=v))
        self.banner.grid(row=6, column=0, sticky="ew", padx=22, pady=(0, 12))

    def open_release(self):
        webbrowser.open(f"https://github.com/{engine.REPO}/releases/latest")

    # ---------------- downloading
    def start_or_stop(self):
        if self.busy:
            self.cancel.set()
            engine.kill_all()
            self.go.configure(state="disabled")
            return
        links = engine.extract_links(self.text())
        if not links:
            self.say(self.t("no_links"), ERR)
            return
        self.cancel.clear()
        self.busy = True
        self.go.configure(text=self.t("stop"), fg_color=STOP, hover_color=STOP_HOVER)
        self.say("")
        self.empty.grid_forget()
        for r in self.rows:
            r.destroy()
        self.rows = []
        self.box.delete("1.0", "end")
        self.update_count()
        placeholders = [self.new_row(l) for l in links]
        threading.Thread(target=self.worker, args=(links, placeholders, self.folder, self.quality),
                         daemon=True).start()

    def new_row(self, title):
        r = Row(self.list, self, title)
        r.grid(row=len(self.rows), column=0, sticky="ew")
        self.rows.append(r)
        return r

    def worker(self, links, placeholders, folder, kbps):
        ok = fail = 0
        generic = False
        if engine._update_lock.locked():
            self.ui(self.say, self.t("updating"))
        with engine._update_lock:
            pass
        self.ui(self.say, "")
        for url, row in zip(links, placeholders):
            if self.cancel.is_set():
                self.ui(row.set, "st_cancelled")
                continue
            self.ui(row.set, "st_reading")
            try:
                items = engine.expand(url, self.cancel)
            except engine.Cancelled:
                self.ui(row.set, "st_cancelled")
                continue
            except engine.FriendlyError as e:
                fail += 1
                generic |= e.key == "err_generic"
                self.ui(row.set, "st_error", None, e.key)
                continue
            if not items:
                fail += 1
                self.ui(row.set, "st_error", None, "err_unavailable")
                continue
            # first item reuses the placeholder row, the rest get new rows
            rows = [row]
            done_evt = threading.Event()

            def make_rows(items=items, rows=rows):
                rows[0].set_title(items[0].title)
                for it in items[1:]:
                    rows.append(self.new_row(it.title))
                done_evt.set()

            self.ui(make_rows)
            done_evt.wait()
            for it, r in zip(items, rows):
                if self.cancel.is_set():
                    self.ui(r.set, "st_cancelled")
                    continue
                if it.status == "st_error":
                    fail += 1
                    self.ui(r.set, "st_error", None, it.error)
                    continue
                try:
                    path = engine.download_item(it, folder, kbps, self.cancel,
                                                lambda k, p, r=r: self.ui(r.set, k, p))
                    r.path = path
                    self.ui(r.render)
                    ok += 1
                except engine.Cancelled:
                    self.ui(r.set, "st_cancelled")
                except engine.FriendlyError as e:
                    fail += 1
                    generic |= e.key == "err_generic"
                    self.ui(r.set, "st_error", None, e.key)
                except Exception:
                    fail += 1
                    generic = True
                    engine.log("unexpected: " + traceback.format_exc())
                    self.ui(r.set, "st_error", None, "err_generic")
        if generic and not self.tried_update:
            self.tried_update = True
            engine.start_update(force=True)
        self.ui(self.finish, ok, fail, generic)

    def finish(self, ok, fail, generic):
        self.busy = False
        self.go.configure(text=self.t("download"), fg_color=ACCENT, hover_color=ACCENT_HOVER, state="normal")
        msg = self.t("summary", ok=ok, fail=fail)
        if generic:
            msg += "\n" + self.t("update_hint")
        self.say(msg, OK if not fail else MUTED)
        if self.cancel.is_set():
            self.say(self.t("st_cancelled"))

    def on_close(self):
        if self.busy and not messagebox.askyesno("Tunegrab", self.t("confirm_close"), parent=self):
            return
        self.cancel.set()
        engine.kill_all()
        self.destroy()


def main():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Tunegrab.App")
    except Exception:
        pass
    App().mainloop()
