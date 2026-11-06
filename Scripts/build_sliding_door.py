"""
Sliding door on Blueprints/Doors/BP_SlidingDoor (parent for the demo child doors).

Components: DefaultSceneRoot, Door (the existing SM_Cube, renamed), TriggerInside and
TriggerOutside (Box). Every variable is Instance Editable (category "Sliding Door"):
  DoorClosedLocation / DoorOpenLocation   door positions (relative to the actor)
  TriggerInsideLocation / TriggerOutsideLocation   trigger box positions
  StayOpenTime                            seconds the door waits before closing

Construction Script: place both triggers and the door (closed) from the variables.
Event Graph (no Event Tick):
  Begin Overlap (TriggerInside / TriggerOutside) -> Branch(OtherActor == Player Pawn) -> DoorTimeline.Play
  DoorTimeline.Update   -> Door.SetRelativeLocation(Lerp(Closed, Open, playback position 0..1))
  DoorTimeline.Finished -> Switch on Direction: Forward -> Delay(StayOpenTime) -> DoorTimeline.Reverse
The timeline is 1 second long; its playback position is the 0..1 alpha (Python cannot add
curve tracks to a timeline).

Run once inside the Unreal Editor (Output Log -> Cmd):
    py "E:/Unreal Projects/Game_Template/Scripts/build_sliding_door.py"
It refuses to run if the event graph already has nodes, so hand edits are never overwritten.
"""

import unreal

BP_PATH = "/Game/GameTemplate/Blueprints/Doors/BP_SlidingDoor"
CATEGORY = "Sliding Door"
KML = "/Script/Engine.KismetMathLibrary"
SET_LOC = "/Script/Engine.SceneComponent.K2_SetRelativeLocation"

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


def get_var(ed, name, x, y):
    node = ed.add_get_member_variable_node(name)
    if node is None:
        raise RuntimeError("Could not create getter for " + name)
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


def build_components(bp):
    comps = components(bp)
    if "Door" not in comps:
        handle = comps["StaticMesh"][0]
        SUB.rename_subobject_member_variable(bp, handle, "Door")
        comps = components(bp)
    door = comps["Door"][1]
    door.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)

    root = comps["DefaultSceneRoot"][0]
    for name in ("TriggerInside", "TriggerOutside"):
        if name not in comps:
            handle, fail = SUB.add_new_subobject(unreal.AddNewSubobjectParams(
                parent_handle=root, new_class=unreal.BoxComponent, blueprint_context=bp))
            if not F.is_handle_valid(handle):
                raise RuntimeError("Could not add {}: {}".format(name, fail))
            SUB.rename_subobject_member_variable(bp, handle, name)
    comps = components(bp)
    for name in ("TriggerInside", "TriggerOutside"):
        box = comps[name][1]
        box.set_editor_property("box_extent", unreal.Vector(645.0, 200.0, 150.0))
        box.set_editor_property("hidden_in_game", True)
    return door


def build_variables(bp, door):
    closed = door.get_editor_property("relative_location")
    centre_x = closed.x + 645.0  # SM_Cube pivot is a corner; door is ~1290 wide
    centre_y = closed.y + 15.0
    defaults = {
        "DoorClosedLocation": closed,
        "DoorOpenLocation": unreal.Vector(closed.x, closed.y, closed.z + 700.0),
        "TriggerInsideLocation": unreal.Vector(centre_x, centre_y + 250.0, 150.0),
        "TriggerOutsideLocation": unreal.Vector(centre_x, centre_y - 250.0, 150.0),
        "StayOpenTime": 3.0,
    }
    vec = L.get_struct_type(unreal.Vector.static_struct())
    flt = L.get_basic_type_by_name("real")
    existing = [str(n) for n in L.list_member_variable_names(bp)]
    for name in defaults:
        if name not in existing:
            if not L.add_member_variable(bp, name, flt if name == "StayOpenTime" else vec):
                raise RuntimeError("Could not add " + name)
        L.set_blueprint_variable_instance_editable(bp, name, True)
        L.set_blueprint_variable_category(bp, name, CATEGORY)
    L.compile_blueprint(bp)
    cdo = unreal.get_default_object(bp.generated_class())
    cdo.modify()
    for k, v in defaults.items():
        cdo.set_editor_property(k, v)


def build_construction_script(bp):
    ed = BGE.get_graph_editor(L.find_graph(bp, "UserConstructionScript"))
    entry_pin = ed.find_graph_entry_pin()
    prev = entry_pin
    for i, (comp, var) in enumerate((("TriggerInside", "TriggerInsideLocation"),
                                     ("TriggerOutside", "TriggerOutsideLocation"),
                                     ("Door", "DoorClosedLocation"))):
        x = 300 + i * 360
        node = call(ed, SET_LOC, x, 0)
        link(out(get_var(ed, comp, x - 120, 200)), L.find_self_pin(node), comp + " -> SetRelativeLocation")
        link(out(get_var(ed, var, x - 120, 280)), inp(node, "NewLocation"), var + " -> NewLocation")
        link(prev, L.find_execute_pin(node), "exec -> SetRelativeLocation " + comp)
        prev = L.find_then_pin(node)
    ed.add_comment_to_nodes("Place the triggers and the closed door from the instance editable locations",
                            list(ed.list_all_nodes()), 40)


def build_event_graph(bp):
    ed = BGE.get_graph_editor(L.find_event_graph(bp))
    comps = components(bp)

    timeline = ed.create_node_from_name("||AddTimeline...", unreal.Vector2D(700, 100), [])
    if timeline is None:
        raise RuntimeError("Could not add a Timeline")
    at(timeline, 700, 100)
    L.compile_blueprint(bp)
    tl_name = str(L.get_node_title(timeline))
    template = unreal.find_object(None, "{}:{}_Template".format(bp.generated_class().get_path_name(), tl_name))
    if template is None:
        raise RuntimeError("Could not find the template for timeline " + tl_name)
    template.modify()
    template.set_editor_property("timeline_length", 1.0)

    # both triggers: only the player opens the door
    pawn = call(ed, "/Script/Engine.GameplayStatics.GetPlayerPawn", 0, 220)
    for i, name in enumerate(("TriggerInside", "TriggerOutside")):
        y = i * 360
        ev = at(ed.add_component_bound_event_node(comps[name][1], "OnComponentBeginOverlap"), -400, y)
        same = call(ed, KML + ".EqualEqual_ObjectObject", 250, y + 120)
        check = at(ed.add_branch_node(), 450, y)
        link(out(ev, "OtherActor"), inp(same, "A"), name + " OtherActor -> ==")
        link(L.find_result_pin(pawn), inp(same, "B"), "Player Pawn -> ==")
        link(L.find_result_pin(same), L.find_condition_pin(check), "== -> Branch")
        link(L.find_then_pin(ev), L.find_execute_pin(check), name + " overlap -> Branch")
        link(L.find_then_pin(check), inp(timeline, "Play"), name + " Branch -> Play")

    # Update: move the door between the two locations
    tl_var = get_var(ed, tl_name, 980, 320)
    alpha = call(ed, "/Script/Engine.TimelineComponent.GetPlaybackPosition", 1160, 320)
    closed = get_var(ed, "DoorClosedLocation", 1160, 420)
    opened = get_var(ed, "DoorOpenLocation", 1160, 500)
    lerp = call(ed, KML + ".VLerp", 1420, 380)
    door = get_var(ed, "Door", 1420, 280)
    move = call(ed, SET_LOC, 1680, 100)
    link(out(timeline, "Update"), L.find_execute_pin(move), "Update -> SetRelativeLocation")
    link(out(tl_var), L.find_self_pin(alpha), "Timeline -> GetPlaybackPosition")
    link(L.find_result_pin(alpha), inp(lerp, "Alpha"), "position -> Lerp Alpha")
    link(out(closed), inp(lerp, "A"), "Closed -> Lerp A")
    link(out(opened), inp(lerp, "B"), "Open -> Lerp B")
    link(L.find_result_pin(lerp), inp(move, "NewLocation"), "Lerp -> NewLocation")
    link(out(door), L.find_self_pin(move), "Door -> SetRelativeLocation")

    # Finished going up -> wait -> come back down (Finished after closing does nothing)
    switch = ed.create_node_from_name("Utilities|FlowControl|Switch|SwitchonETimelineDirection",
                                      unreal.Vector2D(1000, 640), [])
    at(switch, 1000, 640)
    delay = call(ed, "/Script/Engine.KismetSystemLibrary.Delay", 1280, 640)
    stay = get_var(ed, "StayOpenTime", 1080, 780)
    link(out(timeline, "Finished"), L.find_execute_pin(switch), "Finished -> Switch")
    link(out(timeline, "Direction"), inp(switch, "Selection"), "Direction -> Switch")
    link(out(switch, "Forward"), L.find_execute_pin(delay), "Forward -> Delay")
    link(out(stay), inp(delay, "Duration"), "StayOpenTime -> Delay")
    link(L.find_then_pin(delay), inp(timeline, "Reverse"), "Delay -> Reverse")
    ed.add_comment_to_nodes("Sliding door - player enters either trigger, door rises, waits StayOpenTime, "
                            "comes down", list(ed.list_all_nodes()), 50)


def main():
    bp = unreal.load_asset(BP_PATH)
    if BGE.get_graph_editor(L.find_event_graph(bp)).list_all_nodes():
        raise RuntimeError("BP_SlidingDoor's event graph already has nodes - not rebuilding over hand edits.")
    door = build_components(bp)
    build_variables(bp, door)
    build_construction_script(bp)
    build_event_graph(bp)
    L.compile_blueprint(bp)
    bad = []
    for g in L.list_graphs(bp):
        ed = BGE.get_graph_editor(g)
        bad += [str(L.get_node_title(n)) for n in list(ed.list_nodes_with_errors()) + list(ed.list_nodes_with_warnings())]
    unreal.EditorAssetLibrary.save_loaded_asset(bp, False)
    unreal.log("[SlidingDoor] done. Problems: {}".format(bad or "none"))


main()
