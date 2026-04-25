const enabled = document.getElementById("enabled");
const apiBase = document.getElementById("api-base");
const save = document.getElementById("save");
const status = document.getElementById("status");

chrome.storage.sync.get(
  {
    enabled: true,
    apiBase: "http://127.0.0.1:8000",
  },
  (settings) => {
    enabled.checked = settings.enabled;
    apiBase.value = settings.apiBase;
  }
);

save.addEventListener("click", () => {
  const value = apiBase.value.trim().replace(/\/$/, "");
  chrome.storage.sync.set(
    {
      enabled: enabled.checked,
      apiBase: value || "http://127.0.0.1:8000",
    },
    () => {
      status.textContent = "Saved. Reload the page to apply changes.";
    }
  );
});
