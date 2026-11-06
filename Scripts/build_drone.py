"""
Patrol / attack drone on Blueprints/NPCs/BP_Drone (Pawn).

Components (root -> children):
  CollisionSphere (root, r=30, Pawn) - travels along the navmesh at ground level
    VisualRoot (Scene, Z = HoverHeight + bob)
      StaticMesh (body), Booster, Booster2, Muzzle_L, Muzzle_R
  FloatingPawnMovement (Max Speed 400)
Class defaults: AI Controller = AIController, Auto Possess AI = Placed in World or Spawned.

State enum E_DroneState (copied from E_Basic_Example): NewEnumerator0 = Patrol,
NewEnumerator1 = Attack, NewEnumerator2 = Dead.

Event Graph:
  BeginPlay   -> StartLocation, Health = MaxHealth, State = Patrol, Patrol, SetHostile(bHostile)
  Patrol      -> Delay(random pause) -> [Patrol only] random reachable point -> AI MoveTo
                 -> On Success / On Fail -> Patrol
  CheckPlayer (timer 0.2s, hostile only) -> Patrol: in DetectionRange -> StartAttack
                                            Attack: beyond LoseRange   -> StopAttack
  StartAttack -> State = Attack, stop moving, ShotsLeft = BurstCount, FireShot
  StopAttack  -> State = Patrol, Patrol
  FireShot    -> [Attack + hostile] line of sight -> hitscan from alternating muzzle with cone
                 spread, flash, sound, impact, Apply Damage -> next shot after FireRate, or
                 BurstCooldown after BurstCount shots
  Tick        -> hover bob on VisualRoot, smooth yaw towards travel direction / player,
                 booster glow
  AnyDamage   -> Health -= Damage -> at 0: State = Dead, stop, explosion, destroy
Function SetHostile(NewHostile): sets bHostile + tint, starts/stops the detection timer and
drops back to Patrol when switched to friendly mid-attack.
Construction Script: VisualRoot height + booster Dynamic Material Instance tinted red/green.

Run once inside the Unreal Editor (Output Log -> Cmd):
    py "E:/Unreal Projects/Game_Template/Scripts/build_drone.py"
It refuses to run if BP_Drone already has drone variables or wired events.
"""

import unreal

BP_PATH = "/Game/GameTemplate/Blueprints/NPCs/BP_Drone"
ENUM_PATH = "/Game/GameTemplate/Blueprints/Enum/E_DroneState"
ENUM_SOURCE = "/Game/GameTemplate/Blueprints/Enum/E_Basic_Example"
EMISSIVE_MI = "/Game/GameTemplate/MaterialLibrary/MI_Emissive_Inst"
SPARKS = "/Game/GameTemplate/EpicContent/StarterContent/Particles/P_Sparks.P_Sparks"
EXPLOSION = "/Game/GameTemplate/EpicContent/StarterContent/Particles/P_Explosion.P_Explosion"
EXPLOSION_SOUND = "/Game/GameTemplate/EpicContent/StarterContent/Audio/Explosion_Cue.Explosion_Cue"
PATROL, ATTACK, DEAD = "NewEnumerator0", "NewEnumerator1", "NewEnumerator2"
CAMERA_CHANNEL = "TraceTypeQuery2"  # Visibility is ignored by the player's capsule and mesh

KML = "/Script/Engine.KismetMathLibrary."
KSL = "/Script/Engine.KismetSystemLibrary."
GPS = "/Script/Engine.GameplayStatics."
ACTOR = "/Script/Engine.Actor."
SCENE = "/Script/Engine.SceneComponent."
PRIM = "/Script/Engine.PrimitiveComponent."
MID = "/Script/Engine.MaterialInstanceDynamic."

L = unreal.BlueprintEditorLibrary
BGE = unreal.BlueprintGraphEditor
F = unreal.SubobjectDataBlueprintFunctionLibrary
SUB = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
EA = unreal.EditorAssetLibrary

VARIABLES = [  # name, type, default, category (None = internal)
    ("bHostile", "bool", True, "General"),
    ("PatrolRadius", "real", 1500.0, "Patrol"),
    ("PatrolPauseMin", "real", 0.5, "Patrol"),
    ("PatrolPauseMax", "real", 2.0, "Patrol"),
    ("AcceptanceRadius", "real", 100.0, "Patrol"),
    ("HoverHeight", "real", 250.0, "Hover"),
    ("HoverBobHeight", "real", 15.0, "Hover"),
    ("HoverBobSpeed", "real", 2.0, "Hover"),
    ("DetectionRange", "real", 1500.0, "Combat"),
    ("LoseRange", "real", 1800.0, "Combat"),
    ("FireRate", "real", 0.1, "Combat"),
    ("BurstCount", "int", 8, "Combat"),
    ("BurstCooldown", "real", 1.5, "Combat"),
    ("Damage", "real", 5.0, "Combat"),
    ("Spread", "real", 3.0, "Combat"),
    ("TurnSpeed", "real", 4.0, "Combat"),
    ("MaxHealth", "real", 100.0, "Combat"),
    ("State", "enum", None, None),
    ("StartLocation", "vector", None, None),
    ("Health", "real", 100.0, None),
    ("ShotsLeft", "int", 0, None),
    ("bUseLeftMuzzle", "bool", True, None),
    ("DetectTimer", "timer", None, None),
    ("BoosterMID", "mid", None, None),
]
EVENTS = ["Patrol", "CheckPlayer", "StartAttack", "StopAttack", "FireShot"]


# ---------------------------------------------------------------- graph helpers

class G:
    """Small wrapper around one graph: create nodes at a position and wire pins."""

    def __init__(me, bp, graph):
        me.bp = bp
        me.ed = BGE.get_graph_editor(graph)

    @staticmethod
    def at(node, x, y):
        L.set_node_pos(node, unreal.IntPoint(int(x), int(y)))
        return node

    def call(me, path, x, y, **pins):
        node = me.ed.add_call_function_node(path)
        if node is None:
            raise RuntimeError("Could not create " + path)
        me.at(node, x, y)
        me.pins(node, **pins)
        return node

    def node(me, type_id, x, y, **pins):
        node = me.ed.create_node_from_name(type_id, unreal.Vector2D(x, y), [])
        if node is None:
            raise RuntimeError("Could not create " + type_id)
        me.at(node, x, y)
        me.pins(node, **pins)
        return node

    def get(me, name, x, y):
        node = me.ed.add_get_member_variable_node(name)
        if node is None:
            raise RuntimeError("Could not create getter for " + name)
        return out(me.at(node, x, y))

    def set(me, name, x, y, value=None):
        node = me.ed.add_set_member_variable_node(name)
        if node is None:
            raise RuntimeError("Could not create setter for " + name)
        me.at(node, x, y)
        if value is not None:
            me.pins(node, **{name: value})
        return node

    def branch(me, x, y, cond):
        node = me.at(me.ed.add_branch_node(), x, y)
        connect(cond, L.find_condition_pin(node), "Branch condition")
        return node

    def switch(me, x, y, state_pin):
        node = me.node("Utilities|FlowControl|Switch|SwitchonE_DroneState", x, y)
        connect(state_pin, inp(node, "Selection"), "Switch selection")
        return node

    def self_ref(me, x, y):
        return out(me.node("Variables|Getareferencetoself", x, y))

    def event_call(me, name, x, y, **pins):
        return me.call(me.bp.generated_class().get_path_name() + ":" + name, x, y, **pins)

    def pins(me, node, **pins):
        for name, value in pins.items():
            pin = inp(node, name)
            if isinstance(value, unreal.BlueprintGraphPin):
                connect(value, pin, name)
            else:
                if isinstance(value, bool):
                    value = "true" if value else "false"
                pin.set_pin_value(str(value))


def connect(a, b, what):
    if a is None or b is None or not a.try_create_connection(b):
        raise RuntimeError("Could not connect " + what)


def inp(node, name):
    pin = L.find_input_pin(node, name)
    if pin is None:
        raise RuntimeError("No input pin {} on {}".format(name, L.get_node_title(node)))
    return pin


def out(node, name=None):
    for p in L.list_output_pins(node):
        n = str(p.get_pin_name())
        if (name is None and n not in ("then", "OutputDelegate")) or n == name:
            return p
    raise RuntimeError("No output pin {} on {}".format(name, L.get_node_title(node)))


def ex(a, b):
    """Wire exec: a is a node (its Then pin) or an exec output pin; b is a node."""
    a_pin = a if isinstance(a, unreal.BlueprintGraphPin) else L.find_then_pin(a)
    connect(a_pin, L.find_execute_pin(b), "exec -> " + str(L.get_node_title(b)))


def true_pin(branch):
    return L.find_then_pin(branch)


def false_pin(branch):
    return L.find_else_pin(branch)


# ---------------------------------------------------------------- setup

def components(bp):
    found = {}
    for h in SUB.k2_gather_subobject_data_for_blueprint(bp):
        d = F.get_data(h)
        found.setdefault(str(F.get_variable_name(d)), (h, F.get_associated_object(d)))
    return found


def add_component(bp, parent_handle, cls, name):
    handle, fail = SUB.add_new_subobject(unreal.AddNewSubobjectParams(
        parent_handle=parent_handle, new_class=cls, blueprint_context=bp))
    if not F.is_handle_valid(handle):
        raise RuntimeError("Could not add {}: {}".format(name, fail))
    SUB.rename_subobject_member_variable(bp, handle, name)
    return handle


def build_components(bp):
    comps = components(bp)
    actor_handle = comps["None"][0]
    sphere = add_component(bp, comps["DefaultSceneRoot"][0], unreal.SphereComponent, "CollisionSphere")
    if not SUB.make_new_scene_root(actor_handle, sphere, bp):
        raise RuntimeError("Could not make CollisionSphere the root")
    visual = add_component(bp, sphere, unreal.SceneComponent, "VisualRoot")
    comps = components(bp)
    for name in ("StaticMesh", "Booster", "Booster2"):
        if not SUB.attach_subobject(visual, comps[name][0]):
            raise RuntimeError("Could not move {} under VisualRoot".format(name))
    add_component(bp, visual, unreal.SceneComponent, "Muzzle_L")
    add_component(bp, visual, unreal.SceneComponent, "Muzzle_R")
    add_component(bp, actor_handle, unreal.FloatingPawnMovement, "FloatingPawnMovement")

    comps = components(bp)
    if "DefaultSceneRoot" in comps:
        SUB.delete_subobject(actor_handle, comps["DefaultSceneRoot"][0], bp)
    sphere_c = comps["CollisionSphere"][1]
    sphere_c.set_editor_property("sphere_radius", 30.0)
    sphere_c.set_collision_profile_name("Pawn")
    comps["VisualRoot"][1].set_editor_property("relative_location", unreal.Vector(0, 0, 250))
    # SM_Cube's pivot is a corner: centre the body over VisualRoot, keep the boosters' offsets.
    for name, loc in (("StaticMesh", (-22.0, -50.0, -10.0)), ("Booster", (-18.6, -60.0, -10.0)),
                      ("Booster2", (1.4, -60.0, -10.0)), ("Muzzle_L", (30.0, -40.0, -5.0)),
                      ("Muzzle_R", (30.0, 40.0, -5.0))):
        comps[name][1].set_editor_property("relative_location", unreal.Vector(*loc))
    comps["FloatingPawnMovement"][1].set_editor_property("max_speed", 400.0)


def pin_type(kind):
    if kind == "enum":
        t = L.get_basic_type_by_name("byte")
        t.import_text(t.export_text().replace(
            "PinSubCategoryObject=None", 'PinSubCategoryObject="{0}.E_DroneState"'.format(ENUM_PATH)))
        return t
    if kind == "vector":
        return L.get_struct_type(unreal.Vector.static_struct())
    if kind == "timer":
        return L.get_struct_type(unreal.TimerHandle.static_struct())
    if kind == "mid":
        return L.get_object_reference_type(unreal.MaterialInstanceDynamic.static_class())
    return L.get_basic_type_by_name(kind)


def build_variables(bp):
    for name, kind, _, category in VARIABLES:
        if not L.add_member_variable(bp, name, pin_type(kind)):
            raise RuntimeError("Could not add variable " + name)
        if category:
            L.set_blueprint_variable_instance_editable(bp, name, True)
            L.set_blueprint_variable_category(bp, name, category)
    L.set_blueprint_variable_expose_on_spawn(bp, "bHostile", True)


def set_defaults(bp):
    cdo = unreal.get_default_object(bp.generated_class())
    cdo.modify()
    for name, kind, default, _ in VARIABLES:
        if default is not None:
            cdo.set_editor_property(name, default)
    cdo.set_editor_property("ai_controller_class", unreal.AIController.static_class())
    cdo.set_editor_property("auto_possess_ai", unreal.AutoPossessAI.PLACED_IN_WORLD_OR_SPAWNED)


def build_entry_points(bp):
    """Custom events, AnyDamage and the SetHostile function, so the graphs can call them."""
    ed = BGE.get_graph_editor(L.find_event_graph(bp))
    for name in EVENTS:
        if ed.add_custom_event_node(name) is None:
            raise RuntimeError("Could not add custom event " + name)
    if L.add_event_override(bp, "ReceiveAnyDamage", unreal.IntPoint(0, 0)) is None:
        raise RuntimeError("Could not add Event AnyDamage")
    fn = L.add_function_graph(bp, "SetHostile")
    BGE.get_graph_editor(fn).add_graph_input_parameter("NewHostile", L.get_basic_type_by_name("bool"))
    L.compile_blueprint(bp)


def event_node(ed, title_part):
    for n in ed.list_nodes_of_class(unreal.K2Node_Event):
        if title_part in str(L.get_node_title(n)):
            return n
    raise RuntimeError("No event node " + title_part)


# ---------------------------------------------------------------- graphs

def build_construction_script(bp):
    g = G(bp, L.find_graph(bp, "UserConstructionScript"))
    entry = g.ed.find_graph_entry_pin()
    height = g.call(KML + "MakeVector", 120, 180, Z=g.get("HoverHeight", -80, 220))
    place = g.call(SCENE + "K2_SetRelativeLocation", 300, 0, self=g.get("VisualRoot", 100, 100),
                   NewLocation=out(height))
    connect(entry, L.find_execute_pin(place), "Construction -> VisualRoot height")
    # optional tint: one Dynamic Material Instance shared by both boosters
    mid = g.call(PRIM + "CreateDynamicMaterialInstance", 620, 0, self=g.get("Booster", 440, 120),
                 ElementIndex=0, SourceMaterial=unreal.load_asset(EMISSIVE_MI).get_path_name())
    store = g.set("BoosterMID", 940, 0, out(mid))
    share = g.call(PRIM + "SetMaterial", 1200, 0, self=g.get("Booster2", 1020, 140),
                   ElementIndex=0, Material=out(store))
    tint = g.call(MID + "SetVectorParameterValue", 1500, 0, self=g.get("BoosterMID", 1300, 160),
                  ParameterName="Emissive Tint", Value=tint_color(g, 1300, 240))
    for a, b in ((place, mid), (mid, store), (store, share), (share, tint)):
        ex(a, b)
    g.ed.add_comment_to_nodes("Hover height + (optional) red/green booster tint",
                              list(g.ed.list_all_nodes()), 40)


def tint_color(g, x, y):
    sel = g.call(KML + "SelectColor", x, y, A="(R=1.0,G=0.05,B=0.02,A=1.0)",
                 B="(R=0.05,G=1.0,B=0.1,A=1.0)", bPickA=g.get("bHostile", x - 180, y + 120))
    return out(sel)


def build_set_hostile(bp):
    g = G(bp, L.find_graph(bp, "SetHostile"))
    entry = g.ed.find_graph_entry_pin()
    entry_node = entry.get_owning_node()
    store = g.set("bHostile", 300, 0, out(entry_node, "NewHostile"))
    connect(entry, L.find_execute_pin(store), "SetHostile entry -> set")
    tint = g.call(MID + "SetVectorParameterValue", 560, 0, self=g.get("BoosterMID", 380, 160),
                  ParameterName="Emissive Tint", Value=tint_color(g, 380, 240))
    check = g.branch(900, 0, g.get("bHostile", 760, 140))
    timer = g.call(KSL + "K2_SetTimer", 1140, -120, FunctionName="CheckPlayer", Time=0.2, bLooping=True)
    keep = g.set("DetectTimer", 1460, -120, out(timer))
    clear = g.call(KSL + "K2_ClearAndInvalidateTimerHandle", 1140, 200, Handle=g.get("DetectTimer", 960, 320))
    sw = g.switch(1460, 200, g.get("State", 1300, 320))
    stop = g.event_call("StopAttack", 1760, 200)
    ex(store, tint)
    ex(tint, check)
    ex(true_pin(check), timer)
    ex(timer, keep)
    ex(false_pin(check), clear)
    ex(clear, sw)
    ex(out(sw, ATTACK), stop)
    g.ed.add_comment_to_nodes("SetHostile - hostile starts the 0.2s detection timer, friendly stops it "
                              "and leaves Attack", list(g.ed.list_all_nodes()), 40)


def section(g, comment, before):
    new = [n for n in g.ed.list_all_nodes() if n.get_name() not in before]
    g.ed.add_comment_to_nodes(comment, new, 40)
    return set(n.get_name() for n in g.ed.list_all_nodes())


def build_event_graph(bp):
    g = G(bp, L.find_event_graph(bp))
    ed = g.ed
    customs = {str(L.get_node_title(n)).split("\n")[0]: n for n in ed.list_nodes_of_class(unreal.K2Node_CustomEvent)}
    seen = set(n.get_name() for n in ed.list_all_nodes())

    # --- BeginPlay (row 0)
    begin = G.at(event_node(ed, "BeginPlay"), 0, 0)
    s1 = g.set("StartLocation", 300, 0, out(g.call(ACTOR + "K2_GetActorLocation", 100, 160)))
    s2 = g.set("Health", 560, 0, g.get("MaxHealth", 420, 160))
    s3 = g.set("State", 800, 0, PATROL)
    c1 = g.event_call("Patrol", 1040, 0)
    c2 = g.event_call("SetHostile", 1280, 0, NewHostile=g.get("bHostile", 1120, 140))
    for a, b in ((begin, s1), (s1, s2), (s2, s3), (s3, c1), (c1, c2)):
        ex(a, b)
    seen = section(g, "BeginPlay - remember the patrol origin, full health, start patrolling, "
                      "SetHostile starts detection only when hostile", seen)

    # --- Patrol (row 1)
    y = 500
    ev = G.at(customs["Patrol"], 0, y)
    pause = g.call(KSL + "Delay", 300, y, Duration=out(g.call(
        KML + "RandomFloatInRange", 80, y + 160, Min=g.get("PatrolPauseMin", -140, y + 160),
        Max=g.get("PatrolPauseMax", -140, y + 240))))
    sw = g.switch(560, y, g.get("State", 420, y + 160))
    point = g.call("/Script/NavigationSystem.NavigationSystemV1.K2_GetRandomReachablePointInRadius",
                   800, y + 160, Origin=g.get("StartLocation", 600, y + 220),
                   Radius=g.get("PatrolRadius", 600, y + 300))
    move = g.node("AI|AIMoveTo", 1100, y, Destination=out(point, "RandomLocation"),
                  AcceptanceRadius=g.get("AcceptanceRadius", 900, y + 340))
    again = g.event_call("Patrol", 1450, y + 40)
    ex(ev, pause)
    ex(pause, sw)
    ex(out(sw, PATROL), move)
    ex(out(move, "OnSuccess"), again)
    ex(out(move, "OnFail"), again)
    connect(g.self_ref(900, y + 100), inp(move, "Pawn"), "Self -> AI MoveTo Pawn")
    seen = section(g, "Patrol - random pause, then (if still patrolling) move to a random reachable point "
                      "around StartLocation. Success or fail -> Patrol again, so it never locks up", seen)

    # --- CheckPlayer (row 2)
    y = 1100
    ev = G.at(customs["CheckPlayer"], 0, y)
    hostile = g.branch(260, y, g.get("bHostile", 100, y + 140))
    friendly = g.event_call("SetHostile", 560, y + 260, NewHostile=False)
    sw = g.switch(560, y, g.get("State", 400, y + 140))
    dist = out(g.call(ACTOR + "GetDistanceTo", 600, y + 420,
                      OtherActor=out(g.call(GPS + "GetPlayerPawn", 360, y + 460))))
    near = g.branch(900, y - 80, out(g.call(KML + "Less_DoubleDouble", 760, y + 40, A=dist,
                                            B=g.get("DetectionRange", 560, y + 560))))
    far = g.branch(900, y + 200, out(g.call(KML + "Greater_DoubleDouble", 760, y + 320, A=dist,
                                            B=g.get("LoseRange", 560, y + 620))))
    start = g.event_call("StartAttack", 1160, y - 80)
    stop = g.event_call("StopAttack", 1160, y + 200)
    ex(ev, hostile)
    ex(true_pin(hostile), sw)
    ex(false_pin(hostile), friendly)
    ex(out(sw, PATROL), near)
    ex(out(sw, ATTACK), far)
    ex(true_pin(near), start)
    ex(true_pin(far), stop)
    seen = section(g, "CheckPlayer - every 0.2s while hostile. Attack inside DetectionRange, only give up "
                      "beyond LoseRange (no flicker at the edge). bHostile changed directly -> SetHostile(false)", seen)

    # --- StartAttack / StopAttack (row 3)
    y = 1900
    ev = G.at(customs["StartAttack"], 0, y)
    s1 = g.set("State", 260, y, ATTACK)
    halt = g.call("/Script/Engine.Controller.StopMovement", 520, y, self=out(g.call(
        "/Script/AIModule.AIBlueprintHelperLibrary.GetAIController", 300, y + 160,
        ControlledActor=g.self_ref(120, y + 180))))
    s2 = g.set("ShotsLeft", 780, y, g.get("BurstCount", 620, y + 160))
    fire = g.event_call("FireShot", 1040, y)
    for a, b in ((ev, s1), (s1, halt), (halt, s2), (s2, fire)):
        ex(a, b)
    ev = G.at(customs["StopAttack"], 0, y + 320)
    s3 = g.set("State", 260, y + 320, PATROL)
    back = g.event_call("Patrol", 520, y + 320)
    ex(ev, s3)
    ex(s3, back)
    seen = section(g, "StartAttack - stop moving and hover, start a burst  /  StopAttack - back to Patrol "
                      "(FireShot stops itself once State is not Attack)", seen)

    # --- FireShot (row 4)
    y = 2600
    ev = G.at(customs["FireShot"], 0, y)
    sw = g.switch(260, y, g.get("State", 100, y + 140))
    hostile = g.branch(520, y, g.get("bHostile", 380, y + 140))
    pawn = out(g.call(GPS + "GetPlayerPawn", 560, y + 520))
    player_loc = out(g.call(ACTOR + "K2_GetActorLocation", 780, y + 520, self=pawn))
    los = g.call(KSL + "LineTraceSingle", 820, y, TraceChannel=CAMERA_CHANNEL,
                 Start=out(g.call(SCENE + "K2_GetComponentLocation", 620, y + 300,
                                  self=g.get("VisualRoot", 440, y + 320))),
                 End=player_loc)
    los_hit = g.call(GPS + "BreakHitResult", 1100, y + 300, Hit=out(los, "OutHit"))
    visible = g.branch(1400, y, out(g.call(KML + "EqualEqual_ObjectObject", 1280, y + 180,
                                           A=out(los_hit, "HitActor"), B=pawn)))
    retry = g.call(KSL + "K2_SetTimer", 1700, y + 700, FunctionName="FireShot",
                   Time=g.get("FireRate", 1500, y + 820))
    muzzle = out(g.call(KML + "SelectVector", 1500, y + 300,
                        A=out(g.call(SCENE + "K2_GetComponentLocation", 1300, y + 400, self=g.get("Muzzle_L", 1140, y + 420))),
                        B=out(g.call(SCENE + "K2_GetComponentLocation", 1300, y + 500, self=g.get("Muzzle_R", 1140, y + 520))),
                        bPickA=g.get("bUseLeftMuzzle", 1300, y + 600)))
    spread = out(g.call(KML + "RandomUnitVectorInConeInDegrees", 1760, y + 380,
                        # aim from the drone centre so both barrels fire parallel instead of converging
                        ConeDir=out(g.call(KML + "GetDirectionUnitVector", 1560, y + 480, From=out(g.call(
                            SCENE + "K2_GetComponentLocation", 1400, y + 640, self=g.get("VisualRoot", 1240, y + 660))),
                            To=player_loc)),
                        ConeHalfAngleInDegrees=g.get("Spread", 1560, y + 580)))
    shot_end = out(g.call(KML + "Add_VectorVector", 2000, y + 300, A=muzzle, B=out(g.call(
        KML + "Multiply_VectorFloat", 1980, y + 420, A=spread, B=g.get("LoseRange", 1820, y + 520)))))
    shot = g.call(KSL + "LineTraceSingle", 2200, y, TraceChannel=CAMERA_CHANNEL, Start=muzzle, End=shot_end)
    flash = g.call(GPS + "SpawnEmitterAtLocation", 2550, y, EmitterTemplate=SPARKS, Location=muzzle,
                   Scale="0.3,0.3,0.3")
    sound = g.call(GPS + "PlaySoundAtLocation", 2850, y, Location=muzzle)  # placeholder: pick a gun sound
    hit = g.branch(3150, y, out(shot, "ReturnValue"))
    shot_hit = g.call(GPS + "BreakHitResult", 3150, y + 300, Hit=out(shot, "OutHit"))
    impact = g.call(GPS + "SpawnEmitterAtLocation", 3450, y - 200, EmitterTemplate=SPARKS,
                    Location=out(shot_hit, "ImpactPoint"), Scale="0.5,0.5,0.5")
    damage = g.call(GPS + "ApplyDamage", 3750, y - 200, DamagedActor=out(shot_hit, "HitActor"),
                    BaseDamage=g.get("Damage", 3600, y - 20), DamageCauser=g.self_ref(3600, y + 40))
    toggle = g.set("bUseLeftMuzzle", 4050, y, out(g.call(KML + "Not_PreBool", 3900, y + 160,
                                                       A=g.get("bUseLeftMuzzle", 3740, y + 180))))
    count = g.set("ShotsLeft", 4300, y, out(g.call(KML + "Subtract_IntInt", 4160, y + 160,
                                                   A=g.get("ShotsLeft", 4000, y + 220), B=1)))
    more = g.branch(4550, y, out(g.call(KML + "Greater_IntInt", 4420, y + 160,
                                        A=g.get("ShotsLeft", 4260, y + 260), B=0)))
    next_shot = g.call(KSL + "K2_SetTimer", 4800, y - 160, FunctionName="FireShot",
                       Time=g.get("FireRate", 4640, y - 40))
    reload_ = g.set("ShotsLeft", 4800, y + 200, g.get("BurstCount", 4640, y + 340))
    cooldown = g.call(KSL + "K2_SetTimer", 5050, y + 200, FunctionName="FireShot",
                      Time=g.get("BurstCooldown", 4880, y + 360))
    ex(ev, sw)
    ex(out(sw, ATTACK), hostile)
    ex(true_pin(hostile), los)
    ex(los, visible)
    ex(false_pin(visible), retry)
    ex(true_pin(visible), shot)
    for a, b in ((shot, flash), (flash, sound), (sound, hit), (impact, damage), (toggle, count), (count, more)):
        ex(a, b)
    ex(true_pin(hit), impact)
    ex(damage, toggle)
    ex(false_pin(hit), toggle)
    ex(true_pin(more), next_shot)
    ex(false_pin(more), reload_)
    ex(reload_, cooldown)
    seen = section(g, "FireShot - only while attacking and hostile. Line of sight on the Camera channel, "
                      "then a hitscan shot from alternating muzzles with cone Spread. Next shot after "
                      "FireRate, or BurstCooldown after BurstCount shots", seen)

    # --- Tick (row 5)
    y = 3700
    tick = G.at(event_node(ed, "Tick"), 0, y)
    bob = g.call(KML + "Multiply_DoubleDouble", 340, y + 300, A=out(g.call(KML + "Sin", 200, y + 300, A=out(
        g.call(KML + "Multiply_DoubleDouble", 60, y + 300, A=out(g.call(GPS + "GetTimeSeconds", -160, y + 300)),
               B=g.get("HoverBobSpeed", -160, y + 380))))), B=g.get("HoverBobHeight", 200, y + 420))
    height = g.call(KML + "MakeVector", 600, y + 220, Z=out(g.call(
        KML + "Add_DoubleDouble", 480, y + 300, A=g.get("HoverHeight", 340, y + 220), B=out(bob))))
    hover = g.call(SCENE + "K2_SetRelativeLocation", 800, y, self=g.get("VisualRoot", 620, y + 120),
                   NewLocation=out(height))
    sw = g.switch(1120, y, g.get("State", 960, y + 140))
    moving = g.branch(1400, y - 160, out(g.call(KML + "Greater_DoubleDouble", 1280, y - 20, A=out(g.call(
        KML + "VSize", 1140, y - 20, A=out(g.call(ACTOR + "GetVelocity", 980, y - 20)))), B=10)))
    delta = out(tick, "DeltaSeconds")

    def face(x, yy, target_rot):
        yaw = out(g.call(KML + "BreakRotator", x - 340, yy + 200, InRot=target_rot), "Yaw")
        interp = g.call(KML + "RInterpTo", x - 140, yy + 200,
                        Current=out(g.call(ACTOR + "K2_GetActorRotation", x - 340, yy + 120)),
                        Target=out(g.call(KML + "MakeRotator", x - 200, yy + 320, Yaw=yaw)),
                        DeltaTime=delta, InterpSpeed=g.get("TurnSpeed", x - 340, yy + 400))
        return g.call(ACTOR + "K2_SetActorRotation", x, yy, NewRotation=out(interp))

    turn_travel = face(1900, y - 300, out(g.call(KML + "Conv_VectorToRotator", 1360, y - 100,
                                                 InVec=out(g.call(ACTOR + "GetVelocity", 1200, y - 100)))))
    turn_player = face(1900, y + 400, out(g.call(KML + "FindLookAtRotation", 1360, y + 600,
                                                 Start=out(g.call(ACTOR + "K2_GetActorLocation", 1160, y + 580)),
                                                 Target=out(g.call(ACTOR + "K2_GetActorLocation", 1160, y + 680,
                                                                   self=out(g.call(GPS + "GetPlayerPawn", 960, y + 700)))))))
    bright = g.call(MID + "SetScalarParameterValue", 2300, y - 100, self=g.get("BoosterMID", 2140, y + 40),
                    ParameterName="Emissive Strength", Value=80)
    dim = g.call(MID + "SetScalarParameterValue", 2300, y + 160, self=g.get("BoosterMID", 2140, y + 300),
                 ParameterName="Emissive Strength", Value=20)
    ex(tick, hover)
    ex(hover, sw)
    ex(out(sw, PATROL), moving)
    ex(true_pin(moving), turn_travel)
    ex(false_pin(moving), dim)
    ex(out(sw, ATTACK), turn_player)
    ex(turn_travel, bright)
    ex(turn_player, bright)
    seen = section(g, "Tick - hover bob on VisualRoot only, smooth yaw towards the travel direction (Patrol) or "
                      "the player (Attack), (optional) boosters glow while moving or attacking", seen)

    # --- AnyDamage (row 6)
    y = 4900
    hurt = G.at(event_node(ed, "AnyDamage"), 0, y)
    sw = g.switch(260, y, g.get("State", 100, y + 140))
    s1 = g.set("Health", 560, y, out(g.call(KML + "Subtract_DoubleDouble", 420, y + 160,
                                            A=g.get("Health", 260, y + 200), B=out(hurt, "Damage"))))
    dead = g.branch(820, y, out(g.call(KML + "LessEqual_DoubleDouble", 700, y + 160,
                                       A=g.get("Health", 560, y + 200), B=0)))
    s2 = g.set("State", 1080, y, DEAD)
    halt = g.call("/Script/Engine.Controller.StopMovement", 1340, y, self=out(g.call(
        "/Script/AIModule.AIBlueprintHelperLibrary.GetAIController", 1140, y + 160,
        ControlledActor=g.self_ref(980, y + 180))))
    boom_at = out(g.call(SCENE + "K2_GetComponentLocation", 1440, y + 220, self=g.get("VisualRoot", 1280, y + 260)))
    boom = g.call(GPS + "SpawnEmitterAtLocation", 1640, y, EmitterTemplate=EXPLOSION, Location=boom_at)
    bang = g.call(GPS + "PlaySoundAtLocation", 1940, y, Sound=EXPLOSION_SOUND, Location=boom_at)
    gone = g.call(ACTOR + "K2_DestroyActor", 2240, y)
    ex(hurt, sw)
    ex(out(sw, PATROL), s1)
    ex(out(sw, ATTACK), s1)
    ex(s1, dead)
    ex(true_pin(dead), s2)
    for a, b in ((s2, halt), (halt, boom), (boom, bang), (bang, gone)):
        ex(a, b)
    section(g, "AnyDamage - friendly and hostile drones both take damage. At 0: Dead, stop, explode, destroy", seen)
    G.at(event_node(ed, "ActorBeginOverlap"), 0, 5500)


def main():
    bp = unreal.load_asset(BP_PATH)
    if "bHostile" in [str(n) for n in L.list_member_variable_names(bp)]:
        raise RuntimeError("BP_Drone already has the drone variables - not rebuilding over hand edits.")
    if not EA.does_asset_exist(ENUM_PATH):
        EA.duplicate_asset(ENUM_SOURCE, ENUM_PATH)
        EA.save_asset(ENUM_PATH, False)
    build_components(bp)
    build_variables(bp)
    L.compile_blueprint(bp)
    set_defaults(bp)
    build_entry_points(bp)
    build_construction_script(bp)
    build_set_hostile(bp)
    build_event_graph(bp)
    L.compile_blueprint(bp)
    problems = []
    for graph in L.list_graphs(bp):
        ed = BGE.get_graph_editor(graph)
        problems += [str(L.get_node_title(n)) for n in list(ed.list_nodes_with_errors()) + list(ed.list_nodes_with_warnings())]
    EA.save_loaded_asset(bp, False)
    unreal.log("[Drone] done. Problems: {}".format(problems or "none"))


main()
