"""
Moving platform on Blueprints/Lifts/BP_Lift (existing Box trigger, StaticMesh and
event-graph glow logic are left untouched).

Adds:
  InterpToMovement component    Behaviour Type = Ping Pong
  StartLocation / EndLocation   Vector, Instance Editable, Expose on Spawn (category "Moving Platform")
  Duration                      Float, Instance Editable
  Construction Script:
      Construction Script -> Set Control Points (InterpToMovement,
                                 Make Array[ Make InterpControlPoint(StartLocation),
                                             Make InterpControlPoint(EndLocation) ])
                          -> Set Duration (InterpToMovement, Duration)

  MoveWhenSteppedOn             Bool, Instance Editable (default False)
      False: Construction Script sets up the looping InterpToMovement (above).
      True:  Construction Script is skipped (Branch) and the Event Graph moves the
             platform instead - see below.
  Event Graph (step-on mode):
      Event BeginPlay -> Set OriginTransform (actor transform)
                      -> Branch(MoveWhenSteppedOn) True -> InterpToMovement.Deactivate
      On Component Begin Overlap (Box) -> Sequence
          Then 0 -> existing glow Timeline (unchanged behaviour)
          Then 1 -> Branch(MoveWhenSteppedOn AND NOT IsMoving AND OtherActor == Player Pawn)
                 -> StartTrip
      Custom Event StartTrip
                 -> Set IsMoving = true
                 -> Move Component To (DefaultSceneRoot,
                        OriginTransform.TransformLocation(AtEnd ? StartLocation : EndLocation),
                        Duration seconds, ease in/out)
                 -> Completed: Set AtEnd = NOT AtEnd -> Set IsMoving = false
                 -> Branch(AtEnd AND ReturnDelay > 0)
                 -> Retriggerable Delay(ReturnDelay)
                 -> Branch(AtEnd AND NOT IsMoving) -> StartTrip   (auto return)
      The trip always runs to the finish point even if the player steps off; stepping
      on again at the finish sends it back to the start. If nobody does within
      ReturnDelay seconds (default 10, 0 = never), it returns by itself.

Control points are relative to the actor, so StartLocation (0,0,0) is where the
platform is placed in the level.

Run inside the Unreal Editor (Output Log -> Cmd):
    py "E:/Unreal Projects/Game_Template/Scripts/build_moving_platform.py"

Safe to re-run: the construction script is cleared and rebuilt; the component and
variables are only created if missing. The event graph is only rebuilt while it is
still the generated version - once it has hand-made custom events (BP_Lift now has
Trigger_Platform) it is left alone and a warning is logged.
"""

import unreal

BP_PATH = "/Game/GameTemplate/Blueprints/Lifts/BP_Lift"
COMPONENT = "InterpToMovement"
CATEGORY = "Moving Platform"
DEFAULTS = {
    "StartLocation": unreal.Vector(0.0, 0.0, 0.0),
    "EndLocation": unreal.Vector(0.0, 0.0, 400.0),
    "Duration": 3.0,
    "MoveWhenSteppedOn": False,
    "ReturnDelay": 10.0,
}
SWITCH = "MoveWhenSteppedOn"
TRIP_EVENT = "StartTrip"
STEP_COMMENT = "Moving Platform - step on to move (MoveWhenSteppedOn = True)"
TRIP_COMMENT = "Moving Platform - step-on trip, auto return after ReturnDelay seconds"
KML = "/Script/Engine.KismetMathLibrary"

L = unreal.BlueprintEditorLibrary
BGE = unreal.BlueprintGraphEditor
F = unreal.SubobjectDataBlueprintFunctionLibrary
EAL = unreal.EditorAssetLibrary


# ---------------------------------------------------------------- helpers
def link(a, b, what):
    if a is None or b is None or not a.try_create_connection(b):
        raise RuntimeError("Could not connect " + what)


def at(node, x, y):
    L.set_node_pos(node, unreal.IntPoint(x, y))
    return node


def named(ed, name, x, y):
    node = ed.create_node_from_name(name, unreal.Vector2D(x, y), [])
    if node is None:
        raise RuntimeError("Could not create node " + name)
    return at(node, x, y)


def call(ed, path, x, y):
    node = ed.add_call_function_node(path)
    if node is None:
        raise RuntimeError("Could not create call node " + path)
    return at(node, x, y)


def set_var(ed, name, x, y, value=None):
    node = ed.add_set_member_variable_node(name)
    if node is None:
        raise RuntimeError("Could not create setter for " + name)
    if value is not None:
        in_pin(node, name).set_pin_value(value)
    return at(node, x, y)


def chain(*nodes):
    for a, b in zip(nodes, nodes[1:]):
        link(L.find_then_pin(a), L.find_execute_pin(b),
             "exec {} -> {}".format(L.get_node_title(a), L.get_node_title(b)))


def get_var(ed, name, x, y):
    node = ed.add_get_member_variable_node(name)
    if node is None:
        raise RuntimeError("Could not create getter for " + name)
    return at(node, x, y)


def out_pin(node, name=None):
    for p in L.list_output_pins(node):
        if name is None and str(p.get_pin_name()) != "then":
            return p
        if name is not None and str(p.get_pin_name()) == name:
            return p
    return None


def in_pin(node, name):
    p = L.find_input_pin(node, name)
    if p is None:
        raise RuntimeError("No input pin {} on {} (has {})".format(
            name, L.get_node_title(node), [str(q.get_pin_name()) for q in L.list_input_pins(node)]))
    return p


# ---------------------------------------------------------------- component
def ensure_component(bp):
    sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sub.k2_gather_subobject_data_for_blueprint(bp)
    for h in handles:
        if str(F.get_variable_name(F.get_data(h))) == COMPONENT:
            comp = F.get_associated_object(F.get_data(h))
            break
    else:
        params = unreal.AddNewSubobjectParams(
            parent_handle=handles[0], new_class=unreal.InterpToMovementComponent, blueprint_context=bp)
        handle, fail = sub.add_new_subobject(params)
        if not F.is_handle_valid(handle):
            raise RuntimeError("Could not add InterpToMovement component: " + str(fail))
        sub.rename_subobject_member_variable(bp, handle, COMPONENT)
        comp = F.get_associated_object(F.get_data(handle))
    comp.modify()
    comp.set_editor_property("behaviour_type", unreal.InterpToBehaviourType.PING_PONG)
    return comp


# ---------------------------------------------------------------- variables
def ensure_variables(bp):
    existing = [str(n) for n in L.list_member_variable_names(bp)]
    vec = L.get_struct_type(unreal.Vector.static_struct())
    flt = L.get_basic_type_by_name("real")
    boolean = L.get_basic_type_by_name("bool")
    xform = L.get_struct_type(unreal.Transform.static_struct())
    editable = (("StartLocation", vec), ("EndLocation", vec), ("Duration", flt), (SWITCH, boolean),
                ("ReturnDelay", flt))
    internal = (("IsMoving", boolean), ("AtEnd", boolean), ("OriginTransform", xform))
    created = []
    for (name, pin_type), is_editable in [(v, True) for v in editable] + [(v, False) for v in internal]:
        if name not in existing:
            if not L.add_member_variable(bp, name, pin_type):
                raise RuntimeError("Could not add variable " + name)
            created.append(name)
        L.set_blueprint_variable_instance_editable(bp, name, is_editable)
        L.set_blueprint_variable_category(bp, name, CATEGORY)
    for name in ("StartLocation", "EndLocation"):
        L.set_blueprint_variable_expose_on_spawn(bp, name, True)
    return created


def set_defaults(bp, names):
    """Only seed defaults for variables this run created, so edited defaults are kept."""
    cdo = unreal.get_default_object(bp.generated_class())
    cdo.modify()
    for k in names:
        if k in DEFAULTS:
            cdo.set_editor_property(k, DEFAULTS[k])


# ---------------------------------------------------------------- construction script
def build_construction_script(bp):
    ed = BGE.get_graph_editor(L.find_graph(bp, "UserConstructionScript"))
    entry_pin = ed.find_graph_entry_pin()
    entry = entry_pin.get_owning_node()
    old = [n for n in ed.list_all_nodes() if n != entry]
    if old:
        ed.remove_nodes(old)
    for c in ed.list_comment_nodes():
        ed.remove_comment_node(c)
    at(entry, 0, 0)

    switch = get_var(ed, SWITCH, -40, 140)
    branch = at(ed.add_branch_node(), 200, 0)
    interp_a = get_var(ed, COMPONENT, 200, 160)
    set_points = named(ed, "Class|InterptoMovementComponent|SetControlPoints", 480, 0)
    make_array = named(ed, "Utilities|Array|MakeArray", 140, 300)
    if not ed.add_node_pin(make_array):
        raise RuntimeError("Could not add a second pin to Make Array")
    make_start = named(ed, "Utilities|Struct|MakeInterpControlPoint", -260, 260)
    make_end = named(ed, "Utilities|Struct|MakeInterpControlPoint", -260, 440)
    start = get_var(ed, "StartLocation", -520, 280)
    end = get_var(ed, "EndLocation", -520, 460)

    set_duration = named(ed, "Class|InterptoMovementComponent|SetDuration", 880, 0)
    interp_b = get_var(ed, COMPONENT, 620, 200)
    duration = get_var(ed, "Duration", 620, 300)

    # exec: only build the looping movement when the step-on mode is off
    link(entry_pin, L.find_execute_pin(branch), "Construction Script -> Branch")
    link(out_pin(switch), L.find_condition_pin(branch), "MoveWhenSteppedOn -> Branch")
    link(L.find_else_pin(branch), L.find_execute_pin(set_points), "Branch False -> Set Control Points")
    link(L.find_then_pin(set_points), L.find_execute_pin(set_duration), "Set Control Points -> Set Duration")

    # Set Control Points (array first so Make Array resolves its type)
    link(out_pin(interp_a), L.find_self_pin(set_points), "InterpToMovement -> Set Control Points")
    link(out_pin(make_array, "Array"), in_pin(set_points, "ControlPoints"), "Make Array -> Control Points")
    link(out_pin(make_start), in_pin(make_array, "[0]"), "Start point -> [0]")
    link(out_pin(make_end), in_pin(make_array, "[1]"), "End point -> [1]")
    link(out_pin(start), in_pin(make_start, "PositionControlPoint"), "StartLocation -> Position")
    link(out_pin(end), in_pin(make_end, "PositionControlPoint"), "EndLocation -> Position")

    # Set Duration
    link(out_pin(interp_b), L.find_self_pin(set_duration), "InterpToMovement -> Set Duration")
    link(out_pin(duration), in_pin(set_duration, "Duration"), "Duration -> Set Duration")

    ed.add_comment_to_nodes("Moving Platform - ping pong between Start and End Location "
                            "(skipped when MoveWhenSteppedOn is ticked)",
                            list(ed.list_all_nodes()), 50)


# ---------------------------------------------------------------- event graph (step-on mode)
def overlap_event(ed):
    for n in ed.list_nodes_of_class(unreal.K2Node_ComponentBoundEvent):
        if str(L.get_node_title(n)).startswith("On Component Begin Overlap (Box)"):
            return n
    raise RuntimeError("BP_Lift has no 'On Component Begin Overlap (Box)' event")


def trip_event_nodes(ed):
    return [n for n in ed.list_nodes_of_class(unreal.K2Node_CustomEvent)
            if str(L.get_node_title(n)).replace(" ", "") == TRIP_EVENT]


def call_trip(ed, bp, x, y):
    cls = bp.generated_class().get_path_name()
    for path in (cls + ":" + TRIP_EVENT, cls + "." + TRIP_EVENT):
        node = ed.add_call_function_node(path)
        if node is not None:
            return at(node, x, y)
    raise RuntimeError("Could not create a call to " + TRIP_EVENT)


def clean_event_graph(ed, overlap):
    """Remove what a previous run added; the original glow nodes are kept."""
    then = L.find_then_pin(overlap)
    seeds = []
    for p in then.list_connected_pins():
        node = p.get_owning_node()
        if isinstance(node, unreal.K2Node_ExecutionSequence):
            first = out_pin(node, "then_0")
            targets = list(first.list_connected_pins()) if first else []
            then.break_pin_links()
            for t in targets:
                link(then, t, "restore overlap -> " + str(L.get_node_title(t.get_owning_node())))
            seeds.append(node)
    begin = ed.find_event_node("ReceiveBeginPlay")
    if begin:
        seeds.append(begin)
    seeds.extend(trip_event_nodes(ed))
    keep = {overlap.get_name()}
    keep.update(t.get_owning_node().get_name() for t in then.list_connected_pins())
    found, todo = {}, list(seeds)
    while todo:
        n = todo.pop()
        if n.get_name() in found or n.get_name() in keep:
            continue
        found[n.get_name()] = n
        for p in L.list_all_pins(n):
            todo.extend(q.get_owning_node() for q in p.list_connected_pins())
    if found:
        ed.remove_nodes(list(found.values()))
    for c in ed.list_comment_nodes():
        if str(L.get_comment_text(c)) in (STEP_COMMENT, TRIP_COMMENT):
            ed.remove_comment_node(c)


def build_event_graph(bp):
    ed = BGE.get_graph_editor(L.find_event_graph(bp))
    hand_made = [str(L.get_node_title(n)) for n in ed.list_nodes_of_class(unreal.K2Node_CustomEvent)
                 if n not in trip_event_nodes(ed)]
    if hand_made:
        # The event graph was reorganised by hand (e.g. the Trigger_Platform custom event).
        # Rebuilding would add a second trigger/trip next to it, so leave it alone.
        unreal.log_warning("[MovingPlatform] Event graph has hand-made events {} - not rebuilding it."
                           .format(hand_made))
        return
    overlap = overlap_event(ed)
    clean_event_graph(ed, overlap)

    ys = [L.get_node_pos(n).y + L.get_node_size(n).y for n in ed.list_all_nodes()]
    x0, y0 = -300, int(max(ys)) + 250
    ox = L.get_node_pos(overlap).x

    # BeginPlay: remember where the platform starts; switch the looping component off in step-on mode
    begin = named(ed, "AddEvent|EventBeginPlay", x0, y0)
    transform = call(ed, "/Script/Engine.Actor.GetTransform", x0 + 40, y0 + 160)
    store = set_var(ed, "OriginTransform", x0 + 320, y0)
    switch_a = get_var(ed, SWITCH, x0 + 560, y0 + 160)
    is_step = at(ed.add_branch_node(), x0 + 700, y0)
    interp = get_var(ed, COMPONENT, x0 + 900, y0 + 160)
    deactivate = call(ed, "/Script/Engine.ActorComponent.Deactivate", x0 + 1000, y0)
    chain(begin, store, is_step)
    link(L.find_result_pin(transform) or out_pin(transform), in_pin(store, "OriginTransform"), "GetTransform -> OriginTransform")
    link(out_pin(switch_a), L.find_condition_pin(is_step), "MoveWhenSteppedOn -> Branch")
    link(L.find_then_pin(is_step), L.find_execute_pin(deactivate), "Branch True -> Deactivate")
    link(out_pin(interp), L.find_self_pin(deactivate), "InterpToMovement -> Deactivate")

    # StartTrip custom event first, then compile so the class has a function to call
    y2 = y0 + 1100
    trip = ed.add_custom_event_node(TRIP_EVENT)
    if trip is None:
        raise RuntimeError("Could not create custom event " + TRIP_EVENT)
    at(trip, x0, y2)
    L.compile_blueprint(bp)

    # Overlap: keep the glow Timeline on Then 0, step-on trigger on Then 1
    then = L.find_then_pin(overlap)
    old_targets = list(then.list_connected_pins())
    then.break_pin_links()
    seq = named(ed, "Utilities|FlowControl|Sequence", ox + 260, L.get_node_pos(overlap).y)
    link(then, L.find_execute_pin(seq), "Overlap -> Sequence")
    for t in old_targets:
        link(out_pin(seq, "then_0"), t, "Sequence 0 -> " + str(L.get_node_title(t.get_owning_node())))

    y1 = y0 + 420
    pawn = call(ed, "/Script/Engine.GameplayStatics.GetPlayerPawn", x0, y1 + 200)
    is_player = call(ed, KML + ".EqualEqual_ObjectObject", x0 + 300, y1 + 140)
    moving = get_var(ed, "IsMoving", x0 + 40, y1 + 340)
    not_moving = call(ed, KML + ".Not_PreBool", x0 + 300, y1 + 320)
    switch_b = get_var(ed, SWITCH, x0 + 300, y1 + 440)
    all_true = call(ed, KML + ".BooleanAND", x0 + 560, y1 + 200)
    if not ed.add_node_pin(all_true):
        raise RuntimeError("Could not add a third pin to AND")
    can_move = at(ed.add_branch_node(), x0 + 800, y1)
    step_trip = call_trip(ed, bp, x0 + 1060, y1)

    link(out_pin(seq, "then_1"), L.find_execute_pin(can_move), "Sequence 1 -> Branch")
    link(out_pin(overlap, "OtherActor"), in_pin(is_player, "A"), "OtherActor -> ==")
    link(L.find_result_pin(pawn), in_pin(is_player, "B"), "PlayerPawn -> ==")
    link(out_pin(moving), in_pin(not_moving, "A"), "IsMoving -> NOT")
    link(L.find_result_pin(is_player), in_pin(all_true, "A"), "== -> AND")
    link(L.find_result_pin(not_moving), in_pin(all_true, "B"), "NOT -> AND")
    and_pins = [p for p in L.list_input_pins(all_true) if not p.list_connected_pins()]
    link(out_pin(switch_b), and_pins[0], "MoveWhenSteppedOn -> AND")
    link(L.find_result_pin(all_true), L.find_condition_pin(can_move), "AND -> Branch")
    link(L.find_then_pin(can_move), L.find_execute_pin(step_trip), "Branch True -> StartTrip")
    trigger = [pawn, is_player, moving, not_moving, switch_b, all_true, can_move, step_trip]

    # StartTrip: move to the other end, then auto return after ReturnDelay
    start_trip = set_var(ed, "IsMoving", x0 + 300, y2, "true")
    root = get_var(ed, "DefaultSceneRoot", x0 + 300, y2 + 520)
    rotation = call(ed, "/Script/Engine.SceneComponent.K2_GetComponentRotation", x0 + 560, y2 + 560)
    origin = get_var(ed, "OriginTransform", x0 + 60, y2 + 260)
    start = get_var(ed, "StartLocation", x0 + 20, y2 + 340)
    end = get_var(ed, "EndLocation", x0 + 20, y2 + 420)
    at_end = get_var(ed, "AtEnd", x0 + 20, y2 + 500)
    pick = call(ed, KML + ".SelectVector", x0 + 260, y2 + 340)
    target = call(ed, KML + ".TransformLocation", x0 + 540, y2 + 260)
    dur = get_var(ed, "Duration", x0 + 560, y2 + 680)

    move = call(ed, "/Script/Engine.KismetSystemLibrary.MoveComponentTo", x0 + 860, y2)
    in_pin(move, "bEaseIn").set_pin_value("true")
    in_pin(move, "bEaseOut").set_pin_value("true")
    at_end_b = get_var(ed, "AtEnd", x0 + 1160, y2 + 200)
    flip = call(ed, KML + ".Not_PreBool", x0 + 1320, y2 + 200)
    arrived = set_var(ed, "AtEnd", x0 + 1500, y2)
    finish_trip = set_var(ed, "IsMoving", x0 + 1780, y2, "false")

    link(L.find_then_pin(trip), L.find_execute_pin(start_trip), "StartTrip -> Set IsMoving")
    link(L.find_then_pin(start_trip), in_pin(move, "Move"), "Set IsMoving -> Move Component To")
    link(out_pin(root), in_pin(move, "Component"), "DefaultSceneRoot -> Move Component To")
    link(out_pin(root), L.find_self_pin(rotation), "DefaultSceneRoot -> GetWorldRotation")
    link(L.find_result_pin(rotation), in_pin(move, "TargetRelativeRotation"), "rotation -> Move Component To")
    link(out_pin(start), in_pin(pick, "A"), "StartLocation -> Select A")
    link(out_pin(end), in_pin(pick, "B"), "EndLocation -> Select B")
    link(out_pin(at_end), in_pin(pick, "bPickA"), "AtEnd -> Select")
    link(out_pin(origin), in_pin(target, "T"), "OriginTransform -> TransformLocation")
    link(L.find_result_pin(pick), in_pin(target, "Location"), "Select -> TransformLocation")
    link(L.find_result_pin(target), in_pin(move, "TargetRelativeLocation"), "target -> Move Component To")
    link(out_pin(dur), in_pin(move, "OverTime"), "Duration -> Over Time")

    link(L.find_then_pin(move), L.find_execute_pin(arrived), "Completed -> Set AtEnd")
    link(out_pin(at_end_b), in_pin(flip, "A"), "AtEnd -> NOT")
    link(L.find_result_pin(flip), in_pin(arrived, "AtEnd"), "NOT -> Set AtEnd")
    chain(arrived, finish_trip)

    # Arrived at the finish and ReturnDelay > 0 -> wait (retriggerable, so a fresh
    # arrival restarts the countdown) -> still at the finish and idle -> go back
    at_end_c = get_var(ed, "AtEnd", x0 + 1800, y2 + 200)
    delay_a = get_var(ed, "ReturnDelay", x0 + 1800, y2 + 300)
    has_delay = call(ed, KML + ".Greater_DoubleDouble", x0 + 2020, y2 + 300)
    should_wait = call(ed, KML + ".BooleanAND", x0 + 2240, y2 + 200)
    wait_branch = at(ed.add_branch_node(), x0 + 2080, y2)
    delay_b = get_var(ed, "ReturnDelay", x0 + 2300, y2 + 380)
    wait = call(ed, "/Script/Engine.KismetSystemLibrary.RetriggerableDelay", x0 + 2380, y2)
    at_end_d = get_var(ed, "AtEnd", x0 + 2640, y2 + 200)
    moving_b = get_var(ed, "IsMoving", x0 + 2640, y2 + 300)
    idle = call(ed, KML + ".Not_PreBool", x0 + 2860, y2 + 300)
    still_there = call(ed, KML + ".BooleanAND", x0 + 3060, y2 + 200)
    return_branch = at(ed.add_branch_node(), x0 + 2960, y2)
    auto_trip = call_trip(ed, bp, x0 + 3260, y2)

    link(L.find_then_pin(finish_trip), L.find_execute_pin(wait_branch), "Set IsMoving -> Branch")
    link(out_pin(delay_a), in_pin(has_delay, "A"), "ReturnDelay -> >")
    in_pin(has_delay, "B").set_pin_value("0.0")
    link(out_pin(at_end_c), in_pin(should_wait, "A"), "AtEnd -> AND")
    link(L.find_result_pin(has_delay), in_pin(should_wait, "B"), "> -> AND")
    link(L.find_result_pin(should_wait), L.find_condition_pin(wait_branch), "AND -> Branch")
    link(L.find_then_pin(wait_branch), L.find_execute_pin(wait), "Branch True -> Retriggerable Delay")
    link(out_pin(delay_b), in_pin(wait, "Duration"), "ReturnDelay -> Delay Duration")
    link(L.find_then_pin(wait), L.find_execute_pin(return_branch), "Delay Completed -> Branch")
    link(out_pin(moving_b), in_pin(idle, "A"), "IsMoving -> NOT")
    link(out_pin(at_end_d), in_pin(still_there, "A"), "AtEnd -> AND")
    link(L.find_result_pin(idle), in_pin(still_there, "B"), "NOT -> AND")
    link(L.find_result_pin(still_there), L.find_condition_pin(return_branch), "AND -> Branch")
    link(L.find_then_pin(return_branch), L.find_execute_pin(auto_trip), "Branch True -> StartTrip")

    ed.add_comment_to_nodes(STEP_COMMENT, [begin, transform, store, switch_a, is_step, interp, deactivate]
                            + trigger, 50)
    ed.add_comment_to_nodes(TRIP_COMMENT, [trip, start_trip, root, rotation, origin, start, end, at_end, pick,
                                           target, dur, move, at_end_b, flip, arrived, finish_trip, at_end_c,
                                           delay_a, has_delay, should_wait, wait_branch, delay_b, wait,
                                           at_end_d, moving_b, idle, still_there, return_branch, auto_trip], 50)


def problems(bp):
    bad = []
    for g in L.list_graphs(bp):
        ed = BGE.get_graph_editor(g)
        for n in list(ed.list_nodes_with_errors()) + list(ed.list_nodes_with_warnings()):
            bad.append("{}: {}".format(g.get_name(), L.get_node_title(n)))
    return bad


def main():
    bp = unreal.load_asset(BP_PATH)
    if bp is None:
        raise RuntimeError("Missing " + BP_PATH)
    ensure_component(bp)
    created = ensure_variables(bp)
    L.compile_blueprint(bp)
    set_defaults(bp, created)
    build_construction_script(bp)
    build_event_graph(bp)
    L.compile_blueprint(bp)
    EAL.save_loaded_asset(bp, False)
    unreal.log("[MovingPlatform] BP_Lift done. Problems: {}".format(problems(bp) or "none"))
    unreal.log("[MovingPlatform] Tick 'Show 3D Widget' on StartLocation/EndLocation by hand "
               "(no Python API for that flag).")


main()
