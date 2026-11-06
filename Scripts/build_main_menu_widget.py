"""
Creates WBP_MainMenu in /Game/GameTemplate/Blueprints/WidgetBlueprints/Menu: a full-screen main
menu with a title and START / EXIT buttons.

  START -> Set Input Mode Game Only (player 0), then Open Level (Demo_Level)
  EXIT  -> Quit Game

Run inside the Unreal Editor (Output Log -> Cmd):
    py "E:/Unreal Projects/Game_Template/Scripts/build_main_menu_widget.py"

Refuses to overwrite an existing WBP_MainMenu unless OVERWRITE = True.
"""

import unreal

FOLDER = "/Game/GameTemplate/Blueprints/WidgetBlueprints/Menu"
NAME = "WBP_MainMenu"
START_LEVEL = "/Game/GameTemplate/Demo/Maps/Demo_Level"
TITLE = "GAME TEMPLATE"
OVERWRITE = False

BG_COLOR = unreal.LinearColor(0.012, 0.018, 0.035, 1.0)
ACCENT = unreal.LinearColor(0.05, 0.38, 1.0, 1.0)
TEXT_COLOR = unreal.LinearColor(0.92, 0.95, 1.0, 1.0)

UMG = unreal.UMGToolSet.get_default_object()
BGE = unreal.BlueprintGraphEditor


def umg(fn, *args):
    return UMG.call_method(fn, args)


def add(wbp, cls, name, parent=None):
    info = umg("AddWidget", wbp, cls, name, parent, -1)
    widget = info.get_editor_property("widget")
    if widget is None:
        raise RuntimeError("AddWidget failed for " + name)
    return widget, info.get_editor_property("slot")


def style_text(tb, text, size, color=TEXT_COLOR, letter_spacing=0):
    tb.set_text(text)
    font = tb.get_editor_property("font")
    font.set_editor_property("size", size)
    font.set_editor_property("letter_spacing", letter_spacing)
    tb.set_editor_property("font", font)
    tb.set_color_and_opacity(unreal.SlateColor(color))
    tb.set_editor_property("justification", unreal.TextJustify.CENTER)


def build_tree(wbp):
    root, _ = add(wbp, unreal.CanvasPanel, "Root")

    bg, bg_slot = add(wbp, unreal.Image, "Background", root)
    bg.set_color_and_opacity(BG_COLOR)
    bg_slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0, 0), maximum=unreal.Vector2D(1, 1)))
    bg_slot.set_offsets(unreal.Margin(0, 0, 0, 0))

    box, box_slot = add(wbp, unreal.VerticalBox, "MenuBox", root)
    box_slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0.5, 0.5), maximum=unreal.Vector2D(0.5, 0.5)))
    box_slot.set_alignment(unreal.Vector2D(0.5, 0.5))
    box_slot.set_auto_size(True)

    title, t_slot = add(wbp, unreal.TextBlock, "Title", box)
    style_text(title, TITLE, 72, letter_spacing=200)
    t_slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)

    bar, bar_slot = add(wbp, unreal.Image, "TitleBar", box)
    bar.set_color_and_opacity(ACCENT)
    bar.set_desired_size_override(unreal.Vector2D(420, 4))
    bar_slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
    bar_slot.set_padding(unreal.Margin(0, 12, 0, 64))

    buttons = {}
    for key, label in (("Start", "START"), ("Exit", "EXIT")):
        size, s_slot = add(wbp, unreal.SizeBox, "Size_" + key, box)
        size.set_width_override(380)
        size.set_height_override(76)
        s_slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
        s_slot.set_padding(unreal.Margin(0, 10, 0, 10))

        btn, _ = add(wbp, unreal.Button, "Btn_" + key, size)
        btn.set_background_color(ACCENT if key == "Start" else unreal.LinearColor(0.12, 0.14, 0.2, 1.0))

        txt, txt_slot = add(wbp, unreal.TextBlock, "Txt_" + key, btn)
        style_text(txt, label, 30, letter_spacing=300)
        txt_slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
        txt_slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)

        umg("ToggleWidgetAsVariable", wbp, btn, True)
        buttons[key] = btn
    return buttons


def bound_event(wbp, ed, button_name):
    """OnClicked event node for a button variable."""
    before = set(n.get_name() for n in ed.list_nodes_of_class(unreal.K2Node_ComponentBoundEvent))
    if not umg("BindToEventProperty", wbp, "OnClicked", button_name, unreal.Button):
        raise RuntimeError("BindToEventProperty failed for " + button_name)
    for n in ed.list_nodes_of_class(unreal.K2Node_ComponentBoundEvent):
        if n.get_name() not in before:
            return n
    for n in ed.list_nodes_of_class(unreal.K2Node_ComponentBoundEvent):  # already existed
        if button_name in str(unreal.BlueprintEditorLibrary.get_node_title(n)):
            return n
    raise RuntimeError("Could not find OnClicked node for " + button_name)


def link(a_pin, b_pin, what):
    if a_pin is None or b_pin is None or not a_pin.try_create_connection(b_pin):
        raise RuntimeError("Could not connect " + what)


def then_pin(node):
    return unreal.BlueprintEditorLibrary.find_then_pin(node)


def build_graph(wbp):
    ed = BGE.get_graph_editor(unreal.BlueprintEditorLibrary.find_event_graph(wbp))
    lib = unreal.BlueprintEditorLibrary

    # START: Set Input Mode Game Only (player 0) -> Open Level
    ev = bound_event(wbp, ed, "Btn_Start")
    lib.set_node_pos(ev, unreal.IntPoint(0, 0))
    owner = ed.add_call_function_node("/Script/Engine.GameplayStatics.GetPlayerController")
    lib.set_node_pos(owner, unreal.IntPoint(120, 160))
    mode = ed.add_call_function_node("/Script/UMG.WidgetBlueprintLibrary.SetInputMode_GameOnly")
    lib.set_node_pos(mode, unreal.IntPoint(420, 0))
    open_lvl = ed.add_call_function_node("/Script/Engine.GameplayStatics.OpenLevel")
    lib.set_node_pos(open_lvl, unreal.IntPoint(820, 0))
    lib.find_input_pin(open_lvl, "LevelName").set_pin_value(START_LEVEL)
    link(then_pin(ev), lib.find_execute_pin(mode), "Start -> SetInputMode")
    link(lib.find_result_pin(owner), lib.find_input_pin(mode, "PlayerController"), "PlayerController -> SetInputMode")
    link(then_pin(mode), lib.find_execute_pin(open_lvl), "SetInputMode -> OpenLevel")

    # EXIT: Quit Game
    ev = bound_event(wbp, ed, "Btn_Exit")
    lib.set_node_pos(ev, unreal.IntPoint(0, 400))
    quit_node = ed.add_call_function_node("/Script/Engine.KismetSystemLibrary.QuitGame")
    lib.set_node_pos(quit_node, unreal.IntPoint(420, 400))
    link(then_pin(ev), lib.find_execute_pin(quit_node), "Exit -> QuitGame")


def main():
    path = FOLDER + "/" + NAME
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        if not OVERWRITE:
            unreal.log_warning("[MainMenu] {} already exists - set OVERWRITE = True to rebuild it.".format(path))
            return
        unreal.EditorAssetLibrary.delete_asset(path)
    wbp = umg("CreateWidgetBlueprint", FOLDER, NAME, unreal.UserWidget)
    if wbp is None:
        raise RuntimeError("CreateWidgetBlueprint failed")
    build_tree(wbp)
    umg("CompileWidgetBlueprint", wbp)  # button variables must exist before binding events
    build_graph(wbp)
    ok = umg("CompileWidgetBlueprint", wbp)
    unreal.EditorAssetLibrary.save_loaded_asset(wbp, False)
    unreal.log("[MainMenu] Created {} (compiled: {})".format(path, ok))


if __name__ == "__main__":
    main()
