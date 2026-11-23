# Third-party components

## Bundled inside `Tunegrab.exe`

| Component | License | Source |
|---|---|---|
| Python runtime | PSF License | https://www.python.org |
| PyAV | BSD-3-Clause | https://github.com/PyAV-Org/PyAV |
| FFmpeg libraries (shipped with the PyAV wheel; reported license: LGPL-3.0-or-later) | LGPL-3.0-or-later | https://ffmpeg.org · build scripts: https://github.com/PyAV-Org/pyav-ffmpeg |
| LAME MP3 encoder (part of the FFmpeg build above) | LGPL-2.0-or-later | https://lame.sourceforge.io |
| CustomTkinter | MIT | https://github.com/TomSchimansky/CustomTkinter |
| Mutagen | GPL-2.0-or-later | https://github.com/quodlibet/mutagen |
| Pillow | MIT-CMU (HPND) | https://python-pillow.org |
| Tcl/Tk | Tcl/Tk License | https://www.tcl.tk |

Tunegrab's own source code is MIT-licensed. Because the released `Tunegrab.exe` bundles Mutagen (GPL-2.0-or-later),
the executable as a whole is distributed under the terms of the GNU GPL (version 3); its complete source code is this
repository.

The FFmpeg/LAME libraries are loaded as separate DLLs. You may replace them with your own build; the exact versions
used by a release can be reproduced from `requirements.txt` and `build.ps1`.

## Downloaded on first launch (not bundled)

| Component | License | Source |
|---|---|---|
| yt-dlp | Unlicense | https://github.com/yt-dlp/yt-dlp |
| Deno | MIT | https://github.com/denoland/deno |
