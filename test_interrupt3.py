#!/usr/bin/env python3
"""Check if units actually move after move_units command."""
import asyncio
import sys
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
        r0 = await env.call_tool("advance", ticks=1)

        # Check initial state
        state = await env.call_tool("get_game_state")
        units = state.get("units_summary", [])
        for u in units:
            idle = u.get("idle", u.get("is_idle", "?"))
            act = u.get("activity", u.get("current_activity", "?"))
            print(f"  Unit {u.get('id')} {u.get('type')} at ({u.get('cell_x')},{u.get('cell_y')}) idle={idle} activity={act}")

        # Issue move
        uid = units[0].get("id")
        print(f"\nMoving unit {uid} to (60,38)...")
        move_result = await env.call_tool("move_units", unit_ids=str(uid), target_x=60, target_y=38)
        print(f"move_units result: {str(move_result)[:300]}")

        # Advance and check
        r1 = await env.call_tool("advance", ticks=50)
        state2 = await env.call_tool("get_game_state")
        units2 = state2.get("units_summary", [])
        print(f"\nAfter 50 ticks:")
        for u in units2:
            idle = u.get("idle", u.get("is_idle", "?"))
            act = u.get("activity", u.get("current_activity", "?"))
            print(f"  Unit {u.get('id')} {u.get('type')} at ({u.get('cell_x')},{u.get('cell_y')}) idle={idle} activity={act}")

        # Advance more
        r2 = await env.call_tool("advance", ticks=500)
        state3 = await env.call_tool("get_game_state")
        units3 = state3.get("units_summary", [])
        print(f"\nAfter 550 ticks:")
        for u in units3:
            idle = u.get("idle", u.get("is_idle", "?"))
            act = u.get("activity", u.get("current_activity", "?"))
            print(f"  Unit {u.get('id')} {u.get('type')} at ({u.get('cell_x')},{u.get('cell_y')}) idle={idle} activity={act}")

asyncio.run(test())
