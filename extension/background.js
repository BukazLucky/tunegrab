// Tunegrab browser extension — background.
// It never downloads anything itself: it only hands the video link to the
// Tunegrab app on this computer through a tunegrab:// link.

const api = globalThis.browser ?? globalThis.chrome;
const PROTO = "tunegrab://add?url=";
const msg = (k) => api.i18n.getMessage(k) || k;

// Links Tunegrab can turn into MP3 (YouTube videos, Shorts, playlists, YouTube Music).
function videoLink(raw) {
  let u;
  try { u = new URL(raw); } catch { return null; }
  if (!/^https?:$/.test(u.protocol)) return null;
  const host = u.hostname.replace(/^(www|m)\./, "");
  if (host === "youtu.be" && u.pathname.length > 1) return `https://youtu.be/${u.pathname.slice(1).split("/")[0]}`;
  if (host !== "youtube.com" && host !== "music.youtube.com") return null;
  const base = host === "music.youtube.com" ? "https://music.youtube.com" : "https://www.youtube.com";
  const v = u.searchParams.get("v");
  if (u.pathname === "/watch" && v) return `${base}/watch?v=${encodeURIComponent(v)}`;
  const shorts = u.pathname.match(/^\/shorts\/([\w-]{5,})/);
  if (shorts) return `https://www.youtube.com/shorts/${shorts[1]}`;
  const list = u.searchParams.get("list");
  if (u.pathname === "/playlist" && list) return `${base}/playlist?list=${encodeURIComponent(list)}`;
  return null;
}

function openWelcome() {
  api.tabs.create({ url: api.runtime.getURL("welcome.html") });
}

function sendToApp(tabId, raw) {
  const link = videoLink(raw);
  if (!link) {
    openWelcome();
    return;
  }
  // Preferred: let the YouTube page itself open tunegrab:// (same path as the MP3 button).
  // Fallback (tab is not a YouTube page): navigate the tab; the browser asks "Open Tunegrab?"
  // and the page itself stays where it is.
  const fallback = () => api.tabs.update(tabId, { url: PROTO + encodeURIComponent(link) });
  try {
    Promise.resolve(api.tabs.sendMessage(tabId, { type: "tunegrab-open", link }))
      .then((r) => { if (!r?.ok) fallback(); })
      .catch(fallback);
  } catch {
    fallback();
  }
}

function createMenus() {
  api.contextMenus.removeAll(() => {
    api.contextMenus.create({
      id: "tunegrab-link",
      title: msg("menu_send"),
      contexts: ["link"],
      targetUrlPatterns: ["*://*.youtube.com/*", "*://youtu.be/*"],
    });
    api.contextMenus.create({
      id: "tunegrab-page",
      title: msg("menu_send"),
      contexts: ["page", "video"],
      documentUrlPatterns: ["*://*.youtube.com/*"],
    });
  });
}

api.runtime.onInstalled.addListener((details) => {
  createMenus();
  if (details.reason === "install") openWelcome();
});
api.runtime.onStartup?.addListener(createMenus);

api.action.onClicked.addListener((tab) => sendToApp(tab.id, tab.url));

api.contextMenus.onClicked.addListener((info, tab) => {
  const raw = info.menuItemId === "tunegrab-link" ? info.linkUrl : info.pageUrl;
  sendToApp(tab.id, raw);
});
