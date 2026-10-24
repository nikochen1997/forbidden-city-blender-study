"""Read actual WORLD geometry; check full source floors and complete projections."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

MODEL_XY_TOL = 1e-4


def require(value, message):
    if not value:
        raise AssertionError(message)


def projection(row, bottom_only=False):
    vertices = row["vertices_world"]
    bottom = min(v[2] for v in vertices)
    faces = []
    for ids, _ in row["triangles_with_material_index"]:
        points = [vertices[i] for i in ids]
        if bottom_only and any(abs(p[2]-bottom) > 1e-6 for p in points):
            continue
        poly = Polygon([(p[0], p[1]) for p in points])
        if poly.area > 1e-14:
            require(poly.is_valid, "invalid actual projected triangle")
            faces.append(poly)
    require(faces, "no actual projected triangles")
    return unary_union(faces)


def check_building(building, by_name):
    p = building["profile"]
    registered = building["registration"]
    if registered is None:
        source = Polygon(p["source_polygon_world"], p["source_holes_world"])
    else:
        floor = registered["source_reference_floor"]
        source = Polygon(floor["polygon_world"], floor["holes_world"])
    require(source.is_valid and source.area > 0, "invalid full source domain")
    slab = projection(by_name[building["reference_floor"]], bottom_only=True)
    require(source.buffer(MODEL_XY_TOL).covers(slab) and slab.buffer(MODEL_XY_TOL).covers(source),
            "actual complete bottom cap differs from full source/holes " + p["building_id"])
    entire = unary_union([projection(by_name[name]) for name in building["objects"]])
    outside = entire.difference(source)
    require(source.buffer(MODEL_XY_TOL).covers(entire),
            "actual complete building projection leaves full source " + p["building_id"])
    return {"building_id": p["building_id"], "actual_meshes": len(building["objects"]),
            "source_outer_vertices": len(source.exterior.coords)-1, "source_holes": len(source.interiors),
            "source_area_m2": source.area, "actual_bottom_cap_area_m2": slab.area,
            "raw_bottom_cap_source_symmetric_difference_m2": slab.symmetric_difference(source).area,
            "bottom_cap_boundary_hausdorff_m": slab.boundary.hausdorff_distance(source.boundary),
            "raw_full_mesh_projection_outside_area_m2": outside.area,
            "model_XY_tolerance_m": MODEL_XY_TOL, "field_measurement_accuracy_claim": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--readout", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    require(not args.report.exists(), "preserve previous CPU report")
    data = args.readout.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    doc = json.loads(data)
    require(doc["schema"] == "v19-three-formal-body-actual-world/1", "unsupported actual geometry")
    require({b["building_id"] for b in doc["buildings"]} == {"fuwangge", "juanqinzhai", "yucuixuan"}, "three exact subjects required")
    rows = {row["name"]: row for row in doc["objects"]}
    evidence = [check_building(building, rows) for building in doc["buildings"]]
    building = doc["buildings"][0]
    mutant = copy.deepcopy(rows[building["reference_floor"]])
    for point in mutant["vertices_world"]:
        point[0] += .10
    bad_rows = dict(rows)
    bad_rows[mutant["name"]] = mutant
    try:
        check_building(building, bad_rows)
    except AssertionError as exc:
        require("bottom cap" in str(exc), "counterexample failed for unrelated reason")
        reason = str(exc)
    else:
        raise AssertionError("actual-export-derived shifted complete source cap was accepted")
    check_building(building, rows)
    require(hashlib.sha256(args.readout.read_bytes()).hexdigest() == digest, "actual readout changed")
    report = {"schema": "v19-three-formal-actual-source-domains-CPU/1", "summary": {"passed": 5, "failed": 0},
              "actual_readout_sha256": digest, "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "actual_buildings": evidence, "EXTRA_CPU_01": {"type": "private in-memory mutant derived from actual export, not new Blender geometry",
               "operation": "translate full actual first reference floor10cm in X", "rejected": reason, "restored_original_rechecked": True},
              "original_input_unchanged": True, "model_generator_imported": False,
              "scope": "complete actual XY projection and source-bottom-cap parity; source identity, support, materials, saved-native and render approval still separate",
              "source_hide_permission": [], "human_approval": "pending", "whole_city_complete": False, "third_party_cost": 0}
    with args.report.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print("FORMAL_ACTUAL_SOURCE_DOMAINS_CPU", len(evidence), "bodies,5/0")


if __name__ == "__main__":
    main()
