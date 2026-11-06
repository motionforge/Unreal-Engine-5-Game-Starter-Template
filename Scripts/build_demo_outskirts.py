"""
Outskirts around the arena: a boundary wall along the landscape edges and two
flat-roofed outbuildings.

Run inside the Unreal Editor (Output Log -> Cmd), after build_demo_arena.py:
    py "E:/Unreal Projects/Game_Template/Scripts/build_demo_outskirts.py"

- Boundary wall: 15m wall inset from the landscape edge, with buttresses, a blue
  cap strip and corner towers.
- Depot (east, with a ramp up to its roof) and Comms building (west, with a mast
  and dish on the roof). The south side is the grand entrance (build_demo_entrance.py).
- Re-runnable: actors are tagged "ArenaOutskirts" and replaced on each run, and the
  build is one undo transaction. Rebuilding the arena or tower does not touch them.
"""

import importlib
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_demo_arena as arena  # noqa: E402
import build_demo_tower as tower  # noqa: E402

importlib.reload(arena)
importlib.reload(tower)

TAG = "ArenaOutskirts"
WALL_INSET = 300      # gap between the landscape edge and the boundary wall
WALL_T = 200
WALL_H = 1500
BUTTRESS_STEP = 3000
BLD_T = 60            # outbuilding wall thickness
PARAPET_H = 80
DOOR_H = 300


def boundary_wall(b):
    lo, hi = arena.find_landscape_bounds(b)
    if lo is None:
        unreal.log_warning("[Outskirts] No landscape found - skipping boundary wall.")
        return
    x0, x1 = lo.x - b.ox + WALL_INSET, hi.x - b.ox - WALL_INSET
    y0, y1 = lo.y - b.oy + WALL_INSET, hi.y - b.oy - WALL_INSET
    F = "Outskirts/BoundaryWall"
    base = -150  # sink below the (flat) ground
    walls = [
        (x0, y0, x0 + WALL_T, y1),   # south
        (x1 - WALL_T, y0, x1, y1),   # north
        (x0 + WALL_T, y0, x1 - WALL_T, y0 + WALL_T),  # west
        (x0 + WALL_T, y1 - WALL_T, x1 - WALL_T, y1),  # east
    ]
    for wx0, wy0, wx1, wy1 in walls:
        b.box(wx0, wy0, base, wx1, wy1, WALL_H, "wall", F, "BoundaryWall")
        b.box(wx0 - 30, wy0 - 30, WALL_H, wx1 + 30, wy1 + 30, WALL_H + 40, "accent", F, "WallCap")

    # buttresses on the inner face
    def spans(a0, a1):
        n = max(1, int((a1 - a0) // BUTTRESS_STEP))
        step = (a1 - a0) / n
        return [a0 + step * i for i in range(1, n)]
    for y in spans(y0, y1):
        b.box(x0 + WALL_T, y - 200, base, x0 + WALL_T + 300, y + 200, WALL_H + 150, "dark", F, "Buttress")
        b.box(x1 - WALL_T - 300, y - 200, base, x1 - WALL_T, y + 200, WALL_H + 150, "dark", F, "Buttress")
    for x in spans(x0, x1):
        b.box(x - 200, y0 + WALL_T, base, x + 200, y0 + WALL_T + 300, WALL_H + 150, "dark", F, "Buttress")
        b.box(x - 200, y1 - WALL_T - 300, base, x + 200, y1 - WALL_T, WALL_H + 150, "dark", F, "Buttress")

    # corner towers
    for cx in (x0 + WALL_T / 2, x1 - WALL_T / 2):
        for cy in (y0 + WALL_T / 2, y1 - WALL_T / 2):
            b.cylinder(cx, cy, base, WALL_H + 700, 1400, "dark", F, "CornerTower")
            b.cylinder(cx, cy, WALL_H + 700, WALL_H + 760, 1500, "accent", F, "CornerTowerCap")
    unreal.log("[Outskirts] Boundary wall: local X {:.0f}..{:.0f}, Y {:.0f}..{:.0f}".format(x0, x1, y0, y1))


def building(b, name, rect, h, openings, parapet_gaps=None):
    """Flat-roofed box building. rect=(x0,y0,x1,y1) arena-local, floor at 0.
    openings / parapet_gaps: side -> list of (a0, a1, z0, z1) / (a0, a1) along that wall.
    Sides: xmin / xmax (walls running along Y), ymin / ymax (walls running along X)."""
    x0, y0, x1, y1 = rect
    t = BLD_T
    F = "Outskirts/" + name
    parapet_gaps = parapet_gaps or {}

    b.box(x0 - 150, y0 - 150, -60, x1 + 150, y1 + 150, 0, "floor", F, "Pad")
    arena.wall(b, "y", x0, x0 + t, y0, y1, 0, h, openings.get("xmin", []), F, label="Wall")
    arena.wall(b, "y", x1 - t, x1, y0, y1, 0, h, openings.get("xmax", []), F, label="Wall")
    arena.wall(b, "x", y0, y0 + t, x0 + t, x1 - t, 0, h, openings.get("ymin", []), F, label="Wall")
    arena.wall(b, "x", y1 - t, y1, x0 + t, x1 - t, 0, h, openings.get("ymax", []), F, label="Wall")
    roof = h + 50
    b.box(x0, y0, h, x1, y1, roof, "dark", F, "Roof")

    def gaps(side):
        return [(a0, a1, roof, roof + PARAPET_H) for a0, a1 in parapet_gaps.get(side, [])]
    arena.wall(b, "y", x0, x0 + t, y0, y1, roof, roof + PARAPET_H, gaps("xmin"), F, "accent", "Parapet")
    arena.wall(b, "y", x1 - t, x1, y0, y1, roof, roof + PARAPET_H, gaps("xmax"), F, "accent", "Parapet")
    arena.wall(b, "x", y0, y0 + t, x0 + t, x1 - t, roof, roof + PARAPET_H, gaps("ymin"), F, "accent", "Parapet")
    arena.wall(b, "x", y1 - t, y1, x0 + t, x1 - t, roof, roof + PARAPET_H, gaps("ymax"), F, "accent", "Parapet")
    b.light((x0 + x1) / 2.0, (y0 + y1) / 2.0, h - 120, intensity=25.0, radius=2500.0, folder=F)
    return F, roof


def door(a, w):
    return (a - w / 2.0, a + w / 2.0, 0, DOOR_H)


def window(a, w, z0=130, z1=330):
    return (a - w / 2.0, a + w / 2.0, z0, z1)


def outbuildings(b):
    # (the south Checkpoint was removed to make room for the grand entrance - build_demo_entrance.py)

    # --- Depot: east (5000 x 3500), big loading door, ramp up to the roof
    F, roof = building(b, "Depot", (-4500, 9000, 500, 12500), 700, {
        "ymin": [(-3000, -1000, 0, 500), door(-300, 400)],
        "xmax": [door(11250, 500)],
        "xmin": [window(10000, 800, 200, 450), window(11500, 800, 200, 450)],
        "ymax": [window(-3800, 800, 200, 450)],
    }, parapet_gaps={"ymax": [(-1000, 500 - BLD_T)]})
    for x, y, s in [(-4000, 9600, 300), (-3600, 9600, 200), (-4000, 10000, 200), (-500, 12000, 300),
                    (-900, 12000, 200), (-2200, 11400, 400), (-1700, 11400, 250)]:
        b.box(x - s / 2.0, y - s / 2.0, 0, x + s / 2.0, y + s / 2.0, s, "wall", F, "Crate")
    # roof access: ramp along the back wall + landing level with the roof
    b.ramp((-3250, 12500, -1000, 12900), 0, roof, +1, folder=F, label="RoofRamp")
    b.box(-1000, 12500, 0, 500, 12900, roof, "dark", F, "RoofLanding")
    arena.rail(b, "x", 12890, -1000, 500, roof, [], F)
    arena.rail(b, "y", 490, 12500, 12900, roof, [], F)

    # --- Comms: west (3000 x 3000), mast + dish on the roof
    F, roof = building(b, "Comms", (500, -12000, 3500, -9000), 500, {
        "ymax": [door(2000, 600), window(1100, 600), window(2900, 600)],
        "xmin": [door(-9500, 600)],
        "xmax": [window(-11200, 700), window(-9800, 700)],
        "ymin": [window(2000, 1200)],
    })
    b.box(800, -11700, 0, 1400, -11000, 120, "accent", F, "ServerRack")
    b.box(800, -10800, 0, 1400, -10100, 120, "accent", F, "ServerRack")
    b.cylinder(2700, -10900, roof, roof + 3000, 160, "accent", F, "Mast")
    b.cylinder(2700, -10900, roof + 2200, roof + 2260, 1000, "dark", F, "Dish")
    b.box(1000, -9700, roof, 1800, -9300, roof + 180, "wall", F, "RoofUnit")


def main():
    b = arena.Builder()
    b.tag = TAG
    with unreal.ScopedEditorTransaction("Build Arena Outskirts"):
        removed = 0
        for a in b.actor_sub.get_all_level_actors():
            if a.actor_has_tag(TAG):
                b.actor_sub.destroy_actor(a)
                removed += 1
        b.ox, b.oy, b.oz = tower.find_arena_origin(b)
        boundary_wall(b)
        outbuildings(b)
    unreal.log("[Outskirts] Removed {} old actors, spawned {} actors.".format(removed, b.count))


if __name__ == "__main__":
    main()
