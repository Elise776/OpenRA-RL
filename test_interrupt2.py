#!/usr/bin/env python3
"""Detailed interrupt test: step-by-step advances watching for events."""
import asyncio
import sys
import time
sys.path.insert(0, "/home/ubuntu/OpenRA-RL-Training")

from openra_env.mcp_ws_client import OpenRAMCPClient
from openra_rl_training.training.agent_rollout import _generate_scenario_map


async def test():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    kwargs = _generate_scenario_map("scenarios/tempo/sprint-lite.yaml", ep_id=0, _ep="T")
    for k in ["terrain_png", "bounds_x", "bounds_y", "full_map_width", "full_map_height"]:
        kwargs.pop(k, None)

    env = OpenRAMCPClient(base_url=url, message_timeout_s=60.0)
    async with env:
        await env.reset(**kwargs)
        await env.call_tool("advance", ticks=1)
        state = await env.call_tool("get_game_state")
        units = state.get("units_summary", [])
        print(f"Units: {len(units)}")
        for u in units:
            print(f"  {u.get('id')} {u.get('type')} at ({u.get('cell_x')},{u.get('cell_y')})")

        # Move all units toward enemy building at (60,38)
        for u in units:
            uid = u.get("id", 0)
            if uid:
                await env.call_tool("move_units", unit_ids=str(uid), target_x=60, target_y=38)
        print("Moved all units toward (60,38)")

        # Step-by-step advances
        for i in range(20):
            r = await env.call_tool("advance", ticks=200)
            tick = r.get("tick")
            intr = r.get("interrupted")
            reason = r.get("interrupt_reason", "")
            actual = r.get("actual_ticks_advanced")
            expl = r.get("explored_percent", 0)
            enemies = r.get("enemy_summary", [])
            bldgs = r.get("enemy_buildings_summary", [])
            n_e = len(enemies) if isinstance(enemies, list) else 0
            n_b = len(bldgs) if isinstance(bldgs, list) else 0
            marker = " ** INTERRUPT **" if intr else ""
            print(f"  [{i+1:2d}] tick={tick:5d} actual={actual:4d} expl={expl:5.1f}% enemies={n_e} bldgs={n_b} intr={intr} {reason}{marker}")
            if intr:
                break

        print("Done!")


if __name__ == "__main__":
    asyncio.run(test())
