"""Tunegrab launcher (double-click or build with PyInstaller)."""
import sys


def selftest(url: str, folder: str) -> None:
    """Tunegrab.exe --selftest URL FOLDER  -> result goes to the log file."""
    import threading
    from pathlib import Path
    from tunegrab import engine

    import faulthandler

    engine.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(engine.DATA_DIR / "selftest_trace.txt", "w")
    faulthandler.dump_traceback_later(40, exit=True, file=fh)
    cancel = threading.Event()
    try:
        if not engine.components_ready():
            engine.install_components(None, cancel)
        items = engine.expand(url, cancel)
        path = engine.download_item(items[0], Path(folder), 192, cancel, lambda k, p: None)
        engine.log(f"SELFTEST OK {path}")
    except Exception as e:  # noqa: BLE001
        engine.log(f"SELFTEST FAIL {type(e).__name__}: {e}")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2], sys.argv[3])
    else:
        from tunegrab import bridge

        urls = bridge.parse_args(sys.argv[1:])
        # Tunegrab already open? Hand the links over (or just bring it to front) and quit.
        if bridge.send_to_running(urls):
            sys.exit(0)
        from tunegrab.app import main

        main(urls)
