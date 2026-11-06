"""
Spiral tower next to the arena's hangar (north) side.

Run inside the Unreal Editor (Output Log -> Cmd), after build_demo_arena.py:
    py "E:/Unreal Projects/Game_Template/Scripts/build_demo_tower.py"

- 80m square-spiral ramp tower (8 laps, 10m per lap) wrapped around a solid core,
  with an observation deck + beacon on top that overhangs toward the station.
- A sky-bridge from the 30m landing down onto the station roof, plus railings
  around the roof skylight (you can walk the skylight beams).
- Re-runnable: actors are tagged "ArenaTower" and replaced on each run, and the
  build is one undo transaction. Rebuilding the arena does not touch the tower.
"""

import importlib
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_demo_arena as arena  # noqa: E402

importlib.reload(arena)

TAG = "ArenaTower"
FOLDER = "Tower"

TX, TY = 8400, 4800   # tower centre, arena-local (north of the hangar wall, clear of the door)
CORE = 800            # core half-width
OUTER = 1800          # outer half-width (walkway = 1000 wide)
LAP_RISE = 1000       # height gained per lap
LAPS = 8
TOP = LAP_RISE * LAPS
DECK_T = 50
BRIDGE_LAP = 3        # sky-bridge leaves the 30m landing
BRIDGE_Y = (-1700, -900)


def find_arena_origin(b):
    for a in b.actor_sub.get_all_level_actors():
        if a.actor_has_tag(arena.TAG) and a.get_actor_label().startswith("GroundDeck"):
            origin, extent = a.get_actor_bounds(False)
            return origin.x, origin.y, origin.z + extent.z
    raise RuntimeError("Arena not found - run build_demo_arena.py first.")


def slab_between(b, p0, p1, width, thickness, mat, folder, label):
    """Box whose top-surface centre line runs from p0 to p1 (arena-local x, y, z)."""
    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    horiz = math.hypot(dx, dy)
    length = math.hypot(horiz, dz)
    yaw = math.atan2(dy, dx)
    pitch = math.atan2(dz, horiz)
    fwd = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
    right = (-math.sin(yaw), math.cos(yaw), 0.0)
    up = (-math.sin(pitch) * math.cos(yaw), -math.sin(pitch) * math.sin(yaw), math.cos(pitch))

    bmin, bmax = b.bounds[b.cube.get_name()]
    sx = length / (bmax.x - bmin.x)
    sy = width / (bmax.y - bmin.y)
    sz = thickness / (bmax.z - bmin.z)
    lc = ((bmin.x + bmax.x) / 2.0 * sx, (bmin.y + bmax.y) / 2.0 * sy, (bmin.z + bmax.z) / 2.0 * sz)
    centre = [(p0[i] + p1[i]) / 2.0 - up[i] * thickness / 2.0 for i in range(3)]
    loc = [centre[i] - (fwd[i] * lc[0] + right[i] * lc[1] + up[i] * lc[2]) for i in range(3)]

    rot = unreal.Rotator(roll=0.0, pitch=math.degrees(pitch), yaw=math.degrees(yaw))
    vloc = unreal.Vector(b.ox + loc[0], b.oy + loc[1], b.oz + loc[2])
    actor = b.actor_sub.spawn_actor_from_object(b.cube, vloc, rot)
    actor.set_actor_scale3d(unreal.Vector(sx, sy, sz))
    actor.set_actor_rotation(rot, False)
    actor.set_actor_location(vloc, False, False)
    actor.static_mesh_component.set_material(0, b.mats[mat])
    b._tag(actor, folder, label)
    return actor


def sloped_rail(b, p0, p1, folder):
    h = arena.RAIL_H
    slab_between(b, (p0[0], p0[1], p0[2] + h), (p1[0], p1[1], p1[2] + h),
                 arena.RAIL_T, h, "accent", folder, "Rail")


def build_tower(b):
    C, O = CORE, OUTER
    F = FOLDER
    T = lambda x, y: (TX + x, TY + y)  # tower-local -> arena-local

    # plaza joining the arena apron
    b.box(6400, TY - 2600, -arena.SLAB_T, TX + 2600, TY + 2600, 0, "floor", F, "Plaza")

    # core, corner pillars, beacon
    b.box(TX - C, TY - C, 0, TX + C, TY + C, TOP, "wall", F, "Core")
    for sx_ in (-1, 1):
        for sy_ in (-1, 1):
            px, py = T(sx_ * O, sy_ * O)
            b.cylinder(px, py, 0, TOP + 800, 300, "accent", F, "Pillar")
    b.cylinder(TX, TY, TOP, TOP + 120, 1200, "dark", F, "BeaconBase")
    b.cylinder(TX, TY, TOP + 120, TOP + 1800, 400, "accent", F, "Beacon")
    b.light(TX, TY, TOP + 2000, intensity=400.0, radius=8000.0, color=(0.4, 0.7, 1.0), folder=F)

    # square spiral: corner landings (flat) and side ramps, going A -> B -> C -> D -> A
    corners = {  # tower-local rect, outer edges for rails: ("x", X) = edge at X, ("y", Y) = edge at Y
        "A": ((-O, -O, -C, -C), [("y", -O), ("x", -O)]),
        "B": ((-O, C, -C, O), [("x", -O), ("y", O)]),
        "C": ((C, C, O, O), [("y", O), ("x", O)]),
        "D": ((C, -O, O, -C), [("x", O), ("y", -O)]),
    }
    # side: start centre-line point, end point, rail line (start, end) on the outer edge
    mid = (O + C) / 2.0
    sides = [
        ((-mid, -C), (-mid, C), ((-O, -C), (-O, C))),   # A->B along -X face
        ((-C, mid), (C, mid), ((-C, O), (C, O))),        # B->C along +Y face
        ((mid, C), (mid, -C), ((O, C), (O, -C))),        # C->D along +X face
        ((C, -mid), (-C, -mid), ((C, -O), (-C, -O))),    # D->A along -Y face
    ]
    step = LAP_RISE / 4.0
    for lap in range(LAPS):
        z0 = lap * LAP_RISE
        lf = "{}/Lap{:02d}".format(F, lap + 1)
        for i, key in enumerate("ABCD"):
            zc = z0 + step * i
            (x0, y0, x1, y1), edges = corners[key]
            if not (key == "A" and lap == 0):  # lap 1 corner A is the plaza
                bottom = 0 if lap == 0 else zc - DECK_T  # ground-floor landings are solid
                b.box(TX + x0, TY + y0, bottom, TX + x1, TY + y1, zc, "dark", lf, "Landing")
                for axis, edge in edges:
                    if axis == "x":
                        gaps = []
                        if key == "A" and lap == BRIDGE_LAP:
                            gaps = [(TY + BRIDGE_Y[0], TY + BRIDGE_Y[1])]
                        arena.rail(b, "y", TX + edge, TY + y0, TY + y1, zc, gaps, lf)
                    else:
                        arena.rail(b, "x", TY + edge, TX + x0, TX + x1, zc, [], lf)
            # side ramp to the next corner
            (s0, s1, (r0, r1)) = sides[i]
            za, zb = zc, zc + step
            p0 = (TX + s0[0], TY + s0[1], za)
            p1 = (TX + s1[0], TY + s1[1], zb)
            slab_between(b, p0, p1, O - C, DECK_T, "floor", lf, "Ramp")
            sloped_rail(b, (TX + r0[0], TY + r0[1], za), (TX + r1[0], TY + r1[1], zb), lf)

    # top observation deck: over corner A / side A->B / corner B, overhanging toward the station
    deck = (TX - 3400, TY - O, TX - C, TY + O)
    b.box(deck[0], deck[1], TOP - DECK_T, deck[2], deck[3], TOP, "floor", F, "TopDeck")
    df = F + "/TopDeck"
    arena.rail(b, "y", deck[0], deck[1], deck[3], TOP, [], df)
    arena.rail(b, "x", deck[1], deck[0], deck[2], TOP, [], df)
    arena.rail(b, "x", deck[3], deck[0], deck[2], TOP, [], df)
    arena.rail(b, "y", deck[2], TY + C, TY + O, TOP, [], df)    # drop to the lap below
    arena.rail(b, "y", TX + C, TY - C, TY + C, TOP, [], df)     # core top, +X edge
    arena.rail(b, "x", TY + C, TX - C, TX + C, TOP, [], df)     # core top, +Y edge

    # sky-bridge: 30m landing (corner A, lap 4) down onto the station roof
    zb = BRIDGE_LAP * LAP_RISE
    by = TY + (BRIDGE_Y[0] + BRIDGE_Y[1]) / 2.0
    bw = BRIDGE_Y[1] - BRIDGE_Y[0]
    start = (TX - O, by, zb)
    end = (4900, by, arena.ROOF)
    bf = F + "/SkyBridge"
    slab_between(b, start, end, bw, DECK_T, "floor", bf, "SkyBridge")
    for y in (by - bw / 2.0, by + bw / 2.0):
        sloped_rail(b, (start[0], y, start[2]), (end[0], y, end[2]), bf)

    # roof: railings around the skylight, leaving the beams walkable
    beams = [(c - 100, c + 100) for c in (-1100, 1100)]
    arena.rail_hole(b, arena.ATRIUM, arena.ROOF, F + "/Roof",
                    gaps={"xmin": beams, "xmax": beams, "ymin": beams, "ymax": beams})


def expected_points():
    """(label, arena-local x, y, expected walk height) for verification traces."""
    pts = []
    mid = (OUTER + CORE) / 2.0
    for lap in (0, 3, 7):
        z0 = lap * LAP_RISE
        pts.append(("lap{} side A->B mid".format(lap + 1), TX - mid, TY, z0 + 125))
        pts.append(("lap{} corner C".format(lap + 1), TX + mid, TY + mid, z0 + 500))
        pts.append(("lap{} side D->A mid".format(lap + 1), TX, TY - mid, z0 + 875))
    pts.append(("top deck", TX - 2600, TY, TOP))
    pts.append(("sky-bridge mid", (TX - OUTER + 4900) / 2.0, TY - 1300,
                (BRIDGE_LAP * LAP_RISE + arena.ROOF) / 2.0))
    return pts


def main():
    b = arena.Builder()
    b.tag = TAG
    with unreal.ScopedEditorTransaction("Build Arena Tower"):
        removed = 0
        for a in b.actor_sub.get_all_level_actors():
            if a.actor_has_tag(TAG):
                b.actor_sub.destroy_actor(a)
                removed += 1
        b.ox, b.oy, b.oz = find_arena_origin(b)
        build_tower(b)
    unreal.log("[Tower] Removed {} old actors, spawned {} actors. Top deck at {:.0f}m.".format(
        removed, b.count, TOP / 100.0))


if __name__ == "__main__":
    main()
