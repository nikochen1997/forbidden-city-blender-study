"""Isolated caller-context factory audit; root alone runs Blender, no native I/O."""
import argparse
import ast
from collections import Counter
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import traceback

import bpy
from mathutils import Matrix, Vector

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PINS = {
    "work/restoration-v17/context_geometry_v2.py": "c4e74d847dbcef9723728c7d7404fbaad5039341281302c340da5704d082611f",
    "work/restoration-v17/profiles/building-profiles-v3.json": "6bfd22e012990bf49d074ad7df0846ee2d7e4393b469b12cf4b00aed2efcc0c4",
    "work/restoration-v17/registration/registered-buildings.json": "0ff859b0e1434e9ee1c0501aa2f301fd6b8416e85e32a5c2b525f9e3c18479bc",
    "work/restoration-v17/registration/front-entry-context/source-context.json": "65726e73a8cdf2a33b7f39cae30f60febd834bc55600fef108e9080f6d76337f",
    "work/restoration-v17/registration/front-entry-context/concrete-profile-binding-v3.json": "5eba96383820c7a582ef2e75996de1f2c0391b4f393af8ddf76627681d076e46",
    "work/forbidden_city_geometry.py": "23f815fc93057a0f69b66adc25536485fc05a33935f67fb1613073963e276efc",
    "work/imperial_monuments.py": "5af7e855072559b74e5b05964cad0a50420b04e152de8fc04428049ee993f47e",
    "work/restoration_buildings.py": "aac18ca8c219b8de544dd78d8a7b99000a4d0fe83d40553614065e0c998aaf60",
    "work/restoration-v16/saved-audit/saved_audit_core.py": "72d1fc4253231380ae8db9784a3b6a81a3f66307170e4003e85837d5a68e6ae0",
    "work/build_forbidden_city_restoration_v11.py": "1ccce3fcca040d311f6c48fc52cd38cf053d484e627e20f03ad2f4a1c9eeb130",
    "work/restoration-v8/module-research/copy-boolean/test_copy_boolean.py": "57e52b7bddf5de246a3b31e3c2c2916ed07bbfeda579104d0bf11d741907e2ed",
    "work/restoration-v12/registration/probe_saved_v11.py": "001745cdd60cac927eb248304a84ee550ab291810bde7e359115afb2e9cc404c",
}


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, value):
    require(not p.exists(), "preserve previous actual evidence")
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pure_functions(path, names):
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in names]
    require({n.name for n in nodes} == names, "pure capture helper inventory")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), globals())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--front-readout", type=Path, required=True)
    parser.add_argument("--front-readout-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = args.output_dir.resolve()
    require(out.is_relative_to(HERE) and not out.exists(), "fresh context-qa output directory required")
    require(not bpy.data.filepath, "factory startup required; never open native")
    files = {str((ROOT / p).resolve()): digest for p, digest in PINS.items()}
    files[str(args.front_readout.resolve())] = args.front_readout_sha256
    files[str(Path(__file__).resolve())] = sha(__file__)
    for p, expected in files.items():
        require(sha(p) == expected, "frozen input drift " + p)
    out.mkdir(parents=True)
    registry = json.loads((ROOT / "work/restoration-v17/registration/registered-buildings.json").read_text())
    source = json.loads((ROOT / "work/restoration-v17/registration/front-entry-context/source-context.json").read_text())
    binding_path = ROOT / "work/restoration-v17/registration/front-entry-context/concrete-profile-binding-v3.json"
    binding = json.loads(binding_path.read_text())
    front = json.loads((ROOT / "work/restoration-v17/profiles/building-profiles-v3.json").read_text())["buildings"][0]
    front_rows = [r for r in json.loads(args.front_readout.read_text())["buildings"] if r["id"] == "shufang_front_hall"]
    require(len(front_rows) == 1 and front_rows[0]["profile"] == front, "actual earlier front profile differs from current front")
    opening_rows = [r for r in front_rows[0]["openings"] if r["id"] == binding["expected_front_opening_control"]["id"]]
    require(len(opening_rows) == 1, "actual earlier front central row missing/duplicated")
    pure_functions(ROOT / "work/restoration-v8/module-research/copy-boolean/test_copy_boolean.py", {"safe", "digest", "material_digest", "slots"})
    pure_functions(ROOT / "work/restoration-v12/registration/probe_saved_v11.py", {"visibility", "bounds", "evaluated", "record_actor", "material_record"})
    C = load("v17_context_audit_core", ROOT / "work/restoration-v16/saved-audit/saved_audit_core.py")
    sys.path.insert(0, str(ROOT / "work"))
    import forbidden_city_geometry as F
    import restoration_buildings as R
    module = load("v17_caller_context_factory", ROOT / "work/restoration-v17/context_geometry_v2.py")
    F.create_materials()
    materials = R.restoration_materials(F.create_materials("R17_"))
    expected = source["actual_actor_evidence"]
    for name, e in source["actual_material_evidence"].items():
        require(material_record(bpy.data.materials[name]) == e, "source fixture effective material differs " + name)
    mesh = bpy.data.meshes.new(expected["data_name"])
    mesh.from_pydata(expected["raw_vertices"], [], expected["raw_faces"])
    mesh.update()
    for link, name in expected["actual_material_slots"]:
        require(link == "DATA", "source fixture non-DATA slot not supported")
        mesh.materials.append(bpy.data.materials[name])
    for face, index in zip(mesh.polygons, expected["raw_face_material_indices"]):
        face.material_index = index
    original = bpy.data.objects.new(source["original_object"], mesh)
    for row in expected["collections"]:
        col = F.ensure_collection(row["name"])
        col.hide_render, col.hide_viewport = row["hide_render"], row["hide_viewport"]
        col.objects.link(original)
    original.matrix_world = Matrix(expected["matrix_world"])
    original.color = expected["object_rgba"]
    for k, value in expected["custom_properties"].items():
        original[k] = value
    root = bpy.data.objects.new("V17_FRONT_FRAME_FROM_ACTUAL_PROFILE", None)
    bpy.context.scene.collection.objects.link(root)
    root.location = front["anchor"]
    root.rotation_euler.z = front["rotation_z_rad"]
    root["not_historical_mesh"] = True
    root["actual_opening_source_readout_sha256"] = args.front_readout_sha256
    collection = F.ensure_collection("V17_CALLER_CONTEXT_FACTORY_ONLY")
    bpy.context.view_layer.update()
    before = record_actor(original)
    for key, value in before.items():
        require(value == expected[key], "source reconstruction differs from actual source field " + key)
    source_static = copy.deepcopy(before)
    source_static.pop("visibility")
    source_materials = {name: material_record(bpy.data.materials[name]) for name in source["actual_material_evidence"]}
    reader = C.MeshReader(bpy)
    checks, results, extra_ray_targets = [], {}, []
    def case(ident, operation, wanted, fn):
        try:
            evidence = fn()
            checks.append({"id": ident, "input": "pinned actual-source fixture, current registry/binding, actual earlier front row", "operation": operation, "expected": wanted, "passed": True, "evidence": evidence})
            print("PASS", ident, flush=True)
        except Exception as exc:
            checks.append({"id": ident, "operation": operation, "expected": wanted, "passed": False, "error": str(exc), "traceback": traceback.format_exc()})
            print("FAIL", ident, str(exc), flush=True)
    def build_components():
        results["components"] = module.build_components(registry, collection, materials)
        reader.refresh()
        return {"groups": len(results["components"]), "objects": sum(len(r["objects"]) for r in results["components"])}
    def build_portal():
        results["portal"] = module.build_front_entry(binding, original, {"root": root, "openings": front_rows[0]["openings"]}, collection)
        original.hide_render = True
        original.hide_set(True)
        reader.refresh()
        return {"replacement": results["portal"]["object"], "actual_front_opening": results["portal"]["actual_front_opening_record"]}
    case("CONTEXT-01", "Call caller context module for exact three registered components", "Three groups and complete source ownership", build_components)
    case("CONTEXT-02", "Call finite U clone Boolean using real earlier G14 row and current frame", "Single-user applied clone; only original display hides", build_portal)
    def objects():
        require("components" in results and "portal" in results, "context build incomplete")
        return [n for r in results["components"] for n in r["objects"]] + [results["portal"]["object"]] + extra_ray_targets
    def contract():
        names = objects()
        require(len(results["components"]) == 3 and len(names) == 7, "actual context inventory changed")
        clone = bpy.data.objects[results["portal"]["object"]]
        require(clone.data is not original.data and clone.data.users == 1 and not clone.modifiers, "clone is shared/unapplied")
        require("source_building_id" not in clone, "clone duplicated source identity")
        require(clone.matrix_world == original.matrix_world and clone.parent == original.parent and slots(clone) == slots(original), "clone source matrix/parent/material changed")
        require(not clone.hide_render and not clone.hide_viewport and not clone.hide_get(), "clone display hidden")
        require(original.hide_render and original.hide_get() and original.hide_viewport == expected["visibility"]["hide_viewport"], "original exact display exception missing")
        for n in names:
            o = bpy.data.objects[n]
            require(type(o.get("third_party_cost")) is int and o["third_party_cost"] == 0, "cost must be integer zero")
            require(o.get("human_approval") == "pending" and o.get("absolute_accuracy_claim") is False, "source study/approval scope changed")
            require(not o.hide_render and not o.hide_viewport and not o.hide_get(), "context object hidden")
        cap = next(bpy.data.objects[n] for n in names if bpy.data.objects[n].get("semantic_role") == "unknown_roof_thin_reference_cap")
        require(cap.get("actual_historical_roof_type") == "unknown" and cap.get("not_certified_flat_roof") is True, "unknown roof became flat-roof assertion")
        return {"new_meshes": len(names), "source_identity_count_in_fixture": sum(bool(o.get("source_building_id")) for o in bpy.context.scene.objects if o.type == "MESH"), "physical_absolute_accuracy_proven": False}
    def source_guard():
        now = record_actor(original)
        now.pop("visibility")
        require(now == source_static, "immutable source raw/evaluated/properties/matrix/material/relations altered")
        require({n: material_record(bpy.data.materials[n]) for n in source_materials} == source_materials, "source effective shader altered")
        return {"all_original_source_fields_unchanged_except_display": True, "effective_materials_unchanged": True}
    def topology():
        return {n: C.closed_positive_topology(reader.mesh(n)) for n in objects()}
    neck = next(c for c in registry["context_components"] if c["component_id"] == "source_middle_neck")
    def neck_route():
        names = objects()
        a, b = [Vector((p[0], p[1], 0)) for p in neck["passage_axis_world"]]
        axis = (b - a).normalized()
        across = Vector((axis.y, -axis.x, 0))
        rays = []
        for offset in (-.8, -.4, 0, .4, .8):
            for z in (.55, 1.5, 2.5, 3.6, 4.5):
                p, q = a - axis * .20 + across * offset, b + axis * .20 + across * offset
                p.z = q.z = z
                for start, end in ((p, q), (q, p)):
                    hit = reader.ray(names, start, end)
                    require(hit is None, "neck full N-S reference route blocked: " + str(hit["object"] if hit else ""))
                    rays.append({"start": list(start), "end": list(end), "hit": None})
        controls = []
        center = (a + b) / 2
        center.z = 1.5
        for sign in (-1, 1):
            hit = reader.ray(names, center, center + across * sign * 5)
            require(hit and bpy.data.objects[hit["object"]].get("semantic_role") == "unmeasured_reference_passage_side", "actual neck sidewall positive control missing")
            controls.append({"object": hit["object"], "point": list(hit["point"]), "distance": hit["distance"]})
        return {"complete_length_bidirectional_rays": rays, "actual_sidewall_positive_controls": controls, "sample_rays_alone_are_not_full_domain_proof": True}
    def portal_route():
        names = objects()
        f, cut = binding["front_frame"], binding["cutter"]
        x0, y0, x1, y1 = cut["complete_width_strip_actual_U_intersection_bounds_local"]
        rays = []
        for x in (0, -cut["width_m"] * .35, cut["width_m"] * .35):
            for z in (.5, 1.4, 2.5, 3.45):
                p, q = C.world_point(f, (x, y0 - .30, z)), C.world_point(f, (x, y1 + .30, z))
                for start, end in ((p, q), (q, p)):
                    hit = reader.ray(names, start, end)
                    require(hit is None, "finite U central portal blocked: " + str(hit["object"] if hit else ""))
                    rays.append({"start": list(start), "end": list(end), "hit": None})
        controls = []
        for x in (-cut["width_m"] / 2 - .3, cut["width_m"] / 2 + .3):
            hit = reader.ray(names, C.world_point(f, (x, y0 - .3, 1.5)), C.world_point(f, (x, y1 + .3, 1.5)))
            require(hit and hit["object"] == results["portal"]["object"], "actual retained U northbar side positive control missing")
            controls.append({"object": hit["object"], "point": list(hit["point"])})
        return {"full_length_bidirectional_portal_rays": rays, "retained_source_side_positive_controls": controls, "east_real_door_route_completed": False}
    positives = [("CONTEXT-03", "Identity, integer-zero cost and unresolved historical scope", contract), ("CONTEXT-04", "Complete original-source and effective-material guard", source_guard), ("CONTEXT-05", "All seven actual meshes closed/direction-paired/positive", topology), ("CONTEXT-06", "Neck full N-S bidirectional rays plus actual sidewall positive controls", neck_route), ("CONTEXT-07", "Finite U passage full-length rays plus retained source-side controls", portal_route)]
    for ident, label, fn in positives:
        case(ident, label, "actual independent checks pass", fn)
    def all_positive():
        reader.refresh()
        for _, _, fn in positives:
            fn()
    def negative(mutate, restore, check_fn, reason):
        all_positive()
        try:
            mutate()
            reader.refresh()
            try:
                check_fn()
            except AssertionError as exc:
                require(reason in str(exc), "negative masked by unrelated baseline error " + str(exc))
                evidence = {"baseline_passed": True, "actual_private_mutation_rejected": True, "reason": str(exc)}
            else:
                raise AssertionError("actual invalid context mutation accepted")
        finally:
            restore()
            reader.refresh()
            all_positive()
        return {**evidence, "actual_original_state_restored_and_positive": True}
    if "portal" in results:
        clone = bpy.data.objects[results["portal"]["object"]]
        case("EXTRA-CONTEXT-01", "Temporarily replace clone with actual uncut source mesh copy", "Same portal ray rejects then all positives restore", lambda: uncut_negative(clone, original, negative, portal_route))
        case("EXTRA-CONTEXT-02", "Temporarily re-add source_building_id to clone", "Same identity guard rejects then restore", lambda: negative(lambda: clone.__setitem__("source_building_id", binding["source_part_id"]), lambda: clone.__delitem__("source_building_id"), contract, "duplicated source identity"))
        case("EXTRA-CONTEXT-03", "Temporarily hide actual clone", "Same actual visibility contract rejects then restore", lambda: negative(lambda: setattr(clone, "hide_render", True), lambda: setattr(clone, "hide_render", False), contract, "clone display hidden"))
        old = original.data.vertices[0].co.copy()
        case("EXTRA-CONTEXT-04", "Temporarily move original raw vertex1cm", "Same immutable-source guard rejects then exact restore", lambda: negative(lambda: setattr(original.data.vertices[0], "co", old + Vector((.01, 0, 0))), lambda: setattr(original.data.vertices[0], "co", old), source_guard, "immutable source"))
        case("EXTRA-CONTEXT-05", "Temporarily obstruct true neck passage with independent actual box", "Same N-S full route rejects then remove/restore", lambda: blocker_negative(neck, collection, extra_ray_targets, negative, neck_route))
    case("FINAL-GUARD", "All source/input pins and positive checks after every negative restoration", "No mutation leaks; no native/save/render", lambda: final_guard(files, all_positive))
    reader.refresh()
    exported = []
    for record in results.get("components", []):
        geometry = {n: export_object(bpy.data.objects[n], reader) for n in record["objects"]}
        exported.append({**record, "geometry": geometry})
    doc = {"schema": "v17.actual-isolated-caller-context-world-geometry/1", "coordinate_space": "WORLD", "registry_file": "work/restoration-v17/registration/registered-buildings.json", "registry_sha256": PINS["work/restoration-v17/registration/registered-buildings.json"], "producer_module_file": "work/restoration-v17/context_geometry_v2.py", "producer_module_sha256": PINS["work/restoration-v17/context_geometry_v2.py"], "context_components": exported, "inputs_sha256": files, "front_actual_opening_source_readout_sha256": args.front_readout_sha256, "native_opened": False, "native_saved": False, "rendered": False, "third_party_cost": 0, "isolated_fixture_not_saved_city_certificate": True, "east_actual_route_completed": False}
    if "portal" in results:
        doc["front_entry_context"] = {"schema": "v17.actual-front-entry-context-world-geometry/1", "binding_sha256": sha(binding_path), "binding": binding, "original": export_object(original, reader), "replacement": export_object(bpy.data.objects[results["portal"]["object"]], reader), "actual_front_opening_record": results["portal"]["actual_front_opening_record"]}
    write(out / "actual-context-geometry.json", doc)
    report = {"schema": "v17.actual-isolated-caller-context-factory-tests/1", "results": checks, "summary": {"passed": sum(r["passed"] for r in checks), "failed": sum(not r["passed"] for r in checks)}, "actual_geometry_readout_sha256": sha(out / "actual-context-geometry.json"), "inputs_sha256": files, "native_opened": False, "native_saved": False, "rendered": False, "third_party_cost": 0}
    write(out / "actual-context-tests.json", report)
    print("V17_CONTEXT_FACTORY_TERMINAL_READY", json.dumps(report["summary"]), flush=True)
    if report["summary"]["failed"]:
        raise SystemExit(1)


def export_object(o, reader):
    e = record_actor(o)
    m = reader.mesh(o.name)
    return {"object": o.name, "role": o.get("semantic_role"), "vertices": [list(v) for v in m["vertices"]], "triangles": [list(t) for t in m["triangles"]], "raw_vertices": e["raw_vertices"], "raw_faces": e["raw_faces"], "raw_face_material_indices": e["raw_face_material_indices"], "matrix_world": e["matrix_world"], "parent": e["parent"], "actual_material_slots": e["actual_material_slots"], "custom_properties": e["custom_properties"], "collections": e["collections"], "visibility": e["visibility"], "mesh_users": o.data.users, "modifiers": [{"name": m.name, "type": m.type} for m in o.modifiers]}


def uncut_negative(clone, original, negative, check_fn):
    saved, temporary = clone.data, original.data.copy()
    def restore():
        clone.data = saved
        if temporary.users == 0:
            bpy.data.meshes.remove(temporary)
    return negative(lambda: setattr(clone, "data", temporary), restore, check_fn, "finite U central portal blocked")


def blocker_negative(neck, collection, extra_ray_targets, negative, check_fn):
    center = [sum(p[i] for p in neck["passage_axis_world"]) / 2 for i in range(2)]
    vs = [[center[0] + x, center[1] + y, z] for z in (.4, 4.7) for y in (-.1, .1) for x in (-4, 4)]
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    mesh = bpy.data.meshes.new("V17_NEGATIVE_NECK_BLOCKER_MESH")
    mesh.from_pydata(vs, [], faces)
    mesh.update()
    blocker = bpy.data.objects.new("V17_NEGATIVE_NECK_BLOCKER", mesh)
    def mutate():
        collection.objects.link(blocker)
        extra_ray_targets.append(blocker.name)
    def restore():
        extra_ray_targets.remove(blocker.name)
        bpy.data.objects.remove(blocker, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return negative(mutate, restore, check_fn, "neck full N-S reference route blocked")


def final_guard(files, positive):
    positive()
    for p, digest in files.items():
        require(sha(p) == digest, "immutable file changed during fixture: " + p)
    require(not bpy.data.filepath, "native I/O occurred")
    return {"all_frozen_inputs_unchanged": True, "all_positive_checks_repeated": True, "native_opened_saved_rendered": False}


if __name__ == "__main__":
    main()
