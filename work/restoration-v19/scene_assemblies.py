"""Assemble four tested progress studies; no file, visibility or scene-save I/O."""
import json

import bpy

import forbidden_city_geometry as F
import courtyard_hall_buildings as G
import northern_court_towers as T
from biluo_pavilion import build_biluo_pavilion
from juanqin_closure_adapter_v2 import replace_juanqin_closures


def _materials(document, prefix, biluo=False):
    names = [prefix+key for key in document["materials"]]
    if any(name in bpy.data.materials for name in names):
        raise ValueError("new stage material name already exists")
    out = {}
    for key, row in document["materials"].items():
        rgba = row if biluo else row["rgba"]
        material = bpy.data.materials.new(prefix+key)
        material.use_nodes = True
        material.diffuse_color = rgba
        shader = material.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = rgba
        if not biluo:
            material.metallic, material.roughness = row["metallic"], row["roughness"]
            shader.inputs["Metallic"].default_value = row["metallic"]
            shader.inputs["Roughness"].default_value = row["roughness"]
        out[key] = material
    return out


def build_four(documents, collection):
    """Use the same formal inputs and material names as the actual factories.

    Bamboo is explicitly pending independent registration, not silently counted
    as one of these four. No source actor is hidden by the geometry assembly.
    """
    hall_doc = documents["hall_profiles"]
    if {p["building_id"] for p in hall_doc["buildings"]} != {"juanqinzhai", "yucuixuan"}:
        raise ValueError("exact two prepared hall profiles required")
    for profile in hall_doc["buildings"]:
        G._validate(profile)
    hall_mats = _materials(documents["hall_palette"], "V19_FORMAL_HALL_")
    results = []
    for profile in hall_doc["buildings"]:
        result = G.build_hall(profile, collection, hall_mats, {})
        if profile["building_id"] == "juanqinzhai":
            replace_juanqin_closures(result)
        result["builder"] = "hall"
        results.append(result)

    profile = documents["fuwang_profiles"]["profiles"][0]
    registered = documents["fuwang_registry"]["buildings"][0]
    if profile["building_id"] != registered["building_id"] or profile["building_id"] != "fuwangge":
        raise ValueError("exact Fuwang profile and source frame required")
    mats = _materials(documents["fuwang_palette"], "V19_FORMAL_FUWANG_")
    result = T.build_exterior_tower(profile, collection, mats, {})
    floor = registered["source_reference_floor"]
    surface = F._Surface()
    for triangle in F._triangulate_rings([floor["polygon_local"], *floor["holes_local"]]):
        surface.face([(x, y, floor["top_z_m"]) for x, y in triangle])
    F._volume_from_top(surface, floor["bottom_z_m"])
    slab = F._object("V19_Fuwang_complete_source_reference_floor",
                     F._new_mesh("V19_Fuwang_complete_source_reference_floor", surface.vertices, surface.faces, mats["base"]),
                     result["collection"], "source_reference_slab")
    slab.parent = result["root"]
    slab["reference_floor_only"], slab["not_measured_platform"] = True, True
    result["objects"].append(slab)
    result["components"]["source_reference_slab"] = [slab]
    result["reference_floor"] = slab
    result["root"].location = registered["anchor"]
    result["root"].rotation_euler.z = registered["rotation_z_rad"]
    result["registration"], result["builder"] = registered, "tower"
    results.append(result)

    mats = _materials(documents["biluo_palette"], "BILUO_", biluo=True)
    result = build_biluo_pavilion(documents["biluo_profile"], collection, mats, {})
    result["builder"] = "pavilion"
    results.append(result)
    bpy.context.view_layer.update()
    if {r["profile"]["building_id"] for r in results} != {"juanqinzhai", "yucuixuan", "fuwangge", "biluoting"}:
        raise AssertionError("four explicit progress subjects required")
    if sum(len(r["objects"]) for r in results) != 474:
        raise AssertionError("actual factory object inventory differs")
    for result in results:
        ident = result["profile"]["building_id"]
        for obj in [result["root"], *result["objects"]]:
            if "restoration_v14_building_id" in obj:
                del obj["restoration_v14_building_id"]
            obj["restoration_v19_building_id"] = ident
            obj["third_party_cost"], obj["paid_service_calls"] = 0, 0
            obj["human_approval"], obj["absolute_accuracy_claim"] = "pending", False
            obj["whole_city_objective_complete"] = False
        result["root"]["stage19_target_subjects"] = json.dumps(["fuwangge", "juanqinzhai", "yucuixuan", "zhuxiangguan", "biluoting"])
        result["root"]["stage19_pending_registration"] = "zhuxiangguan"
    return results
