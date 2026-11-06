"""
Grand entrance on the arena's south side, below the Atlas statue.

Run inside the Unreal Editor (Output Log -> Cmd), after build_demo_arena.py:
    py "E:/Unreal Projects/Game_Template/Scripts/build_demo_entrance.py"

Walking in from the boundary wall:
- Gateway: two 17m pylons and a lintel on a stepped platform (3 steps up, 3 down).
- Processional avenue: 20m wide, kerbed, lined with lamp pillars, ending between
  two obelisks on stepped plinths.
- Forecourt plaza (46m x 92m) with an inlaid axis strip.
- A 26m-wide central grand stairway flanked by twin staircases (all 20 steps of
  40cm) up to a 76m-wide balcony at F2 height, with inlaid rings and an upper
  doorway into the F2 corridor.
- Portico under the balcony, reached by the walkways either side of the central
  stairway: columns framing the stair top, the framed 22m x 7.5m main doorway, and
  two colossal columns holding up the statue pedestal's overhang.

The doorway openings live in build_demo_arena.py (SOUTH_DOOR / SOUTH_UPPER_DOOR);
this script rebuilds just the arena's south wall so it matches them.
Re-runnable: entrance actors are tagged "ArenaEntrance" and replaced on each run,
and the build is one undo transaction.
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

TAG = "ArenaEntrance"
F = "Entrance"

FACADE = -arena.HALF          # outer face of the south wall
DECK = FACADE - 400           # edge of the arena ground deck
L2 = arena.LEVELS[1]          # balcony / F2 height

# balcony + portico (under it), and the stair landings at either end
BAL_X = -8000                 # front edge of the balcony
PORTICO_Y = 2400              # portico half-width (between the stair blocks)
LANDING_Y = 3800              # outer edge of the stair landings
CENTRE_Y = 1300               # central stairway half-width (walkways to the portico either side)
BAL_T = 50

# grand staircases: rise toward +X onto the landings
STEPS = 20
RISE = L2 / STEPS             # 40cm - under the character's 45cm max step height
TREAD = 120
STAIR_X0 = BAL_X - STEPS * TREAD

PLAZA = (-11000, -4600, DECK, 4600)
AVENUE = (-13800, -1000, -11000, 1000)
GATE_X = (-14800, -13800)     # stepped gate platform incl. both flights
GATE_Y = 2000
GATE_RISE, GATE_TREAD, GATE_STEPS = 40, 100, 3


def portico(b):
    P = F + "/Portico"
    door = arena.SOUTH_DOOR
    up = arena.SOUTH_UPPER_DOOR

    # balcony slab (portico roof) spanning both landings
    b.box(BAL_X, -LANDING_Y, L2 - BAL_T, FACADE, LANDING_Y, L2, "floor", P, "Balcony")
    b.box(BAL_X - 20, -PORTICO_Y, L2 - BAL_T - 80, BAL_X + 30, PORTICO_Y, L2 - BAL_T, "accent", P, "Fascia")
    arena.rail(b, "y", BAL_X + 10, -PORTICO_Y, PORTICO_Y, L2, [(-CENTRE_Y, CENTRE_Y)], P)
    for s in (-1, 1):
        arena.rail(b, "x", s * (LANDING_Y - 10), BAL_X, FACADE, L2, [], P)

    # front columns framing the top of the central stairway (walkways stay clear)
    for y in (-CENTRE_Y - 180, CENTRE_Y + 180):
        b.box(BAL_X + 40, y - 220, 0, BAL_X + 480, y + 220, 120, "dark", P, "ColumnBase")
        b.cylinder(BAL_X + 260, y, 120, L2 - BAL_T - 80, 320, "wall", P, "Column")
        b.box(BAL_X + 60, y - 200, L2 - BAL_T - 160, BAL_X + 460, y + 200, L2 - BAL_T - 80, "accent", P, "Capital")

    # main doorway frame
    for s in (-1, 1):
        b.box(FACADE - 200, s * door[1], 0, FACADE, s * (door[1] + 250), door[3], "dark", P, "DoorJamb")
        b.box(FACADE - 120, s * (door[1] + 250), 0, FACADE, s * (door[1] + 330), door[3], "accent", P, "DoorTrim")
    # upper doorway frame + emblem
    for s in (-1, 1):
        b.box(FACADE - 150, s * up[1], up[2], FACADE, s * (up[1] + 200), up[3] + 100, "dark", P, "UpperJamb")
    b.box(FACADE - 150, -up[1] - 200, up[3], FACADE, up[1] + 200, up[3] + 100, "dark", P, "UpperLintel")
    b.box(FACADE - 60, -900, up[3] + 160, FACADE, 900, up[3] + 240, "accent", P, "Emblem")
    # inlaid rings on the balcony at the head of the central stairway
    rx = (BAL_X + FACADE) / 2.0 - 100
    b.cylinder(rx, 0, L2, L2 + 2, 1800, "accent", P, "Ring")
    b.cylinder(rx, 0, L2, L2 + 3, 1500, "dark", P, "RingInner")
    b.cylinder(rx, 0, L2, L2 + 4, 400, "accent", P, "RingCentre")

    # colossal columns rising to the statue pedestal's overhang
    for s in (-1, 1):
        y = s * 1750
        b.box(FACADE - 600, y - 320, 0, FACADE, y + 320, 200, "dark", P, "GiantBase")
        b.cylinder(FACADE - 280, y, 200, arena.ROOF - 100, 460, "wall", P, "GiantColumn")
        b.box(FACADE - 560, y - 300, arena.ROOF - 100, FACADE, y + 300, arena.ROOF, "accent", P, "GiantCapital")

    b.light(BAL_X + 1000, -1200, L2 - 250, intensity=60.0, radius=3000.0, folder=P)
    b.light(BAL_X + 1000, 1200, L2 - 250, intensity=60.0, radius=3000.0, folder=P)
    b.light(FACADE - 600, 0, up[3] + 300, intensity=80.0, radius=3500.0, color=(0.4, 0.7, 1.0), folder=P)


def flight(b, y0, y1, S):
    """20 solid steps from the plaza up to the balcony edge, with balustrades and lamp newels."""
    for i in range(STEPS):
        x = STAIR_X0 + i * TREAD
        b.box(x, y0, 0, x + TREAD, y1, RISE * (i + 1), "floor" if i % 2 else "wall", S, "Step")
    for y in (y0 + 40, y1 - 40):
        tower.slab_between(b, (STAIR_X0, y, arena.RAIL_H + 40), (BAL_X, y, L2 + arena.RAIL_H),
                           80, 260, "dark", S, "Balustrade")
        b.box(STAIR_X0 - 300, y - 120, 0, STAIR_X0, y + 120, 300, "dark", S, "Newel")
        b.cylinder(STAIR_X0 - 150, y, 300, 420, 200, "accent", S, "NewelLamp")
    b.light(STAIR_X0 - 150, (y0 + y1) / 2.0, 450, intensity=40.0, radius=2500.0,
            color=(0.4, 0.7, 1.0), folder=S)


def staircases(b):
    flight(b, -CENTRE_Y, CENTRE_Y, F + "/StairCentre")
    for s in (-1, 1):
        S = F + ("/StairWest" if s < 0 else "/StairEast")
        y0, y1 = sorted((s * PORTICO_Y, s * LANDING_Y))
        flight(b, y0, y1, S)
        # solid landing block under the balcony end
        b.box(BAL_X, y0, 0, FACADE, y1, L2 - BAL_T, "dark", S, "LandingBlock")
        b.box(BAL_X - 10, y0 - 10, L2 - BAL_T - 200, FACADE, y1 + 10, L2 - BAL_T - 140, "accent", S, "LandingBand")


def plaza(b):
    P = F + "/Plaza"
    x0, y0, x1, y1 = PLAZA
    b.box(x0, y0, -30, x1, y1, 0, "floor", P, "Plaza")
    border = 300
    b.box(x0, y0, 0, x0 + border, y1, 2, "dark", P, "Border")
    b.box(x0 + border, y0, 0, x1, y0 + border, 2, "dark", P, "Border")
    b.box(x0 + border, y1 - border, 0, x1, y1, 2, "dark", P, "Border")
    # inlaid axis strip leading to the foot of the central stairway
    b.box(x0 + border, -150, 0, STAIR_X0 - 300, 150, 1, "dark", P, "AxisStrip")
    # obelisks on stepped plinths where the avenue meets the plaza
    for s in (-1, 1):
        ox, oy = x0 - 300, s * 2100
        for k, half in enumerate((500, 380, 260)):
            b.box(ox - half, oy - half, 60 * k, ox + half, oy + half, 60 * (k + 1), "dark", P, "Plinth")
        b.box(ox - 180, oy - 180, 180, ox + 180, oy + 180, 2600, "wall", P, "Obelisk")
        b.box(ox - 130, oy - 130, 2600, ox + 130, oy + 130, 3000, "wall", P, "Obelisk")
        b.box(ox - 70, oy - 70, 3000, ox + 70, oy + 70, 3150, "accent", P, "ObeliskTip")
        b.light(ox + 700, oy, 400, intensity=40.0, radius=2000.0, color=(0.4, 0.7, 1.0), folder=P)


def avenue(b):
    A = F + "/Avenue"
    x0, y0, x1, y1 = AVENUE
    b.box(x0, y0, -30, x1, y1, 0, "floor", A, "Avenue")
    for s in (-1, 1):
        b.box(x0, s * y1, 0, x1, s * (y1 + 150), 15, "dark", A, "Kerb")
    for x in (-13400, -12750, -12100):
        for s in (-1, 1):
            y = s * 1700
            b.box(x - 220, y - 220, 0, x + 220, y + 220, 80, "dark", A, "PillarBase")
            b.cylinder(x, y, 80, 1100, 340, "dark", A, "Pillar")
            b.cylinder(x, y, 1100, 1180, 460, "accent", A, "PillarCap")
            b.light(x, y, 1300, intensity=30.0, radius=1600.0, color=(0.4, 0.7, 1.0), folder=A)


def gateway(b):
    G = F + "/Gateway"
    gx0, gx1 = GATE_X
    top = GATE_RISE * (GATE_STEPS + 1)  # 3 steps up onto it, 3 down
    run = GATE_STEPS * GATE_TREAD
    for i in range(GATE_STEPS):  # up from outside, down toward the avenue
        b.box(gx0 + i * GATE_TREAD, -GATE_Y, 0, gx0 + (i + 1) * GATE_TREAD, GATE_Y, GATE_RISE * (i + 1),
              "wall", G, "Step")
        b.box(gx1 - (i + 1) * GATE_TREAD, -GATE_Y, 0, gx1 - i * GATE_TREAD, GATE_Y, GATE_RISE * (i + 1),
              "wall", G, "Step")
    px0, px1 = gx0 + run, gx1 - run
    b.box(px0, -GATE_Y, 0, px1, GATE_Y, top, "dark", G, "GatePlatform")
    # pylons + lintel
    for s in (-1, 1):
        b.box(px0 + 50, s * 1000, top, px1 - 50, s * 1800, 1900, "wall", G, "Pylon")
        b.box(px0 + 30, s * 1820, top, px1 - 30, s * 1780, 1900, "accent", G, "PylonTrim")
    b.box(px0, -1900, 1900, px1, 1900, 2200, "dark", G, "Lintel")
    b.box(px0 - 20, -1920, 2120, px1 + 20, 1920, 2160, "accent", G, "LintelBand")
    b.light((px0 + px1) / 2.0, 0, 1600, intensity=60.0, radius=3000.0, color=(0.4, 0.7, 1.0), folder=G)


def rebuild_south_wall(b):
    """Swap the arena's south wall for one with the grand doorway openings."""
    old = [a for a in b.actor_sub.get_all_level_actors()
           if a.actor_has_tag(arena.TAG) and a.get_actor_label().startswith("OuterWall_S_")]
    for a in old:
        b.actor_sub.destroy_actor(a)
    b.tag = arena.TAG
    arena.south_wall(b)
    b.tag = TAG
    return len(old)


def expected_points():
    """(label, arena-local x, y, expected walk height) for verification traces."""
    mid = STEPS // 2
    return [
        ("gateway step 3", GATE_X[0] + 2.5 * GATE_TREAD, 0, GATE_RISE * 3),
        ("gateway platform", GATE_X[1] - GATE_STEPS * GATE_TREAD - 20, 0, GATE_RISE * (GATE_STEPS + 1)),
        ("avenue", -12850, 0, 0),
        ("plaza", -10000, -1500, 0),
        ("centre stair step 6", STAIR_X0 + 5.5 * TREAD, 0, RISE * 6),
        ("centre stair top step", BAL_X - 60, 600, L2),
        ("walkway to portico", -8600, 1850, 0),
        ("portico, beside door", -6700, 1900, 0),
        ("east stair step {}".format(mid + 1), STAIR_X0 + (mid + 0.5) * TREAD, 3100, RISE * (mid + 1)),
        ("west stair top step", BAL_X - 60, -3100, L2),
        ("east landing", -7000, 3100, L2),
        ("balcony ring", (BAL_X + FACADE) / 2.0 - 100, 0, L2 + 4),
        ("balcony", -6500, 1200, L2),
    ]


def main():
    b = arena.Builder()
    b.tag = TAG
    with unreal.ScopedEditorTransaction("Build Grand Entrance"):
        removed = 0
        for a in b.actor_sub.get_all_level_actors():
            if a.actor_has_tag(TAG):
                b.actor_sub.destroy_actor(a)
                removed += 1
        b.ox, b.oy, b.oz = tower.find_arena_origin(b)
        walls = rebuild_south_wall(b)
        before = b.count
        portico(b)
        staircases(b)
        plaza(b)
        avenue(b)
        gateway(b)
    unreal.log("[Entrance] Removed {} old actors, replaced {} south wall pieces, spawned {} entrance actors."
               .format(removed, walls, b.count - before))


if __name__ == "__main__":
    main()
