"""Small isolated gate/context factory. Root alone runs Blender; never saves."""
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
BINDING_SHA = "86bff49073c9da30ebed91b4b2f92620067216cb7d3c6f6596d844a67d94a94e"
GATE = "nansansuo_common_gate"


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "to_list"):
        return [plain(v) for v in value.to_list()]
    if hasattr(value, "items"):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    raise TypeError(type(value).__name__)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = args.output_dir.resolve()
    require(out.is_relative_to(HERE) and not out.exists(), "Fresh connection-qa output directory required")
    require(not bpy.data.filepath, "Factory startup required")
    bindings_path = HERE / "fixture-bindings-v1.json"
    require(sha(bindings_path) == BINDING_SHA, "Frozen binding drift")
    bindings = json.loads(bindings_path.read_text())
    files = dict(bindings["inputs_sha256"])
    files[str(bindings_path.relative_to(ROOT))] = BINDING_SHA
    files[str(Path(__file__).resolve().relative_to(ROOT))] = sha(__file__)
    for path, expected in files.items():
        require(sha(ROOT / path) == expected, "Input SHA drift: " + path)
    out.mkdir(parents=True)
    profile_doc = json.loads((ROOT / "work/restoration-v18/profiles/building-profiles-v1.json").read_text())
    palette_doc = json.loads((ROOT / "work/restoration-v18/profiles/palette-v1.json").read_text())
    for path, expected in {**profile_doc["source_files"], **palette_doc["source_files_sha256"]}.items():
        require(sha(ROOT / path) == expected, "Transitive input drift: " + path)
        files[path] = expected
    proposal = json.loads((ROOT / "work/restoration-v18/registration/gate-wall-connection/planned-gap-and-source-contained-proposal-01.json").read_text())
    capture = json.loads((ROOT / "work/restoration-v18/registration/actual-source-actors.json").read_text())
    p = next(p for p in profile_doc["buildings"] if p["building_id"] == GATE)
    C = module("v18_connector_audit_core", ROOT / "work/restoration-v16/saved-audit/saved_audit_core.py")
    sys.path.insert(0, str(ROOT / "work"))
    import courtyard_hall_buildings as G
    import forbidden_city_geometry as F
    H = module("v18_gate_context_builder", ROOT / "work/restoration-v18/gate_wall_connections.py")
    helpers = C.frozen_helpers(ROOT)
    reader = C.MeshReader(bpy)
    checks, mutants = [], []

    def case(ident, operation, expected, fn):
        try:
            evidence = fn()
            checks.append({"id": ident, "input": "frozen gate/proposal and reconstructed captured old walls", "operation": operation,
                           "expected": expected, "passed": True, "evidence": evidence})
            print("PASS", ident, flush=True)
        except Exception as exc:
            checks.append({"id": ident, "operation": operation, "expected": expected, "passed": False,
                           "error": str(exc), "traceback": traceback.format_exc()})
            print("FAIL", ident, str(exc), flush=True)

    def make_material(name, rgba, metallic, roughness):
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        material.diffuse_color = rgba
        material.metallic, material.roughness = metallic, roughness
        node = material.node_tree.nodes.get("Principled BSDF")
        for socket, value in (("Base Color", rgba), ("Metallic", metallic), ("Roughness", roughness)):
            node.inputs[socket].default_value = value
        return material

    materials = {k: make_material("R18_" + k, state["rgba"], state["metallic"], state["roughness"])
                 for k, state in palette_doc["materials"].items()}
    old_materials = {k: make_material(k, v["diffuse_rgba"], v["metallic"], v["roughness"])
                     for k, v in capture["material_evidence"].items()}
    old_walls = {}
    for row in proposal["rows"]:
        source = capture["actor_evidence"][row["original_wall_actor"]]
        require(source["parent"] is None, "Only captured world-root old wall fixture supported")
        mesh = bpy.data.meshes.new(source["data_name"])
        mesh.from_pydata(source["raw_vertices"], [], source["raw_faces"])
        mesh.update()
        for link, name in source["actual_material_slots"]:
            require(link == "DATA", "Captured material linkage differs")
            mesh.materials.append(old_materials[name])
        for face, index in zip(mesh.polygons, source["raw_face_material_indices"]):
            face.material_index = index
        obj = bpy.data.objects.new(source["name"], mesh)
        for state in source["collections"]:
            collection = F.ensure_collection(state["name"])
            collection.hide_render, collection.hide_viewport = state["hide_render"], state["hide_viewport"]
            collection.objects.link(obj)
        obj.matrix_world = Matrix(source["matrix_world"])
        obj.color = source["object_rgba"]
        for k, v in source["custom_properties"].items():
            obj[k] = v
        for key in ("hide_render", "hide_viewport"):
            setattr(obj, key, source["visibility"][key])
        obj.hide_set(source["visibility"]["hide_get"])
        old_walls[row["side"]] = obj

    collection = F.ensure_collection("V18_GATE_CONNECTION_FACTORY_ONLY")
    result = G.build_hall(p, collection, materials, {})
    body_names = [o.name for o in result["objects"]]
    require(len(body_names) == 49, "Frozen gate body mesh population differs")
    reader.refresh()

    def geometry(obj):
        m = reader.mesh(obj.name)
        states = []
        for material in obj.data.materials:
            node = material.node_tree.nodes.get("Principled BSDF") if material and material.use_nodes else None
            states.append({"name": material.name if material else None,
                           "diffuse": list(material.diffuse_color) if material else None,
                           "shader": list(node.inputs["Base Color"].default_value) if node else None})
        return {"object": obj.name, "role": obj.get("semantic_role"),
                "vertices": [list(v) for v in m["vertices"]], "triangles": [list(t) for t in m["triangles"]],
                "triangle_materials": m["triangle_materials"], "material_indices": m["triangle_materials"],
                "raw_vertices": [list(v.co) for v in obj.data.vertices], "raw_faces": [list(f.vertices) for f in obj.data.polygons],
                "raw_face_material_indices": [f.material_index for f in obj.data.polygons],
                "matrix_world": [list(row) for row in obj.matrix_world], "parent": obj.parent.name if obj.parent else None,
                "custom_properties": plain(dict(obj.items())), "materials": states,
                "actual_material_slots": [[slot.link, slot.material.name if slot.material else None] for slot in obj.material_slots],
                "collections": [{"name": c.name, "hide_render": c.hide_render, "hide_viewport": c.hide_viewport} for c in obj.users_collection],
                "visibility": helpers["visibility"](obj), "hidden": bool(obj.hide_render or obj.hide_viewport or obj.hide_get())}

    before_old = {side: geometry(obj) for side, obj in old_walls.items()}
    before_body = {name: geometry(bpy.data.objects[name]) for name in body_names}
    original_source_population_before = sum(bool(o.get("source_building_id")) for o in bpy.data.objects)
    created = H.build_gate_wall_connections(result, materials, proposal)
    reader.refresh()
    connectors = {row["side"]: bpy.data.objects[row["objects"][0]] for row in created["components"]}
    sidewalls = {side: bpy.data.objects["V14_" + GATE + "_wall_" + side] for side in ("west", "east")}

    def contract():
        require(set(connectors) == {"west", "east"} and len(created["objects"]) == 2, "Exactly two source context connectors required")
        require(set(body_names).isdisjoint(o.name for o in created["objects"]), "Context overlaps frozen body inventory")
        require(len(result["objects"]) == 51, "Caller context append changed expected inventory")
        for obj in connectors.values():
            require(obj.parent == result["root"] and obj.get("semantic_role") == H.ROLE, "Context role/root differs")
            require(not any(key in obj for key in ("source_building_id", "source_part_id", "source_wall_id", "source_reference_part_id")), "Old source identifier inherited")
            require(list(obj.data.materials) == [materials["grey"]], "Connector neutral material differs")
            require(obj.get("unmeasured_source_context") is True and obj.get("not_historical_attachment") is True, "Unknown scope promoted")
            require(obj.get("complete_old_endcap_continuation_claimed") is False, "Partial endcap promoted to full width")
            require(type(obj.get("third_party_cost")) is int and obj["third_party_cost"] == 0, "Integer-zero cost differs")
        return {"body_objects_preserved": 49, "new_context_objects": 2, "base_embedded_in_reference_slab": True,
                "historical_attachment_or_dimension_proven": False, "complete_join_external_CPU": "pending"}

    def topology():
        return {o.name: C.closed_positive_topology(reader.mesh(o.name)) for o in list(connectors.values()) + list(old_walls.values()) + list(sidewalls.values()) + [result["reference_floor"]]}

    def probes():
        evidence = []
        for probe in bindings["bvh_probes"]:
            side = probe["side"]
            other = old_walls[side] if probe["end"] == "old_wall" else sidewalls[side]
            x, y = probe["xy_world"]
            for obj, z in ((connectors[side], 0), (connectors[side], 3), (other, probe["other_bottom_z_m"])):
                hit = reader.ray([obj.name], Vector((x, y, z-.02)), Vector((x, y, z+.02)))
                require(hit is not None and abs(hit["point"].z-z) < C.EPS, "Actual overlap-interior cap probe misses: " + obj.name)
            evidence.append({**probe, "actual_connector": connectors[side].name, "actual_other": other.name, "actual_cap_hits": 3})
        return {"selected_actual_cap_probes": evidence, "full_area_join_proven_by_these_probes": False}

    def guards():
        for side, obj in old_walls.items():
            require(geometry(obj) == before_old[side], "Reconstructed captured old wall changed: " + side)
        for name, expected in before_body.items():
            require(geometry(bpy.data.objects[name]) == expected, "Frozen gate body geometry/material/matrix changed: " + name)
        return {"complete_old_wall_fixture_states_unchanged": 2, "complete_gate_body_mesh_states_unchanged": 49,
                "original_city_native_opened": False, "original_native_guard_claimed": False}

    for ident, operation, fn in (("CON-01", "Read caller inventory, scope and actual materials", contract),
                                  ("CON-02", "Check complete actual triangle topology and signed component volumes", topology),
                                  ("CON-03", "BVH at four frozen overlap-interior points", probes),
                                  ("CON-04", "Full captured-wall and gate-body state equality", guards)):
        case(ident, operation, "Actual positive control; whole-area join still requires external CPU", fn)

    def snapshot():
        return {"objects": {o.name: ({"fingerprint": helpers["mesh_fingerprint"](o), "relations": C.mesh_relations(o), "visibility": helpers["visibility"](o)} if o.type == "MESH" else C.nonmesh_state(o, helpers["visibility"])) for o in bpy.data.objects},
                "materials": {m.name: helpers["material_state"](m) for m in bpy.data.materials},
                "data_names": {key: sorted(v.name for v in getattr(bpy.data, key)) for key in ("objects", "meshes", "materials", "collections", "cameras", "images", "curves")}}
    baseline = C.canonical(snapshot())

    def positive():
        reader.refresh()
        return {"contract": contract(), "topology": topology(), "probes": probes(), "guards": guards()}

    def negative(ident, operation, mutate, restore, checker, expected_reason):
        def run():
            positive()
            token = None
            try:
                token = mutate()
                reader.refresh()
                mutants.append({"id": ident, "mutation": operation, "connectors": {side: geometry(obj) for side, obj in connectors.items()},
                                "expected_failure": expected_reason, "actual_geometry_exported_before_restore": True})
                rejected = C.negative_rejected(checker)
                require(expected_reason in rejected["reason"], "Unrelated mutation rejection: " + rejected["reason"])
            finally:
                restore(token)
                reader.refresh()
            positive()
            require(C.canonical(snapshot()) == baseline, "Mutation failed exact complete-state restore")
            return {**rejected, "actual_mutant_world_exported": True, "exact_state_restored": True,
                    "external_whole_area_mutant_rejection": "pending"}
        case(ident, operation, "Reject actual geometry change and restore exact original state", run)

    if not any(not row["passed"] for row in checks):
        west = connectors["west"]
        def move():
            state = {"basis": west.matrix_basis.copy(), "location": west.location.copy(), "scale": west.scale.copy(), "rotation_euler": west.rotation_euler.copy()}
            west.location.x += .03
            return state
        def restore_move(state):
            if state is not None:
                west.matrix_basis = state["basis"]
                west.location, west.scale, west.rotation_euler = state["location"], state["scale"], state["rotation_euler"]
        negative("EXTRA-01", "Move actual west connector local X by 0.03m with labels unchanged", move, restore_move, probes, "Actual overlap-interior cap probe misses")
        def delete_cap():
            old, mesh = west.data, west.data.copy()
            bm = bmesh.new()
            try:
                bm.from_mesh(mesh)
                z = max(v.co.z for v in bm.verts)
                face = next(f for f in bm.faces if all(abs(v.co.z-z) < 1e-6 for v in f.verts))
                bmesh.ops.delete(bm, geom=[face], context="FACES_ONLY")
                bm.to_mesh(mesh)
            finally:
                bm.free()
            west.data = mesh
            return old, mesh
        def restore_cap(state):
            if state:
                old, mesh = state
                west.data = old
                bpy.data.meshes.remove(mesh)
        negative("EXTRA-02", "Delete one actual west top-cap face from private copied mesh; labels unchanged", delete_cap, restore_cap, topology, "actual boundary/nonmanifold edge")
    else:
        checks.append({"id": "EXTRA-PRECONDITION", "passed": False, "error": "Positive failed; no negative success claimed"})

    def export():
        names = set(body_names) | {o.name for o in connectors.values()} | {o.name for o in old_walls.values()}
        readout = {"schema": "v18-gate-wall-connections-actual-factory-world/1", "coordinate_space": "WORLD", "inputs_sha256": files,
                   "proposal_sha256": H.PROPOSAL_FILE_SHA256,
                   "source_capture_sha256": files["work/restoration-v18/registration/actual-source-actors.json"],
                   "profile": p, "gate_root": result["root"].name, "actual_root_matrix_world": [list(r) for r in result["root"].matrix_world],
                   "context_components": created["components"], "connectors": [{"id": row["component_id"], "side": row["side"], "object": row["objects"][0]} for row in created["components"]],
                   "geometry": {name: geometry(bpy.data.objects[name]) for name in sorted(names)},
                   "actual_gate_sidewalls": {side: obj.name for side, obj in sidewalls.items()}, "reference_floor": result["reference_floor"].name,
                   "old_walls": {side: {"object": obj.name, "before": before_old[side], "after": geometry(obj)} for side, obj in old_walls.items()},
                   "original_source_population_before": original_source_population_before,
                   "original_source_population_after": sum(bool(o.get("source_building_id")) for o in bpy.data.objects),
                   "original_source_population_predicate": "count scene objects with truthy source_building_id; isolated factory count, not original-city2845",
                   "new_original_source_identifier_count": sum(any(k in o for k in ("source_building_id", "source_part_id", "source_wall_id", "source_reference_part_id")) for o in connectors.values()),
                   "old_source_visibility_changes": [side for side, obj in old_walls.items() if geometry(obj)["visibility"] != before_old[side]["visibility"]],
                   "real_geometry_negative_controls": mutants, "gate_body_objects_before_context": body_names,
                   "native_opened": False, "native_saved": False, "rendered": False, "producer_imported": False,
                   "raw_old_wall_fixture_reconstructed": True, "original_native_oldwall_guard_claimed": False,
                   "full_area_join_and_5mm_overlap_external_CPU": "pending", "source_and_floor_complete_area_external_CPU": "pending",
                   "third_party_cost": 0, "human_approval": "pending", "whole_city_objective_complete": False}
        path = out / "actual-gate-connections-geometry.json"
        write(path, readout)
        return {"file": str(path), "sha256": sha(path), "actual_exported_meshes": len(names), "real_geometry_mutants": len(mutants)}
    case("CON-05-READOUT", "Export actual restored WORLD and real mutant triangles", "Complete independent CPU input; no native saved", export)

    def final_guard():
        positive()
        require(C.canonical(snapshot()) == baseline, "Final complete scene/material state differs")
        require(all(sha(ROOT/path) == value for path, value in files.items()), "Frozen input bytes changed")
        require(not bpy.data.filepath, "Factory acquired native filepath")
        return {"all_factory_state_and_input_bytes_unchanged": True, "source_join_actual_CPU": "pending"}
    case("FINAL-GUARD", "Exact final scene and input SHA guard", "Original factory state restored", final_guard)
    report = {"schema": "v18-gate-connections-actual-factory-tests/1", "passed": sum(c["passed"] for c in checks), "failed": sum(not c["passed"] for c in checks),
              "checks": checks, "inputs_sha256": files, "scope": "Small real factory: gate49 + two reconstructed captured old walls + connectors2. Not saved native or full join proof.", "third_party_cost": 0}
    write(out / "actual-gate-connections-tests.json", report)
    print("V18-CONNECTION-QA", report["passed"], report["failed"], flush=True)
    if report["failed"]:
        raise AssertionError("Actual connection factory failed; preserve real red report")


if __name__ == "__main__":
    main()
