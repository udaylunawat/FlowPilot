from pathlib import Path

from ui_bot.models import AgentAction, FeedbackCreate, LocationCreate
from ui_bot.storage import Storage


def test_locations_round_trip(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "test.sqlite3")

    saved = storage.save_location(
        LocationCreate(
            session_id="session-1",
            name="Example",
            url="https://example.test",
            metadata={"fields": ["email"]},
        )
    )

    locations = storage.list_locations("session-1")

    assert saved.id == locations[0].id
    assert locations[0].metadata == {"fields": ["email"]}
    storage.close()


def test_feedback_promotes_field_selector_template(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "test.sqlite3")

    feedback = storage.add_feedback(
        FeedbackCreate(
            session_id="session-1",
            trace_id="trace-1",
            kind="correct",
            target_action=AgentAction(type="fill", fields={"Email": "a@example.test"}),
            url="https://example.test/contact?ref=home",
            correction={
                "kind": "field_selector",
                "field_label": "Email",
                "selector": "input[name=email]",
            },
        )
    )
    templates = storage.list_templates("https://example.test/contact")

    assert feedback.kind == "correct"
    assert templates[0].field_label == "Email"
    assert templates[0].selector == "input[name=email]"
    storage.close()


def test_workflow_run_and_step_round_trip(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "test.sqlite3")
    storage.start_workflow_run("trace-1", "session-1", "fill form")
    storage.add_workflow_step(
        "trace-1",
        "session-1",
        AgentAction(type="ask", reason="missing_required_field"),
        result="Please provide Email",
        url="https://example.test/contact",
        title="Contact",
    )
    storage.finish_workflow_run("trace-1", "needs_human")

    runs = storage.list_workflow_runs("session-1")

    assert runs[0].id == "trace-1"
    assert runs[0].status == "needs_human"
    storage.close()
