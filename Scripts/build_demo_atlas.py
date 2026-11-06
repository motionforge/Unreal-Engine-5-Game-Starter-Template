"""
Blocked-out colossal statue of the titan Atlas on the arena roof: kneeling on one
knee, head bowed, arms raised, holding the celestial sphere on his shoulders.

Run inside the Unreal Editor (Output Log -> Cmd), after build_demo_arena.py:
    py "E:/Unreal Projects/Game_Template/Scripts/build_demo_atlas.py"

- ~83m tall from the pedestal (top of the globe is ~112m above the ground).
- Stands on a walkable pedestal on the south half of the roof, facing the main
  entrance, with ramps up both sides of the pedestal.
- Re-runnable: actors are tagged "ArenaAtlas" and replaced on each run, and the
  build is one undo transaction.
"""

import importlib
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_demo_arena as arena  # noqa: E402
import build_demo_tower as tower  # noqa: E402

importlib.reload(arena)
importlib.reload(tower)

TAG = "ArenaAtlas"
FOLDER = "Atlas"
MESH_CHAMFER = arena.PROTO + "/Meshes/SM_ChamferCube.SM_ChamferCube"

# Statue frame: u = forward (statue faces -X, toward the main entrance),
# v = statue's left, w = up from the pedestal top.
PX, PY = -4100, 0
PED_H = 500
PZ = arena.ROOF + PED_H
PED_U = (-1700, 2400)   # pedestal overhangs the south facade a little
PED_V = 2300
K = 1.15                # overall statue scale (joint positions below are at K = 1)
BULK = 1.3              # extra thickness for limbs / torso so he reads as a titan

GLOBE_C = (0, 0, 5300)
GLOBE_R = 2000

BODY = "floor"     # light grey stone
CLOTH = "wall"
GLOBE = "accent"
BAND = "dark"
GLOBE_SLICES = 19


def S(u, v, w):
    """Statue frame (unscaled) -> arena-local."""
    return (PX - u * K, PY - v * K, PZ + w * K)


class Sculptor:
    def __init__(self, b):
        self.b = b
        self.chamfer = arena.Builder._load(MESH_CHAMFER)
        self.bounds = {}
        for m in (self.chamfer, b.cube, b.cyl):
            bb = m.get_bounding_box()
            self.bounds[m.get_name()] = (bb.min, bb.max)

    def part(self, mesh, centre, size, pitch=0.0, yaw=0.0, roll=0.0, mat=BODY, folder=FOLDER, label="Part"):
        """Place mesh with its bounds centred on `centre` (arena-local), sized along its local axes."""
        bmin, bmax = self.bounds[mesh.get_name()]
        sc = [size[0] / (bmax.x - bmin.x), size[1] / (bmax.y - bmin.y), size[2] / (bmax.z - bmin.z)]
        lc = ((bmin.x + bmax.x) / 2.0 * sc[0], (bmin.y + bmax.y) / 2.0 * sc[1], (bmin.z + bmax.z) / 2.0 * sc[2])
        p, y, r = math.radians(pitch), math.radians(yaw), math.radians(roll)
        sp, cp, sy, cy, sr, cr = math.sin(p), math.cos(p), math.sin(y), math.cos(y), math.sin(r), math.cos(r)
        ax = (cp * cy, cp * sy, sp)
        ay = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
        az = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
        loc = [centre[i] - (lc[0] * ax[i] + lc[1] * ay[i] + lc[2] * az[i]) for i in range(3)]
        b = self.b
        rot = unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw)
        vloc = unreal.Vector(b.ox + loc[0], b.oy + loc[1], b.oz + loc[2])
        actor = b.actor_sub.spawn_actor_from_object(mesh, vloc, rot)
        actor.set_actor_scale3d(unreal.Vector(*sc))
        actor.set_actor_rotation(rot, False)
        actor.set_actor_location(vloc, False, False)
        actor.static_mesh_component.set_material(0, b.mats[mat])
        b._tag(actor, folder, label)
        return actor

    def limb(self, j0, j1, width, depth, extend=0.0, mat=BODY, label="Limb", folder=FOLDER + "/Body", bulk=BULK):
        """Chamfered block running between two statue-frame joints."""
        width, depth, extend = width * K * bulk, depth * K * bulk, extend * K
        p0, p1 = S(*j0), S(*j1)
        d = [p1[i] - p0[i] for i in range(3)]
        horiz = math.hypot(d[0], d[1])
        length = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2) + extend
        yaw = math.degrees(math.atan2(d[1], d[0])) if horiz > 1e-3 else 0.0
        pitch = math.degrees(math.atan2(d[2], horiz))
        centre = [(p0[i] + p1[i]) / 2.0 for i in range(3)]
        return self.part(self.chamfer, centre, (length, width, depth), pitch, yaw, 0.0, mat, folder, label)

    def block(self, c, size, mat=BODY, label="Block", folder=FOLDER + "/Body"):
        """Axis-aligned chamfered block centred on a statue-frame point (size in u, v, w)."""
        size = [x * K * BULK for x in size]
        return self.part(self.chamfer, S(*c), size, 0, 0, 0, mat, folder, label)


def pedestal(sc):
    b = sc.b
    F = FOLDER + "/Pedestal"
    x0, x1 = PX - PED_U[1], PX - PED_U[0]
    R = arena.ROOF
    b.box(x0, PY - PED_V, R, x1, PY + PED_V, PZ, "dark", F, "Pedestal")
    b.box(x0 - 20, PY - PED_V - 20, PZ - 160, x1 + 20, PY + PED_V + 20, PZ - 100, "accent", F, "PedestalBand")
    b.box(x0 + 150, PY - PED_V + 150, PZ, x1 - 150, PY + PED_V - 150, PZ + 40, "dark", F, "PedestalTop")
    # ramps up both sides (18 degrees), arriving on the pedestal's long edges
    for side in (-1, 1):
        y_edge = PY + side * PED_V
        tower.slab_between(b, (PX - 200, y_edge + side * 1500, R), (PX - 200, y_edge, PZ),
                           1200, 50, "floor", F, "PedestalRamp")


def body(sc):
    L = sc.limb
    # --- legs: right knee down, left foot planted forward
    L((0, -500, 1300), (350, -850, 180), 620, 620, 250, label="ThighR")
    L((350, -850, 180), (-1050, -800, 170), 470, 470, 200, label="ShinR")
    L((-1000, -800, 260), (-1400, -800, 40), 380, 300, label="FootR")
    sc.block((360, -850, 230), (420, 520, 420), label="KneeR")
    L((0, 500, 1300), (1350, 950, 1400), 640, 640, 250, label="ThighL")
    L((1350, 950, 1400), (1500, 1000, 230), 480, 480, 150, label="ShinL")
    sc.block((1380, 950, 1480), (420, 480, 420), label="KneeL")
    sc.block((1690, 1000, 110), (600, 320, 220), label="FootL")

    # --- torso, leaning forward ~25 degrees under the weight
    L((-50, 0, 1050), (150, 0, 1650), 1150, 800, label="Pelvis")
    L((0, 0, 1450), (500, 0, 2450), 950, 700, label="Abdomen")
    L((430, 0, 2250), (950, 0, 3300), 1500, 950, label="Chest")
    lean = math.radians(25)
    du, dw = math.sin(lean), math.cos(lean)       # spine direction
    nu, nw = math.cos(lean), -math.sin(lean)      # forward normal
    for v in (-380, 380):  # pecs
        cu, cw = 690 + nu * 450, 2775 + nw * 450
        L((cu - du * 275, v, cw - dw * 275), (cu + du * 275, v, cw + dw * 275), 650, 300, label="Pec")
    for k, w in enumerate((1650, 1950, 2250)):  # abs
        cu = (w - 1350) * math.tan(lean) + nu * 360
        cw = w + nw * 360
        for v in (-200, 200):
            L((cu - du * 130, v, cw - dw * 130), (cu + du * 130, v, cw + dw * 130), 330, 160, label="Ab")
    L((-150, 0, 2300), (250, 0, 3350), 1300, 700, label="Back")
    for v in (-850, 850):
        sc.block((850, v, 3150), (650, 600, 620), label="Deltoid")
    # loincloth
    L((-100, 0, 1550), (250, 0, 900), 1260, 920, mat=CLOTH, label="Loincloth")
    L((330, 0, 1300), (480, 0, 650), 720, 160, mat=CLOTH, label="ClothFlap")

    # --- neck + bowed head (crown pressed under the sphere)
    hb = 1.1  # heroic statues keep the head relatively small
    L((950, 0, 3250), (1250, 0, 3420), 470, 470, 150, label="Neck", bulk=1.25)
    L((1200, 0, 3700), (1550, 0, 3050), 560, 620, label="Head", bulk=hb)
    L((1480, 0, 3250), (1720, 0, 2850), 480, 360, mat=CLOTH, label="Beard", bulk=hb)
    L((1420, 0, 3450), (1560, 0, 3420), 560, 120, label="Brow", bulk=hb)
    L((1560, 0, 3380), (1640, 0, 3220), 130, 120, label="Nose", bulk=hb)
    L((1100, 0, 3750), (1250, 0, 3500), 620, 420, mat=CLOTH, label="Hair", bulk=hb)

    # --- arms raised, hands bracing the sphere
    for v in (-1, 1):
        sh = (850, v * 850, 3200)
        el = (600, v * 1650, 3850)
        ha = (100, v * 1880, 4750)
        L(sh, el, 520, 520, 250, label="UpperArm")
        L(el, ha, 420, 420, 200, label="Forearm")
        sc.block(el, (430, 430, 430), label="Elbow")
        L((150, v * 1870, 4600), (40, v * 1900, 5150), 420, 300, label="Hand")


def globe(sc):
    F = FOLDER + "/Globe"
    gx, gy, gz = S(*GLOBE_C)
    R = GLOBE_R * K * 0.95
    n = GLOBE_SLICES
    t = 2.0 * R / n
    for i in range(n):
        zc = -R + t * (i + 0.5)
        d = 2.0 * math.sqrt(max(R * R - zc * zc, 0.0))
        # three stacks of discs (along Z, X and Y) -> much rounder stepped sphere
        sc.part(sc.b.cyl, (gx, gy, gz + zc), (d, d, t + 2), mat=GLOBE, folder=F, label="GlobeSliceZ")
        sc.part(sc.b.cyl, (gx + zc, gy, gz), (d, d, t + 2), pitch=90.0, mat=GLOBE, folder=F, label="GlobeSliceX")
        sc.part(sc.b.cyl, (gx, gy + zc, gz), (d, d, t + 2), roll=90.0, mat=GLOBE, folder=F, label="GlobeSliceY")
    ring = 2 * R + 160
    sc.part(sc.b.cyl, (gx, gy, gz), (ring, ring, 90), mat=BAND, folder=F, label="Equator")
    sc.part(sc.b.cyl, (gx, gy, gz), (ring, ring, 70), pitch=23.5, mat=BAND, folder=F, label="Ecliptic")
    sc.part(sc.b.cyl, (gx, gy, gz), (ring, ring, 70), pitch=90.0, mat=BAND, folder=F, label="Meridian")


def main():
    b = arena.Builder()
    b.tag = TAG
    with unreal.ScopedEditorTransaction("Build Atlas Statue"):
        removed = 0
        for a in b.actor_sub.get_all_level_actors():
            if a.actor_has_tag(TAG):
                b.actor_sub.destroy_actor(a)
                removed += 1
        b.ox, b.oy, b.oz = tower.find_arena_origin(b)
        sc = Sculptor(b)
        pedestal(sc)
        body(sc)
        globe(sc)
    unreal.log("[Atlas] Removed {} old actors, spawned {} actors. Globe top {:.0f}m above ground.".format(
        removed, b.count, (PZ + (GLOBE_C[2] + GLOBE_R * 0.95) * K) / 100.0))


if __name__ == "__main__":
    main()
