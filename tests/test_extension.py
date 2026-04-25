import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extensions" / "chrome"


def test_chrome_extension_manifest_is_valid() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text())

    assert manifest["manifest_version"] == 3
    assert manifest["name"] == "FlowPilot Local Assistant"
    assert "storage" in manifest["permissions"]
    assert manifest["content_scripts"][0]["js"] == ["content.js", "widget.js"]


def test_chrome_extension_files_exist() -> None:
    for path in [
        "manifest.json",
        "content.js",
        "widget.js",
        "popup.html",
        "popup.js",
    ]:
        assert (EXTENSION / path).is_file()


def test_extension_widget_copy_matches_app_widget() -> None:
    app_widget = (ROOT / "src" / "ui_bot" / "static" / "widget.js").read_text()
    extension_widget = (EXTENSION / "widget.js").read_text()

    assert extension_widget == app_widget
