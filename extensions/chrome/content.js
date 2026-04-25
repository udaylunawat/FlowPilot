(function () {
  if (globalThis.__FLOWPILOT_CONTENT_READY__) return;
  globalThis.__FLOWPILOT_CONTENT_READY__ = true;
  globalThis.__FLOWPILOT_EXTENSION_MODE__ = true;
  document.documentElement.dataset.flowpilotExtensionMode = "true";
  globalThis.__FLOWPILOT_API_BASE__ = "http://127.0.0.1:8000";

  chrome.storage.sync.get(
    {
      enabled: true,
      apiBase: "http://127.0.0.1:8000",
    },
    (settings) => {
      globalThis.__FLOWPILOT_API_BASE__ = settings.apiBase;
      if (!settings.enabled) {
        document.getElementById("ui-bot-widget")?.remove();
      }
    }
  );
})();
