"""
Pause menu: a parent widget + controller logic in the core GameTemplate/Blueprints
folders, and child Blueprints for the demo.

Core (GameTemplate/Blueprints):
  WidgetBlueprints/Menu/WBP_PauseMenu   PAUSED title, RESUME / EXIT buttons.
      OpenPauseMenu  - add to viewport, pause, show cursor, Game+UI input (focus RESUME)
      Resume         - remove from viewport, unpause, hide cursor, Game-only input
      ExitGame       - unpause, then open ExitLevel if set, otherwise Quit Game
      ExitLevel      - soft World reference (empty = Quit Game); children set it
  Core/BP_PlayerController (existing, nodes added - nothing removed)
      PauseMenuClass - which pause widget to use (default WBP_PauseMenu)
      TogglePauseMenu - creates the widget once, then opens / resumes it
      Escape, P and Gamepad Start call TogglePauseMenu (they fire while paused)

Demo (GameTemplate/Demo):
  Widgets/Menu/WBP_PauseMenu_Child         child of WBP_PauseMenu, ExitLevel = Demo_Menu
  Blueprints/BP_PlayerController_Child     child of BP_PlayerController, PauseMenuClass = WBP_PauseMenu_Child
  Blueprints/BP_Gamemode_Child             child of BP_Gamemode using the demo controller,
                                           BP_ThirdPersonCharacter and BP_HUD_CORE
  Demo_Level's GameMode Override is set to BP_Gamemode_Child (save the level afterwards).

Run inside the Unreal Editor (Output Log -> Cmd):
    py "E:/Unreal Projects/Game_Template/Scripts/build_pause_menu.py"

Existing assets are left alone unless OVERWRITE = True (the controller is always
cleaned of its old pause nodes and rebuilt, the rest of its graph is untouched).
"""

import importlib
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_main_menu_widget as mm  # noqa: E402

importlib.reload(mm)

CORE = "/Game/GameTemplate/Blueprints"
WIDGET = CORE + "/WidgetBlueprints/Menu/WBP_PauseMenu"
CONTROLLER = CORE + "/Core/BP_PlayerController"
GAMEMODE = CORE + "/Core/BP_Gamemode"

DEMO = "/Game/GameTemplate/Demo"
WIDGET_CHILD = DEMO + "/Widgets/Menu/WBP_PauseMenu_Child"
CONTROLLER_CHILD = DEMO + "/Blueprints/BP_PlayerController_Child"
GAMEMODE_CHILD = DEMO + "/Blueprints/BP_Gamemode_Child"
DEMO_LEVEL = DEMO + "/Maps/Demo_Level"
DEMO_EXIT_LEVEL = DEMO + "/Maps/Demo_Menu"
DEMO_PAWN = "/Game/GameTemplate/ThirdPerson/Blueprints/BP_ThirdPersonCharacter"
DEMO_HUD = CORE + "/Core/BP_HUD_CORE"

PAUSE_KEYS = ["Input|KeyboardEvents|Escape", "Input|KeyboardEvents|P", "Input|GamepadEvents|GamepadSpecialRight"]
CATEGORY = "Pause Menu"
OVERWRITE = False

DIM_COLOR = unreal.LinearColor(0.0, 0.0, 0.0, 0.6)
PANEL_COLOR = unreal.LinearColor(0.012, 0.018, 0.035, 0.94)

L = unreal.BlueprintEditorLibrary
BGE = unreal.BlueprintGraphEditor
EAL = unreal.EditorAssetLibrary


# ---------------------------------------------------------------- graph helpers
def pin(node, name, out=False):
    for p in L.list_all_pins(node):
        is_out = p.get_pin_direction() == unreal.EdGraphPinDirection.EGPD_OUTPUT
        if str(p.get_pin_name()) == name and is_out == out:
            return p
    return None


def out_pin(node, name=None):
    """Named output pin, or the first non-exec output (variable gets, pure calls)."""
    if name:
        return pin(node, name, True)
    for p in L.list_all_pins(node):
        if p.get_pin_direction() == unreal.EdGraphPinDirection.EGPD_OUTPUT and str(p.get_pin_name()) != "then":
            return p
    return None


def link(a, b, what):
    mm.link(a, b, what)


def chain(*nodes):
    """Wire exec: each node's then -> the next node's execute."""
    for a, b in zip(nodes, nodes[1:]):
        link(L.find_then_pin(a), L.find_execute_pin(b), "exec {} -> {}".format(L.get_node_title(a), L.get_node_title(b)))


def at(node, x, y):
    L.set_node_pos(node, unreal.IntPoint(x, y))
    return node


def call(ed, path, x, y):
    node = ed.add_call_function_node(path)
    if node is None:
        raise RuntimeError("Could not create call node " + path)
    return at(node, x, y)


def self_call(ed, bp, func, x, y):
    cls = bp.generated_class().get_path_name()
    for path in (cls + ":" + func, cls + "." + func):
        node = ed.add_call_function_node(path)
        if node is not None:
            return at(node, x, y)
    raise RuntimeError("Could not create call to {}.{}".format(cls, func))


def named(ed, name, x, y):
    node = ed.create_node_from_name(name, unreal.Vector2D(x, y), [])
    if node is None:
        raise RuntimeError("Could not create node " + name)
    return at(node, x, y)


def cursor_node(ed, x, y):
    """Set bShowMouseCursor on a PlayerController (connect its Target pin)."""
    node = ed.add_set_member_variable_node("bShowMouseCursor", "/Script/Engine.PlayerController")
    if node is None:
        raise RuntimeError("Could not create Set Show Mouse Cursor")
    return at(node, x, y)


def get_var(ed, name, x, y):
    node = ed.add_get_member_variable_node(name)
    if node is None:
        raise RuntimeError("Could not create getter for " + name)
    return at(node, x, y)


def set_var(ed, name, x, y):
    node = ed.add_set_member_variable_node(name)
    if node is None:
        raise RuntimeError("Could not create setter for " + name)
    return at(node, x, y)


def set_input(node, name, value):
    p = L.find_input_pin(node, name)
    if p is None:
        raise RuntimeError("No pin {} on {}".format(name, L.get_node_title(node)))
    p.set_pin_value(value)


def soft_type(cls_path):
    """EdGraphPinType for a soft object reference (BlueprintEditorLibrary has no helper)."""
    text = L.get_object_reference_type(unreal.UserWidget.static_class()).export_text()
    text = text.replace('PinCategory="object"', 'PinCategory="softobject"')
    text = text.replace("/Script/UMG.UserWidget", cls_path)
    t = unreal.EdGraphPinType()
    t.import_text(text)
    return t


def add_var(bp, name, pin_type, tooltip_category=CATEGORY):
    if name not in [str(n) for n in L.list_member_variable_names(bp)]:
        if not L.add_member_variable(bp, name, pin_type):
            raise RuntimeError("Could not add variable " + name)
    L.set_blueprint_variable_instance_editable(bp, name, True)
    L.set_blueprint_variable_category(bp, name, tooltip_category)


def compile_bp(bp):
    L.compile_blueprint(bp)


def errors(bp):
    bad = []
    for g in L.list_graphs(bp):
        ed = BGE.get_graph_editor(g)
        for n in list(ed.list_nodes_with_errors()) + list(ed.list_nodes_with_warnings()):
            bad.append("{}: {}".format(g.get_name(), L.get_node_title(n)))
    return bad


# ---------------------------------------------------------------- pause widget (core)
def build_widget_tree(wbp):
    add = mm.add
    root, _ = add(wbp, unreal.CanvasPanel, "Root")

    dim, dim_slot = add(wbp, unreal.Image, "Dim", root)
    dim.set_color_and_opacity(DIM_COLOR)
    dim_slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0, 0), maximum=unreal.Vector2D(1, 1)))
    dim_slot.set_offsets(unreal.Margin(0, 0, 0, 0))

    panel, panel_slot = add(wbp, unreal.Border, "Panel", root)
    panel.set_brush_color(PANEL_COLOR)
    panel.set_padding(unreal.Margin(80, 60, 80, 50))
    panel_slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0.5, 0.5), maximum=unreal.Vector2D(0.5, 0.5)))
    panel_slot.set_alignment(unreal.Vector2D(0.5, 0.5))
    panel_slot.set_auto_size(True)

    box, _ = add(wbp, unreal.VerticalBox, "MenuBox", panel)

    title, t_slot = add(wbp, unreal.TextBlock, "Title", box)
    mm.style_text(title, "PAUSED", 56, letter_spacing=200)
    t_slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)

    bar, bar_slot = add(wbp, unreal.Image, "TitleBar", box)
    bar.set_color_and_opacity(mm.ACCENT)
    bar.set_desired_size_override(unreal.Vector2D(320, 4))
    bar_slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
    bar_slot.set_padding(unreal.Margin(0, 10, 0, 44))

    for key, label in (("Resume", "RESUME"), ("Exit", "EXIT")):
        size, s_slot = add(wbp, unreal.SizeBox, "Size_" + key, box)
        size.set_width_override(340)
        size.set_height_override(70)
        s_slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
        s_slot.set_padding(unreal.Margin(0, 8, 0, 8))

        btn, _ = add(wbp, unreal.Button, "Btn_" + key, size)
        btn.set_background_color(mm.ACCENT if key == "Resume" else unreal.LinearColor(0.12, 0.14, 0.2, 1.0))

        txt, txt_slot = add(wbp, unreal.TextBlock, "Txt_" + key, btn)
        mm.style_text(txt, label, 28, letter_spacing=300)
        txt_slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
        txt_slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
        mm.umg("ToggleWidgetAsVariable", wbp, btn, True)


def build_widget_functions(wbp):
    sys_lib, gs, wbl = "/Script/Engine.KismetSystemLibrary", "/Script/Engine.GameplayStatics", "/Script/UMG.WidgetBlueprintLibrary"

    # OpenPauseMenu: AddToViewport -> SetGamePaused(true) -> Game+UI input (focus Resume) -> show cursor
    ed = BGE.create_and_edit_function_graph(wbp, "OpenPauseMenu")
    entry = ed.find_graph_entry_pin().get_owning_node()
    at(entry, 0, 0)
    owner = named(ed, "Widget|GetOwningPlayer", 300, 220)
    add_vp = call(ed, "/Script/UMG.UserWidget.AddToViewport", 300, 0)
    set_input(add_vp, "ZOrder", "100")
    pause = call(ed, gs + ".SetGamePaused", 620, 0)
    set_input(pause, "bPaused", "true")
    mode = call(ed, wbl + ".SetInputMode_GameAndUIEx", 920, 0)
    focus = get_var(ed, "Btn_Resume", 620, 260)
    cursor = cursor_node(ed, 1320, 0)
    set_input(cursor, "bShowMouseCursor", "true")
    link(ed.find_graph_entry_pin(), L.find_execute_pin(add_vp), "entry -> AddToViewport")
    chain(add_vp, pause, mode, cursor)
    link(out_pin(owner), L.find_input_pin(mode, "PlayerController"), "owner -> SetInputMode")
    link(out_pin(focus), L.find_input_pin(mode, "InWidgetToFocus"), "Btn_Resume -> focus")
    link(out_pin(owner), L.find_self_pin(cursor), "owner -> SetShowMouseCursor")

    # Resume: RemoveFromParent -> SetGamePaused(false) -> Game-only input -> hide cursor
    ed = BGE.create_and_edit_function_graph(wbp, "Resume")
    at(ed.find_graph_entry_pin().get_owning_node(), 0, 0)
    owner = named(ed, "Widget|GetOwningPlayer", 600, 220)
    remove = call(ed, "/Script/UMG.Widget.RemoveFromParent", 300, 0)
    pause = call(ed, gs + ".SetGamePaused", 620, 0)
    set_input(pause, "bPaused", "false")
    mode = call(ed, wbl + ".SetInputMode_GameOnly", 920, 0)
    cursor = cursor_node(ed, 1240, 0)
    set_input(cursor, "bShowMouseCursor", "false")
    link(ed.find_graph_entry_pin(), L.find_execute_pin(remove), "entry -> RemoveFromParent")
    chain(remove, pause, mode, cursor)
    link(out_pin(owner), L.find_input_pin(mode, "PlayerController"), "owner -> SetInputMode")
    link(out_pin(owner), L.find_self_pin(cursor), "owner -> SetShowMouseCursor")

    # ExitGame: SetGamePaused(false) -> Branch(ExitLevel valid) -> OpenLevel(ExitLevel) / QuitGame
    ed = BGE.create_and_edit_function_graph(wbp, "ExitGame")
    at(ed.find_graph_entry_pin().get_owning_node(), 0, 0)
    pause = call(ed, gs + ".SetGamePaused", 300, 0)
    set_input(pause, "bPaused", "false")
    level = get_var(ed, "ExitLevel", 300, 260)
    valid = call(ed, sys_lib + ".IsValidSoftObjectReference", 560, 200)
    branch = at(ed.add_branch_node(), 640, 0)
    open_lvl = call(ed, gs + ".OpenLevelBySoftObjectPtr", 940, -120)
    owner = named(ed, "Widget|GetOwningPlayer", 640, 340)
    quit_node = call(ed, sys_lib + ".QuitGame", 940, 160)
    link(ed.find_graph_entry_pin(), L.find_execute_pin(pause), "entry -> SetGamePaused")
    chain(pause, branch)
    link(out_pin(level), L.find_input_pin(valid, "SoftObjectReference"), "ExitLevel -> IsValid")
    link(L.find_result_pin(valid), L.find_condition_pin(branch), "IsValid -> Branch")
    link(L.find_then_pin(branch), L.find_execute_pin(open_lvl), "Branch true -> OpenLevel")
    link(out_pin(level), L.find_input_pin(open_lvl, "Level"), "ExitLevel -> OpenLevel")
    link(L.find_else_pin(branch), L.find_execute_pin(quit_node), "Branch false -> QuitGame")
    link(out_pin(owner), L.find_input_pin(quit_node, "SpecificPlayer"), "owner -> QuitGame")


def build_widget_events(wbp):
    ed = BGE.get_graph_editor(L.find_event_graph(wbp))
    for row, (button, func) in enumerate((("Btn_Resume", "Resume"), ("Btn_Exit", "ExitGame"))):
        ev = at(mm.bound_event(wbp, ed, button), 0, row * 240)
        fn = self_call(ed, wbp, func, 420, row * 240)
        chain(ev, fn)


def build_pause_widget():
    folder, name = WIDGET.rsplit("/", 1)
    wbp = mm.umg("CreateWidgetBlueprint", folder, name, unreal.UserWidget)
    if wbp is None:
        raise RuntimeError("CreateWidgetBlueprint failed for " + WIDGET)
    build_widget_tree(wbp)
    add_var(wbp, "ExitLevel", soft_type("/Script/Engine.World"))
    mm.umg("CompileWidgetBlueprint", wbp)
    build_widget_functions(wbp)
    mm.umg("CompileWidgetBlueprint", wbp)
    build_widget_events(wbp)
    mm.umg("CompileWidgetBlueprint", wbp)
    EAL.save_loaded_asset(wbp, False)
    return wbp


# ---------------------------------------------------------------- player controller (core)
def clean_controller(pc):
    ed = BGE.get_graph_editor(L.find_event_graph(pc))
    toggle = "TogglePauseMenu"
    old = []
    for n in ed.list_nodes_of_class(unreal.K2Node_InputKey):
        if n.get_editor_property("input_key").get_editor_property("key_name") in ("Escape", "P", "Gamepad_Special_Right"):
            old.append(n)
    for n in ed.list_nodes_of_class(unreal.K2Node_CallFunction):
        if toggle in str(L.get_node_title(n)).replace(" ", ""):
            old.append(n)
    if old:
        ed.remove_nodes(old)
    for n in ed.list_comment_nodes():
        if "Pause Menu" in str(L.get_comment_text(n)):
            ed.remove_comment_node(n)
    if L.find_graph(pc, toggle):
        L.remove_function_graph(pc, toggle)
    return len(old)


def build_controller(pc, widget_bp):
    widget_cls = widget_bp.generated_class()
    widget_path = widget_cls.get_path_name()
    add_var(pc, "PauseMenuClass", L.get_class_reference_type(widget_cls))
    add_var(pc, "PauseMenu", L.get_object_reference_type(widget_cls))
    L.set_blueprint_variable_instance_editable(pc, "PauseMenu", False)
    compile_bp(pc)
    unreal.get_default_object(pc.generated_class()).set_editor_property("PauseMenuClass", widget_cls)
    compile_bp(pc)

    # TogglePauseMenu: create the widget once, then open it or resume
    ed = BGE.create_and_edit_function_graph(pc, "TogglePauseMenu")
    at(ed.find_graph_entry_pin().get_owning_node(), 0, 0)
    menu = get_var(ed, "PauseMenu", 60, 200)
    valid = call(ed, "/Script/Engine.KismetSystemLibrary.IsValid", 240, 180)
    has_menu = at(ed.add_branch_node(), 300, 0)
    create = named(ed, "UserInterface|CreateWidget", 600, 180)
    cls = get_var(ed, "PauseMenuClass", 360, 300)
    me = named(ed, "Variables|Getareferencetoself", 360, 400)
    store = set_var(ed, "PauseMenu", 960, 180)
    menu2 = get_var(ed, "PauseMenu", 1200, 260)
    in_vp = call(ed, "/Script/UMG.Widget.IsInViewport", 1240, 140)
    is_open = at(ed.add_branch_node(), 1500, 0)
    resume = self_call(ed, widget_bp, "Resume", 1800, -120)
    open_ = self_call(ed, widget_bp, "OpenPauseMenu", 1800, 140)

    link(ed.find_graph_entry_pin(), L.find_execute_pin(has_menu), "entry -> Branch")
    link(out_pin(menu), L.find_input_pin(valid, "Object"), "PauseMenu -> IsValid")
    link(L.find_result_pin(valid), L.find_condition_pin(has_menu), "IsValid -> Branch")
    link(L.find_else_pin(has_menu), L.find_execute_pin(create), "no menu -> CreateWidget")
    link(out_pin(cls), L.find_input_pin(create, "Class"), "PauseMenuClass -> CreateWidget")
    link(out_pin(me), L.find_input_pin(create, "OwningPlayer"), "self -> CreateWidget")
    chain(create, store)
    link(L.find_result_pin(create), L.find_input_pin(store, "PauseMenu"), "CreateWidget -> Set PauseMenu")
    link(L.find_then_pin(has_menu), L.find_execute_pin(is_open), "has menu -> Branch")
    chain(store, is_open)
    link(out_pin(menu2), L.find_self_pin(in_vp), "PauseMenu -> IsInViewport")
    link(L.find_result_pin(in_vp), L.find_condition_pin(is_open), "IsInViewport -> Branch")
    link(L.find_then_pin(is_open), L.find_execute_pin(resume), "open -> Resume")
    link(L.find_else_pin(is_open), L.find_execute_pin(open_), "closed -> OpenPauseMenu")
    link(out_pin(menu2), L.find_self_pin(resume), "PauseMenu -> Resume")
    link(out_pin(menu2), L.find_self_pin(open_), "PauseMenu -> OpenPauseMenu")
    compile_bp(pc)

    # event graph: pause keys (fire while paused) -> TogglePauseMenu, below the existing nodes
    ed = BGE.get_graph_editor(L.find_event_graph(pc))
    ys = [L.get_node_pos(n).y + L.get_node_size(n).y for n in ed.list_all_nodes()]
    y0 = int(max(ys) if ys else 0) + 300
    keys, calls = [], []
    for i, key in enumerate(PAUSE_KEYS):
        node = named(ed, key, 64, y0 + i * 180)
        node.set_editor_property("execute_when_paused", True)
        keys.append(node)
        fn = self_call(ed, pc, "TogglePauseMenu", 420, y0 + i * 180)
        calls.append(fn)
        link(out_pin(node, "Pressed"), L.find_execute_pin(fn), "{} -> TogglePauseMenu".format(key))
    ed.add_comment_to_nodes("Pause Menu (keys work while paused)", keys + calls, 50)
    compile_bp(pc)
    EAL.save_loaded_asset(pc, False)


# ---------------------------------------------------------------- demo children
def child_blueprint(path, parent_bp, is_widget=False):
    if EAL.does_asset_exist(path):
        bp = unreal.load_asset(path)
        if L.get_blueprint_parent_class(bp) != parent_bp.generated_class():
            raise RuntimeError("{} exists but is not a child of {}".format(path, parent_bp.get_path_name()))
        return bp
    folder, name = path.rsplit("/", 1)
    if is_widget:
        bp = mm.umg("CreateWidgetBlueprint", folder, name, parent_bp.generated_class())
    else:
        bp = L.create_blueprint_asset_with_parent(path, parent_bp.generated_class())
    if bp is None:
        raise RuntimeError("Could not create " + path)
    compile_bp(bp)
    return bp


def set_defaults(bp, **props):
    cdo = unreal.get_default_object(bp.generated_class())
    cdo.modify()
    for k, v in props.items():
        cdo.set_editor_property(k, v)
    # recompile so spawned instances pick the new defaults up (they only copy
    # properties that differed from the parent when the class was compiled)
    compile_bp(bp)
    for k, v in props.items():
        if cdo_value(bp, k) != v:
            raise RuntimeError("{}.{} did not keep its default".format(bp.get_name(), k))
    EAL.save_loaded_asset(bp, False)


def cdo_value(bp, prop):
    return unreal.get_default_object(bp.generated_class()).get_editor_property(prop)


def build_demo(widget_bp, pc):
    w_child = child_blueprint(WIDGET_CHILD, widget_bp, is_widget=True)
    set_defaults(w_child, ExitLevel=unreal.load_asset(DEMO_EXIT_LEVEL))

    pc_child = child_blueprint(CONTROLLER_CHILD, pc)
    set_defaults(pc_child, PauseMenuClass=w_child.generated_class())

    gm_child = child_blueprint(GAMEMODE_CHILD, unreal.load_asset(GAMEMODE))
    set_defaults(gm_child,
                 player_controller_class=pc_child.generated_class(),
                 default_pawn_class=unreal.load_asset(DEMO_PAWN).generated_class(),
                 hud_class=unreal.load_asset(DEMO_HUD).generated_class())

    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] == DEMO_LEVEL:
        settings = world.get_world_settings()
        settings.modify()
        settings.set_editor_property("default_game_mode", gm_child.generated_class())
        unreal.log("[PauseMenu] Demo_Level GameMode Override -> BP_Gamemode_Child (save the level to keep it)")
    else:
        unreal.log_warning("[PauseMenu] Demo_Level is not open - set its GameMode Override to BP_Gamemode_Child by hand.")
    return w_child, pc_child, gm_child


# ---------------------------------------------------------------- main
def main():
    pc = unreal.load_asset(CONTROLLER)
    removed = clean_controller(pc)
    if EAL.does_asset_exist(WIDGET):
        if OVERWRITE:
            for name in ("PauseMenuClass", "PauseMenu"):
                if name in [str(n) for n in L.list_member_variable_names(pc)]:
                    BGE.get_graph_editor(L.find_event_graph(pc)).remove_member_variable(name)
            compile_bp(pc)
            if EAL.does_asset_exist(WIDGET_CHILD):
                EAL.delete_asset(WIDGET_CHILD)
            EAL.delete_asset(WIDGET)
            widget_bp = build_pause_widget()
        else:
            widget_bp = unreal.load_asset(WIDGET)
            unreal.log("[PauseMenu] Keeping existing {} (OVERWRITE = False)".format(WIDGET))
    else:
        widget_bp = build_pause_widget()

    build_controller(pc, widget_bp)
    children = build_demo(widget_bp, pc)

    problems = errors(widget_bp) + errors(pc) + [e for c in children for e in errors(c)]
    unreal.log("[PauseMenu] Done (removed {} old controller nodes). Problems: {}".format(removed, problems or "none"))


if __name__ == "__main__":
    main()
