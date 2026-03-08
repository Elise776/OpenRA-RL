"""Local-only FastAPI app for replay pairing and preference capture."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from openra_env.arena_ui import ArenaController, empty_arena_state, render_arena_page


def create_arena_app(controller: Optional[ArenaController] = None) -> FastAPI:
    """Create the local-only arena app."""
    app = FastAPI(title="OpenRA-RL Local Arena")

    def arena_snapshot() -> dict:
        if controller is None:
            return empty_arena_state()
        return controller.snapshot()

    def require_controller() -> ArenaController:
        if controller is None:
            raise HTTPException(status_code=503, detail="Arena mode is not configured in this local app.")
        return controller

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/arena", status_code=307)

    @app.get("/arena", response_class=HTMLResponse, include_in_schema=False)
    async def arena_page():
        return render_arena_page(arena_snapshot())

    @app.get("/arena/state", include_in_schema=False)
    async def arena_state():
        return arena_snapshot()

    @app.post("/arena/session", include_in_schema=False)
    async def arena_start_session(payload: dict | None = Body(default=None)):
        current = require_controller()
        payload = payload or {}
        left_run_id = str(payload.get("left_run_id", "")).strip()
        right_run_id = str(payload.get("right_run_id", "")).strip()
        comparison_mode = str(payload.get("comparison_mode", "fair")).strip() or "fair"
        fair_fields = [str(field) for field in (payload.get("fair_fields") or []) if str(field)]
        try:
            session = current.start_session(left_run_id, right_run_id, comparison_mode, fair_fields)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "session": session}

    @app.post("/arena/preferences", include_in_schema=False)
    async def arena_save_preference(payload: dict | None = Body(default=None)):
        current = require_controller()
        payload = payload or {}
        preferred_side = str(payload.get("preferred_side", "")).strip()
        try:
            saved_path = current.save_vote(preferred_side)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "path": saved_path}

    @app.delete("/arena/session", include_in_schema=False)
    async def arena_stop_session():
        current = require_controller()
        current.stop_session()
        return {"ok": True}

    return app


@dataclass
class BackgroundArenaApp:
    """Background uvicorn server handle for the local-only arena app."""

    server: object
    thread: threading.Thread
    base_url: str

    def close(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


def start_background_arena_app(
    controller: ArenaController,
    host: str = "127.0.0.1",
    port: int = 8090,
    startup_timeout: float = 15.0,
) -> BackgroundArenaApp:
    """Start the local-only arena app in a background thread."""
    import urllib.error
    import urllib.request

    import uvicorn

    app = create_arena_app(controller)
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{host}:{port}"
    start = time.time()
    last_error: Exception | None = None
    while time.time() - start < startup_timeout:
        if getattr(server, "started", False):
            return BackgroundArenaApp(server=server, thread=thread, base_url=base_url)
        try:
            req = urllib.request.urlopen(f"{base_url}/arena/state", timeout=1)
            if req.status == 200:
                return BackgroundArenaApp(server=server, thread=thread, base_url=base_url)
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
        if not thread.is_alive():
            break
        time.sleep(0.1)

    server.should_exit = True
    thread.join(timeout=5)
    if last_error is not None:
        raise OSError(f"Local arena app did not become ready on port {port}") from last_error
    raise OSError(f"Local arena app did not become ready on port {port}")
