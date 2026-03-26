#!/usr/bin/env python3
"""Debug: check if move_units actually works."""
import asyncio
import sys
sys.path.insert(0, "/home/ubuntu/OpenRA-RL-Training")

from openra_env.mcp_ws_client import OpenRAMCPClient
from openra_rl_training.training.agent_rollout import _generate_scenario_map


async def test():
    kwargs = _generate_scenario_map("scenarios/tempo/sprint-lite.yaml", ep_id=99, _ep="DBG")
    for k in ["terrain_png", "bounds_x", "bounds_y", "full_map_width", "full_map_height"]:
        kwargs.pop(k, None)

    env = OpenRAMCPClient("http://localhost:8000", message_timeout_s=60.0)
    async with env:
        await env.reset(**kwargs)
        await env.call_tool("advance", ticks=1)
        state = await env.call_tool("get_game_state")
        units = state.get("units_summary", [])
        print("Initial units:")
        for u in units:
            print(f"  {u.get('id')} {u.get('type')} at ({u.get('cell_x')},{u.get('cell_y')}) idle={u.get('idle')}")

        # Try move
        uid = units[0]["id"]
        print(f"\nMoving unit {uid} to (60,38)...")
        result = await env.call_tool("move_units", unit_ids=str(uid), target_x=60, target_y=38)
        print(f"move_units result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
        if isinstance(result, dict):
            print(f"  commanded_units: {result.get('commanded_units', 'N/A')}")
            print(f"  error: {result.get('error', 'none')}")

        # Advance 100 ticks and check position
        await env.call_tool("advance", ticks=100)
        state2 = await env.call_tool("get_game_state")
        units2 = state2.get("units_summary", [])
        print("\nAfter 100 ticks:")
        for u in units2:
            print(f"  {u.get('id')} {u.get('type')} at ({u.get('cell_x')},{u.get('cell_y')}) idle={u.get('idle')} activity={u.get('activity','?')}")

        # Advance 500 more
        await env.call_tool("advance", ticks=500)
        state3 = await env.call_tool("get_game_state")
        units3 = state3.get("units_summary", [])
        expl = state3.get("explored_percent", 0)
        print(f"\nAfter 600 ticks (explored={expl:.1f}%):")
        for u in units3:
            print(f"  {u.get('id')} {u.get('type')} at ({u.get('cell_x')},{u.get('cell_y')}) idle={u.get('idle')} activity={u.get('activity','?')}")


if __name__ == "__main__":
    asyncio.run(test())
