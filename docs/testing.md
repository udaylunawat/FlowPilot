# UI Bot Test Plan

## Validation Layers

1. Unit tests for parsing, storage, provider fallback, HITL promotion, and
   deterministic action routing.
2. Local fixture workflow tests against the built-in demo page.
3. Browser smoke tests for widget rendering, text chat, feedback controls, and
   voice button behavior.
4. Optional live-provider smoke tests using `.env` keys.
5. Optional real-website exploratory tests with submit actions blocked until
   explicit approval.

## Sample Workflow Cases

### 1. Generic Navigation

- Command: `open https://example.com`
- Expected: agent navigates, snapshots title/links, saves location.

### 2. Click A Link

- Command: `click Learn more`
- Expected: agent resolves one visible link/button, clicks it, records the step.
- Failure case: if more than one target matches, agent asks instead of guessing.

### 3. Scroll And Back

- Commands: `scroll down`, `scroll up`, `go back`
- Expected: agent executes browser primitives without LLM.

### 4. Fill Form With Missing Required Fields

- Command: `fill the form`
- Expected: agent detects required fields and asks for missing values.

### 5. Fill Form With Provided Values

- Command payload:
  ```json
  {
    "message": "fill the form",
    "answers": {
      "Name": "Test User",
      "Email": "user@example.test"
    }
  }
  ```
- Expected: agent fills matching fields and does not submit.

### 6. HITL Correction Reuse

- Step 1: submit correction:
  ```json
  {
    "kind": "correct",
    "correction": {
      "kind": "field_selector",
      "field_label": "Email",
      "selector": "input[name=email]"
    }
  }
  ```
- Step 2: run a later fill workflow on the same URL pattern.
- Expected: agent rewrites `Email` to `input[name=email]` before filling.

### 7. Voice Control

- Open the widget.
- Click `Mic`.
- Browser should request microphone permission.
- Speak: `inspect`.
- Expected: transcript appears in the input. Press `Send` to run it.

Voice uses the browser Web Speech API. Automated tests can verify the button,
fallback copy, and that mocked speech results populate the input. Real speech
recognition still needs a manual browser/microphone test because permission and
audio capture are controlled by the browser/OS.

### 8. Downloaded React-Site Fixture

- Open `/fixtures/react-site/`.
- Commands:
  - `inspect`
  - `click Support`
  - `fill the form`
  - provide `Name`, `Email`, `Topic`, `Message`, and `Send me updates`
  - `click Review request`
- Expected: the bot navigates between sections, asks for missing fields, fills
  text/select/checkbox controls, and stops without submitting.

## Real Website Smoke Candidates

Use low-risk pages and avoid login/signup/account flows:

- `https://example.com`: open and click `Learn more`.
- A public documentation site: search or click navigation links.
- A public contact/demo form that does not submit sensitive data.
- Local static fixture pages for repeated regression tests.
