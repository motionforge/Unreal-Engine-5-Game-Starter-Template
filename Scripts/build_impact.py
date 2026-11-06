"""
Bullet impact for the drone, built into /Game/GameTemplate/Niagara/NS_Impact.

Everything fires along the system's local +Z (up), so rotating the spawned system
(e.g. to the hit's Impact Normal) aims the whole effect. All emitters are one-shot bursts
and the system finishes on its own after ~2 seconds (when the smoke is gone).

  Flash  - one soft HDR orange pop, 0.12s
  Sparks - 120 hot sparks shot up in a 35 degree cone at 500-1200 cm/s, gravity + drag,
           stretched along their velocity, 0.4-1.1s
  Smoke  - 10 grey puffs (flipbook M_smoke_subUV, 8x8) drifting up, billowing out to 3.5x,
           fading in fast and out slowly, gone within 2s

Run inside the Unreal Editor (Output Log -> Cmd):
    py "E:/Unreal Projects/Game_Template/Scripts/build_impact.py"
Re-running rebuilds all emitters from scratch (any hand edits to NS_Impact are lost).
"""

import importlib
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import niagara_tools  # noqa: E402

importlib.reload(niagara_tools)  # the editor keeps modules loaded between runs
from niagara_tools import System, b, curve, enum, f, i, rgba, v2, v3  # noqa: E402

SYSTEM = "/Game/GameTemplate/Niagara/NS_Impact.NS_Impact"
TEMPLATES = "/Niagara/DefaultAssets/Templates/Emitters/"
MODULES = "/Niagara/Modules/"
ENUMS = "/Niagara/Enums/"
SMOKE_MATERIAL = "/Game/GameTemplate/EpicContent/StarterContent/Particles/Materials/M_smoke_subUV"

ES, PS, PU = "EmitterUpdateScript", "ParticleSpawnScript", "ParticleUpdateScript"
INIT = "InitializeParticle"
LIFETIME_MODE, SIZE_MODE = ENUMS + "ENiagara_LifetimeMode", ENUMS + "ENiagara_SizeScaleMode"
RANDOM, RANDOM_UNIFORM, UNIFORM = 1, 1, 3


def one_shot(s, emitter):
    s.set(emitter, ES, "EmitterState", "Loop Behavior", enum(ENUMS + "ENiagara_EmitterStateOptions", 1))  # Once
    s.set(emitter, ES, "EmitterState", "Loop Duration", f(0.1))


def lifetime(s, emitter, lo, hi):
    s.set(emitter, PS, INIT, "Lifetime Mode", enum(LIFETIME_MODE, RANDOM))
    s.set(emitter, PS, INIT, "Lifetime Min", f(lo))
    s.set(emitter, PS, INIT, "Lifetime Max", f(hi))


def build_flash(s):
    e = "Flash"
    s.add_emitter(e, TEMPLATES + "SimpleSpriteBurst.SimpleSpriteBurst")
    one_shot(s, e)
    s.set(e, PS, INIT, "Lifetime", f(0.12))
    s.set(e, PS, INIT, "Color", rgba(12.0, 5.0, 1.5))  # bright enough to bloom, soft enough to keep its falloff
    s.set(e, PS, INIT, "Sprite Size Mode", enum(SIZE_MODE, UNIFORM))
    s.set(e, PS, INIT, "Uniform Sprite Size", f(130.0))


def build_sparks(s):
    e = "Sparks"
    s.add_emitter(e, TEMPLATES + "DirectionalBurst.DirectionalBurst")
    one_shot(s, e)
    s.set(e, ES, "SpawnBurst_Instantaneous", "Spawn Count", i(120))
    lifetime(s, e, 0.4, 1.1)
    s.set(e, PS, INIT, "Color", rgba(40.0, 12.0, 2.0))
    s.set(e, PS, INIT, "Sprite Size Min", v2(2.0, 8.0))
    s.set(e, PS, INIT, "Sprite Size Max", v2(4.0, 18.0))
    s.set(e, PS, "AddVelocity", "Cone Axis", v3(0.0, 0.0, 1.0))  # local up
    s.set(e, PS, "AddVelocity", "Cone Angle", f(35.0))
    s.set_random_range(e, PS, "AddVelocity", "Velocity Speed", 500.0, 1200.0)


def build_smoke(s):
    e = "Smoke"
    s.add_emitter(e, TEMPLATES + "SimpleSpriteBurst.SimpleSpriteBurst")
    one_shot(s, e)
    s.set(e, ES, "SpawnBurst_Instantaneous", "Spawn Count", i(10))
    lifetime(s, e, 1.6, 2.0)  # every puff is gone by 2 seconds
    s.set(e, PS, INIT, "Color", rgba(0.25, 0.25, 0.25, 0.7))
    s.set(e, PS, INIT, "Sprite Size Mode", enum(SIZE_MODE, RANDOM_UNIFORM))
    s.set(e, PS, INIT, "Uniform Sprite Size Min", f(50.0))
    s.set(e, PS, INIT, "Uniform Sprite Size Max", f(90.0))
    s.set(e, PS, INIT, "Sprite Rotation Mode", enum(ENUMS + "ENiagara_SpriteRotationMode", 2))  # Random
    s.set(e, PS, INIT, "Write Material Random", b(False))

    sphere = s.add_module(e, PS, MODULES + "Spawn/Location/V2/SphereLocation.SphereLocation", after=INIT)
    s.set(e, PS, sphere, "Sphere Radius", f(15.0))
    vel = s.add_module(e, PS, MODULES + "Spawn/Velocity/AddVelocity.AddVelocity", after=sphere)
    s.set(e, PS, vel, "Velocity Mode", enum(ENUMS + "Utility/ENiagara_VelocityMode", 2))  # In Cone
    s.set(e, PS, vel, "Cone Axis", v3(0.0, 0.0, 1.0))
    s.set(e, PS, vel, "Cone Angle", f(40.0))
    s.set_random_range(e, PS, vel, "Velocity Speed", 120.0, 300.0)

    rise = s.add_module(e, PU, MODULES + "Update/Forces/GravityForce.GravityForce", after="ParticleState")
    s.set(e, PU, rise, "Gravity", v3(0.0, 0.0, 60.0))  # slight buoyancy
    drag = s.add_module(e, PU, MODULES + "Update/Forces/Drag.Drag", after=rise)
    s.set(e, PU, drag, "Drag", f(2.5))
    grow = s.add_module(e, PU, MODULES + "Update/Size/ScaleSpriteSize.ScaleSpriteSize", after=drag)
    # Grow with the module's own age curve (0 -> 1) scaled 3.5x: puffs start small and billow out.
    # Note: HLSL expressions or new dynamic inputs reading Particles.NormalizedAge evaluated as
    # constants when set through the toolset, so age-driven values use the modules' built-in links.
    s.set(e, PU, grow, "Uniform Curve Scale", f(3.5))
    s.set(e, PU, "ScaleColor", ["Scale Alpha", "FloatCurve"], curve((0.0, 0.0), (0.1, 1.0), (1.0, 0.0)))  # fade in/out
    subuv = s.add_module(e, PU, MODULES + "Update/SubUV/V2/SubUVAnimation.SubUVAnimation")
    s.set(e, PU, subuv, "Define SubUV Setup Manually", enum(ENUMS + "SpriteRenderer/ENiagara_AutomaticManual", 1))
    s.set(e, PU, subuv, "Manual SubImage Size", v2(8.0, 8.0))

    s.set_renderer(e, 0, Material={"refPath": SMOKE_MATERIAL + ".M_smoke_subUV"}, SubImageSize={"x": 8, "y": 8})


def smoke_material_usage():
    """Niagara sprites need the usage flag on the material, or it renders as the default material in builds."""
    m = unreal.load_asset(SMOKE_MATERIAL)
    if not m.get_editor_property("used_with_niagara_sprites"):
        m.set_editor_property("used_with_niagara_sprites", True)
        unreal.MaterialEditingLibrary.recompile_material(m)
        unreal.EditorAssetLibrary.save_loaded_asset(m, only_if_is_dirty=False)


def main():
    smoke_material_usage()
    s = System(SYSTEM)
    for name in s.emitters():
        s.remove_emitter(name)
    build_flash(s)
    build_sparks(s)
    build_smoke(s)
    s.save()
    unreal.log("NS_Impact built. The system compiles on the next editor ticks; open it to check the stack.")


main()
