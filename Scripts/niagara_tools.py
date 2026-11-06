"""
Helpers for editing Niagara systems from Python via the NiagaraToolsets plugin.

The toolset functions are AI-callable only (not exposed to Python), so they are run through
ToolsetRegistry.execute_tool with JSON arguments. Stack values are instanced structs:
{"struct": {"refPath": <struct path>}, "value": {...fields...}}.
"""

import json
import unreal

TOOLSET = "NiagaraToolsets.NiagaraToolset_System"
EDITOR = "/Script/NiagaraEditor."
FLOAT = "/Script/Niagara.NiagaraFloat"
INT = "/Script/Niagara.NiagaraInt32"
BOOL = "/Script/Niagara.NiagaraBool"
POSITION = "/Script/Niagara.NiagaraPosition"
COLOR = "/Script/CoreUObject.LinearColor"
VEC2 = "/Script/CoreUObject.Vector2f"
VEC3 = "/Script/CoreUObject.Vector3f"
RANDOM_RANGE_FLOAT = "/Niagara/DynamicInputs/UniformRange/V2/RandomRangeFloat.RandomRangeFloat"


def tool(name, **args):
    """Run a Niagara toolset tool with JSON args and return its decoded result, raising on errors."""
    r = unreal.ToolsetRegistry.execute_tool(TOOLSET, name, json.dumps(args))
    if not r.is_complete:
        raise RuntimeError("%s did not complete synchronously" % name)
    if r.error and str(r.error) not in ("", "None"):
        raise RuntimeError("%s: %s" % (name, r.error))
    result = r.get_value_as_json_string()
    while isinstance(result, str) and result:
        result = json.loads(result)
    return result.get("returnValue", result) if isinstance(result, dict) else result


def asset(path):
    return {"refPath": path}


def value(struct, **fields):
    return {"struct": {"refPath": struct}, "value": fields}


def f(x):
    return value(FLOAT, value=x)


def i(x):
    return value(INT, value=x)


def b(x):
    return value(BOOL, value=-1 if x else 0)


def v2(x, y):
    return value(VEC2, x=x, y=y)


def v3(x, y, z):
    return value(VEC3, x=x, y=y, z=z)


def rgba(r, g, b_, a=1.0):
    return value(COLOR, r=r, g=g, b=b_, a=a)


def enum(enum_path, index):
    """enum_path like "/Niagara/Enums/ENiagara_LifetimeMode"; entries are NewEnumerator<index>."""
    name = enum_path.rsplit("/", 1)[-1]
    return value(EDITOR + "NiagaraExt_StackInputData_Enum", enum=asset("%s.%s" % (enum_path, name)),
                 enumName="%s::NewEnumerator%d" % (name, index), displayName="")


def hlsl(expr):
    return value(EDITOR + "NiagaraExt_StackInputData_HlslExpression", hlslExpression=expr)


def linked(name, type_path):
    return value(EDITOR + "NiagaraExt_StackInputData_Linked",
                 linkedVariable={"name": name, "type": {"classStructOrEnum": asset(type_path)}})


def curve(*keys):
    """Float curve data interface value from (time, value) pairs, linear interpolation."""
    points = [{"interpMode": "RCIM_Linear", "tangentMode": "RCTM_Auto", "time": t, "value": v} for t, v in keys]
    return value(EDITOR + "NiagaraExt_StackInputData_DataInterface",
                 propertyValues=json.dumps({"Curve": {"keys": points}}))


def dynamic(script_path):
    return value(EDITOR + "NiagaraExt_StackInputData_DynamicInput", dynamicInputAsset=asset(script_path))


class System:
    """One Niagara system asset, with stack references scoped to it."""

    def __init__(self, path):
        self.path = path
        self.asset = unreal.load_asset(path)
        if self.asset is None:
            raise RuntimeError("Missing " + path)

    def ref(self, emitter, script="", module="", inputs=(), renderer=-1):
        return {"system": asset(self.path), "emitterName": emitter, "scriptName": script,
                "moduleName": module, "rendererIndex": renderer, "inputNameStack": list(inputs)}

    def emitters(self):
        return [e["emitterName"] for e in tool("GetSystemSummary", system=asset(self.path)).get("emitters", [])]

    def remove_emitter(self, name):
        tool("RemoveEmitter", emitterToRemove=self.ref(name))

    def add_emitter(self, name, template_path):
        tool("AddEmitter", system=asset(self.path), templateEmitter=asset(template_path), emitterName=name)

    def set(self, emitter, script, module, inp, data):
        """inp is an input name, or a list for nested dynamic inputs, e.g. ["Velocity Speed", "Minimum"]."""
        stack = inp if isinstance(inp, (list, tuple)) else [inp]
        tool("SetStackInputData", stackInputRef=self.ref(emitter, script, module, stack), inputData=data)

    def set_random_range(self, emitter, script, module, inp, lo, hi):
        self.set(emitter, script, module, inp, dynamic(RANDOM_RANGE_FLOAT))
        self.set(emitter, script, module, [inp, "Minimum"], f(lo))
        self.set(emitter, script, module, [inp, "Maximum"], f(hi))

    def add_module(self, emitter, script, module_path, after=""):
        """Adds a module after `after` (or at the end of the stack) and returns its module name."""
        added = tool("AddModule", moduleLocationRef=self.ref(emitter, script, after), moduleAsset=asset(module_path))
        return added["moduleName"]

    def remove_module(self, emitter, script, module):
        tool("RemoveModule", moduleToRemove=self.ref(emitter, script, module))

    def set_renderer(self, emitter, index, **props):
        tool("SetRendererData", renderer=self.ref(emitter, renderer=index),
             rendererData={"propertyValues": json.dumps(props)})

    def save(self):
        unreal.EditorAssetLibrary.save_loaded_asset(self.asset, only_if_is_dirty=False)

    def report(self):
        """Logs compile errors and stack warnings/errors; returns True when clean.
        Run it in a separate `py` call after editing: the compile only finishes on later editor ticks."""
        state = tool("GetSystemCompileState", system=asset(self.path))  # waits for an in-flight compile
        issues = tool("GetStackIssues", system=asset(self.path))
        bad = [x for x in issues.get("issues", []) if x.get("severity") in ("Error", "Warning")]
        for x in bad:
            unreal.log_warning("%s %s: %s" % (x["severity"], x.get("stackDisplayPath"), x.get("shortDescription")))
        if state.get("bHasErrors"):
            unreal.log_warning("Compile errors in %s" % self.path)
        return not bad and not state.get("bHasErrors")
