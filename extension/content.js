// Tunegrab — adds an "MP3" button to YouTube video, Shorts and playlist pages.
(() => {
  const api = globalThis.browser ?? globalThis.chrome;
  const PROTO = "tunegrab://add?url=";
  const ID = "tunegrab-mp3-button";
  const msg = (k) => api.i18n.getMessage(k) || k;

  const ICON_PATH =
    "M12 3a1 1 0 0 1 1 1v9.59l3.3-3.3a1 1 0 1 1 1.4 1.42l-5 5a1 1 0 0 1-1.4 0l-5-5a1 1 0 1 1 " +
    "1.4-1.42l3.3 3.3V4a1 1 0 0 1 1-1zM5 19a1 1 0 1 0 0 2h14a1 1 0 1 0 0-2H5z";

  function makeIcon() {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "20");
    svg.setAttribute("height", "20");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(NS, "path");
    path.setAttribute("fill", "currentColor");
    path.setAttribute("d", ICON_PATH);
    svg.appendChild(path);
    return svg;
  }

  function currentLink() {
    const u = new URL(location.href);
    const base = u.hostname === "music.youtube.com" ? "https://music.youtube.com" : "https://www.youtube.com";
    const v = u.searchParams.get("v");
    if (u.pathname === "/watch" && v) return `${base}/watch?v=${encodeURIComponent(v)}`;
    const shorts = u.pathname.match(/^\/shorts\/([\w-]{5,})/);
    if (shorts) return `https://www.youtube.com/shorts/${shorts[1]}`;
    const list = u.searchParams.get("list");
    if (u.pathname === "/playlist" && list) return `${base}/playlist?list=${encodeURIComponent(list)}`;
    return null;
  }

  function makeButton() {
    const b = document.createElement("button");
    b.id = ID;
    b.type = "button";
    b.title = msg("button_title");
    b.setAttribute("aria-label", msg("button_title"));
    const label = document.createElement("span");
    label.className = "tunegrab-label";
    label.textContent = "MP3";
    b.append(makeIcon(), label);
    b.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const link = currentLink();
      if (!link) return;
      // A real click counts as a user gesture, so the browser may open tunegrab://
      location.href = PROTO + encodeURIComponent(link);
      const label = b.querySelector(".tunegrab-label");
      label.textContent = "✓ " + msg("sent");
      b.classList.add("tunegrab-sent");
      setTimeout(() => {
        label.textContent = "MP3";
        b.classList.remove("tunegrab-sent");
      }, 2500);
    });
    return b;
  }

  // Next to Like / Share under a normal video; floating button elsewhere (Shorts, playlists, YouTube Music).
  function findSlot() {
    return (
      document.querySelector("ytd-watch-metadata #top-level-buttons-computed") ||
      document.querySelector("ytd-watch-metadata #actions-inner #menu")
    );
  }

  function place() {
    const link = currentLink();
    let b = document.getElementById(ID);
    if (!link) {
      b?.remove();
      return;
    }
    if (!b) b = makeButton();
    const slot = location.pathname === "/watch" ? findSlot() : null;
    if (slot) {
      b.classList.remove("tunegrab-floating");
      if (b.parentElement !== slot) slot.prepend(b);
    } else {
      b.classList.add("tunegrab-floating");
      if (b.parentElement !== document.body) document.body.appendChild(b);
    }
  }

  let queued = false;
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      place();
    });
  }

  // Toolbar icon / right-click menu: the background asks this page to open the link,
  // because a YouTube page is allowed to open tunegrab:// once the user ticked "Always allow".
  api.runtime.onMessage.addListener((message, _sender, reply) => {
    if (message?.type === "tunegrab-open" && typeof message.link === "string" && /^https:\/\//.test(message.link)) {
      location.href = PROTO + encodeURIComponent(message.link);
      reply({ ok: true });
    }
  });

  // YouTube is a single-page app: re-check after navigation and when its UI re-renders.
  document.addEventListener("yt-navigate-finish", schedule);
  window.addEventListener("popstate", schedule);
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  schedule();
})();
