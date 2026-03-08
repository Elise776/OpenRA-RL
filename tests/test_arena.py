"""Tests for local replay comparison and preference export helpers."""

import json
from pathlib import Path


def test_save_and_load_run_artifact(tmp_path, monkeypatch):
    from openra_env import arena_data

    monkeypatch.setattr(arena_data, "RUNS_DIR", tmp_path / "runs")
    saved = arena_data.save_run_artifact({
        "run_id": "run_test",
        "messages": [{"role": "system", "content": "hello"}],
    })
    loaded = arena_data.load_run_artifact("run_test")

    assert saved["run_id"] == "run_test"
    assert Path(saved["path"]).exists()
    assert loaded["messages"][0]["content"] == "hello"


def test_resolve_compare_entry_from_run_artifact(tmp_path, monkeypatch):
    from openra_env import arena_data

    runs_dir = tmp_path / "runs"
    replay_dir = tmp_path / "replays"
    monkeypatch.setattr(arena_data, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(arena_data.docker, "LOCAL_REPLAY_DIR", replay_dir)
    replay_dir.mkdir(parents=True)
    (replay_dir / "demo.orarep").write_text("stub", encoding="utf-8")

    arena_data.save_run_artifact({
        "run_id": "run_demo",
        "agent": {"name": "DemoBot", "model": "qwen3:4b"},
        "match": {"map_name": "singles", "opponent": "normal"},
        "summary": {"result": "win", "ticks": 1234},
        "replay": {"filename": "demo.orarep"},
        "messages": [],
    })

    entry = arena_data.resolve_compare_entry("run_demo", slot="left")
    assert entry["run_id"] == "run_demo"
    assert entry["replay_path"].endswith("demo.orarep")
    assert entry["metadata"]["map"] == "singles"


def test_extract_start_state_and_compatibility():
    from openra_env import arena_data

    left = {
        "config": {
            "game": {"map_name": "singles.oramap", "seed": 7, "mod": "ra"},
            "opponent": {"bot_type": "easy", "ai_slot": "Multi0"},
        },
        "match": {"map_name": "singles.oramap", "opponent": "easy", "faction": "france"},
        "engine": {"image_version": "0.4.1-ra"},
    }
    right = {
        "config": {
            "game": {"map_name": "singles.oramap", "seed": 7, "mod": "ra"},
            "opponent": {"bot_type": "easy", "ai_slot": "Multi0"},
        },
        "match": {"map_name": "singles.oramap", "opponent": "easy", "faction": "france"},
        "engine": {"image_version": "0.4.1-ra"},
    }
    mismatch = {
        "config": {
            "game": {"map_name": "singles.oramap", "seed": 9, "mod": "ra"},
            "opponent": {"bot_type": "easy", "ai_slot": "Multi0"},
        },
        "match": {"map_name": "singles.oramap", "opponent": "easy", "faction": "france"},
        "engine": {"image_version": "0.4.1-ra"},
    }

    left_entry = arena_data.build_run_browser_entry_from_artifact({"run_id": "left", **left, "replay": {}})
    right_entry = arena_data.build_run_browser_entry_from_artifact({"run_id": "right", **right, "replay": {}})
    mismatch_entry = arena_data.build_run_browser_entry_from_artifact({"run_id": "mismatch", **mismatch, "replay": {}})

    assert left_entry["start_state"]["class"] == "ra"
    assert left_entry["start_state"]["seed"] == 7
    assert arena_data.runs_are_compatible(left_entry, right_entry, ["map", "seed", "class"])
    assert not arena_data.runs_are_compatible(left_entry, mismatch_entry, ["map", "seed", "class"])


def test_export_preference_pairs(tmp_path, monkeypatch):
    from openra_env import arena_data

    runs_dir = tmp_path / "runs"
    prefs_dir = tmp_path / "preferences"
    export_dir = tmp_path / "exports"
    monkeypatch.setattr(arena_data, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(arena_data, "PREFERENCES_DIR", prefs_dir)
    monkeypatch.setattr(arena_data, "EXPORTS_DIR", export_dir)

    left = arena_data.save_run_artifact({
        "run_id": "run_left",
        "agent": {"model": "model-a"},
        "match": {"map_name": "singles"},
        "summary": {"result": "win"},
        "replay": {"filename": "left.orarep"},
        "messages": [{"role": "user", "content": "left"}],
    })
    right = arena_data.save_run_artifact({
        "run_id": "run_right",
        "agent": {"model": "model-b"},
        "match": {"map_name": "singles"},
        "summary": {"result": "lose"},
        "replay": {"filename": "right.orarep"},
        "messages": [{"role": "user", "content": "right"}],
    })

    pref = arena_data.comparison_record(
        {
            "run_id": left["run_id"],
            "run_path": left["path"],
            "replay_path": "left.orarep",
            "metadata": {},
        },
        {
            "run_id": right["run_id"],
            "run_path": right["path"],
            "replay_path": "right.orarep",
            "metadata": {},
        },
        preferred_side="left",
    )
    arena_data.save_preference(pref)

    export_path, count = arena_data.export_preference_pairs()
    lines = export_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])

    assert count == 1
    assert payload["chosen_run_id"] == "run_left"
    assert payload["rejected_run_id"] == "run_right"
    assert payload["chosen"]["text"].startswith("[user] left")


def test_arena_controller_and_fastapi_routes():
    from fastapi.testclient import TestClient

    from openra_env.arena_ui import ArenaController
    from openra_env.local.arena_app import create_arena_app

    runs = [{
        "run_id": "run_demo",
        "label": "DemoBot",
        "replay_available": True,
        "metadata": {"result": "win"},
        "start_state": {"map": "singles", "seed": 7, "class": "ra"},
        "search_blob": "run_demo demobot singles",
    }]
    session = {
        "left": {"run_id": "run_a", "slot": "left", "port": 6080},
        "right": {"run_id": "run_b", "slot": "right", "port": 6081},
        "comparison_mode": "fair",
        "fair_fields": ["map", "seed"],
    }
    saved_votes: list[str] = []
    stop_calls: list[str] = []

    def _list_runs():
        return runs

    def _start_compare(left_run_id, right_run_id, comparison_mode, fair_fields):
        assert left_run_id == "run_demo"
        assert right_run_id == "run_demo"
        assert comparison_mode == "ab"
        assert fair_fields == ["map"]
        return session

    def _save_preference(side):
        saved_votes.append(side)
        return "saved.json"

    def _stop_compare():
        stop_calls.append("stop")

    controller = ArenaController(
        list_runs=_list_runs,
        start_compare=_start_compare,
        save_preference=_save_preference,
        stop_compare=_stop_compare,
        fair_fields=[{"key": "map", "label": "Map"}],
        default_fair_fields=["map"],
    )
    client = TestClient(create_arena_app(controller))

    root_html = client.get("/arena")
    state_payload = client.get("/arena/state")

    assert root_html.status_code == 200
    assert "Replay Arena" in root_html.text
    assert "Fair Comparison" in root_html.text
    assert "local evaluation workflow" in root_html.text
    assert state_payload.status_code == 200
    assert state_payload.json()["runs"][0]["run_id"] == "run_demo"

    payload = client.post(
        "/arena/session",
        json={
            "left_run_id": "run_demo",
            "right_run_id": "run_demo",
            "comparison_mode": "ab",
            "fair_fields": ["map"],
        },
    ).json()
    assert payload["session"]["comparison_mode"] == "fair"

    vote_payload = client.post("/arena/preferences", json={"preferred_side": "left"}).json()
    assert vote_payload["path"] == "saved.json"
    assert saved_votes == ["left"]

    stop_response = client.delete("/arena/session")
    assert stop_response.status_code == 200
    assert stop_calls == ["stop"]
