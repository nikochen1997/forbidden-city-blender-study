"""V18 caller-only front paint reference. No imports, I/O, saves or geometry edits."""
import json

PHOTO_BUILDING_ID = "nansansuo_middle_middle_hall"
PHOTO_SHA256 = "11ee8578f62e1566467928a81ef5ae793746dd89978a6e762b51659c049d47ce"


def _geometry(mesh):
    return ([tuple(v.co) for v in mesh.vertices], [tuple(f.vertices) for f in mesh.polygons],
            [f.material_index for f in mesh.polygons])


def apply_front_reference_paint(result, materials):
    """Apply only explicit profile caller_front_columns_material_key on private mesh copies."""
    profile = result["profile"]
    key = profile.get("caller_front_columns_material_key")
    if key is None:
        return []
    if profile["building_id"] != PHOTO_BUILDING_ID or key != "red" or key not in materials:
        raise ValueError("front paint is qualified only for this photographed hall and red category")
    front_y = -profile["dimensions"]["body_depth_m"] / 2
    columns = result["components"].get("column", []) + result["components"].get("pilaster", [])
    selected = [obj for obj in columns if abs(obj["study_column_axis"][1] - front_y) <= 1e-7]
    if len(selected) != profile["bays_x"] + 1:
        raise ValueError("complete front reference-column population differs")
    records = []
    for obj in selected:
        before = _geometry(obj.data)
        obj.data = obj.data.copy()
        if _geometry(obj.data) != before:
            raise AssertionError("material copy changed actual geometry")
        if not obj.data.materials:
            raise ValueError("front reference column has no existing material slot")
        obj.data.materials[0] = materials[key]
        obj["v18_front_paint_reference"] = True
        obj["paint_category_source_sha256"] = PHOTO_SHA256
        obj["paint_scope"] = "front photographed red category; RGB unmeasured; no rear/side paint inference"
        records.append({"object": obj.name, "material_key": key, "actual_material_name": materials[key].name,
                        "private_mesh_copy": True, "source_sha256": PHOTO_SHA256,
                        "scope": "front reference column only; no measured pigment or historical grid count"})
    result["caller_material_overrides"] = records
    result["manifest"]["caller_material_overrides"] = records
    result["root"]["v18_caller_material_overrides"] = json.dumps(records, ensure_ascii=False)
    return records
