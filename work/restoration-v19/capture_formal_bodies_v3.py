"""Build three formal, source-bounded studies in an isolated Blender factory.

Export actual WORLD triangles for independent complete-domain CPU checks.
No city is opened, hidden, saved, accepted or rendered by this script.
"""
import argparse
import copy
import hashlib
import json
import math
import sys
import traceback
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "work"))
sys.path.insert(0, str(HERE))
import forbidden_city_geometry as F
import courtyard_hall_buildings as G
import northern_court_towers as T
from juanqin_closure_adapter_v2 import replace_juanqin_closures, _digest

PINS = {
    "work/restoration-v19/juanqin_closure_adapter_v2.py": "76df84e167b9962e9e269af1748bf60037aaae3fe4d34618ea7abb19de2164d2",
    "work/restoration-v19/juanqin_closure_adapter.py": "8d23a76deab54030dd4978f6ed367625055e3e4bd3cda25f2cba3ed5a421012c",
    "work/restoration-v19/hall-profile-prep/building-profiles-v1.json": "1c5a96b76fd47b042801795728399171bbf7c7bff24dafecb3e309d62ddc5672",
    "work/restoration-v19/hall-profile-prep/palette-v1.json": "4bd454267656a98bef1bed3b9fd176a5e60cae6b1e25196efa80e52ff51568f2",
    "work/restoration-v19/fuwang-profile-prep/prepared-01/production-profiles.json": "a9d8f25cc1c346167d7d18f4e9d1b1b430ac45885e317d46cbe0ab58e3f82db5",
    "work/restoration-v19/fuwang-profile-prep/prepared-01/production-registry.json": "f0b4f77fe58c542fa6fce422a0a1a62614700661beeeca5bbb777645e010c09b",
    "work/restoration-v19/fuwang-profile-prep/prepared-01/production-palette.json": "50d1d537e90b6dc7ae6c72f874bd48bae4cd554f1e68b8f9ca2b86211d693540",
    "work/restoration-v19/northern_court_towers.py": "e71af7ab930eb8b5e209071a8ecbed06a7fc518d7c8e732776b55c736b74a613",
    "work/courtyard_hall_buildings.py": "5123db7be8948e9bdb4dc6d8edb712d01ad98075e5e6a40251be5aa8f666a86d",
    "work/forbidden_city_geometry.py": "23f815fc93057a0f69b66adc25536485fc05a33935f67fb1613073963e276efc",
    "work/restoration_buildings.py": "aac18ca8c219b8de544dd78d8a7b99000a4d0fe83d40553614065e0c998aaf60",
    "work/four_hall_buildings.py": "1d3267d25946ecf468da3a9d60103ef522c202452f60d0e500643d14ce9dcc1a",
    "work/square_garden_pavilions.py": "3370d6ae8fe7081f64686e4cf9ea33a192cba03d23af3433502f26662cf56d58",
    "work/imperial_monuments.py": "5af7e855072559b74e5b05964cad0a50420b04e152de8fc04428049ee993f47e",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(relative):
    return json.loads((ROOT / relative).read_text())


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        stream.write("\n")


def materials(doc, prefix):
    out = {}
    for key, row in doc["materials"].items():
        material = bpy.data.materials.new(prefix + key)
        material.use_nodes = True
        material.diffuse_color = row["rgba"]
        material.metallic, material.roughness = row["metallic"], row["roughness"]
        shader = material.node_tree.nodes.get("Principled BSDF")
        for name, value in (("Base Color", row["rgba"]), ("Metallic", row["metallic"]), ("Roughness", row["roughness"])):
            shader.inputs[name].default_value = value
        out[key] = material
    return out


def actual(obj, graph):
    evaluated = obj.evaluated_get(graph)
    data = evaluated.to_mesh()
    data.calc_loop_triangles()
    try:
        return {"name": obj.name, "role": obj.get("semantic_role"),
                "raw_vertices": [list(v.co) for v in obj.data.vertices],
                "raw_faces": [list(p.vertices) for p in obj.data.polygons],
                "vertices_world": [list(evaluated.matrix_world @ v.co) for v in data.vertices],
                "faces": [list(p.vertices) for p in data.polygons],
                "triangles_with_material_index": [[list(t.vertices), data.polygons[t.polygon_index].material_index] for t in data.loop_triangles],
                "matrix_world": [list(row) for row in obj.matrix_world],
                "material_slots": [m.name if m else None for m in data.materials],
                "props_json": json.dumps({k: obj[k] for k in obj.keys()}, ensure_ascii=False, default=list)}
    finally:
        evaluated.to_mesh_clear()


def topology(rows):
    principal = 0
    for row in rows:
        if row["role"] in ("ridge", "tile", "tile_ribs"):
            continue
        vertices = [Vector(p) for p in row["vertices_world"]]
        assert vertices and row["faces"]
        assert all(math.isfinite(x) for p in vertices for x in p)
        edges = Counter(tuple(sorted((a, b))) for face in row["faces"] for a, b in zip(face, face[1:] + face[:1]))
        assert edges and all(count == 2 for count in edges.values()), "not closed " + row["name"]
        origin = vertices[0]
        volume = sum((vertices[a] - origin).dot((vertices[b] - origin).cross(vertices[c] - origin)) / 6
                     for (a, b, c), _ in row["triangles_with_material_index"])
        assert volume > 1e-9, "nonpositive volume " + row["name"]
        principal += 1
    return {"principal_closed_positive_meshes": principal, "decorative_grouped_tubes_excluded": True}


def apertures(results, rows):
    by_name = {row["name"]: row for row in rows}
    ray_count = wall_controls = 0
    for result in results:
        for opening in result["openings"]:
            wall_name = opening["wall_segment_names"][0]
            row = by_name[wall_name]
            tree = BVHTree.FromPolygons([Vector(p) for p in row["vertices_world"]],
                                       [t[0] for t in row["triangles_with_material_index"]], all_triangles=True)
            center, normal = Vector(opening["center_world"]), Vector(opening["normal_world"])
            tangent = Vector((-normal.y, normal.x, 0))
            for horizontal in (-.4, 0, .4):
                for vertical in (-.4, 0, .4):
                    point = center + tangent * horizontal * opening["clear_width_m"] + Vector((0, 0, vertical * opening["clear_height_m"]))
                    for sign in (-1, 1):
                        assert tree.ray_cast(point + normal * sign, -normal * sign, 2)[0] is None, "blocked aperture " + opening["id"]
                        ray_count += 1
            for sign in (-1, 1):
                point = center + tangent * sign * (opening["clear_width_m"] / 2 + .04)
                assert tree.ray_cast(point + normal, -normal, 2)[0] is not None, "missing adjacent wall control"
                wall_controls += 1
    assert ray_count == 90 and wall_controls == 10, "Only the five qualified Juanqin study apertures are expected"
    return {"bidirectional_wall_aperture_rays": ray_count, "solid_wall_controls": wall_controls,
            "scope": "wall only; unresolved closed infill references are separately retained"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    dest = args.output_dir.resolve()
    assert dest.is_relative_to(HERE) and not dest.exists()
    assert all(sha(ROOT / relative) == pin for relative, pin in PINS.items())
    assert bpy.data.filepath == "", "Only factory-startup is allowed"
    pins = {**PINS, str(Path(__file__).relative_to(ROOT)): sha(__file__)}
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    collection = bpy.data.collections.new("V19_FORMAL_THREE_BODY_FACTORY_ONLY")
    bpy.context.scene.collection.children.link(collection)
    dest.mkdir(parents=True)
    results, checks, rows = [], [], []
    try:
        hall_doc = read("work/restoration-v19/hall-profile-prep/building-profiles-v1.json")
        hall_mats = materials(read("work/restoration-v19/hall-profile-prep/palette-v1.json"), "V19_FORMAL_HALL_")
        for profile in hall_doc["buildings"]:
            assert profile["allowed_hidden_source_actor_names"] == []
            built = G.build_hall(profile, collection, hall_mats, {})
            if profile["building_id"] == "juanqinzhai":
                before = {o.name: (_digest(o), [list(r) for r in o.matrix_local]) for o in built["objects"]}
                wrong = dict(built, profile=copy.deepcopy(profile))
                wrong["profile"]["building_id"] = "unrelated_hall"
                try:
                    replace_juanqin_closures(wrong)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Wrong-scope adapter input accepted")
                assert before == {o.name: (_digest(o), [list(r) for r in o.matrix_local]) for o in built["objects"]}
                replacements = replace_juanqin_closures(built)
                targets = {row["object"] for row in replacements}
                assert len(targets) == 4
                assert all(before[o.name] == (_digest(o), [list(r) for r in o.matrix_local])
                           for o in built["objects"] if o.name not in targets)
                checks.append({"id": "ADAPTER-SCOPE", "passed": True,
                               "evidence": {"actual_replaced_new_closures": len(targets),
                                            "all_other_new_meshes_and_transforms_unchanged": True,
                                            "wrong_scope_rejected_without_mutation": True}})
            results.append(built)
        base = "work/restoration-v19/fuwang-profile-prep/prepared-01/"
        profile = read(base + "production-profiles.json")["profiles"][0]
        registered = read(base + "production-registry.json")["buildings"][0]
        mats = materials(read(base + "production-palette.json"), "V19_FORMAL_FUWANG_")
        result = T.build_exterior_tower(profile, collection, mats, {})
        floor = registered["source_reference_floor"]
        surface = F._Surface()
        for triangle in F._triangulate_rings([floor["polygon_local"], *floor["holes_local"]]):
            surface.face([(x, y, floor["top_z_m"]) for x, y in triangle])
        F._volume_from_top(surface, floor["bottom_z_m"])
        slab = F._object("V19_Fuwang_complete_source_reference_floor", F._new_mesh("V19_Fuwang_complete_source_reference_floor", surface.vertices, surface.faces, mats["base"]), result["collection"], "source_reference_slab")
        slab.parent = result["root"]
        slab["reference_floor_only"], slab["not_measured_platform"] = True, True
        result["objects"].append(slab)
        result["components"]["source_reference_slab"] = [slab]
        result["reference_floor"] = slab
        result["root"].location = registered["anchor"]
        result["root"].rotation_euler.z = registered["rotation_z_rad"]
        result["registration"] = registered
        results.append(result)
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        rows = [actual(obj, graph) for result in results for obj in result["objects"]]
        for label, operation in (("FORMAL-01", lambda: topology(rows)), ("FORMAL-02", lambda: apertures(results, rows))):
            try:
                evidence = operation()
                checks.append({"id": label, "passed": True, "evidence": evidence})
            except Exception as exc:
                checks.append({"id": label, "passed": False, "error": str(exc), "traceback": traceback.format_exc()})
    except Exception as exc:
        checks.append({"id": "FORMAL-CONSTRUCTION", "passed": False, "error": str(exc), "traceback": traceback.format_exc()})
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        rows = [actual(obj, graph) for obj in collection.all_objects if obj.type == "MESH"]
    assert all(sha(ROOT / relative) == pin for relative, pin in pins.items())
    export = {"schema": "v19-three-formal-body-actual-world/1", "inputs_sha256": pins,
              "objects": rows, "buildings": [{"building_id": result["profile"]["building_id"],
               "profile": result["profile"], "registration": result.get("registration"),
               "root": result["root"].name, "root_matrix_world": [list(row) for row in result["root"].matrix_world],
               "objects": [o.name for o in result["objects"]], "components": {role: [o.name for o in objects] for role, objects in result["components"].items()},
               "reference_floor": result["reference_floor"].name, "openings": result["openings"], "roofs": result["roofs"],
               "contacts": result.get("contacts", []), "caller_closure_replacements": result.get("caller_closure_replacements", []), "unbuilt_features": result["unbuilt_features"]} for result in results],
              "scope": "actual isolated meshes only; complete source/support CPU still required; no current city/native approval",
              "native_opened": False, "native_saved": False, "source_hidden": False, "third_party_cost": 0}
    write(dest / "actual-world-geometry.json", export)
    report = {"schema": "v19-three-formal-body-actual-construction-tests/1", "checks": checks,
              "summary": {"passed": sum(row["passed"] for row in checks), "failed": sum(not row["passed"] for row in checks)},
              "actual_geometry_sha256": sha(dest / "actual-world-geometry.json"), "inputs_sha256": pins,
              "whole_city_complete": False, "human_approval": "pending", "third_party_cost": 0}
    write(dest / "actual-tests.json", report)
    print("V19_FORMAL_FACTORY", json.dumps(report["summary"]), flush=True)
    if report["summary"]["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
