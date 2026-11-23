# Privacy Policy — Tunegrab

_Last updated: 24 November 2026_

Tunegrab consists of a Windows app and an optional browser extension ("Tunegrab: MP3 button").

## The browser extension

- **Collects no data.** It has no analytics, no tracking, no accounts, no remote servers and no storage of any kind.
- It reads the address of the current YouTube page **only when you click** the MP3 button, the toolbar icon or the
  right-click menu item, and passes that address to the Tunegrab app on your own computer through a `tunegrab://` link.
  Nothing is sent anywhere else.
- Permissions: `activeTab` (read the current tab's address when you click), `contextMenus` (the right-click item), and a
  content script on youtube.com pages (to show the MP3 button).

## The Windows app

- No analytics, no accounts, no personal data.
- It connects to YouTube to fetch the audio you asked for, and to GitHub to download and update its download engine
  (yt-dlp, Deno) and to check whether a new Tunegrab version exists.
- Settings and a small error log are stored only on your computer in `%LOCALAPPDATA%\Tunegrab`.

## Contact

Questions: open an issue at https://github.com/BukazLucky/tunegrab/issues
