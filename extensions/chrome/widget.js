(function () {
  if (document.getElementById("ui-bot-widget")) return;

  const script = document.currentScript;
  const configuredApiBase = script?.dataset.apiBase || "";
  let sessionId = window.localStorage.getItem("ui_bot_session_id");
  let lastResponse = null;

  const root = document.createElement("div");
  root.id = "ui-bot-widget";
  root.innerHTML = `
    <style>
      #ui-bot-widget {
        position: fixed;
        right: 20px;
        bottom: 20px;
        z-index: 2147483000;
        font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      }
      .ui-bot-panel {
        width: min(360px, calc(100vw - 40px));
        height: 500px;
        max-height: calc(100vh - 110px);
        display: none;
        grid-template-rows: auto 1fr auto;
        background: #ffffff;
        border: 1px solid #cfd7df;
        border-radius: 8px;
        box-shadow: 0 16px 48px rgba(22, 27, 34, 0.18);
        overflow: hidden;
      }
      .ui-bot-panel[data-open="true"] { display: grid; }
      .ui-bot-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 14px;
        background: #17202a;
        color: #fff;
        font-weight: 650;
      }
      .ui-bot-messages {
        padding: 12px;
        overflow: auto;
        display: flex;
        flex-direction: column;
        gap: 8px;
        background: #f7f8fa;
      }
      .ui-bot-message {
        max-width: 88%;
        padding: 9px 10px;
        border-radius: 8px;
        font-size: 14px;
        line-height: 1.35;
        overflow-wrap: anywhere;
      }
      .ui-bot-user {
        align-self: flex-end;
        color: #fff;
        background: #1f6feb;
      }
      .ui-bot-assistant {
        align-self: flex-start;
        color: #17202a;
        background: #fff;
        border: 1px solid #d8dee4;
      }
      .ui-bot-form {
        display: grid;
        grid-template-columns: auto auto 1fr;
        gap: 8px;
        padding: 10px;
        border-top: 1px solid #d8dee4;
        background: #fff;
      }
      .ui-bot-input {
        grid-column: 1 / -1;
        width: 100%;
        box-sizing: border-box;
        border: 1px solid #cfd7df;
        border-radius: 6px;
        padding: 10px;
        font: inherit;
      }
      .ui-bot-button, .ui-bot-toggle {
        border: 1px solid #cfd7df;
        background: #fff;
        color: #17202a;
        border-radius: 6px;
        min-width: 38px;
        height: 38px;
        font: inherit;
        cursor: pointer;
      }
      .ui-bot-send {
        background: #1f6feb;
        color: #fff;
        border-color: #1f6feb;
        padding: 0 14px;
      }
      .ui-bot-toggle {
        width: 56px;
        height: 56px;
        margin-top: 10px;
        float: right;
        border-radius: 50%;
        color: #fff;
        background: #17202a;
        border-color: #17202a;
        box-shadow: 0 10px 26px rgba(22, 27, 34, 0.22);
      }
      .ui-bot-feedback {
        display: none;
        grid-template-columns: repeat(4, 1fr);
        gap: 6px;
        padding: 8px 10px 0;
        border-top: 1px solid #d8dee4;
        background: #fff;
      }
      .ui-bot-feedback[data-visible="true"] { display: grid; }
      .ui-bot-feedback .ui-bot-button {
        font-size: 12px;
        min-width: 0;
        width: 100%;
      }
    </style>
    <section class="ui-bot-panel" aria-label="UI Bot chat">
      <div class="ui-bot-header">
        <span>UI Bot</span>
        <button class="ui-bot-button" data-close title="Close">×</button>
      </div>
      <div class="ui-bot-messages" role="log" aria-live="polite"></div>
      <div class="ui-bot-feedback">
        <button class="ui-bot-button" type="button" data-feedback="approve">Approve</button>
        <button class="ui-bot-button" type="button" data-feedback="correct">Correct</button>
        <button class="ui-bot-button" type="button" data-feedback="reject">Reject</button>
        <button class="ui-bot-button" type="button" data-feedback="done">Done</button>
      </div>
      <form class="ui-bot-form">
        <input class="ui-bot-input" name="message" autocomplete="off" placeholder="Ask UI Bot">
        <button class="ui-bot-button" type="button" data-voice title="Voice input">Mic</button>
        <button class="ui-bot-button ui-bot-send" type="submit">Send</button>
      </form>
    </section>
    <button class="ui-bot-toggle" title="Open UI Bot">Chat</button>
  `;

  document.body.appendChild(root);

  const panel = root.querySelector(".ui-bot-panel");
  const toggle = root.querySelector(".ui-bot-toggle");
  const close = root.querySelector("[data-close]");
  const form = root.querySelector(".ui-bot-form");
  const input = root.querySelector(".ui-bot-input");
  const messages = root.querySelector(".ui-bot-messages");
  const voice = root.querySelector("[data-voice]");
  const feedbackBar = root.querySelector(".ui-bot-feedback");

  toggle.addEventListener("click", () => {
    panel.dataset.open = "true";
    input.focus();
  });
  close.addEventListener("click", () => {
    panel.dataset.open = "false";
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    addMessage(text, "user");
    await send(text);
  });

  voice.addEventListener("click", () => {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      addMessage("Voice input is not supported in this browser.", "assistant");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      input.value = event.results[0][0].transcript;
      input.focus();
    };
    recognition.onerror = () => {
      addMessage("Voice input failed. Please type the command.", "assistant");
    };
    recognition.start();
  });

  feedbackBar.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-feedback]");
    if (!button || !lastResponse) return;
    const kind = button.dataset.feedback;
    let comment = "";
    let correction = {};
    if (kind === "correct") {
      const fieldLabel = window.prompt("Field label to correct, for example Email");
      if (!fieldLabel) return;
      const selector = window.prompt(
        "Correct CSS selector, for example input[name='contact_email']"
      );
      if (!selector) return;
      comment = `Use ${selector} for ${fieldLabel}`;
      correction = { kind: "field_selector", field_label: fieldLabel, selector };
    }
    await sendFeedback(kind, comment, correction);
  });

  async function send(text) {
    try {
      const response = await fetch(`${getApiBase()}/api/chat`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: text,
          current_url: window.location.href
        })
      });
      const data = await response.json();
      lastResponse = data;
      sessionId = data.session_id;
      window.localStorage.setItem("ui_bot_session_id", sessionId);
      addMessage(data.question || data.message, "assistant");
      feedbackBar.dataset.visible = data.actions?.length ? "true" : "false";
      applyLocalActions(data.actions || []);
    } catch (error) {
      addMessage("The UI Bot service is not reachable.", "assistant");
    }
  }

  async function sendFeedback(kind, comment, correction) {
    const action = lastResponse.actions?.[lastResponse.actions.length - 1] || null;
    const snapshot = lastResponse.snapshot || {};
    try {
      const response = await fetch(`${getApiBase()}/api/feedback`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          trace_id: lastResponse.trace_id,
          kind,
          target_action: action,
          url: snapshot.url || window.location.href,
          page_title: snapshot.title || document.title,
          comment,
          correction
        })
      });
      if (!response.ok) throw new Error("feedback failed");
      addMessage(feedbackMessage(kind), "assistant");
      if (kind === "done") feedbackBar.dataset.visible = "false";
    } catch (error) {
      addMessage("Feedback could not be saved.", "assistant");
    }
  }

  function feedbackMessage(kind) {
    if (kind === "correct") return "Correction saved and promoted for reuse.";
    if (kind === "approve") return "Approval saved.";
    if (kind === "reject") return "Rejection saved.";
    return "Workflow marked done.";
  }

  function addMessage(text, role) {
    const node = document.createElement("div");
    node.className = `ui-bot-message ui-bot-${role}`;
    node.textContent = text;
    messages.appendChild(node);
    messages.scrollTop = messages.scrollHeight;
  }

  function getApiBase() {
    return globalThis.__FLOWPILOT_API_BASE__ || configuredApiBase;
  }

  function applyLocalActions(actions) {
    const extensionMode =
      globalThis.__FLOWPILOT_EXTENSION_MODE__ ||
      document.documentElement.dataset.flowpilotExtensionMode === "true";
    if (!extensionMode) return;
    for (const action of actions) {
      if (action.type === "navigate" && action.value) {
        window.location.href = action.value;
      }
      if (action.type === "click") {
        clickLocalTarget(action);
      }
      if (action.type === "fill") {
        fillLocalFields(action.fields || {});
      }
      if (action.type === "scroll") {
        const delta = action.value === "up" ? -700 : 700;
        window.scrollBy({ top: delta, behavior: "smooth" });
      }
      if (action.type === "back") {
        window.history.back();
      }
    }
  }

  function clickLocalTarget(action) {
    const target = findLocalTarget(action.selector, action.value);
    if (!target || isSubmitLike(target)) return;
    target.click();
  }

  function fillLocalFields(fields) {
    for (const [key, value] of Object.entries(fields)) {
      const target = findLocalField(key);
      if (!target) continue;
      if (target.type === "checkbox" || target.type === "radio") {
        target.checked = isTruthy(value);
      } else if (target.tagName === "SELECT") {
        setSelectValue(target, value);
      } else {
        target.value = value;
      }
      target.dispatchEvent(new Event("input", { bubbles: true }));
      target.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function findLocalTarget(selector, text) {
    if (selector) {
      const bySelector = document.querySelector(selector);
      if (bySelector) return bySelector;
    }
    if (!text) return null;
    const normalized = normalize(text);
    const candidates = Array.from(
      document.querySelectorAll("a[href], button, input[type=button], [role=button]")
    ).filter((element) => normalize(element.innerText || element.value || "") === normalized);
    return candidates.length === 1 ? candidates[0] : null;
  }

  function findLocalField(key) {
    if (key.includes("[") || key.startsWith("#") || key.startsWith(".")) {
      const bySelector = document.querySelector(key);
      if (bySelector) return bySelector;
    }
    const normalized = normalize(key);
    for (const field of document.querySelectorAll("input, textarea, select")) {
      const label = labelFor(field);
      const candidates = [label, field.name, field.id, field.placeholder, field.type];
      if (candidates.some((candidate) => normalize(candidate || "") === normalized)) {
        return field;
      }
    }
    return null;
  }

  function labelFor(field) {
    if (field.id) {
      const explicit = document.querySelector(`label[for="${CSS.escape(field.id)}"]`);
      if (explicit) return directText(explicit) || explicit.innerText;
    }
    const wrapping = field.closest("label");
    if (wrapping) return directText(wrapping) || wrapping.innerText;
    return "";
  }

  function directText(element) {
    return Array.from(element.childNodes)
      .filter((child) => child.nodeType === Node.TEXT_NODE)
      .map((child) => child.textContent || "")
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function setSelectValue(select, value) {
    const option = Array.from(select.options).find(
      (item) => item.value === value || item.text === value
    );
    if (option) select.value = option.value;
  }

  function isSubmitLike(element) {
    return (
      element.matches("input[type=submit], button[type=submit]") ||
      element.getAttribute("type") === "submit"
    );
  }

  function isTruthy(value) {
    return ["1", "true", "yes", "y", "on", "checked"].includes(
      String(value).trim().toLowerCase()
    );
  }

  function normalize(value) {
    return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  }
})();
