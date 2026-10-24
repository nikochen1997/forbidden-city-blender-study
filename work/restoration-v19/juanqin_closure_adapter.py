"""Whole-face junctions for four newly generated V19 Juanqin closures only.

The frozen G14 helper and all previously saved city geometry remain untouched.
This adapts caller-owned new meshes to the already generated actual roof.
"""
import hashlib
import json

from mathutils import Matrix

import forbidden_city_geometry as F
import northern_court_towers as T


def _digest(obj):
    doc = {"vertices": [list(v.co) for v in obj.data.vertices],
           "faces": [list(p.vertices) for p in obj.data.polygons],
           "material_indices": [p.material_index for p in obj.data.polygons],
           "materials": [m.name if m else None for m in obj.data.materials]}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _identity(obj):
    return all(abs(obj.matrix_basis[i][j]-Matrix.Identity(4)[i][j]) < 1e-12
               for i in range(4) for j in range(4))


def replace_juanqin_closures(result):
    """Replace only data of four new, local, single-material closure objects.

    XY boundaries and bottom elevation are taken from the actual new mesh.
    Top faces are clipped from every actual downward roof triangle, preserving
    all roof panel seams rather than interpolating forty sampled stations.
    """
    profile = result["profile"]
    if profile["building_id"] != "juanqinzhai" or profile["source_part_id"] != "way-1341826246-p0":
        raise ValueError("adapter limited to this newly generated Juanqin study")
    roofs = result["roofs"]
    if len(roofs) != 1 or roofs[0]["roof_type"] != "juanpeng_yingshan":
        raise ValueError("single generated rolled hard-gable roof required")
    objects = {obj.name: obj for obj in result["objects"]}
    roof = objects[roofs[0]["roof_object"]]
    closures = result["components"].get("roof_closure_wall", [])
    if len(closures) != 4 or {obj.get("wall_side") for obj in closures} != {"south", "north", "west", "east"}:
        raise ValueError("exact four newly generated side closures required")
    if not _identity(roof) or any(not _identity(obj) or obj.parent != result["root"] for obj in closures):
        raise ValueError("actual mesh-local frame must match the common study root")
    if any(len(obj.data.materials) != 1 or obj.data.materials[0] is None or obj.data.users != 1 for obj in closures):
        raise ValueError("caller-owned independent single-material closure data required")
    if any(len(face.vertices) != 3 for face in roof.data.polygons):
        raise ValueError("actual fixed roof triangles required")
    prepared = []
    for obj in closures:
        vertices = [tuple(v.co) for v in obj.data.vertices]
        xmin, xmax = min(v[0] for v in vertices), max(v[0] for v in vertices)
        ymin, ymax = min(v[1] for v in vertices), max(v[1] for v in vertices)
        bottom = min(v[2] for v in vertices)
        if abs(bottom-obj["closure_bottom_z_m"]) > 1e-6:
            raise ValueError("actual closure bottom differs from declared new wall junction")
        footprint = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
        surface = T._contact_surface(roof, footprint, bottom)
        prepared.append((obj, footprint, bottom, surface, _digest(obj)))
    # All four complete domains have succeeded before any datablock changes.
    records = []
    for obj, footprint, bottom, surface, before in prepared:
        old_name = obj.data.name
        obj.data = F._new_mesh("V19_Juanqin_exact_"+obj["wall_side"], surface.vertices,
                               surface.faces, obj.data.materials[0])
        T._fixed(obj)
        if "roof_contact_points_local" in obj:
            obj["legacy_sampled_points_for_diagnosis_only"] = obj["roof_contact_points_local"]
            del obj["roof_contact_points_local"]
        obj["caller_junction_adapter"] = "V19 exact actual downward roof triangles, four new Juanqin closures only"
        obj["support_footprint_local"] = json.dumps(footprint)
        obj["not_measured_concealed_structure"] = True
        records.append({"object": obj.name, "wall_side": obj["wall_side"],
                        "original_new_mesh_name": old_name, "original_new_mesh_sha256": before,
                        "replacement_local_mesh_sha256": _digest(obj), "roof": roof.name,
                        "footprint_local": footprint, "bottom_z_m": bottom,
                        "method": "whole convex footprint clipped to actual fixed roof underside triangles",
                        "dimension_status": "unmeasured_study"})
    result["caller_closure_replacements"] = records
    result["manifest"]["caller_closure_replacements"] = records
    result["assumptions"].append("V19 replaces only four newly generated Juanqin junction meshes with full actual roof-triangle contact caps; frozen G14 and saved city geometry unchanged.")
    result["root"]["caller_closure_replacements"] = json.dumps(records, ensure_ascii=False)
    return records
