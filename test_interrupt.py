#!/usr/bin/env python3
"""Test server-side interrupt detection with a real scenario."""
import asyncio
import sys
import time
sys.path.insert(0, "/home/ubuntu/OpenRA-RL-Training")

from openra_env.mcp_ws_client import OpenRAMCPClient
from openra_rl_training.training.agent_rollout import _generate_scenario_map


async def test():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    print(f"Connecting to {url}...")

    # Generate a scenario map with enemies
    kwargs = _generate_scenario_map("scenarios/tempo/sprint-lite.yaml", ep_id=0, _ep="TEST")
    for k in ["terrain_png", "bounds_x", "bounds_y", "full_map_width", "full_map_height"]:
        kwargs.pop(k, None)

    env = OpenRAMCPClient(base_url=url, message_timeout_s=120.0)
    async with env:
        print("Resetting with sprint-lite scenario...")
        obs = await env.reset(**kwargs)
        print(f"Reset OK. tick={obs.get('tick')}")

        # Advance 1 tick to spawn units, then get state
        await env.call_tool("advance", ticks=1)
        state = await env.call_tool("get_game_state")
        units = state.get("units_summary", [])
        print(f"Units: {[(u.get('id', u.get('actor_id')), u.get('type')) for u in units]}")

        # Move all units toward enemy building locations
        print("\n--- Moving units toward enemies ---")
        for u in units:
            uid = u.get("id", u.get("actor_id", 0))
            if uid:
                await env.call_tool("move_units", unit_ids=str(uid), target_x=60, target_y=38)

        # Advance 1000 ticks — should trigger enemy_spotted or building_discovered
        t0 = time.monotonic()
        r = await env.call_tool("advance", ticks=1000)
        t1 = time.monotonic()
        print(f"  Took {t1-t0:.2f}s, tick={r.get('tick')}")
        print(f"  interrupted={r.get('interrupted')}")
        print(f"  interrupt_reason={r.get('interrupt_reason')}")
        print(f"  actual_ticks_advanced={r.get('actual_ticks_advanced')}")
        print(f"  explored_percent={r.get('explored_percent'):.1f}%")

        if not r.get("interrupted"):
            # Try again with more ticks
            print("\n--- Advancing 2000 more ticks ---")
            t0 = time.monotonic()
            r2 = await env.call_tool("advance", ticks=2000)
            t1 = time.monotonic()
            print(f"  Took {t1-t0:.2f}s, tick={r2.get('tick')}")
            print(f"  interrupted={r2.get('interrupted')}")
            print(f"  interrupt_reason={r2.get('interrupt_reason')}")
            print(f"  actual_ticks_advanced={r2.get('actual_ticks_advanced')}")
            print(f"  explored_percent={r2.get('explored_percent'):.1f}%")

        print("\nDone!")


if __name__ == "__main__":
    asyncio.run(test())
