"""Isolated V18 ten-exterior factory audit. Root alone executes Blender.

Never opens/saves a native or renders. Geometry is read from evaluated meshes;
source reconstruction is an immutable fixture, not a native replay certificate.
"""
import argparse
from contextlib import contextmanager
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
IDS = tuple("nansansuo_" + group + "_" + row + "_hall" for group in ("east", "middle", "west") for row in ("front", "middle", "rear")) + ("nansansuo_common_gate",)
PHOTO_ID = "nansansuo_middle_middle_hall"
GATE_ID = "nansansuo_common_gate"
PINS = {
    "work/restoration-v18/caller_material_overrides.py": "a35f3df5db221c4167030dbaf145ade53902ff7dfb70c0ba8c0baef38a7d9b0c",
    "work/restoration-v18/module-qa/fixture_profile_contract_v2.py": "c4e8c8a71e403edcd5575fd73fb4c957e44c56cc7bac7056b34070cfd92cc218",
    "work/courtyard_hall_buildings.py": "5123db7be8948e9bdb4dc6d8edb712d01ad98075e5e6a40251be5aa8f666a86d",
    "work/four_hall_buildings.py": "1d3267d25946ecf468da3a9d60103ef522c202452f60d0e500643d14ce9dcc1a",
    "work/forbidden_city_geometry.py": "23f815fc93057a0f69b66adc25536485fc05a33935f67fb1613073963e276efc",
    "work/restoration_buildings.py": "aac18ca8c219b8de544dd78d8a7b99000a4d0fe83d40553614065e0c998aaf60",
    "work/restoration-v16/saved-audit/saved_audit_core.py": "72d1fc4253231380ae8db9784a3b6a81a3f66307170e4003e85837d5a68e6ae0",
    "work/build_forbidden_city_restoration_v11.py": "1ccce3fcca040d311f6c48fc52cd38cf053d484e627e20f03ad2f4a1c9eeb130",
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
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--registry-sha256", required=True)
    parser.add_argument("--expectations", type=Path, required=True)
    parser.add_argument("--expectations-sha256", required=True)
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
    files[str(args.registry.resolve())] = args.registry_sha256
    files[str(args.expectations.resolve())] = args.expectations_sha256
    files[str(Path(__file__).resolve())] = sha(__file__)
    for p, h in files.items():
        require(sha(p) == h, "Input SHA drift: " + p)
    doc = json.loads(args.profiles.read_text())
    palette_doc = json.loads(args.palette.read_text())
    expectation_doc = json.loads(args.expectations.read_text())
    for p, h in {**doc["source_files"], **palette_doc["source_files_sha256"], **expectation_doc["source_files_sha256"]}.items():
        require(sha(ROOT / p) == h, "Profile transitive input drift: " + p)
        files[str((ROOT / p).resolve())] = h
    profiles = {p["building_id"]: p for p in doc["buildings"] if p["builder"] == "hall"}
    require(set(profiles) == set(IDS) and len(doc["buildings"]) == 10, "Exact nine halls and one common gate required")
    registry = json.loads(args.registry.read_text())
    registered = {p["building_id"]: p for p in registry["buildings"]}
    expected = {p["building_id"]: p for p in expectation_doc["buildings"]}
    require(set(expected) == set(IDS) and len(expectation_doc["buildings"]) == 10, "Independent ten-entity expectation binding required")
    expected_aperture_count = sum(len(p["apertures"]) for p in expected.values())
    require(set(IDS) <= set(registered), "Registry lacks exact ten entity rows")
    C = load_module("v18_exterior_audit_core", ROOT / "work/restoration-v16/saved-audit/saved_audit_core.py")
    K = load_module("v18_fixture_profile_contract", HERE / "fixture_profile_contract_v2.py")
    M = load_module("v18_caller_front_materials", ROOT / "work/restoration-v18/caller_material_overrides.py")
    sys.path.insert(0, str(ROOT / "work"))
    import courtyard_hall_buildings as G
    import forbidden_city_geometry as F
    helpers = C.frozen_helpers(ROOT)
    reader = C.MeshReader(bpy)
    results, checks = {}, []
    collection = F.ensure_collection("V18_TEN_EXTERIOR_FACTORY_ONLY")
    # Actual raw source capture is locked transitively by final profile/registry.
    # This minimal factory does not clone old actors or open a prior city native.
    materials = {}
    for key in sorted({p["material_scheme"][k] for p in profiles.values() for k in p["material_scheme"]} | {p["caller_front_columns_material_key"] for p in profiles.values() if p.get("caller_front_columns_material_key") is not None}):
        state = palette_doc["materials"][key]
        material = bpy.data.materials.new("R18_" + key)
        material.use_nodes = True
        material.diffuse_color = state["rgba"]
        material.metallic, material.roughness = state["metallic"], state["roughness"]
        node = material.node_tree.nodes.get("Principled BSDF")
        for socket, value in (("Base Color", state["rgba"]), ("Metallic", state["metallic"]), ("Roughness", state["roughness"])):
            node.inputs[socket].default_value = value
        materials[key] = material
    cache = {}

    def case(ident, operation, expected, fn):
        try:
            evidence = fn()
            checks.append({"id": ident, "input": "frozen ten profiles / actual evaluated fixture meshes", "operation": operation,
                           "expected": expected, "passed": True, "evidence": evidence})
            print("PASS", ident, flush=True)
        except Exception as exc:
            checks.append({"id": ident, "operation": operation, "expected": expected, "passed": False,
                           "error": str(exc), "traceback": traceback.format_exc()})
            print("FAIL", ident, str(exc), flush=True)

    def build(p):
        r = G.build_hall(p, collection, materials, cache)
        M.apply_front_reference_paint(r, materials)
        results[p["building_id"]] = r
        reader.refresh()
        return {"id": p["building_id"], "actual_meshes": len(r["objects"]), "actual_openings": len(r["openings"])}

    def expectation(ident):
        return expected[ident]

    def transform_state(obj):
        return {"basis": obj.matrix_basis.copy(), "location": obj.location.copy(), "scale": obj.scale.copy(),
                "rotation_mode": obj.rotation_mode, "rotation_euler": obj.rotation_euler.copy(),
                "rotation_quaternion": obj.rotation_quaternion.copy(), "rotation_axis_angle": tuple(obj.rotation_axis_angle)}

    def restore_transform(obj, state):
        obj.matrix_basis = state["basis"]
        obj.rotation_mode = state["rotation_mode"]
        obj.location = state["location"]
        obj.scale = state["scale"]
        if obj.rotation_mode == "QUATERNION":
            obj.rotation_quaternion = state["rotation_quaternion"]
        elif obj.rotation_mode == "AXIS_ANGLE":
            obj.rotation_axis_angle = state["rotation_axis_angle"]
        else:
            obj.rotation_euler = state["rotation_euler"]

    @contextmanager
    def moved_proxies(names):
        require(len(names) == len(set(names)), "Repeated proxy movement")
        states = {name: transform_state(bpy.data.objects[name]) for name in names}
        try:
            for name in names:
                bpy.data.objects[name].location.x += 1000
            reader.refresh()
            yield
        finally:
            for name, state in states.items():
                restore_transform(bpy.data.objects[name], state)
            reader.refresh()

    for i, ident in enumerate(IDS, 1):
        case("EXT-BUILD-" + str(i), "Call frozen G14 only", "actual independent meshes", lambda ident=ident: build(profiles[ident]))

    def contract():
        require(set(results) == set(IDS), "Not all ten exteriors built")
        require(doc["whole_city_objective_complete"] is False and doc["human_approval"] == "pending", "Whole-city/approval scope changed")
        for k in ("third_party_cost", "paid_service_calls"):
            require(type(doc[k]) is int and doc[k] == 0, "integer-zero budget contract: " + k)
        fields = ("source_polygon_world", "source_holes_world", "source_polygon_local", "source_holes_local", "anchor", "rotation_z_rad", "source_part_id")
        for ident, r in results.items():
            p = r["profile"]
            require(all(p[k] == registered[ident][k] for k in fields), "Source/frame binding differs " + ident)
            for key in ("source_component_id", "source_actual_actor_names", "typed_factual_source_fields", "original_typed_factual_source_fields"):
                if key in p and key in registered[ident]:
                    require(p[key] == registered[ident][key], "Registry fact/provenance differs " + key)
            require(p["source_part_id"] == expectation(ident)["source_part_id"], "Independent official/source expectation differs")
            K.check_profile_intent(p, expectation(ident))
            require(not p.get("source6m_proxy_height_is_real_building_height", False), "Source proxy height promoted")
            require(r["manifest"]["occupied_storeys"] is None and not r["manifest"]["complete_reconstruction_proven"], "Completion falsely certified")
            for obj in [r["root"]] + r["objects"]:
                require(type(obj["third_party_cost"]) is int and obj["third_party_cost"] == 0, "integer-zero budget contract: " + obj.name)
                require(obj["human_approval"] == "pending", "Approval changed")
            require(all(o.parent == r["root"] for o in r["objects"]), "Factory body parent differs")
        require(sum(len(r["openings"]) for r in results.values()) == expected_aperture_count, "Independently qualified representative aperture population differs")
        require(all(not r["openings"] for ident, r in results.items() if ident not in (PHOTO_ID, GATE_ID)), "Unknown hall aperture invented")
        return {"source_frames_bound": 10, "factual_main_depths_null": 9, "gate_factual_depth": 1,
                "historical_accuracy_proven": False, "saved_city_CPU_and_media": "pending"}

    def topology():
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
        evidence = []
        for r in results.values():
            p, d = r["profile"], r["profile"]["dimensions"]
            axes = K.reference_axes(p)
            expected = axes["perimeter"]
            columns = r["components"].get("column", []) + r["components"].get("pilaster", [])
            require(len(columns) == len(expected) == len(r["components"]["column_base"]), "Actual perimeter column inventory differs")
            used = set()
            for obj in columns:
                low, high = C.bounds(local_vertices(r, obj))
                center = [(low[i] + high[i]) / 2 for i in (0, 1)]
                errors = [max(abs(center[k] - point[k]) for k in (0, 1)) for point in expected]
                index = min(range(len(errors)), key=errors.__getitem__)
                require(errors[index] <= C.EPS and index not in used, "Actual column axis differs: " + obj.name)
                used.add(index)
                C.close(low[2], d["floor_z_m"] + d["column_base_height_m"], "Actual column lowZ")
                C.close(high[2], d["column_top_z_m"], "Actual column highZ")
            evidence.append({"id": p["building_id"], "actual_perimeter_columns": len(columns),
                             "factual_bays": [p["bays_x"], p["bays_y"]], "study_reference_counts": [axes["reference_count_x"], axes["reference_count_y"]]})
        return evidence

    def contact_ray(names, point, upward, label):
        dz = Vector((0, 0, .02))
        hit = reader.ray(names, point - dz if upward else point + dz, point + dz if upward else point - dz)
        require(hit is not None and abs(hit["point"].z - point.z) <= C.EPS, label)

    def contacts():
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
        rays, solids, total = 0, 0, 0
        for r in results.values():
            movable = [n for row in r["openings"] for k in ("infill_proxy_names", "leaf_reference_names") for n in row[k]]
            with moved_proxies(movable):
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
        require(total == expected_aperture_count and rays == expected_aperture_count * 50, "Independent aperture population differs")
        require(not any(o.name.startswith("TEMP_OPENING_") for o in bpy.data.objects), "Temporary cutter object remains")
        return {"actual_apertures": total, "bidirectional_rays": rays, "solid_jamb_controls": solids, "all_hall_meshes_queried_with_only_declared_proxies_temporarily_moved": True, "runtime_passability_certified": False}

    def unknown_infills():
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
        require(count == expected_aperture_count, "Independent unresolved set proxy count differs")
        return {"unknown_set_proxies": count, "actual_leaf_count_certified": False}

    def roof_form(only=None):
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
        evidence = []
        used = {v for p in profiles.values() for v in p["material_scheme"].values()} | {p["caller_front_columns_material_key"] for p in profiles.values() if p.get("caller_front_columns_material_key") is not None}
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
            for index in (0, 1):
                color = obj.data.materials[index].node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value
                require(color[1] > color[0] * 1.25 and color[1] > color[2] * 1.1, "Actual green roof material replaced")
            evidence.append({"id": r["profile"]["building_id"], "actual_face_material_counts": counts})
        front_red = 0
        neutral_columns = 0
        for r in results.values():
            profile = r["profile"]
            for obj in r["components"].get("column", []) + r["components"].get("pilaster", []):
                low, high = C.bounds(local_vertices(r, obj))
                y = (low[1] + high[1]) / 2
                front = profile["building_id"] == PHOTO_ID and abs(y + profile["dimensions"]["body_depth_m"] / 2) <= C.EPS
                key = "red" if front else profile["material_scheme"]["column"]
                require(list(obj.data.materials) == [materials[key]], "Actual reference-column material scope differs")
                if front:
                    require(obj.data.users == 1 and obj.get("v18_front_paint_reference") is True, "Front paint changed shared data or lacks scope")
                    front_red += 1
                else:
                    require(not obj.get("v18_front_paint_reference", False), "Unseen side/rear paint promoted")
                    neutral_columns += 1
            for role, key in (("beam", "beam"), ("wall", "wall"), ("roof_closure_wall", "wall")):
                for obj in r["components"].get(role, []):
                    require(list(obj.data.materials) == [materials[profile["material_scheme"][key]]], "Unverified wall/beam paint differs")
        require(front_red == profiles[PHOTO_ID]["bays_x"] + 1, "Photo-qualified front reference paint count differs")
        return {"used_actual_palette_keys": sorted(used), "roof_domains": evidence, "green_top_category_only_not_measured_pigment": True, "actual_red_front_reference_columns": front_red, "actual_neutral_other_reference_columns": neutral_columns}

    def proxy_occlusion():
        hits = []
        for r in results.values():
            all_names = [obj.name for obj in r["collection"].objects if obj.type == "MESH"]
            for row in r["openings"]:
                require(row["kind"] in ("door", "window") and row["leaf_pose"] == "unknown", "Unknown pose converted to open/closed fact")
                center, normal = Vector(row["center_world"]), Vector(row["normal_world"])
                names = row["infill_proxy_names"]
                hit = reader.ray(names, center-normal*.6, center+normal*.6)
                require(hit is not None, "Actual unresolved display proxy does not occlude centre")
                require(reader.ray(all_names, center-normal*.6, center+normal*.6) is not None, "Original exterior display falsely presented as clear passage")
                hits.append({"opening": row["id"], "actual_proxy_hit": hit["object"], "historical_open_or_closed_state_proven": False})
        require(len(hits) == expected_aperture_count, "Independent proxy centre test population differs")
        return {"actual_display_proxy_hits": hits, "gate_runtime_through_route_certified": False}

    positives = [("HALL-01", contract), ("HALL-02", topology), ("HALL-03", column_axes), ("HALL-04", contacts),
                 ("HALL-05", apertures), ("HALL-06", unknown_infills), ("HALL-07", roof_form), ("HALL-08", palette), ("HALL-08B", proxy_occlusion)]
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
        r = results[PHOTO_ID]
        base = r["components"]["column_base"][0]
        def move(obj, axis):
            old = transform_state(obj)
            obj.location[axis] += .01
            return old
        def unmove(obj, matrix):
            if matrix is not None:
                restore_transform(obj, matrix)
        negative("EXTRA-01", "Lift actual base by .01m", lambda: move(base, 2), lambda m: unmove(base, m), contacts, "bottom rim leaves actual support")
        col = (r["components"].get("column", []) + r["components"].get("pilaster", []))[0]
        negative("EXTRA-02", "Move actual column axis .01m", lambda: move(col, 0), lambda m: unmove(col, m), column_axes, "Actual column axis differs")
        row = next(x for x in r["openings"] if x["kind"] == "door")
        def curtain():
            o = F.box("V18_QA_TEMP_OPAQUE_CURTAIN", row["center_local"], (row["clear_width_m"], .12, row["clear_height_m"]), materials[r["profile"]["material_scheme"]["wall"]], r["collection"], None, "qa_curtain")
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
            old = transform_state(proxy)
            proxy.scale.x *= .5
            return old
        negative("EXTRA-04", "Halve actual unknown set proxy width", shrink, lambda m: unmove(proxy, m), unknown_infills, "Actual unknown proxy width differs")
        gate = results[GATE_ID]
        front_roof = bpy.data.objects[gate["roofs"][0]["roof_object"]]
        rear_roof = bpy.data.objects[r["roofs"][0]["roof_object"]]
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
        negative("EXTRA-05", "Replace actual front hip skin by closed hard-gable geometry; labels unchanged", swap_roof, restore_roof, lambda: roof_form(gate), "Actual xieshan hip end fall missing")
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
        def wrong_green():
            obj = bpy.data.objects[r["roofs"][0]["roof_object"]]
            old = obj.data.materials[0]
            obj.data.materials[0] = materials[r["profile"]["material_scheme"]["frame"]]
            return obj, old
        def restore_material(token):
            if token:
                obj, old = token
                obj.data.materials[0] = old
        negative("EXTRA-08", "Replace actual roof-main material by a distinct actual frame slot", wrong_green, restore_material, palette, "Actual roof material slots differ")
        def hide_proxy():
            old = (proxy.hide_render, proxy.hide_viewport, proxy.hide_get())
            proxy.hide_render = True
            proxy.hide_set(True)
            return old
        def restore_proxy_visibility(token):
            if token is not None:
                proxy.hide_render, proxy.hide_viewport = token[:2]
                proxy.hide_set(token[2])
        negative("EXTRA-09", "Actually hide unresolved set proxy", hide_proxy, restore_proxy_visibility, unknown_infills, "Unknown proxy unexpectedly hidden")
        back_column = next(obj for obj in r["components"].get("column", []) + r["components"].get("pilaster", []) if obj["study_column_axis"][1] > 0)
        def spread_paint():
            old = back_column.data
            private = old.copy()
            back_column.data = private
            private.materials[0] = materials["red"]
            return old, private
        def restore_spread(token):
            if token:
                old, private = token
                back_column.data = old
                bpy.data.meshes.remove(private)
        negative("EXTRA-10", "Actually spread front photo red to an unseen rear reference column", spread_paint, restore_spread, palette, "Actual reference-column material scope differs")
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

    def plain(value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if hasattr(value, "to_list"):
            return [plain(item) for item in value.to_list()]
        if hasattr(value, "items"):
            return {str(key): plain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [plain(item) for item in value]
        raise TypeError("Unsupported actual property type " + type(value).__name__)

    def export():
        buildings = []
        for r in results.values():
            selected = {o.name for o in r["objects"]}
            geometry = {}
            for name in sorted(selected):
                m, obj = reader.mesh(name), bpy.data.objects[name]
                material_states = []
                for material in obj.data.materials:
                    node = material.node_tree.nodes.get("Principled BSDF") if material and material.use_nodes else None
                    material_states.append({"name": material.name if material else None, "diffuse": list(material.diffuse_color) if material else None,
                                            "shader": list(node.inputs["Base Color"].default_value) if node else None})
                geometry[name] = {"object": name, "role": obj.get("semantic_role"), "vertices": [list(v) for v in m["vertices"]],
                                  "triangles": [list(t) for t in m["triangles"]], "triangle_materials": m["triangle_materials"],
                                  "material_indices": m["triangle_materials"], "materials": material_states,
                                  "raw_vertices": [list(v.co) for v in obj.data.vertices], "raw_faces": [list(f.vertices) for f in obj.data.polygons],
                                  "raw_face_material_indices": [f.material_index for f in obj.data.polygons],
                                  "matrix_world": [list(row) for row in obj.matrix_world], "parent": obj.parent.name if obj.parent else None,
                                  "custom_properties": plain(dict(obj.items())), "hidden": bool(obj.hide_render or obj.hide_viewport or obj.hide_get()),
                                  "support_object": obj.get("support_object"), "roof_contact_object": obj.get("roof_contact_object")}
            buildings.append({"id": r["profile"]["building_id"], "profile": r["profile"], "root": r["root"].name,
                              "actual_root_matrix_world": [list(row) for row in r["root"].matrix_world],
                              "root_custom_properties": plain(dict(r["root"].items())), "reference_floor": r["reference_floor"].name,
                              "components": {k: [o.name for o in objects] for k, objects in r["components"].items()}, "geometry": geometry,
                              "roofs": r["roofs"], "openings": r["openings"], "caller_material_overrides": r.get("caller_material_overrides", []), "objects": [o.name for o in r["objects"]], "all_new_mesh_count": len(r["objects"])})
        readout = {"schema": "v18-ten-exterior-actual-factory-geometry/1", "coordinate_space": "WORLD", "profiles_sha256": args.profiles_sha256,
                   "registry_file": str(args.registry.resolve()), "registry_sha256": args.registry_sha256,
                   "expectations_file": str(args.expectations.resolve()), "expectations_sha256": args.expectations_sha256,
                   "representative_apertures_not_historical_opening_count": True,
                   "palette_sha256": args.palette_sha256, "inputs_sha256": files, "buildings": buildings,
                   "producer_module_file": "work/courtyard_hall_buildings.py", "producer_module_sha256": PINS["work/courtyard_hall_buildings.py"],
                   "native_opened": False, "native_saved": False, "rendered": False, "third_party_cost": 0,
                   "raw_old_source_fixture_reconstructed": False, "physical_absolute_accuracy_proven": False,
                   "complete_source_cap_and_area_support_external_CPU": "pending", "caller_context_and_saved_city": "pending"}
        path = out / "actual-exterior-geometry.json"
        write(path, readout)
        return {"path": str(path), "sha256": sha(path), "full_geometry_objects": sum(len(b["geometry"]) for b in buildings)}
    case("HALL-09-READOUT", "Export restored actual full cap/support/roof triangles", "Independent CPU input; no native saved", export)

    def final_guard():
        reader.refresh()
        require(C.canonical(snapshot()) == baseline, "Final all-object/material/camera/datablock fingerprint changed")
        require(all(sha(p) == h for p, h in files.items()), "Input file bytes changed")
        require(not bpy.data.filepath, "Factory script acquired native filepath")
        return {"raw_source_fixtures_reconstructed": False, "all_postbuild_objects_materials_camera_data_restored": True,
                "all_input_sha_unchanged": True, "saved_city_CPU_and_media": "pending"}
    case("FINAL-GUARD", "Full state and input bytes after all mutations", "Exact original-state restoration", final_guard)
    report = {"schema": "v18-ten-exterior-factory-tests/1", "passed": sum(c["passed"] for c in checks),
              "failed": sum(not c["passed"] for c in checks), "checks": checks, "inputs_sha256": files,
              "scope": "Actual factory geometry only; complete caller contexts/native/saved/media pending", "third_party_cost": 0}
    write(out / "actual-exterior-tests.json", report)
    print("V18-EXTERIOR-QA", report["passed"], report["failed"], flush=True)
    if report["failed"]:
        raise AssertionError("Actual hall factory QA failed; retain real red report")


if __name__ == "__main__":
    main()
