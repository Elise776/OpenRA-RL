#!/usr/bin/env python3
"""Load test: 64 concurrent episodes across 2 game servers."""
import asyncio
import sys
import time
sys.path.insert(0, "/home/ubuntu/OpenRA-RL-Training")

from openra_env.mcp_ws_client import OpenRAMCPClient
from openra_rl_training.training.agent_rollout import _generate_scenario_map


async def run_episode(url: str, ep_id: int):
    """Run a single test episode: reset, move, advance 500 ticks."""
    kwargs = _generate_scenario_map("scenarios/tempo/sprint-lite.yaml", ep_id=ep_id, _ep=f"LOAD{ep_id}")
    for k in ["terrain_png", "bounds_x", "bounds_y", "full_map_width", "full_map_height"]:
        kwargs.pop(k, None)

    t0 = time.monotonic()
    try:
        env = OpenRAMCPClient(base_url=url, message_timeout_s=60.0)
        async with env:
            await env.reset(**kwargs)
            await env.call_tool("advance", ticks=1)
            state = await env.call_tool("get_game_state")
            units = state.get("units_summary", [])

            # Issue move commands for all units
            for u in units:
                uid = u.get("id", 0)
                if uid:
                    await env.call_tool("move_units", unit_ids=str(uid), target_x=60, target_y=38)

            # Advance 500 ticks
            r = await env.call_tool("advance", ticks=500)
            elapsed = time.monotonic() - t0
            return {"ep": ep_id, "ok": True, "elapsed": elapsed, "tick": r.get("tick", 0)}
    except Exception as e:
        elapsed = time.monotonic() - t0
        return {"ep": ep_id, "ok": False, "elapsed": elapsed, "error": str(e)[:100]}


async def main():
    urls = sys.argv[1:] if len(sys.argv) > 1 else ["http://localhost:8000", "http://localhost:8001"]
    n_episodes = 64
    print(f"Load test: {n_episodes} episodes across {len(urls)} servers")

    # Round-robin distribute
    tasks = []
    for i in range(n_episodes):
        url = urls[i % len(urls)]
        tasks.append(run_episode(url, i))

    t0 = time.monotonic()
    results = await asyncio.gather(*tasks)
    total = time.monotonic() - t0

    ok = sum(1 for r in results if r["ok"])
    fail = sum(1 for r in results if not r["ok"])
    times = [r["elapsed"] for r in results if r["ok"]]
    avg_t = sum(times) / len(times) if times else 0
    max_t = max(times) if times else 0

    print(f"\nResults: {ok}/{n_episodes} ok, {fail} failed, total={total:.1f}s")
    print(f"Per-episode: avg={avg_t:.1f}s, max={max_t:.1f}s")
    if fail > 0:
        for r in results:
            if not r["ok"]:
                print(f"  FAIL ep{r['ep']}: {r['error']}")


if __name__ == "__main__":
    asyncio.run(main())
