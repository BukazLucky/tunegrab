const api = globalThis.browser ?? globalThis.chrome;
document.documentElement.lang = api.i18n.getUILanguage();
for (const el of document.querySelectorAll("[data-i18n]")) {
  el.textContent = api.i18n.getMessage(el.dataset.i18n);
}
document.title = "Tunegrab — " + api.i18n.getMessage("w_subtitle");
