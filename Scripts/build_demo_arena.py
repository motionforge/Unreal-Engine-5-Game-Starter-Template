"""
Space-station arena blockout for the currently open level (Demo_Level).

Run inside the Unreal Editor (Output Log -> Cmd):
    py "E:/Unreal Projects/Game_Template/Scripts/build_demo_arena.py"

- Uses only the LevelPrototyping meshes (SM_Cube / SM_Cylinder).
- Centres itself on the landscape and sits on top of the ground at the centre.
- Re-runnable: every actor it spawns is tagged "ArenaBlockout" and is deleted
  before rebuilding. The whole build is one undo transaction (Ctrl+Z).

Layout (cm, +X = "north"):
  Footprint 120m x 120m, 3 floors at 0 / 800 / 1600, roof at 2400.
  - Central atrium (44m square, full height, open skylight) with a reactor core,
    a floating spiral jump-path, and bridges on floors 2 and 3.
  - North hangar: double-height bay with a huge door, landing pad, catwalk, ramp.
  - South wing: entrance hall + rooms (F1), crew quarters (F2), observation deck (F3).
  - East / West wings: switch-back ramps F1->F2->F3, cargo hall, control room, labs.
"""

import math
import unreal

TAG = "ArenaBlockout"
ROOT_FOLDER = "Arena_Blockout"
ADD_LIGHTS = True
MOVE_PLAYER_START = False  # the PlayerStart has been placed by hand out on the entrance plaza

PROTO = "/Game/GameTemplate/EpicContent/LevelPrototyping"
MESH_CUBE = PROTO + "/Meshes/SM_Cube.SM_Cube"
MESH_CYL = PROTO + "/Meshes/SM_Cylinder.SM_Cylinder"
MAT_FLOOR = PROTO + "/Materials/MI_PrototypeGrid_Gray.MI_PrototypeGrid_Gray"
MAT_WALL = PROTO + "/Materials/MI_PrototypeGrid_Gray_02.MI_PrototypeGrid_Gray_02"
MAT_DARK = PROTO + "/Materials/MI_PrototypeGrid_TopDark.MI_PrototypeGrid_TopDark"
MAT_ACCENT = PROTO + "/Materials/MI_Solid_Blue.MI_Solid_Blue"

# ---------------------------------------------------------------- dimensions
HALF = 6000          # half footprint
WALL_T = 100         # outer wall thickness (walls occupy HALF-WALL_T .. HALF)
IN = HALF - WALL_T   # inner face of outer walls
SLAB_T = 50
LEVELS = [0, 800, 1600]
ROOF = 2400
PARAPET = 100
ROOM_T = 40          # interior wall thickness
DOOR_H = 350
# south facade: grand main entrance (ground) + balcony door onto F2 (see build_demo_entrance.py)
SOUTH_DOOR = (-1100, 1100, 0, 750)
SOUTH_UPPER_DOOR = (-600, 600, 800, 1400)
RAIL_H = 110
RAIL_T = 20

ATRIUM = (-2200, -2200, 2200, 2200)
HANGAR = (3000, -3500, IN, 3500)

# Ramps: footprint (x0, y0, x1, y1), bottom level, rise direction (+1 = up toward +X)
RAMPS = {
    "R1_West_F1toF2": ((-1500, -IN, 900, -5100), 0, +1),
    "R2_West_F2toF3": ((-1500, -4900, 900, -4100), 1, -1),
    "R3_East_F1toF2": ((-1500, 5100, 900, IN), 0, +1),
    "R4_East_F2toF3": ((-1500, 4100, 900, 4900), 1, -1),
    "R5_Hangar_F1toF2": ((3000, -3400, 5400, -2600), 0, -1),
}
# F3 -> roof (rises toward +X, arrives next to where the tower sky-bridge lands)
ROOF_RAMP = (2600, 4800, 5000, 5600)


# ================================================================ helpers
class Builder:
    def __init__(self):
        self.actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        self.cube = self._load(MESH_CUBE)
        self.cyl = self._load(MESH_CYL)
        self.mats = {
            "floor": self._load(MAT_FLOOR),
            "wall": self._load(MAT_WALL),
            "dark": self._load(MAT_DARK),
            "accent": self._load(MAT_ACCENT),
        }
        self.bounds = {}
        for m in (self.cube, self.cyl):
            bb = m.get_bounding_box()
            self.bounds[m.get_name()] = (bb.min, bb.max)
        self.tag = TAG
        self.ox = 0.0
        self.oy = 0.0
        self.oz = 0.0
        self.count = 0
        self.counter = {}

    @staticmethod
    def _load(path):
        asset = unreal.load_asset(path)
        if asset is None:
            raise RuntimeError("Could not load asset: " + path)
        return asset

    def _tag(self, actor, folder, label):
        actor.set_editor_property("tags", [unreal.Name(self.tag)])
        actor.set_folder_path(ROOT_FOLDER + "/" + folder)
        n = self.counter.get(label, 0) + 1
        self.counter[label] = n
        actor.set_actor_label("{}_{:03d}".format(label, n))
        self.count += 1

    def box(self, x0, y0, z0, x1, y1, z1, mat="floor", folder="Misc", label="Block", mesh=None):
        """Place a mesh so it exactly fills the local-space AABB given."""
        mesh = mesh or self.cube
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        z0, z1 = min(z0, z1), max(z0, z1)
        if x1 - x0 < 1 or y1 - y0 < 1 or z1 - z0 < 1:
            return None
        bmin, bmax = self.bounds[mesh.get_name()]
        sx = (x1 - x0) / (bmax.x - bmin.x)
        sy = (y1 - y0) / (bmax.y - bmin.y)
        sz = (z1 - z0) / (bmax.z - bmin.z)
        loc = unreal.Vector(self.ox + x0 - bmin.x * sx,
                            self.oy + y0 - bmin.y * sy,
                            self.oz + z0 - bmin.z * sz)
        actor = self.actor_sub.spawn_actor_from_object(mesh, loc, unreal.Rotator(0, 0, 0))
        actor.set_actor_scale3d(unreal.Vector(sx, sy, sz))
        actor.set_actor_location(loc, False, False)
        actor.static_mesh_component.set_material(0, self.mats[mat])
        self._tag(actor, folder, label)
        return actor

    def cylinder(self, cx, cy, z0, z1, diameter, mat="accent", folder="Misc", label="Cylinder"):
        r = diameter / 2.0
        return self.box(cx - r, cy - r, z0, cx + r, cy + r, z1, mat, folder, label, mesh=self.cyl)

    def ramp(self, footprint, z_bottom, z_top, direction, width_axis="y", thickness=40,
             mat="dark", folder="Ramps", label="Ramp"):
        """Sloped slab rising along X (direction +1 -> up toward +X, -1 -> up toward -X)."""
        x0, y0, x1, y1 = footprint
        run = x1 - x0
        rise = z_top - z_bottom
        length = math.hypot(run, rise)
        ang = math.atan2(rise, run)
        pitch_deg = math.degrees(ang) * direction
        p = math.radians(pitch_deg)
        # top surface midpoint, then drop half thickness along the surface normal
        mx, mz = (x0 + x1) / 2.0, (z_bottom + z_top) / 2.0
        nx, nz = -math.sin(p), math.cos(p)
        cx = mx - nx * thickness / 2.0
        cz = mz - nz * thickness / 2.0
        cy = (y0 + y1) / 2.0
        width = y1 - y0

        bmin, bmax = self.bounds[self.cube.get_name()]
        sx = length / (bmax.x - bmin.x)
        sy = width / (bmax.y - bmin.y)
        sz = thickness / (bmax.z - bmin.z)
        # mesh-local centre (scaled), rotated by pitch about Y
        lcx = (bmin.x + bmax.x) / 2.0 * sx
        lcy = (bmin.y + bmax.y) / 2.0 * sy
        lcz = (bmin.z + bmax.z) / 2.0 * sz
        rcx = lcx * math.cos(p) - lcz * math.sin(p)
        rcz = lcx * math.sin(p) + lcz * math.cos(p)
        loc = unreal.Vector(self.ox + cx - rcx, self.oy + cy - lcy, self.oz + cz - rcz)
        rot = unreal.Rotator(roll=0.0, pitch=pitch_deg, yaw=0.0)
        actor = self.actor_sub.spawn_actor_from_object(self.cube, loc, rot)
        actor.set_actor_scale3d(unreal.Vector(sx, sy, sz))
        actor.set_actor_location(loc, False, False)
        actor.set_actor_rotation(rot, False)
        actor.static_mesh_component.set_material(0, self.mats[mat])
        self._tag(actor, folder, label)
        return actor

    def light(self, x, y, z, intensity=40.0, radius=2500.0, color=(0.85, 0.92, 1.0), folder="Lights"):
        """Shadowless point light; intensity in candelas."""
        loc = unreal.Vector(self.ox + x, self.oy + y, self.oz + z)
        actor = self.actor_sub.spawn_actor_from_class(unreal.PointLight, loc, unreal.Rotator(0, 0, 0))
        comp = actor.get_component_by_class(unreal.PointLightComponent)
        comp.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
        comp.set_intensity(intensity)
        comp.set_attenuation_radius(radius)
        comp.set_cast_shadows(False)
        comp.set_light_color(unreal.LinearColor(color[0], color[1], color[2], 1.0))
        self._tag(actor, folder, "Light")


# ------------------------------------------------------------ 2D geometry
def subtract_rects(outer, holes):
    """outer=(a0,b0,a1,b1); holes list of same. Returns rects covering outer minus holes."""
    a0, b0, a1, b1 = outer
    clipped = []
    for h in holes:
        h = (max(a0, h[0]), max(b0, h[1]), min(a1, h[2]), min(b1, h[3]))
        if h[2] > h[0] and h[3] > h[1]:
            clipped.append(h)
    xs = sorted({a0, a1} | {v for h in clipped for v in (h[0], h[2])})
    ys = sorted({b0, b1} | {v for h in clipped for v in (h[1], h[3])})

    def solid(cx, cy):
        return not any(h[0] < cx < h[2] and h[1] < cy < h[3] for h in clipped)

    # vertical runs per column
    columns = []
    for i in range(len(xs) - 1):
        cx = (xs[i] + xs[i + 1]) / 2.0
        runs = []
        start = None
        for j in range(len(ys) - 1):
            cy = (ys[j] + ys[j + 1]) / 2.0
            if solid(cx, cy):
                if start is None:
                    start = ys[j]
                end = ys[j + 1]
            elif start is not None:
                runs.append((start, end))
                start = None
        if start is not None:
            runs.append((start, end))
        columns.append(runs)

    # merge identical runs across neighbouring columns
    out = []
    open_runs = {}
    for i, runs in enumerate(columns):
        new_open = {}
        for r in runs:
            if r in open_runs:
                new_open[r] = open_runs[r]
            else:
                new_open[r] = xs[i]
        for r, sx in open_runs.items():
            if r not in new_open:
                out.append((sx, r[0], xs[i], r[1]))
        open_runs = new_open
    for r, sx in open_runs.items():
        out.append((sx, r[0], xs[-1], r[1]))
    return out


def subtract_spans(a0, a1, gaps):
    """1D: span a0..a1 minus gap spans."""
    segs = [(a0, a1)]
    for g0, g1 in gaps:
        nxt = []
        for s0, s1 in segs:
            if g1 <= s0 or g0 >= s1:
                nxt.append((s0, s1))
                continue
            if g0 > s0:
                nxt.append((s0, g0))
            if g1 < s1:
                nxt.append((g1, s1))
        segs = nxt
    return [s for s in segs if s[1] - s[0] > 1]


# ------------------------------------------------------------ composite parts
def slab(b, top, holes, folder, outer=(-IN, -IN, IN, IN), mat="floor"):
    for r in subtract_rects(outer, holes):
        b.box(r[0], r[1], top - SLAB_T, r[2], r[3], top, mat, folder, "Floor")


def wall(b, axis, t0, t1, a0, a1, z0, z1, openings, folder, mat="wall", label="Wall"):
    """axis 'x': wall runs along X, thickness spans Y t0..t1. openings: (a0,a1,z0,z1)."""
    for r in subtract_rects((a0, z0, a1, z1), [(o[0], o[2], o[1], o[3]) for o in openings]):
        if axis == "x":
            b.box(r[0], t0, r[1], r[2], t1, r[3], mat, folder, label)
        else:
            b.box(t0, r[0], r[1], t1, r[2], r[3], mat, folder, label)


def room(b, x0, y0, x1, y1, z, h, doors, folder, skip=(), t=ROOM_T, door_h=DOOR_H):
    """doors: dict side -> list of (centre, width). sides: xmin, xmax, ymin, ymax.
    skip: sides with no wall (e.g. the side backing onto an outer wall, so its windows stay open)."""
    def ops(side):
        return [(c - w / 2.0, c + w / 2.0, z, z + door_h) for c, w in doors.get(side, [])]
    xa = x0 if "xmin" in skip else x0 + t
    xb = x1 if "xmax" in skip else x1 - t
    if "xmin" not in skip:
        wall(b, "y", x0, x0 + t, y0, y1, z, z + h, ops("xmin"), folder, label="RoomWall")
    if "xmax" not in skip:
        wall(b, "y", x1 - t, x1, y0, y1, z, z + h, ops("xmax"), folder, label="RoomWall")
    if "ymin" not in skip:
        wall(b, "x", y0, y0 + t, xa, xb, z, z + h, ops("ymin"), folder, label="RoomWall")
    if "ymax" not in skip:
        wall(b, "x", y1 - t, y1, xa, xb, z, z + h, ops("ymax"), folder, label="RoomWall")


def rail(b, axis, fixed, a0, a1, z, gaps, folder):
    """Railing along an edge. axis 'x' -> runs along X at Y=fixed."""
    for s0, s1 in subtract_spans(a0, a1, gaps):
        if axis == "x":
            b.box(s0, fixed - RAIL_T / 2, z, s1, fixed + RAIL_T / 2, z + RAIL_H, "accent", folder, "Rail")
        else:
            b.box(fixed - RAIL_T / 2, s0, z, fixed + RAIL_T / 2, s1, z + RAIL_H, "accent", folder, "Rail")


def rail_hole(b, hole, z, folder, skip=(), gaps=None):
    """Railings around a floor opening. skip: sides to leave open. gaps: side -> [(a0,a1)]."""
    gaps = gaps or {}
    x0, y0, x1, y1 = hole
    if "ymin" not in skip:
        rail(b, "x", y0, x0, x1, z, gaps.get("ymin", []), folder)
    if "ymax" not in skip:
        rail(b, "x", y1, x0, x1, z, gaps.get("ymax", []), folder)
    if "xmin" not in skip:
        rail(b, "y", x0, y0, y1, z, gaps.get("xmin", []), folder)
    if "xmax" not in skip:
        rail(b, "y", x1, y0, y1, z, gaps.get("xmax", []), folder)


# ================================================================ level setup
def delete_previous(b):
    removed = 0
    for a in b.actor_sub.get_all_level_actors():
        if a.actor_has_tag(TAG):
            b.actor_sub.destroy_actor(a)
            removed += 1
    return removed


def find_landscape_bounds(b):
    lo = None
    hi = None
    for a in b.actor_sub.get_all_level_actors():
        if isinstance(a, unreal.LandscapeProxy):
            origin, extent = a.get_actor_bounds(False)
            amin = origin - extent
            amax = origin + extent
            if lo is None:
                lo, hi = amin, amax
            else:
                lo = unreal.Vector(min(lo.x, amin.x), min(lo.y, amin.y), min(lo.z, amin.z))
                hi = unreal.Vector(max(hi.x, amax.x), max(hi.y, amax.y), max(hi.z, amax.z))
    return lo, hi


def trace_ground(b, x, y, z_top, z_bottom):
    hit = unreal.SystemLibrary.line_trace_single(
        b.world, unreal.Vector(x, y, z_top), unreal.Vector(x, y, z_bottom),
        getattr(unreal.TraceTypeQuery, "ECC_VISIBILITY", None) or unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    try:
        parts = unreal.GameplayStatics.break_hit_result(hit)
    except Exception:
        parts = hit.to_tuple()
    for p in parts:
        if isinstance(p, unreal.Vector):  # first vector = hit location
            return p.z
    return None


def place_origin(b):
    lo, hi = find_landscape_bounds(b)
    if lo is None:
        unreal.log_warning("[Arena] No landscape found - building at world origin.")
        return 0.0, 0.0, 0.0, 0.0
    cx = (lo.x + hi.x) / 2.0
    cy = (lo.y + hi.y) / 2.0
    zs = []
    steps = 8
    for i in range(steps + 1):
        for j in range(steps + 1):
            x = cx - HALF + 2 * HALF * i / steps
            y = cy - HALF + 2 * HALF * j / steps
            z = trace_ground(b, x, y, hi.z + 1000.0, lo.z - 1000.0)
            if z is not None:
                zs.append(z)
    if not zs:
        unreal.log_warning("[Arena] Ground traces missed - using landscape bounds height.")
        return cx, cy, hi.z, lo.z
    return cx, cy, max(zs) + 20.0, min(zs)


# ================================================================ the arena
def build_roof(b):
    """Roof slab, skylight lattice and the F3 -> roof ramp (all in the Roof folder)."""
    slab(b, ROOF, [ATRIUM, ROOF_RAMP], "Roof", mat="dark")
    for c in (-1100, 1100):
        b.box(c - 100, ATRIUM[1], ROOF - 150, c + 100, ATRIUM[3], ROOF, "dark", "Roof", "SkyBeam")
        b.box(ATRIUM[0], c - 100, ROOF - 150, ATRIUM[2], c + 100, ROOF, "dark", "Roof", "SkyBeam")
    b.ramp(ROOF_RAMP, LEVELS[2], ROOF, +1, folder="Roof", label="R6_F3toRoof")
    rail_hole(b, ROOF_RAMP, ROOF, "Roof", skip=("xmax",))


def south_wall(b):
    """South facade: main entrance, balcony door, F2 windows and F3 observation windows."""
    top = ROOF + PARAPET
    L2, L3 = LEVELS[1], LEVELS[2]
    f3_win = [(c - 500, c + 500, L3 + 200, L3 + 650) for c in (-4500, -3000, -1500, 0, 1500, 3000, 4500)]
    # inner pair kept clear of the entrance's colossal columns (y +-1750)
    f2_win_s = [(c - 300, c + 300, L2 + 200, L2 + 600) for c in (-3700, -2450, 2450, 3700)]
    wall(b, "y", -HALF, -IN, -HALF, HALF, 0, top,
         [SOUTH_DOOR, SOUTH_UPPER_DOOR] + f2_win_s + f3_win, "Structure", label="OuterWall_S")


def build(b, ground_min):
    L1, L2, L3 = LEVELS
    F = "Structure"

    # ---------------- foundation + ground deck
    b.box(-HALF - 400, -HALF - 400, -SLAB_T, HALF + 400, HALF + 400, 0, "floor", F, "GroundDeck")
    depth = ground_min - b.oz - 300
    if depth < -SLAB_T:
        b.box(-HALF - 400, -HALF - 400, depth, HALF + 400, HALF + 400, -SLAB_T, "dark", F, "Foundation")

    # ---------------- outer walls (full height + parapet)
    top = ROOF + PARAPET
    # north: hangar door
    wall(b, "y", IN, HALF, -HALF, HALF, 0, top, [(-2500, 2500, 0, 1300)], F, label="OuterWall_N")
    # south: main entrance + F2 windows + F3 observation windows
    south_wall(b)
    side_win = [(c - 500, c + 500, L3 + 200, L3 + 650) for c in (-4500, -3000, 1500, 3000, 4500)]
    wall(b, "x", IN, HALF, -IN, IN, 0, top, [(-4000, -3200, 0, 500)] + side_win, F, label="OuterWall_E")
    wall(b, "x", -HALF, -IN, -IN, IN, 0, top, [(-4000, -3200, 0, 500)] + side_win, F, label="OuterWall_W")

    # ---------------- floor slabs + roof
    hole = {name: r[0] for name, r in RAMPS.items()}
    slab(b, L2, [ATRIUM, HANGAR, hole["R1_West_F1toF2"], hole["R3_East_F1toF2"]], "Floor2")
    slab(b, L3, [ATRIUM, hole["R2_West_F2toF3"], hole["R4_East_F2toF3"]], "Floor3")
    build_roof(b)

    # ---------------- ramps
    for name, (fp, lvl, direction) in RAMPS.items():
        b.ramp(fp, LEVELS[lvl], LEVELS[lvl + 1], direction, label=name)

    # ---------------- atrium: pillars, core, bridges, spiral
    A = "Atrium"
    for p in (-2300, -1150, 1150, 2300):
        for q in (-2300, 2300):
            b.cylinder(p, q, 0, ROOF, 200, "dark", A, "Pillar")
            if abs(p) != 2300:
                b.cylinder(q, p, 0, ROOF, 200, "dark", A, "Pillar")
    b.cylinder(0, 0, 0, 120, 1700, "dark", A, "CoreBase")
    b.cylinder(0, 0, 0, ROOF + 600, 1000, "accent", A, "ReactorCore")
    for z in (L2 - 200, L3 - 200, ROOF - 200):
        b.cylinder(0, 0, z, z + 120, 1150, "dark", A, "CoreRing")

    # core platforms
    b.box(-900, -900, L2 - SLAB_T, 900, 900, L2, "floor", A, "CorePlatform_F2")
    b.box(-900, -900, L3 - SLAB_T, 900, 900, L3, "floor", A, "CorePlatform_F3")
    # F2 bridges east/west, F3 bridges north/south
    b.box(-250, 900, L2 - SLAB_T, 250, ATRIUM[3], L2, "floor", A, "Bridge_F2")
    b.box(-250, ATRIUM[1], L2 - SLAB_T, 250, -900, L2, "floor", A, "Bridge_F2")
    b.box(900, -250, L3 - SLAB_T, ATRIUM[2], 250, L3, "floor", A, "Bridge_F3")
    b.box(ATRIUM[0], -250, L3 - SLAB_T, -900, 250, L3, "floor", A, "Bridge_F3")
    # rails on F3 bridges + both core platforms
    for y in (-250, 250):
        rail(b, "x", y, 900, ATRIUM[2], L3, [], A)
        rail(b, "x", y, ATRIUM[0], -900, L3, [], A)
    rail_hole(b, (-900, -900, 900, 900), L2, A,
              gaps={"ymin": [(-250, 250)], "ymax": [(-250, 250)]})
    rail_hole(b, (-900, -900, 900, 900), L3, A,
              gaps={"xmin": [(-250, 250)], "xmax": [(-250, 250)]})

    # floating spiral jump-path from the atrium floor up to the F2 east bridge
    for k in range(1, 9):
        ang = math.radians(-105 + 25 * (k - 1))
        cx, cy = 1600 * math.cos(ang), 1600 * math.sin(ang)
        ztop = L1 + 100 * k
        b.box(cx - 200, cy - 200, ztop - 60, cx + 200, cy + 200, ztop, "accent", A, "JumpPad")

    # ---------------- hangar (north)
    H = "Hangar"
    b.cylinder(4500, 0, 0, 30, 2000, "accent", H, "LandingPad")
    b.cylinder(4500, 0, 30, 45, 1400, "dark", H, "LandingPadInner")
    crates = [(3300, 2600, 400), (3700, 2600, 300), (3300, 3000, 200), (5400, 2900, 400),
              (5400, 2400, 250), (5600, -1800, 300), (3400, -1800, 200), (5000, 2900, 200)]
    for x, y, s in crates:
        b.box(x - s / 2, y - s / 2, 0, x + s / 2, y + s / 2, s, "wall", H, "Crate")
    # catwalk across the hangar at F2 height
    b.box(HANGAR[0], -200, L2 - SLAB_T, IN, 200, L2, "floor", H, "Catwalk")
    rail(b, "x", -200, HANGAR[0], IN, L2, [], H)
    rail(b, "x", 200, HANGAR[0], IN, L2, [], H)
    rail(b, "y", IN - 20, -200, 200, L2, [], H)
    # railings around the hangar void on F2
    rail_hole(b, HANGAR, L2, H, skip=("xmax",),
              gaps={"xmin": [(-3400, -2600), (-200, 200)]})

    # ---------------- F1: south entrance hall + rooms
    F1 = "Floor1"
    h1 = L2 - SLAB_T
    room(b, -IN, -4000, -3900, -1200, 0, h1, {"ymax": [(-4900, 500)], "xmax": [(-2600, 500)]}, F1,
         skip=("xmin",))
    room(b, -IN, 1200, -3900, 4000, 0, h1, {"ymin": [(-4900, 500)], "xmax": [(2600, 500)]}, F1,
         skip=("xmin",))
    # security gate in the entrance hall
    for y in (-700, 700):
        b.box(-3600, y - 60, 0, -3300, y + 60, 300, "dark", F1, "Gate")
    b.box(-3600, -760, 300, -3300, 760, 380, "dark", F1, "Gate")
    # west wing: cover blocks
    for x, y, sx, sy, h in [(-3200, -3200, 600, 200, 120), (-1800, -3000, 200, 600, 120),
                            (1800, -3600, 400, 400, 200), (2600, -4600, 600, 200, 120)]:
        b.box(x - sx / 2, y - sy / 2, 0, x + sx / 2, y + sy / 2, h, "wall", F1, "Cover")
    # east wing: cargo stack you can climb
    for i, (x, y, s, h) in enumerate([(1500, 2800, 400, 100), (1500, 3300, 400, 200),
                                      (2000, 3300, 400, 300), (2500, 3300, 400, 400),
                                      (2500, 3800, 400, 300), (-3200, 3000, 500, 250),
                                      (-2600, 3600, 300, 150)]):
        b.box(x - s / 2, y - s / 2, 0, x + s / 2, y + s / 2, h, "wall", F1, "CargoCrate")

    # ---------------- F2
    F2 = "Floor2"
    h2 = L3 - L2 - SLAB_T
    # crew quarters along the south wall
    for y0, y1 in [(-4600, -2800), (-2800, -1000), (1000, 2800), (2800, 4600)]:
        room(b, -IN, y0, -4200, y1, L2, h2, {"xmax": [((y0 + y1) / 2.0, 300)]}, F2, skip=("xmin",))
    # control room over the cargo hall
    room(b, 1200, 2500, 2800, 3900, L2, h2, {"ymin": [(2000, 500)], "xmin": [(3200, 400)]}, F2)
    b.box(1500, 3300, L2, 2500, 3600, L2 + 100, "accent", F2, "Console")
    # lab benches west
    for x in (-3400, -2800):
        b.box(x - 100, -3800, L2, x + 100, -2600, L2 + 100, "wall", F2, "Bench")
    # rails around the F2 openings
    rail_hole(b, ATRIUM, L2, F2, gaps={"ymin": [(-250, 250)], "ymax": [(-250, 250)]})
    rail_hole(b, RAMPS["R1_West_F1toF2"][0], L2, F2, skip=("xmax", "ymin"))
    rail_hole(b, RAMPS["R3_East_F1toF2"][0], L2, F2, skip=("xmax", "ymax"))

    # ---------------- F3
    F3 = "Floor3"
    h3 = ROOF - L3 - SLAB_T
    room(b, -4000, -IN, -2000, -3000, L3, h3, {"xmax": [(-4500, 800)], "ymax": [(-3000, 500)]}, F3,
         skip=("ymin",))
    room(b, 1400, -IN, 2900, -3000, L3, h3, {"ymax": [(2150, 500)]}, F3, skip=("ymin",))
    # command dais above the hangar (stepped, 40cm steps)
    for i, inset in enumerate((0, 200, 400)):
        b.box(3600 + inset, -2000 + inset, L3, 5600, 2000 - inset, L3 + 40 * (i + 1), "dark", F3, "Dais")
    # observation deck benches
    for y in (-3000, 0, 3000):
        b.box(-5200, y - 600, L3, -5000, y + 600, L3 + 45, "wall", F3, "Bench")
    rail_hole(b, ATRIUM, L3, F3, gaps={"xmin": [(-250, 250)], "xmax": [(-250, 250)]})
    rail_hole(b, RAMPS["R2_West_F2toF3"][0], L3, F3, skip=("xmin",))
    rail_hole(b, RAMPS["R4_East_F2toF3"][0], L3, F3, skip=("xmin",))

    # ---------------- lights
    if ADD_LIGHTS:
        for z in (L1 + 600, L2 + 600, L3 + 600):
            for x in (-4600, -3000, 3000, 4600):
                for y in (-4600, -3000, 3000, 4600):
                    if z == L2 + 600 and HANGAR[0] < x < HANGAR[2] and HANGAR[1] < y < HANGAR[3]:
                        continue
                    b.light(x, y, z)
            for x, y in ((0, -3800), (0, 3800), (-3800, 0), (3800, 0)):
                b.light(x, y, z)
        b.light(4500, 0, 1200, intensity=150.0, radius=5000.0)
        for z in (400, 1200, 2000):
            b.light(1300, 0, z, intensity=100.0, radius=4000.0, color=(0.4, 0.7, 1.0))


def move_player_start(b):
    starts = [a for a in b.actor_sub.get_all_level_actors() if isinstance(a, unreal.PlayerStart)]
    if len(starts) != 1:
        unreal.log_warning("[Arena] Found {} PlayerStarts - not moving any.".format(len(starts)))
        return
    loc = unreal.Vector(b.ox - 5200, b.oy, b.oz + 120)
    starts[0].set_actor_location(loc, False, False)
    starts[0].set_actor_rotation(unreal.Rotator(0, 0, 0), False)


def main():
    b = Builder()
    with unreal.ScopedEditorTransaction("Build Arena Blockout"):
        removed = delete_previous(b)
        cx, cy, ground_top, ground_min = place_origin(b)
        b.ox, b.oy, b.oz = cx, cy, ground_top
        build(b, ground_min)
        if MOVE_PLAYER_START:
            move_player_start(b)
    unreal.log("[Arena] Removed {} old actors, spawned {} actors. Origin = ({:.0f}, {:.0f}, {:.0f}), "
               "ground range {:.0f}..{:.0f}".format(removed, b.count, cx, cy, ground_top,
                                                    ground_min, ground_top - 20))


if __name__ == "__main__":
    main()
