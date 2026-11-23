"""Packs the browser extension into store-ready zips:
   dist/tunegrab-extension-chromium-<ver>.zip  (Chrome, Edge, Opera, Yandex, Brave)
   dist/tunegrab-extension-firefox-<ver>.zip
Run:  python tools/build_extension.py
"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"
DIST = ROOT / "dist"


def files():
    for p in sorted(EXT.rglob("*")):
        if p.is_file() and p.name != "manifest.json" and not p.name.startswith("."):
            yield p


def check_locales(manifest):
    en = json.loads((EXT / "_locales" / "en" / "messages.json").read_text(encoding="utf-8"))
    for f in sorted((EXT / "_locales").glob("*/messages.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        missing = set(en) - set(d)
        assert not missing, f"{f.parent.name}: missing {missing}"
        assert len(d["ext_name"]["message"]) <= 45, f"{f.parent.name}: name too long"
        assert len(d["ext_description"]["message"]) <= 132, f"{f.parent.name}: description too long"


def pack(name, manifest):
    DIST.mkdir(exist_ok=True)
    out = DIST / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for p in files():
            z.write(p, p.relative_to(EXT).as_posix())
    print("built", out.relative_to(ROOT), round(out.stat().st_size / 1024), "KB")


def main():
    base = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    check_locales(base)
    ver = base["version"]
    pack(f"tunegrab-extension-chromium-{ver}.zip", base)

    ff = json.loads(json.dumps(base))
    ff["background"] = {"scripts": ["background.js"]}
    ff["browser_specific_settings"] = {
        "gecko": {
            "id": "tunegrab@bukazlucky.github.io",
            "strict_min_version": "128.0",
            "data_collection_permissions": {"required": ["none"]},
        }
    }
    pack(f"tunegrab-extension-firefox-{ver}.zip", ff)


if __name__ == "__main__":
    main()
