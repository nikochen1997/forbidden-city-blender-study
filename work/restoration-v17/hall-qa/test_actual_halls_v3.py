"""V3 isolated V17 three-hall audit, using separately SHA-bound caller v2 profiles.

Never opens/saves a native or renders. Geometry is read from evaluated meshes;
source reconstruction is an immutable fixture, not a native replay certificate.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
IDS = ("shufang_front_hall", "shufang_rear_hall", "baohuadian_main")
PINS = {
    "work/courtyard_hall_buildings.py": "5123db7be8948e9bdb4dc6d8edb712d01ad98075e5e6a40251be5aa8f666a86d",
    "work/four_hall_buildings.py": "1d3267d25946ecf468da3a9d60103ef522c202452f60d0e500643d14ce9dcc1a",
    "work/forbidden_city_geometry.py": "23f815fc93057a0f69b66adc25536485fc05a33935f67fb1613073963e276efc",
    "work/restoration_buildings.py": "aac18ca8c219b8de544dd78d8a7b99000a4d0fe83d40553614065e0c998aaf60",
    "work/restoration-v16/saved-audit/saved_audit_core.py": "72d1fc4253231380ae8db9784a3b6a81a3f66307170e4003e85837d5a68e6ae0",
    "work/build_forbidden_city_restoration_v11.py": "1ccce3fcca040d311f6c48fc52cd38cf053d484e627e20f03ad2f4a1c9eeb130",
    "work/restoration-v17/registration/registered-buildings.json": "0ff859b0e1434e9ee1c0501aa2f301fd6b8416e85e32a5c2b525f9e3c18479bc",
    "work/restoration-v17/registration/actual-source-actors.json": "584510afec3f8a8d9b77ed57b7424dc2089bbb35b22c1e172c1f6901fce39400",
}


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--profiles-sha256", required=True)
    parser.add_argument("--palette", type=Path, required=True)
    parser.add_argument("--palette-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = args.output_dir.resolve()
    require(out.is_relative_to(HERE) and not out.exists(), "Fresh hall-qa output directory required")
    out.mkdir(parents=True)
    require(not bpy.data.filepath, "Factory startup required")
    files = {str((ROOT / p).resolve()): h for p, h in PINS.items()}
    files[str(args.profiles.resolve())] = args.profiles_sha256
    files[str(args.palette.resolve())] = args.palette_sha256
    files[str(Path(__file__).resolve())] = sha(__file__)
    for p, h in files.items():
        require(sha(p) == h, "Input SHA drift: " + p)
    doc = json.loads(args.profiles.read_text())
    palette_doc = json.loads(args.palette.read_text())
    for p, h in {**doc["source_files"], **palette_doc["source_files_sha256"]}.items():
        require(sha(ROOT / p) == h, "Profile transitive input drift: " + p)
        files[str((ROOT / p).resolve())] = h
    profiles = {p["building_id"]: p for p in doc["buildings"] if p["builder"] == "hall"}
    require(set(profiles) == set(IDS), "Exact three hall profiles required")
    registry = json.loads((ROOT / "work/restoration-v17/registration/registered-buildings.json").read_text())
    registered = {p["building_id"]: p for p in registry["buildings"]}
    capture = json.loads((ROOT / "work/restoration-v17/registration/actual-source-actors.json").read_text())
    C = load_module("v17_hall_audit_core", ROOT / "work/restoration-v16/saved-audit/saved_audit_core.py")
    sys.path.insert(0, str(ROOT / "work"))
    import courtyard_hall_buildings as G
    import forbidden_city_geometry as F
    import restoration_buildings as R
    helpers = C.frozen_helpers(ROOT)
    reader = C.MeshReader(bpy)
    results, checks = {}, []
    collection = F.ensure_collection("V17_THREE_HALL_FACTORY_ONLY")
    source_collection = F.ensure_collection("V17_IMMUTABLE_RAW_SOURCE_FIXTURE")
    source_objects = []
    # Preserve actual source raw arrays/matrix without importing a prior producer.
    source_names = sorted({n for p in profiles.values() for n in p["source_actual_actor_names"]})
    for name in source_names:
        e = capture["actor_evidence"][name]
        mesh = bpy.data.meshes.new(name + "_fixture_raw")
        mesh.from_pydata(e["raw_vertices"], [], e["raw_faces"])
        mesh.update()
        for _, material_name in e["actual_material_slots"]:
            material = bpy.data.materials.get("V17_source_fixture_" + material_name)
            if material is None:
                state = capture["material_evidence"][material_name]
                material = bpy.data.materials.new("V17_source_fixture_" + material_name)
                material.diffuse_color = state["diffuse_rgba"]
                material.metallic, material.roughness = state["metallic"], state["roughness"]
            mesh.materials.append(material)
        for polygon, index in zip(mesh.polygons, e["raw_face_material_indices"]):
            polygon.material_index = index
        obj = bpy.data.objects.new(name, mesh)
        source_collection.objects.link(obj)
        obj.matrix_world = Matrix(e["matrix_world"])
        obj.color = e["object_rgba"]
        for k, v in e["custom_properties"].items():
            obj[k] = v if isinstance(v, (str, int, float, bool)) else json.dumps(v, ensure_ascii=False)
        source_objects.append(obj)
    bpy.context.view_layer.update()
    source_pin = {o.name: helpers["mesh_fingerprint"](o) for o in source_objects}
    materials = R.restoration_materials(F.create_materials("R17_"))
    for key in {p["material_scheme"][k] for p in profiles.values() for k in p["material_scheme"]}:
        if key not in materials:
            state = palette_doc["materials"][key]
            m = bpy.data.materials.new("R17_" + key)
            m.use_nodes = True
            m.diffuse_color = state["rgba"]
            m.metallic, m.roughness = state["metallic"], state["roughness"]
            node = m.node_tree.nodes.get("Principled BSDF")
            for socket, value in (("Base Color", state["rgba"]), ("Metallic", state["metallic"]), ("Roughness", state["roughness"])):
                node.inputs[socket].default_value = value
            materials[key] = m
    cache = {}

    def case(ident, operation, expected, fn):
        try:
            evidence = fn()
            checks.append({"id": ident, "input": "frozen three profiles / actual evaluated fixture meshes", "operation": operation,
                           "expected": expected, "passed": True, "evidence": evidence})
            print("PASS", ident, flush=True)
        except Exception as exc:
            checks.append({"id": ident, "operation": operation, "expected": expected, "passed": False,
                           "error": str(exc), "traceback": traceback.format_exc()})
            print("FAIL", ident, str(exc), flush=True)

    def build(p):
        r = G.build_hall(p, collection, materials, cache)
        results[p["building_id"]] = r
        reader.refresh()
        return {"id": p["building_id"], "actual_meshes": len(r["objects"]), "actual_openings": len(r["openings"])}

    for i, ident in enumerate(IDS, 1):
        case("HALL-PROFILE-VALIDATE-" + str(i), "Actual frozen G14 validate before any hall construction",
             "Complete caller/API compatibility", lambda ident=ident: {"actual_validated_source_rings": len(G._validate(profiles[ident]))})
    if all(c["passed"] for c in checks):
        for i, ident in enumerate(IDS, 1):
            case("HALL-BUILD-" + str(i), "Call frozen G14 only", "actual independent meshes", lambda ident=ident: build(profiles[ident]))

    def contract():
        require(set(results) == set(IDS), "Not all halls built")
        require(doc["whole_city_objective_complete"] is False and doc["human_approval"] == "pending", "Whole-city/approval scope changed")
        for k in ("third_party_cost", "paid_service_calls"):
            require(type(doc[k]) is int and doc[k] == 0, "integer-zero budget contract: " + k)
        fields = ("source_polygon_world", "source_holes_world", "source_polygon_local", "source_holes_local", "anchor", "rotation_z_rad", "source_component_id", "original_typed_factual_source_fields", "typed_factual_source_fields")
        for ident, r in results.items():
            p = r["profile"]
            require(all(p[k] == registered[ident][k] for k in fields), "Source/frame/fact binding differs " + ident)
            require(p["occupied_storeys"] is None and p["reference_floor_count"] == 1, "Reference slab promoted to occupied floor")
            require(not p["source6m_proxy_height_is_real_building_height"], "Source6m promoted to survey")
            require(r["manifest"]["occupied_storeys"] is None and not r["manifest"]["complete_reconstruction_proven"], "Completion falsely certified")
            for obj in [r["root"]] + r["objects"]:
                require(type(obj["third_party_cost"]) is int and obj["third_party_cost"] == 0, "integer-zero budget contract: " + obj.name)
                require(obj["human_approval"] == "pending", "Approval changed")
            require(all(o.parent == r["root"] for o in r["objects"]), "Wrong actual hall parent")
        require(profiles[IDS[0]]["eaves_tiers"] is None and profiles[IDS[1]]["eaves_tiers"] is None, "Unknown eaves became historical assertion")
        require(not results[IDS[2]]["openings"], "Bao unknown apertures invented")
        return {"source_frames_bound": 3, "historical_accuracy_proven": False, "G14_factory_tags_only": True,
                "neck_U_wall_stage_Bao_baoxia_context": "pending caller audit", "saved_city_and_media": "pending"}

    def require_all_results():
        require(set(results) == set(IDS), "All three hall results required before geometry certification")

    def topology():
        require_all_results()
        evidence = {}
        for r in results.values():
            for obj in r["objects"]:
                try:
                    evidence[obj.name] = C.closed_positive_topology(reader.mesh(obj.name))
                except AssertionError as exc:
                    raise AssertionError(obj.name + ": " + str(exc)) from exc
        return {"actual_closed_positive_meshes": len(evidence), "all_triangle_components_checked": True}

    def local_vertices(r, obj):
        return [Vector(C.local_point(r["profile"], v)) for v in reader.mesh(obj.name)["vertices"]]

    def column_axes():
        require_all_results()
        evidence = []
        for r in results.values():
            p, d = r["profile"], r["profile"]["dimensions"]
            require(not p.get("column_bay_widths_x_m") and not p.get("column_bay_widths_y_m"), "Explicit spans need separate independent grid")
            xs = [-d["body_width_m"] / 2 + d["body_width_m"] * i / p["bays_x"] for i in range(p["bays_x"] + 1)]
            ys = [-d["body_depth_m"] / 2 + d["body_depth_m"] * i / p["bays_y"] for i in range(p["bays_y"] + 1)]
            expected = [(x, y) for x in xs for y in (ys[0], ys[-1])] + [(x, y) for x in (xs[0], xs[-1]) for y in ys[1:-1]]
            columns = r["components"].get("column", []) + r["components"].get("pilaster", [])
            require(len(columns) == len(expected) == len(r["components"]["column_base"]), "Actual perimeter column inventory differs")
            used = set()
            for o in columns:
                low, high = C.bounds(local_vertices(r, o))
                center = [(low[i] + high[i]) / 2 for i in (0, 1)]
                errors = [max(abs(center[k] - q[k]) for k in (0, 1)) for q in expected]
                idx = min(range(len(errors)), key=errors.__getitem__)
                require(errors[idx] <= C.EPS and idx not in used, "Actual column axis differs: " + o.name)
                used.add(idx)
                C.close(low[2], d["floor_z_m"] + d["column_base_height_m"], "Actual column lowZ")
                C.close(high[2], d["column_top_z_m"], "Actual column highZ")
            evidence.append({"id": p["building_id"], "actual_perimeter_columns": len(columns), "independent_grid": [p["bays_x"], p["bays_y"]]})
        return evidence

    def contact_ray(names, point, upward, label):
        dz = Vector((0, 0, .02))
        hit = reader.ray(names, point - dz if upward else point + dz, point + dz if upward else point - dz)
        require(hit is not None and abs(hit["point"].z - point.z) <= C.EPS, label)

    def contacts():
        require_all_results()
        count = 0
        for r in results.values():
            comps = r["components"]
            beam_names = [o.name for o in comps["beam"]]
            for role, support, upward in (("column_base", [r["reference_floor"].name], False), ("column", None, False), ("pilaster", None, False)):
                for obj in comps.get(role, []):
                    vertices = reader.mesh(obj.name)["vertices"]
                    low = min(v.z for v in vertices)
                    for v in vertices:
                        if abs(v.z - low) <= 1e-6:
                            contact_ray(support or [obj["support_object"]], v, upward, "Complete bottom rim leaves actual support: " + obj.name)
                            count += 1
                    if role != "column_base":
                        high = max(v.z for v in vertices)
                        for v in vertices:
                            if abs(v.z - high) <= 1e-6:
                                contact_ray(beam_names, v, True, "Complete column top rim leaves beam: " + obj.name)
                                count += 1
            for obj in comps.get("roof_bearing_post", []):
                vertices = reader.mesh(obj.name)["vertices"]
                low = min(v.z for v in vertices)
                roof = reader.mesh(obj["roof_contact_object"])["tree"]
                for v in vertices:
                    if abs(v.z - low) <= 1e-6:
                        contact_ray(beam_names, v, False, "Complete bearing bottom leaves beam: " + obj.name)
                    else:
                        nearest = roof.find_nearest(v)
                        require(nearest[0] is not None and nearest[3] <= C.EPS, "Actual bearing top leaves roof: " + obj.name)
                    count += 1
            for obj in comps.get("roof_closure_wall", []):
                roof = reader.mesh(obj["roof_contact_object"])["tree"]
                for v in reader.mesh(obj.name)["vertices"]:
                    if v.z > obj["closure_bottom_z_m"] + r["profile"]["anchor"][2] + 1e-5:
                        nearest = roof.find_nearest(v)
                        require(nearest[0] is not None and nearest[3] <= C.EPS, "Actual closure top leaves roof: " + obj.name)
                        count += 1
        return {"actual_rim_and_skin_vertex_contacts": count, "full_cap_area": "external CPU pending"}

    def apertures():
        require_all_results()
        rays, solids, total = 0, 0, 0
        for r in results.values():
            movable = [n for row in r["openings"] for k in ("infill_proxy_names", "leaf_reference_names") for n in row[k]]
            with C.moved_and_restored(bpy, reader, movable):
                # Query every actual hall mesh, including undeclared opaque additions.
                names = [o.name for o in r["collection"].objects if o.type == "MESH"]
                for row in r["openings"]:
                    normal = Vector(row["normal_world"])
                    across = r["root"].matrix_world.to_3x3() @ Vector((1, 0, 0) if row["wall_side"] in ("south", "north") else (0, 1, 0))
                    center = Vector(row["center_world"])
                    for u in (-.4, -.2, 0, .2, .4):
                        for v in (-.4, -.2, 0, .2, .4):
                            point = center + across * u * row["clear_width_m"] + Vector((0, 0, v * row["clear_height_m"]))
                            for sign in (-1, 1):
                                require(reader.ray(names, point - normal * .6 * sign, point + normal * .6 * sign) is None,
                                        "Actual hall aperture blocked: " + row["id"])
                                rays += 1
                    for sign in (-1, 1):
                        point = center + across * sign * (row["clear_width_m"] / 2 + .15)
                        require(reader.ray([row["wall"]], point - normal * .6, point + normal * .6) is not None, "Actual solid jamb control absent")
                        solids += 1
                    wall = bpy.data.objects[row["wall"]]
                    require(wall.data.users == 1 and not wall.modifiers, "Actual cut wall shared or Boolean unapplied")
                    require(row["id"] in {x["id"] for x in json.loads(wall["applied_openings"])}, "Actual wall cut record absent")
                    total += 1
        require(total == 11 and rays == 550, "Declared aperture population differs")
        require(not any(o.name.startswith("TEMP_OPENING_") for o in bpy.data.objects), "Temporary cutter object remains")
        return {"actual_apertures": total, "bidirectional_rays": rays, "solid_jamb_controls": solids, "all_hall_meshes_queried": True}

    def unknown_infills():
        require_all_results()
        count = 0
        for r in results.values():
            for row in r["openings"]:
                require(row["leaf_count"] is None and not row["leaf_reference_names"], "Unknown actual leaf count invented")
                if row["kind"] == "passage":
                    require(not row["infill_proxy_names"], "Passage has invented infill")
                    continue
                require(len(row["infill_proxy_names"]) == 1, "Unknown set proxy inventory differs")
                obj = bpy.data.objects[row["infill_proxy_names"][0]]
                require(obj["not_actual_leaf_count"] and obj["leaf_count_status"] == "unknown_not_one_actual_leaf" and "leaf_count" not in obj, "Unknown set mislabelled as one leaf")
                low, high = C.bounds(local_vertices(r, obj))
                axis = 0 if row["wall_side"] in ("south", "north") else 1
                C.close(high[axis] - low[axis], row["clear_width_m"] * .985, "Actual unknown proxy width differs")
                C.close(high[2] - low[2], row["clear_height_m"] * .99, "Actual unknown proxy height differs")
                require(not obj.hide_render and obj.visible_get(), "Unknown proxy unexpectedly hidden")
                count += 1
        return {"unknown_set_proxies": count, "actual_leaf_count_certified": False}

    def roof_form(only=None):
        require_all_results()
        evidence = []
        for r in ([only] if only else results.values()):
            p, roof_spec = r["profile"], r["profile"]["roof_tiers"][0]
            obj = bpy.data.objects[r["roofs"][0]["roof_object"]]
            actual = reader.mesh(obj.name)
            a, b = roof_spec["outer_width_m"] / 2, roof_spec["outer_depth_m"] / 2
            def height(x, y):
                start = Vector(C.world_point(p, (x, y, roof_spec["top_z_m"] + 1)))
                end = Vector(C.world_point(p, (x, y, roof_spec["eave_z_m"] - 1)))
                hit = reader.ray([obj.name], start, end)
                require(hit is not None, "Actual roof category ray missed")
                return C.local_point(p, hit["point"])[2]
            center, ends = height(0, 0), [height(-.92 * a, 0), height(.92 * a, 0)]
            if roof_spec["roof_type"] == "xieshan":
                require(all(center - z > .25 * (roof_spec["top_z_m"] - roof_spec["eave_z_m"]) for z in ends), "Actual xieshan hip end fall missing")
            else:
                require(roof_spec["roof_type"] == "yingshan", "Unexpected roof category")
                require(all(abs(center - z) <= C.EPS for z in ends), "Actual hard-gable ridge does not reach both ends")
                low, high = C.bounds(local_vertices(r, obj))
                C.close(high[0] - low[0], p["dimensions"]["body_width_m"], "Actual hard-gable end projects beyond body")
            offset = .025 * b
            slopes = [(center - height(0, sign * offset)) / offset for sign in (-1, 1)]
            require(all(s > .3 for s in slopes), "Actual pointed transverse crown slope missing")
            require(all(len(poly.vertices) == 3 for poly in obj.data.polygons), "Actual roof skin not fixed triangles")
            evidence.append({"id": p["building_id"], "actual_center_z_m": center, "actual_end_z_m": ends,
                             "actual_near_crown_slopes": slopes, "roof_type": roof_spec["roof_type"], "roof_triangles": len(actual["triangles"]),
                             "historical_eaves": p["eaves_tiers"], "modeled_roofs": len(r["roofs"])})
        return evidence

    def palette():
        require_all_results()
        evidence = []
        used = {v for p in profiles.values() for v in p["material_scheme"].values()}
        for key in used:
            material, state = materials[key], palette_doc["materials"][key]
            node = material.node_tree.nodes.get("Principled BSDF")
            require(node is not None, "Actual material has no Principled shader")
            for actual, expected in ((material.diffuse_color, state["rgba"]), (node.inputs["Base Color"].default_value, state["rgba"])):
                require(max(abs(a - b) for a, b in zip(actual, expected)) < 1e-6, "Actual palette RGBA differs " + key)
            for k, socket in (("metallic", "Metallic"), ("roughness", "Roughness")):
                require(abs(node.inputs[socket].default_value - state[k]) < 1e-6, "Actual node material finish differs " + key)
        for r in results.values():
            obj = bpy.data.objects[r["roofs"][0]["roof_object"]]
            expected = [materials[r["profile"]["material_scheme"][k]] for k in ("roof_main", "roof_edge", "roof_under")]
            require(list(obj.data.materials) == expected, "Actual roof material slots differ")
            counts = {i: sum(poly.material_index == i for poly in obj.data.polygons) for i in range(3)}
            require(all(counts.values()) and all(poly.material_index in counts for poly in obj.data.polygons), "Actual roof lost material surface domain")
            evidence.append({"id": r["profile"]["building_id"], "actual_face_material_counts": counts})
        return {"used_actual_palette_keys": sorted(used), "roof_domains": evidence, "rear_color_is_neutral_unknown": True}

    positives = [("HALL-01", contract), ("HALL-02", topology), ("HALL-03", column_axes), ("HALL-04", contacts),
                 ("HALL-05", apertures), ("HALL-06", unknown_infills), ("HALL-07", roof_form), ("HALL-08", palette)]
    for ident, fn in positives:
        case(ident, "Read actual mesh/shader geometry", "Pass independent positive assertion", fn)

    # Bind every object/data/material/camera existing after actual baseline build.
    def snapshot():
        return {"objects": {o.name: ({"fingerprint": helpers["mesh_fingerprint"](o), "relations": C.mesh_relations(o), "visibility": helpers["visibility"](o)} if o.type == "MESH" else C.nonmesh_state(o, helpers["visibility"])) for o in bpy.data.objects},
                "materials": {m.name: helpers["material_state"](m) for m in bpy.data.materials},
                "cameras": {c.name: C.camera_state(c) for c in bpy.data.cameras},
                "data_names": {k: sorted(x.name for x in getattr(bpy.data, k)) for k in ("objects", "meshes", "materials", "collections", "cameras", "images", "curves")}}
    baseline = C.canonical(snapshot())

    def all_positive():
        reader.refresh()
        return {ident: fn() for ident, fn in positives}

    def negative(ident, operation, mutate, restore, checker, reason):
        def run():
            all_positive()
            token = None
            try:
                token = mutate()
                reader.refresh()
                rejected = C.negative_rejected(checker)
                require(reason in rejected["reason"], "Mutation rejected for unrelated reason: " + rejected["reason"])
            finally:
                restore(token)
                reader.refresh()
            all_positive()
            require(C.canonical(snapshot()) == baseline, "Negative control failed exact original-state restoration")
            return {**rejected, "positive_before_and_after": True, "exact_all_state_restored": True}
        case(ident, operation, "Specific real-geometry rejection and exact restore", run)

    baseline_green = not any(not c["passed"] for c in checks)
    if baseline_green:
        r = results[IDS[0]]
        base = r["components"]["column_base"][0]
        def move(obj, axis):
            old = obj.matrix_basis.copy()
            obj.location[axis] += .01
            return old
        def unmove(obj, matrix):
            if matrix is not None:
                obj.matrix_basis = matrix
        negative("EXTRA-01", "Lift actual base by .01m", lambda: move(base, 2), lambda m: unmove(base, m), contacts, "bottom rim leaves actual support")
        col = (r["components"].get("column", []) + r["components"].get("pilaster", []))[0]
        negative("EXTRA-02", "Move actual column axis .01m", lambda: move(col, 0), lambda m: unmove(col, m), column_axes, "Actual column axis differs")
        row = next(x for x in r["openings"] if x["kind"] == "door")
        def curtain():
            o = F.box("V17_QA_TEMP_OPAQUE_CURTAIN", row["center_local"], (row["clear_width_m"], .12, row["clear_height_m"]), materials["red"], r["collection"], None, "qa_curtain")
            o.parent = r["root"]
            return o
        def remove_object(o):
            if o is not None:
                data = o.data
                bpy.data.objects.remove(o, do_unlink=True)
                if data.users == 0:
                    bpy.data.meshes.remove(data)
        negative("EXTRA-03", "Add opaque mesh curtain to known aperture without semantic wall label", curtain, remove_object, apertures, "Actual hall aperture blocked")
        proxy = bpy.data.objects[row["infill_proxy_names"][0]]
        def shrink():
            old = proxy.matrix_basis.copy()
            proxy.scale.x *= .5
            return old
        negative("EXTRA-04", "Halve actual unknown set proxy width", shrink, lambda m: unmove(proxy, m), unknown_infills, "Actual unknown proxy width differs")
        front_roof = bpy.data.objects[r["roofs"][0]["roof_object"]]
        rear_roof = bpy.data.objects[results[IDS[1]]["roofs"][0]["roof_object"]]
        def swap_roof():
            old = front_roof.data
            mesh = rear_roof.data.copy()
            src = [v.co.copy() for v in mesh.vertices]
            target = [v.co.copy() for v in old.vertices]
            slo, shi = C.bounds(src)
            tlo, thi = C.bounds(target)
            for vertex in mesh.vertices:
                vertex.co = [(vertex.co[k] - slo[k]) * (thi[k] - tlo[k]) / (shi[k] - slo[k]) + tlo[k] for k in range(3)]
            front_roof.data = mesh
            return old, mesh
        def restore_roof(token):
            if token:
                old, mesh = token
                front_roof.data = old
                bpy.data.meshes.remove(mesh)
        negative("EXTRA-05", "Replace actual front hip skin by closed hard-gable geometry; labels unchanged", swap_roof, restore_roof, lambda: roof_form(r), "Actual xieshan hip end fall missing")
        slab = r["reference_floor"]
        def cut_cap():
            old = slab.data
            mesh = old.copy()
            bm = bmesh.new()
            try:
                bm.from_mesh(mesh)
                top = max(v.co.z for v in bm.verts)
                face = next(f for f in bm.faces if all(abs(v.co.z - top) < 1e-6 for v in f.verts))
                bmesh.ops.delete(bm, geom=[face], context="FACES_ONLY")
                bm.to_mesh(mesh)
            finally:
                bm.free()
            slab.data = mesh
            return old, mesh
        def restore_cap(token):
            if token:
                old, mesh = token
                slab.data = old
                bpy.data.meshes.remove(mesh)
        negative("EXTRA-06", "Delete a real top cap face from copied actual slab", cut_cap, restore_cap, topology, "actual boundary/nonmanifold edge")
        def budget():
            rejections = []
            root = r["root"]
            for value in (-1, 1, 0.0):
                try:
                    del root["third_party_cost"]
                    root["third_party_cost"] = value
                    rejection = C.negative_rejected(contract)
                    require("integer-zero budget contract" in rejection["reason"], "Unrelated budget rejection")
                    rejections.append({"value": value, "type": type(value).__name__, **rejection})
                finally:
                    del root["third_party_cost"]
                    root["third_party_cost"] = 0
                all_positive()
            return rejections
        case("EXTRA-07", "Actual root cost -1,+1,float0", "All reject integer-zero contract; restore int0", budget)
    else:
        checks.append({"id": "EXTRA-PRECONDITION", "passed": False, "error": "Positive baseline failed; no negative-control success claimed"})

    def export():
        export_roles = {"source_reference_slab", "column_base", "column", "pilaster", "beam", "roof_bearing_post", "roof_closure_wall"}
        buildings = []
        for r in results.values():
            selected = {o.name for role, objects in r["components"].items() if role in export_roles for o in objects}
            selected.update(row["roof_object"] for row in r["roofs"])
            geometry = {}
            for name in sorted(selected):
                m, obj = reader.mesh(name), bpy.data.objects[name]
                geometry[name] = {"object": name, "role": obj.get("semantic_role"), "vertices": [list(v) for v in m["vertices"]],
                                  "triangles": [list(t) for t in m["triangles"]], "triangle_materials": m["triangle_materials"],
                                  "support_object": obj.get("support_object"), "roof_contact_object": obj.get("roof_contact_object")}
            buildings.append({"id": r["profile"]["building_id"], "profile": r["profile"], "reference_floor": r["reference_floor"].name,
                              "components": {k: [o.name for o in objects] for k, objects in r["components"].items()}, "geometry": geometry,
                              "roofs": r["roofs"], "openings": r["openings"], "all_new_mesh_count": len(r["objects"])})
        readout = {"schema": "v17-three-hall-actual-factory-geometry/1", "profiles_sha256": args.profiles_sha256,
                   "palette_sha256": args.palette_sha256, "inputs_sha256": files, "buildings": buildings,
                   "native_opened": False, "native_saved": False, "rendered": False, "third_party_cost": 0,
                   "physical_absolute_accuracy_proven": False, "caller_context_and_saved_city": "pending"}
        path = out / "actual-hall-geometry.json"
        write(path, readout)
        return {"path": str(path), "sha256": sha(path), "full_geometry_objects": sum(len(b["geometry"]) for b in buildings)}
    case("HALL-09-READOUT", "Export restored actual full cap/support/roof triangles", "Independent CPU input; no native saved", export)

    def final_guard():
        reader.refresh()
        require(C.canonical(snapshot()) == baseline, "Final all-object/material/camera/datablock fingerprint changed")
        require(source_pin == {o.name: helpers["mesh_fingerprint"](o) for o in source_objects}, "Original source fixture changed")
        require(all(sha(p) == h for p, h in files.items()), "Input file bytes changed")
        require(not bpy.data.filepath, "Factory script acquired native filepath")
        return {"all_source_fixtures_unchanged": len(source_pin), "all_postbuild_objects_materials_camera_data_restored": True,
                "all_input_sha_unchanged": True, "saved_city_CPU_and_media": "pending"}
    case("FINAL-GUARD", "Full state and input bytes after all mutations", "Exact original-state restoration", final_guard)
    report = {"schema": "v17-three-hall-factory-tests/1", "passed": sum(c["passed"] for c in checks),
              "failed": sum(not c["passed"] for c in checks), "checks": checks, "inputs_sha256": files,
              "scope": "Actual factory geometry only; complete caller contexts/native/saved/media pending", "third_party_cost": 0}
    write(out / "actual-hall-tests.json", report)
    print("HALL-QA", report["passed"], report["failed"], flush=True)
    if report["failed"]:
        raise AssertionError("Actual hall factory QA failed; retain real red report")


if __name__ == "__main__":
    main()
