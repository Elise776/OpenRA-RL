#!/usr/bin/env python3
"""Debug: check if enemy buildings are visible after moving toward them."""
import asyncio
import sys
sys.path.insert(0, "/home/ubuntu/OpenRA-RL-Training")

from openra_env.mcp_ws_client import OpenRAMCPClient
from openra_rl_training.training.agent_rollout import _generate_scenario_map


async def test():
    kwargs = _generate_scenario_map("scenarios/tempo/sprint-lite.yaml", ep_id=99, _ep="DBG")
    for k in ["terrain_png", "bounds_x", "bounds_y", "full_map_width", "full_map_height"]:
        kwargs.pop(k, None)

    # Print building positions from scenario
    print("Scenario actors:")
    for a in kwargs.get("actors", []):
        print(f"  owner={a.get('owner')} type={a.get('type')} pos={a.get('position')}")

    env = OpenRAMCPClient("http://localhost:8000", message_timeout_s=60.0)
    async with env:
        await env.reset(**kwargs)
        r = await env.call_tool("advance", ticks=1)
        state = await env.call_tool("get_game_state")
        units = state.get("units_summary", [])
        for u in units:
            cx, cy = u.get("cell_x", 0), u.get("cell_y", 0)
            print(f"Unit {u['id']} {u['type']} at ({cx},{cy})")

        # Move ALL units toward building at ~(40,8)
        for u in units:
            await env.call_tool("move_units", unit_ids=str(u["id"]), target_x=40, target_y=8)

        # Advance and check for buildings
        for i in range(10):
            r = await env.call_tool("advance", ticks=500)
            tick = r.get("tick", 0)
            ebs = r.get("enemy_buildings_summary", [])
            expl = r.get("explored_percent", 0)
            n_ebs = len(ebs) if isinstance(ebs, list) else 0
            print(f"  [{i+1}] tick={tick} enemy_bldgs={n_ebs} explored={expl:.1f}%")
            if n_ebs > 0:
                print(f"  FOUND: {ebs}")
                break

        # Final check via get_game_state
        gs = await env.call_tool("get_game_state")
        eb2 = gs.get("enemy_buildings_summary", [])
        veb = gs.get("visible_enemy_buildings", [])
        print(f"\nFinal state: enemy_bldgs_summary={len(eb2)}, visible_enemy_bldgs={len(veb)}")
        if eb2:
            for b in eb2:
                print(f"  {b}")
        if veb:
            for b in veb:
                print(f"  visible: {b}")


if __name__ == "__main__":
    asyncio.run(test())
