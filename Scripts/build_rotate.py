"""
Simple rotating mesh on Blueprints/Transforms/BP_Rotate.

Components: DefaultSceneRoot, Mesh (SM_ChamferCube - its pivot is the centre, so it spins in place).
Variable:   RotationSpeed (degrees per second, Instance Editable, category "Rotate").
Event Graph:
  Event Tick -> Add Actor Local Rotation (Yaw = DeltaSeconds * RotationSpeed)
Multiplying by DeltaSeconds keeps the speed the same at any frame rate.

Run once inside the Unreal Editor (Output Log -> Cmd):
    py "E:/Unreal Projects/Game_Template/Scripts/build_rotate.py"
It refuses to run if Event Tick is already wired, so hand edits are never overwritten.
"""

import unreal

BP_PATH = "/Game/GameTemplate/Blueprints/Transforms/BP_Rotate"
MESH = "/Game/GameTemplate/EpicContent/LevelPrototyping/Meshes/SM_ChamferCube"
SPEED = 90.0
KML = "/Script/Engine.KismetMathLibrary"

L = unreal.BlueprintEditorLibrary
BGE = unreal.BlueprintGraphEditor
F = unreal.SubobjectDataBlueprintFunctionLibrary
SUB = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)


def link(a, b, what):
    if a is None or b is None or not a.try_create_connection(b):
        raise RuntimeError("Could not connect " + what)


def at(node, x, y):
    L.set_node_pos(node, unreal.IntPoint(x, y))
    return node


def call(ed, path, x, y):
    node = ed.add_call_function_node(path)
    if node is None:
        raise RuntimeError("Could not create " + path)
    return at(node, x, y)


def out(node, name=None):
    for p in L.list_output_pins(node):
        if (name is None and str(p.get_pin_name()) != "then") or str(p.get_pin_name()) == name:
            return p
    return None


def inp(node, name):
    p = L.find_input_pin(node, name)
    if p is None:
        raise RuntimeError("No pin {} on {}".format(name, L.get_node_title(node)))
    return p


def components(bp):
    found = {}
    for h in SUB.k2_gather_subobject_data_for_blueprint(bp):
        d = F.get_data(h)
        found[str(F.get_variable_name(d))] = (h, F.get_associated_object(d))
    return found


def build_mesh(bp):
    comps = components(bp)
    if "Mesh" not in comps:
        handle, fail = SUB.add_new_subobject(unreal.AddNewSubobjectParams(
            parent_handle=comps["DefaultSceneRoot"][0], new_class=unreal.StaticMeshComponent, blueprint_context=bp))
        if not F.is_handle_valid(handle):
            raise RuntimeError("Could not add Mesh: {}".format(fail))
        SUB.rename_subobject_member_variable(bp, handle, "Mesh")
        comps = components(bp)
    mesh = comps["Mesh"][1]
    mesh.set_editor_property("static_mesh", unreal.load_asset(MESH))
    mesh.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)


def build_variable(bp):
    if "RotationSpeed" not in [str(n) for n in L.list_member_variable_names(bp)]:
        if not L.add_member_variable(bp, "RotationSpeed", L.get_basic_type_by_name("real")):
            raise RuntimeError("Could not add RotationSpeed")
    L.set_blueprint_variable_instance_editable(bp, "RotationSpeed", True)
    L.set_blueprint_variable_category(bp, "RotationSpeed", "Rotate")
    L.compile_blueprint(bp)
    cdo = unreal.get_default_object(bp.generated_class())
    cdo.modify()
    cdo.set_editor_property("RotationSpeed", SPEED)


def find_tick(ed):
    for n in ed.list_nodes_of_class(unreal.K2Node_Event):
        if "Tick" in str(L.get_node_title(n)):
            return n
    return ed.add_event_override("ReceiveTick") if hasattr(ed, "add_event_override") else None


def build_graph(bp, ed, tick):
    x, y = L.get_node_pos(tick).x, L.get_node_pos(tick).y
    speed = at(ed.add_get_member_variable_node("RotationSpeed"), x + 40, y + 200)
    mul = call(ed, KML + ".Multiply_DoubleDouble", x + 300, y + 140)
    rot = call(ed, KML + ".MakeRotator", x + 480, y + 140)
    add = call(ed, "/Script/Engine.Actor.K2_AddActorLocalRotation", x + 760, y)
    link(out(tick, "DeltaSeconds"), inp(mul, "A"), "DeltaSeconds -> Multiply A")
    link(out(speed), inp(mul, "B"), "RotationSpeed -> Multiply B")
    link(L.find_result_pin(mul), inp(rot, "Yaw"), "Multiply -> Yaw")
    link(L.find_result_pin(rot), inp(add, "DeltaRotation"), "MakeRotator -> DeltaRotation")
    link(L.find_then_pin(tick), L.find_execute_pin(add), "Tick -> AddActorLocalRotation")


def main():
    bp = unreal.load_asset(BP_PATH)
    ed = BGE.get_graph_editor(L.find_event_graph(bp))
    tick = find_tick(ed)
    if tick is None:
        raise RuntimeError("No Event Tick node in BP_Rotate")
    if L.find_then_pin(tick).list_connected_pins():
        raise RuntimeError("BP_Rotate's Event Tick is already wired - not rebuilding over hand edits.")
    build_mesh(bp)
    build_variable(bp)
    build_graph(bp, ed, tick)
    L.compile_blueprint(bp)
    bad = [str(L.get_node_title(n)) for n in list(ed.list_nodes_with_errors()) + list(ed.list_nodes_with_warnings())]
    unreal.EditorAssetLibrary.save_loaded_asset(bp, False)
    unreal.log("[Rotate] done. Problems: {}".format(bad or "none"))


main()
