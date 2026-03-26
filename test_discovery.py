#!/usr/bin/env python3
"""Integration test: verify buildings are discoverable in training scenario."""
import asyncio
import sys
sys.path.insert(0, "/home/ubuntu/OpenRA-RL-Training")

from openra_env.mcp_ws_client import OpenRAMCPClient
from openra_rl_training.training.agent_rollout import _generate_scenario_map


async def test():
    kwargs = _generate_scenario_map("scenarios/tempo/sprint-lite.yaml", ep_id=0, _ep="T")
    for k in ["terrain_png", "bounds_x", "bounds_y", "full_map_width", "full_map_height"]:
        kwargs.pop(k, None)

    print(f"bot_type: {kwargs.get('bot_type')}")
    print(f"n_enemy_buildings: {kwargs.get('n_enemy_buildings')}")

    env = OpenRAMCPClient("http://localhost:8000", message_timeout_s=60.0)
    async with env:
        await env.reset(**kwargs)
        r0 = await env.call_tool("advance", ticks=1)

        gs = await env.call_tool("get_game_state")
        ebs = gs.get("enemy_buildings_summary", [])
        veb = gs.get("visible_enemy_buildings", 0)
        units = gs.get("units_summary", [])
        print(f"\nInitial: {len(units)} units, enemy_bldgs={len(ebs) if isinstance(ebs, list) else ebs}, visible={veb}")
        for u in units:
            utype = u.get("type", "?")
            cx, cy = u.get("cell_x", 0), u.get("cell_y", 0)
            print(f"  Unit {u['id']} {utype} at ({cx},{cy})")

        # Move all 3 units to 3 different building locations
        targets = [(40, 8), (60, 38), (18, 30)]
        for i, u in enumerate(units):
            t = targets[i % len(targets)]
            uid = u["id"]
            utype = u.get("type", "?")
            await env.call_tool("move_units", unit_ids=str(uid), target_x=t[0], target_y=t[1])
            print(f"  Moved {uid} ({utype}) toward {t}")

        # Advance in chunks, check for buildings each time
        total_found = set()
        for chunk in range(20):
            r = await env.call_tool("advance", ticks=500)
            tick = r.get("tick", 0)
            adv_ebs = r.get("enemy_buildings_summary", [])
            expl = r.get("explored_percent", 0)

            if isinstance(adv_ebs, list):
                for b in adv_ebs:
                    bid = b.get("id", 0)
                    if bid and bid not in total_found:
                        total_found.add(bid)
                        btype = b.get("type", "?")
                        bx, by = b.get("cell_x", 0), b.get("cell_y", 0)
                        print(f"  NEW BUILDING at tick {tick}: {btype} id={bid} at ({bx},{by})")

            n_adv = len(adv_ebs) if isinstance(adv_ebs, list) else 0
            print(f"  [{chunk+1:2d}] tick={tick:5d} expl={expl:5.1f}% visible_bldgs={n_adv} total_found={len(total_found)}")

            if len(total_found) >= 3:
                print(f"\n  ALL 3 BUILDINGS FOUND at tick {tick}!")
                break

        # Final state
        gs_final = await env.call_tool("get_game_state")
        gs_ebs = gs_final.get("enemy_buildings_summary", [])
        gs_n = len(gs_ebs) if isinstance(gs_ebs, list) else 0
        print(f"\nFinal: total_found={len(total_found)}, gs_enemy_bldgs={gs_n}")
        if isinstance(gs_ebs, list):
            for b in gs_ebs:
                print(f"  {b}")

        if len(total_found) == 0:
            print("\n*** FAIL: No buildings discovered! ***")
            return False
        elif len(total_found) < 3:
            print(f"\n*** PARTIAL: Found {len(total_found)}/3 buildings ***")
            return True
        else:
            print("\n*** PASS: All 3 buildings discovered ***")
            return True


if __name__ == "__main__":
    result = asyncio.run(test())
    sys.exit(0 if result else 1)
