"""
Tracer round for the drone, built into /Game/GameTemplate/Niagara/NS_Tracer.

One emitter "Tracer" (from the SimpleSpriteBurst template, CPU, world space):
  Emitter State   -> Loop Once, 0.05s, so each shot is a one-off that cleans itself up
  Spawn Burst     -> 1 particle
  Initialize      -> Lifetime = distance to User.TracerEnd / User.TracerSpeed (dies on arrival)
                     Color = User.TracerColor (HDR, so it blooms), sprite 6 x 250 (width x length)
  Add Velocity    -> towards User.TracerEnd at User.TracerSpeed
  Sprite renderer -> Velocity Aligned, so the sprite stretches along its flight path

User parameters (set them on the spawned Niagara component):
  User.TracerEnd   (Position)     world-space end point, e.g. the line trace hit / trace end
  User.TracerSpeed (float)        cm/s, default 8000
  User.TracerColor (Linear Color) default orange (20, 6, 1)

Usage from the drone's FireShot: Spawn System at Location (NS_Tracer, muzzle location),
then Set Niagara Variable (Position) "TracerEnd" = hit location (or trace end on a miss).

Run inside the Unreal Editor (Output Log -> Cmd):
    py "E:/Unreal Projects/Game_Template/Scripts/build_tracer.py"
Re-running rebuilds the Tracer emitter from scratch (any hand edits to it are lost).
"""

import json
import unreal

SYSTEM = "/Game/GameTemplate/Niagara/NS_Tracer.NS_Tracer"
TEMPLATE = "/Niagara/DefaultAssets/Templates/Emitters/SimpleSpriteBurst.SimpleSpriteBurst"
ADD_VELOCITY = "/Niagara/Modules/Spawn/Velocity/AddVelocity.AddVelocity"
EMITTER = "Tracer"

SPEED = 8000.0
COLOR = (20.0, 6.0, 1.0, 1.0)
SPRITE_SIZE = (6.0, 250.0)  # x = width, y = length along the velocity
PREVIEW_END = (1500.0, 0.0, 0.0)

# "End - Start" is guarded against zero length so a point-blank shot doesn't produce NaNs.
DELTA = "(User.TracerEnd - Engine.Owner.Position)"
LIFETIME_EXPR = "length(%s) / max(User.TracerSpeed, 1.0)" % DELTA
VELOCITY_EXPR = "%s / max(length(%s), 0.001) * User.TracerSpeed" % (DELTA, DELTA)

TOOLSET = "NiagaraToolsets.NiagaraToolset_System"
EDITOR = "/Script/NiagaraEditor."
FLOAT, POSITION, COLOR_T = "/Script/Niagara.NiagaraFloat", "/Script/Niagara.NiagaraPosition", "/Script/CoreUObject.LinearColor"


def tool(name, **args):
    """Run a Niagara toolset tool with JSON args, raising on errors."""
    r = unreal.ToolsetRegistry.execute_tool(TOOLSET, name, json.dumps(args))
    if not r.is_complete:
        raise RuntimeError("%s did not complete synchronously" % name)
    if r.error and str(r.error) not in ("", "None"):
        raise RuntimeError("%s: %s" % (name, r.error))
    value = r.get_value_as_json_string()
    while isinstance(value, str) and value:
        value = json.loads(value)
    return value.get("returnValue", value) if isinstance(value, dict) else value


def ref(script="", module="", inputs=(), renderer=-1, emitter=EMITTER):
    return {"system": {"refPath": SYSTEM}, "emitterName": emitter, "scriptName": script,
            "moduleName": module, "rendererIndex": renderer, "inputNameStack": list(inputs)}


def value(struct, **fields):
    return {"struct": {"refPath": struct}, "value": fields}


def enum(enum_name, index):
    path = "/Niagara/Enums/%s.%s" % (enum_name, enum_name)
    return value(EDITOR + "NiagaraExt_StackInputData_Enum", enum={"refPath": path},
                 enumName="%s::NewEnumerator%d" % (enum_name, index), displayName="")


def hlsl(expr):
    return value(EDITOR + "NiagaraExt_StackInputData_HlslExpression", hlslExpression=expr)


def linked(name, type_path):
    return value(EDITOR + "NiagaraExt_StackInputData_Linked",
                 linkedVariable={"name": name, "type": {"classStructOrEnum": {"refPath": type_path}}})


def set_input(script, module, inp, data):
    tool("SetStackInputData", stackInputRef=ref(script, module, [inp]), inputData=data)


def rebuild_emitter(system):
    summary = tool("GetSystemSummary", system={"refPath": SYSTEM})
    for e in summary.get("emitters", []):
        if e["emitterName"] in (EMITTER, "CompletelyEmpty"):
            tool("RemoveEmitter", emitterToRemove=ref(emitter=e["emitterName"]))
    tool("AddEmitter", system={"refPath": SYSTEM}, templateEmitter={"refPath": TEMPLATE}, emitterName=EMITTER)


def user_variables():
    names = ["User.TracerEnd", "User.TracerSpeed", "User.TracerColor"]
    existing = [v["name"] for v in tool("GetUserVariables", system={"refPath": SYSTEM}).get("userVariables", [])]
    stale = [{"name": n, "type": {"classStructOrEnum": {"refPath": t}}}
             for n, t in zip(names, [POSITION, FLOAT, COLOR_T]) if n in existing]
    if stale:
        tool("RemoveUserVariables", system={"refPath": SYSTEM}, variablesToRemove=stale)
    end, (r, g, b, a) = PREVIEW_END, COLOR
    tool("AddUserVariables", system={"refPath": SYSTEM}, variablesToAdd=[
        {"name": names[0], "type": {"classStructOrEnum": {"refPath": POSITION}},
         "defaultValue": value(POSITION, x=end[0], y=end[1], z=end[2]),
         "description": "World-space point the tracer flies to (trace hit or trace end)."},
        {"name": names[1], "type": {"classStructOrEnum": {"refPath": FLOAT}},
         "defaultValue": value(FLOAT, value=SPEED), "description": "Tracer speed in cm/s."},
        {"name": names[2], "type": {"classStructOrEnum": {"refPath": COLOR_T}},
         "defaultValue": value(COLOR_T, r=r, g=g, b=b, a=a), "description": "HDR tracer colour."},
    ])


def configure_stack():
    es, ps, pu = "EmitterUpdateScript", "ParticleSpawnScript", "ParticleUpdateScript"
    set_input(es, "EmitterState", "Loop Behavior", enum("ENiagara_EmitterStateOptions", 1))  # Once
    set_input(es, "EmitterState", "Loop Duration", value(FLOAT, value=0.05))

    init = "InitializeParticle"
    set_input(ps, init, "Lifetime", hlsl(LIFETIME_EXPR))
    set_input(ps, init, "Color Mode", enum("ENiagara_ColorInitializationMode", 1))  # Direct Set
    set_input(ps, init, "Color", linked("User.TracerColor", COLOR_T))
    set_input(ps, init, "Sprite Size Mode", enum("ENiagara_SizeScaleMode", 4))  # Non-Uniform
    set_input(ps, init, "Sprite Size", value("/Script/CoreUObject.Vector2f", x=SPRITE_SIZE[0], y=SPRITE_SIZE[1]))
    set_input(ps, init, "Write Material Random", value("/Script/Niagara.NiagaraBool", value=0))

    tool("RemoveModule", moduleToRemove=ref(pu, "ScaleColor"))  # keep the tracer at full brightness

    added = tool("AddModule", moduleLocationRef=ref(ps, init), moduleAsset={"refPath": ADD_VELOCITY})
    set_input(ps, added["moduleName"], "Velocity", hlsl(VELOCITY_EXPR))

    tool("SetRendererData", renderer=ref(renderer=0),
         rendererData={"propertyValues": json.dumps({"Alignment": "VelocityAligned"})})


def main():
    system = unreal.load_asset(SYSTEM)
    if system is None:
        raise RuntimeError("Missing " + SYSTEM)
    rebuild_emitter(system)
    user_variables()
    configure_stack()
    unreal.EditorAssetLibrary.save_loaded_asset(system, only_if_is_dirty=False)
    unreal.log("NS_Tracer built.")


main()
