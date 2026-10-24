"""CPU-only full-area checks for immutable, world-coordinate saved geometry.

No Blender imports, builder imports, native opens, geometry repairs or bbox proofs.
Public check_* functions do not mutate their arguments or write files.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

EPS = 1e-4
AREA_EPS = 1e-8


def require(value, message):
    if not value:
        raise AssertionError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def polygon(exterior, holes=()):
    p = Polygon(exterior, holes)
    require(not p.is_empty and p.is_valid and p.area > 0, "invalid/empty declared polygon")
    return p


def mesh_projection(vertices, triangles, upward_only=False):
    require(bool(vertices) and bool(triangles), "empty actual mesh")
    require(all(len(v) == 3 and all(math.isfinite(float(x)) for x in v) for v in vertices),
            "nonfinite or non-XYZ world vertex")
    polygons = []
    selected_vertices = set()
    for tri in triangles:
        require(len(tri) == 3 and all(type(k) is int and 0 <= k < len(vertices) for k in tri),
                "invalid actual triangle index")
        a, b, c = [vertices[k] for k in tri]
        cross_z = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
        if upward_only and cross_z <= 1e-12:
            continue
        p = Polygon([(a[0], a[1]), (b[0], b[1]), (c[0], c[1])])
        if p.area > 1e-12:
            polygons.append(p)
            selected_vertices.update(tri)
    require(polygons, "actual mesh has no requested projected area")
    projected = unary_union(polygons)
    require(projected.is_valid and not projected.is_empty, "invalid actual projected union")
    return projected, selected_vertices


def hole_count(p):
    if p.geom_type == "Polygon":
        return len(p.interiors)
    if p.geom_type == "MultiPolygon":
        return sum(len(x.interiors) for x in p.geoms)
    raise AssertionError("projection is not polygonal")


def compare_complete(actual, expected, label):
    require(actual.is_valid and expected.is_valid, label+": invalid geometry")
    require(actual.geom_type == expected.geom_type == "Polygon", label+": unexpected disconnected fragments")
    require(hole_count(actual) == hole_count(expected), label+": complete hole count differs")
    gap = actual.boundary.hausdorff_distance(expected.boundary)
    missing = expected.difference(actual.buffer(EPS)).area
    extra = actual.difference(expected.buffer(EPS)).area
    require(gap <= EPS, label+": full boundary/hole difference exceeds 1e-4 m: "+repr(gap))
    require(missing < AREA_EPS, label+": expected full area missing beyond tolerance: "+repr(missing))
    require(extra < AREA_EPS, label+": unexpected full area beyond tolerance: "+repr(extra))
    return {"boundary_hausdorff_m": gap, "actual_area_m2": actual.area,
            "expected_area_m2": expected.area, "raw_symmetric_difference_m2": actual.symmetric_difference(expected).area,
            "missing_outside_actual_buffer_m2": missing, "extra_outside_expected_buffer_m2": extra,
            "actual_holes": hole_count(actual), "expected_holes": hole_count(expected),
            "complete_area_and_boundary_checked": True}


def check_shared_support(support):
    source = support["source"]
    records = source["source_part_records"]
    require(isinstance(records, dict) and len(records) == 6, "shared support must bind six raw flat parts")
    require(set(records) == set(source["source_part_ids"]), "raw six part inventory differs")
    raw = []
    for key, record in records.items():
        require(record["id"] == key, "raw support record identity differs")
        raw.append(polygon(record["polygon"], record.get("holes", [])))
    expected = unary_union(raw)
    declared = polygon(source["polygon_world"], source["holes_world"])
    declaration = compare_complete(declared, expected, "declared support vs full raw six union")
    actual, top_ids = mesh_projection(support["vertices"], support["triangles"], upward_only=True)
    require(top_ids, "no actual upward support top")
    top = source["top_z_m"]
    require(all(abs(support["vertices"][i][2]-top) <= EPS for i in top_ids),
            "actual upward support surface is not at declared relative top Z")
    return {"object": support["object"], "raw_source_parts": sorted(records),
            "declaration_vs_raw_six": declaration,
            "actual_top_vs_raw_six": compare_complete(actual, expected, "actual support top vs full raw six union"),
            "actual_top_vs_declared": compare_complete(actual, declared, "actual support top vs source polygon_world"),
            "upward_top_vertex_count": len(top_ids), "world_datum_calibration_proven": False}


def check_ramp(ramp):
    record = ramp["source"]["original_source_record"]
    require(record["id"] == ramp["source"]["source_part_id"], "ramp source identity differs from original raw record")
    expected = polygon(record["polygon"], record.get("holes", []))
    actual, _ = mesh_projection(ramp["vertices"], ramp["triangles"])
    original, _ = mesh_projection(ramp["original_vertices"], ramp["original_triangles"])
    return {"object": ramp["object"], "source_part_id": record["id"],
            "actual_vs_full_raw_source": compare_complete(actual, expected, "ramp actual vs raw source"),
            "original_vs_full_raw_source": compare_complete(original, expected, "ramp original vs raw source"),
            "actual_vs_original_projection": compare_complete(actual, original, "ramp actual vs original projection"),
            "relative_z_faces_and_xy_vertex_identity_checked_here": False}


def remainder_projection(row):
    return mesh_projection(row["actual_vertices"], row["actual_triangles"])[0]


def check_remainder(row):
    record = row["row"]
    expected = polygon(record["polygon_world"], record["holes_world"])
    return {"row_index": row["row_index"], "actual_object": row["actual_object_name"],
            **compare_complete(remainder_projection(row), expected, "actual remainder retained polygon/hole")}


def check_partition_groups(rows):
    require(len(rows) == 9, "must export nine actual remainder rows")
    require({r["row_index"] for r in rows} == set(range(9)), "remainder row indexes omitted/duplicated")
    identities = [(r["row"]["original_material_actor"], r["row"]["partition_fragment_index"]) for r in rows]
    require(len(set(identities)) == 9, "canonical remainder identities duplicated")
    require(len({r["actual_object_name"] for r in rows}) == 9, "actual remainder object names duplicated")
    inventory = {}
    for r in rows:
        inventory.setdefault(r["row"]["partition_group_id"], []).append(r)
    require(len(inventory) == 7, "must bind seven source actor partition groups")
    evidence = []
    same_fields = ("original_material_actor", "original_source_polygon_world", "original_source_holes_world",
                   "retained_group_geometry_world", "replacement_geometry_world", "partition_fragment_count")
    for gid, items in inventory.items():
        first = items[0]["row"]
        require(all(all(x["row"][key] == first[key] for key in same_fields) for x in items),
                "group rows disagree about immutable source/partition declaration")
        require(len(items) == first["partition_fragment_count"], "partition fragment count differs")
        require({x["row"]["partition_fragment_index"] for x in items} == set(range(len(items))),
                "partition fragment indexes omitted/duplicated")
        retained = unary_union([polygon(x["row"]["polygon_world"], x["row"]["holes_world"]) for x in items])
        declared = shape(first["retained_group_geometry_world"])
        original = polygon(first["original_source_polygon_world"], first["original_source_holes_world"])
        replacement = shape(first["replacement_geometry_world"])
        require(declared.is_valid and replacement.is_valid, "invalid declared partition geometry")
        require(retained.equals(declared), "declared retained fragments do not equal complete retained group")
        require(original.equals(unary_union([retained, replacement])), "complete declared original partition does not close")
        require(retained.intersection(replacement).area < AREA_EPS, "retained/replacement overlap area")
        actual = unary_union([remainder_projection(x) for x in items])
        require(actual.is_valid, "invalid actual retained fragment union")
        require(actual.geom_type == retained.geom_type, "actual retained group geometry type differs")
        require(hole_count(actual) == hole_count(retained), "actual retained group hole count differs")
        gap = actual.boundary.hausdorff_distance(retained.boundary)
        require(gap <= EPS, "complete actual retained group boundary differs")
        require(retained.difference(actual.buffer(EPS)).area < AREA_EPS and
                actual.difference(retained.buffer(EPS)).area < AREA_EPS, "complete actual retained group area differs")
        evidence.append({"partition_group_id": gid, "fragment_count": len(items),
                         "actual_union_area_m2": actual.area, "full_boundary_gap_m": gap,
                         "declared_partition_union_exact": True,
                         "replacement_is_declared_geometry_only_not_actual_building_geometry": True})
    return evidence


def check_base_footprint(base, support_surfaces_by_name):
    require(base["support"] in support_surfaces_by_name, "base references an unexported actual support")
    surface = support_surfaces_by_name[base["support"]]
    actual, _ = mesh_projection(surface["vertices"], surface["triangles"], upward_only=True)
    footprint = polygon(base["footprint_polygon_world"], base.get("footprint_holes_world", []))
    outside = footprint.difference(actual.buffer(EPS)).area
    require(outside < AREA_EPS, "complete base footprint extends beyond actual support top: "+repr(outside))
    return {"object": base["object"], "support": base["support"],
            "complete_footprint_area_m2": footprint.area, "outside_actual_support_buffer_m2": outside,
            "bbox_used_as_coverage_proof": False, "vertical_contact_checked_here": False}


def check_support_surface(surface):
    """Compare the whole upward slab face, including all expected holes."""
    expected = polygon(surface["expected_polygon_world"], surface["expected_holes_world"])
    actual, top_ids = mesh_projection(surface["vertices"], surface["triangles"], upward_only=True)
    return {"object": surface["object"], "upward_top_vertex_count": len(top_ids),
            **compare_complete(actual, expected, "actual full slab top vs source-shaped expected polygon/hole"),
            "bbox_used_as_coverage_proof": False, "native_source_binding_checked_here": False}


def negative_rejected(fn):
    try:
        fn()
    except AssertionError as e:
        return {"same_checker_rejected": True, "reason": str(e)}
    raise AssertionError("negative control was accepted")


def source_shaped_slab_negative_controls(surfaces, shared_support_name):
    candidates = []
    for surface in surfaces:
        if surface["object"] == shared_support_name:
            continue
        expected = polygon(surface["expected_polygon_world"], surface["expected_holes_world"])
        x0, y0, x1, y1 = expected.bounds
        wrong_box = polygon([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        if wrong_box.symmetric_difference(expected).area > 1e-6:
            candidates.append(surface)
    require(candidates, "source-shaped slab control needs an exported nonrectangular owned slab")
    source = candidates[0]
    expected = polygon(source["expected_polygon_world"], source["expected_holes_world"])
    upwards = []
    for index, tri in enumerate(source["triangles"]):
        a, b, c = [source["vertices"][k] for k in tri]
        cross_z = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if cross_z > 1e-12:
            upwards.append((cross_z/2, index))
    require(upwards, "source-shaped slab has no actual top triangle for negative control")
    area, index = max(upwards)
    missing = copy.deepcopy(source)
    del missing["triangles"][index]
    x0, y0, x1, y1 = expected.bounds
    z = max(v[2] for v in source["vertices"])
    wrongly_filled = copy.deepcopy(source)
    wrongly_filled["vertices"] = [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]
    wrongly_filled["triangles"] = [[0, 1, 2], [0, 2, 3]]
    return {"source_shaped_surface": source["object"], "removed_actual_upward_triangle_area_m2": area,
            "actual_top_triangle_removed": negative_rejected(lambda: check_support_surface(missing)),
            "source_outline_wrongly_filled_as_rectangle": negative_rejected(lambda: check_support_surface(wrongly_filled)),
            "controls_used_deep_copies": True, "bbox_used_only_to_construct_deliberately_wrong_negative_mesh": True}


def remainder_negative_controls(rows):
    require(bool(rows), "negative controls need an actual remainder")
    shifted = copy.deepcopy(rows[0])
    for v in shifted["actual_vertices"]:
        v[0] += .01
    hole = copy.deepcopy(rows[0])
    expected = polygon(hole["row"]["polygon_world"], hole["row"]["holes_world"])
    interior = expected.representative_point().buffer(.1, resolution=4)
    require(expected.contains(interior), "fake-hole negative is not wholly inside footprint")
    hole["row"]["holes_world"].append([list(p) for p in list(interior.exterior.coords)[:-1]])
    return {"actual_vertices_shifted_1cm": negative_rejected(lambda: check_remainder(shifted)),
            "declared_fake_hole_not_present_in_actual_mesh": negative_rejected(lambda: check_remainder(hole)),
            "actual_hole_mesh_constructed": False, "controls_used_deep_copies": True}


def validate_inventory(doc):
    require(isinstance(doc["support"], dict), "one shared support required")
    require(len(doc["ramps"]) == 7 and len({x["object"] for x in doc["ramps"]}) == 7,
            "seven distinct actual ramp meshes required")
    require(len({x["source"]["source_part_id"] for x in doc["ramps"]}) == 7,
            "seven distinct source ramp identities required")
    require(len(doc["remainders"]) == 9, "nine actual remainder rows required")
    surfaces = doc["support_surfaces"]
    require(bool(surfaces) and len({x["object"] for x in surfaces}) == len(surfaces),
            "actual support surfaces omitted/duplicated")
    require(doc["support"]["object"] in {x["object"] for x in surfaces}, "shared support missing from exported surfaces")
    shared = next(x for x in surfaces if x["object"] == doc["support"]["object"])
    require(shared["vertices"] == doc["support"]["vertices"] and shared["triangles"] == doc["support"]["triangles"],
            "shared support duplicate surface differs from support actual geometry")
    bases = doc["base_footprints"]
    require(bool(bases) and len({x["object"] for x in bases}) == len(bases), "exported base footprints omitted/duplicated")
    if "expected_base_footprint_count" in doc:
        require(len(bases) == doc["expected_base_footprint_count"], "expected base footprint count differs")
    return {"shared_supports": 1, "ramps": len(doc["ramps"]), "remainders": len(doc["remainders"]),
            "support_surfaces": len(surfaces), "exported_base_footprints": len(bases),
            "export_completeness_must_be_bound_by_blender_manifest_checker": True}


def run_checks(doc):
    before = canonical(doc)
    results = []
    def test(key, operation, expected, fn):
        try:
            results.append({"id": key, "input": "immutable exported world geometry", "operation": operation,
                            "expected": expected, "passed": True, "evidence": fn()})
        except Exception as e:
            results.append({"id": key, "input": "immutable exported world geometry", "operation": operation,
                            "expected": expected, "passed": False, "error": repr(e)})
    test("SAVED-PROJ-INVENTORY", "bind counts and unique source/object identities", "complete declared inventory", lambda: validate_inventory(doc))
    test("SAVED-PROJ-SUPPORT", "union all actual upward top triangles; compare both raw-six and declared full polygon/holes",
         "one continuous complete top with matching holes within 1e-4 m", lambda: check_shared_support(doc["support"]))
    for i, surface in enumerate(doc.get("support_surfaces", [])):
        test("SAVED-PROJ-SLAB-"+str(i), "union every actual upward slab triangle vs entire expected source polygon/holes",
             "full slab face, boundary and holes agree within 1e-4 m", lambda surface=surface: check_support_surface(surface))
    for i, row in enumerate(doc.get("ramps", [])):
        test("SAVED-PROJ-RAMP-"+str(i), "complete projected triangle union vs raw and original source",
             "entire source footprint preserved", lambda row=row: check_ramp(row))
    for i, row in enumerate(doc.get("remainders", [])):
        test("SAVED-PROJ-REMAINDER-"+str(i), "complete actual retained polygon/hole union",
             "full retained area and boundary agree", lambda row=row: check_remainder(row))
    test("SAVED-PROJ-PARTITIONS", "nine fragments and seven complete source partition groups",
         "declared original partition closes and actual retained group agrees", lambda: check_partition_groups(doc["remainders"]))
    surfaces = {x["object"]: x for x in doc.get("support_surfaces", [])}
    for i, base in enumerate(doc.get("base_footprints", [])):
        test("SAVED-PROJ-BASE-"+str(i), "entire base polygon difference against actual upward support top",
             "full footprint covered within 1e-4 m", lambda base=base: check_base_footprint(base, surfaces))
    test("EXTRA-SAVED-PROJ-01", "shift actual remainder world vertices 1 cm and add fake declared interior hole in deep copies",
         "same full-area checker rejects both controls", lambda: remainder_negative_controls(doc["remainders"]))
    def shifted_source():
        support = copy.deepcopy(doc["support"])
        for v in support["source"]["polygon_world"]:
            v[0] += .01
        return negative_rejected(lambda: check_shared_support(support))
    test("EXTRA-SAVED-PROJ-02", "shift declared support source polygon 1 cm in memory, keep raw six/actual top fixed",
         "same shared-support checker rejects mismatch", shifted_source)
    test("EXTRA-SAVED-PROJ-03", "remove actual owned source-shaped slab top triangle and replace outline by wrong rectangle in deep copies",
         "same complete slab checker rejects both", lambda: source_shaped_slab_negative_controls(doc["support_surfaces"], doc["support"]["object"]))
    def unchanged():
        require(canonical(doc) == before, "input geometry mutated by checker/negative controls")
        return {"all_input_geometry_and_source_records_unchanged": True}
    test("FINAL-SAVED-PROJ-MEMORY-GUARD", "compare complete canonical input after all deep-copy controls",
         "original input unchanged", unchanged)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--readout-sha256", required=True)
    args = parser.parse_args()
    require(args.readout.resolve() != args.output.resolve(), "output must not replace input")
    require(not args.output.exists(), "preserve earlier report; output already exists")
    data = args.readout.read_bytes()
    require(digest(data) == args.readout_sha256, "readout SHA mismatch before checking")
    doc = json.loads(data)
    results = run_checks(doc)
    unchanged = args.readout.read_bytes() == data
    results.append({"id": "FINAL-SAVED-PROJ-FILE-GUARD", "input": str(args.readout),
                    "operation": "reread full input bytes after all checks", "expected": "file unchanged",
                    "passed": unchanged, "evidence": {"actual_readout_file_unchanged": unchanged}})
    failed = sum(not x["passed"] for x in results)
    report = {"schema": "v14-saved-actual-world-full-projection/1", "readout": str(args.readout.resolve()),
              "readout_sha256": digest(data), "checker_sha256": digest(Path(__file__).read_bytes()),
              "construction_coordinate_tolerance_m": EPS, "results": results,
              "summary": {"passed": len(results)-failed, "failed": failed},
              "scope": "full-area CPU projection of supplied saved-world readout; provenance/native/3D topology audited separately",
              "input_evidence_scope": doc.get("evidence_scope", "export provenance must be established by Blender checker"),
              "native_opened_by_this_checker": False, "native_saved_by_this_checker": False,
              "whole_city_reconstruction_proven": False, "human_approval": "pending", "third_party_cost": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    print(json.dumps(report["summary"]))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
