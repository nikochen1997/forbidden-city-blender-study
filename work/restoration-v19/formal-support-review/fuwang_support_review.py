"""CPU-only complete support domains of the 290 exported formal Fuwang meshes.

No Blender/builder import, native I/O, repairs, or Nansansuo identity adapter.
Public checks read their argument without mutation and retain every failed check.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

from shapely.geometry import Polygon
from shapely.ops import unary_union

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FROZEN = ROOT / "work/restoration-v17/hall-qa/check_actual_supports_v3.py"
FROZEN_SHA = "65e4663f3caa3724103357fde71e0fd5d2db9c561e71798a4a45775ac5f769cf"
V18 = ROOT / "work/restoration-v18/module-qa/check_actual_exterior_supports.py"
EXPECTED_READOUT_SHA = "da5c38ed9f7fc502095726b27a6c58f8a32d09465e02519d4c4ba3bce6bcf466"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def require(value, message):
    if not value:
        raise AssertionError(message)


require(sha(FROZEN) == FROZEN_SHA, "Frozen full-cap support primitives drift")
_spec = importlib.util.spec_from_file_location("formal_fuwang_frozen_caps", FROZEN)
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)
P = G.P
require(P.EPS == 1e-4 and P.AREA_EPS == 1e-8, "Frozen support tolerance drift")


def context(doc):
    require(doc["schema"] == "v19-three-formal-body-actual-world/1", "Formal WORLD readout required")
    require(doc["native_opened"] is False and doc["native_saved"] is False, "Isolated factory readout required")
    rows = [b for b in doc["buildings"] if b["building_id"] == "fuwangge"]
    require(len(rows) == 1, "Exactly one formal Fuwang row required")
    b = rows[0]
    require(b["profile"]["building_id"] == b["registration"]["building_id"] == "fuwangge", "Fuwang identity binding differs")
    require(b["registration"]["source_part_id"] == "way-40629261-p0", "Formal Fuwang source binding differs")
    names = b["objects"]
    require(len(names) == len(set(names)) == 290, "Complete 290 formal Fuwang mesh population required")
    require(all("nansansuo" not in n.lower() for n in names), "Foreign building identity adapter forbidden")
    exported = {o["name"]: o for o in doc["objects"]}
    require(len(exported) == len(doc["objects"]), "Duplicate actual exported mesh identity")
    components = b["components"]
    grouped = [n for items in components.values() for n in items]
    require(len(grouped) == len(set(grouped)) == 290 and set(grouped) == set(names), "Complete role inventory omitted/duplicated")
    counts = {"beam": 16, "column_base": 48, "core_pilaster": 32, "open_veranda_column": 48,
              "walkway_support_beam": 8, "exterior_walkway": 1, "railing_post": 20, "railing_bar": 40,
              "study_enclosure_wall": 8, "roof": 2, "ridge": 2, "roof_bearing_post": 60,
              "study_roof_closure_wall": 4, "source_reference_slab": 1}
    require({k: len(v) for k, v in components.items()} == counts, "Formal Fuwang role counts differ")
    meshes, props = {}, {}
    expected_profile_sha = digest(b["profile"])
    for role, items in components.items():
        for name in items:
            row = exported[name]
            props[name] = json.loads(row["props_json"])
            require(row["role"] == props[name]["semantic_role"] == role, "Actual role identity differs: " + name)
            if role != "source_reference_slab":
                require(props[name]["building_id"] == "fuwangge" and props[name]["profile_sha256"] == expected_profile_sha,
                        "Actual Fuwang/profile identity differs: " + name)
            meshes[name] = {"vertices": row["vertices_world"],
                            "triangles": [t[0] for t in row["triangles_with_material_index"]]}
    require(components["source_reference_slab"] == [b["reference_floor"]], "Complete source floor identity differs")
    require(len(b["contacts"]) == 64 and {c["object"] for c in b["contacts"]} ==
            set(components["roof_bearing_post"] + components["study_roof_closure_wall"]), "Actual roof contact inventory differs")
    return b, meshes, props


def check_fuwang(doc):
    """Return full check/evidence, including failures; do not mutate doc or write."""
    checks = []

    def run(ident, description, fn):
        row = {"id": ident, "input": description, "operation": "actual complete triangle-domain union and support contact",
               "expected": "XY 100 um / horizontal Z 100 um, unchanged frozen area threshold"}
        try:
            row.update(passed=True, evidence=fn())
        except Exception as exc:
            row.update(passed=False, error=str(exc), traceback=traceback.format_exc())
        checks.append(row)
        return row

    try:
        b, meshes, props = context(doc)
    except Exception as exc:
        return {"passed": False, "summary": {"passed": 0, "failed": 1}, "checks": [
            {"id": "FW-INVENTORY", "passed": False, "error": str(exc), "traceback": traceback.format_exc()}]}
    c, d = b["components"], b["profile"]["study"]
    floor, deck = b["reference_floor"], c["exterior_walkway"][0]
    cap_cache, surface_cache = {}, {}

    def full(name, upward):
        key = name, upward
        if key not in cap_cache:
            cap_cache[key] = G.full_cap(meshes[name], upward)
        return cap_cache[key]

    def surface(name, upward):
        key = name, upward
        if key not in surface_cache:
            z = G.zrange(meshes[name])[1 if upward else 0]
            surface_cache[key] = G.horizontal(meshes[name], z, upward), z
        return surface_cache[key]

    def on_domain(name, upward, support, support_top, label):
        cap, z, capcheck = full(name, upward)
        domain, support_z = surface(support, support_top)
        gap = abs(z - support_z)
        require(gap <= P.EPS, label + ": horizontal Z gap exceeds100um")
        outside = cap.difference(domain.buffer(P.EPS)).area
        require(outside < P.AREA_EPS, label + ": complete actual cap leaves support domain " + repr(outside))
        return {"object": name, "support_object": support, "whole_cap": capcheck,
                "actual_z_gap_m": gap, "outside_support_buffer_m2": outside, "full_support_holes_retained": True}

    def on_convex(name, upward, candidates, support_top, label):
        cap, z, capcheck = full(name, upward)
        evidence = G.supported(cap, z, [meshes[n] for n in candidates], support_top, label)
        touching = [n for n in candidates if abs(G.zrange(meshes[n])[1 if support_top else 0] - z) <= P.EPS
                    and cap.intersection(full(n, support_top)[0]).area > P.AREA_EPS]
        return {"object": name, "whole_cap": capcheck, "contacting_actual_supports": touching, **evidence}

    def floor_check():
        expected = P.polygon(b["registration"]["source_polygon_world"], b["registration"]["source_holes_world"])
        lo, hi = G.zrange(meshes[floor])
        require(abs(lo - b["registration"]["anchor"][2]) <= P.EPS and
                abs(hi - b["registration"]["anchor"][2] - d["floor_z_m"]) <= P.EPS, "Actual reference floor Z differs")
        projection, _ = P.mesh_projection(meshes[floor]["vertices"], meshes[floor]["triangles"])
        return {"object": floor, "top": P.compare_complete(surface(floor, True)[0], expected, "full Fuwang source top"),
                "bottom": P.compare_complete(surface(floor, False)[0], expected, "full Fuwang source bottom"),
                "projection": P.compare_complete(projection, expected, "full Fuwang source projection")}

    matrix = b["root_matrix_world"]

    def world_ring(half):
        return [(matrix[0][0]*x + matrix[0][1]*y + matrix[0][3],
                 matrix[1][0]*x + matrix[1][1]*y + matrix[1][3])
                for x, y in ((-half, -half), (half, -half), (half, half), (-half, half))]

    annulus = P.polygon(world_ring(d["walkway_outer_side_m"]/2), [world_ring(d["walkway_inner_side_m"]/2)])

    def walkway_check():
        lo, hi = G.zrange(meshes[deck])
        require(abs(hi - d["level_break_z_m"]) <= P.EPS and abs(hi-lo-d["walkway_thickness_m"]) <= P.EPS,
                "Actual exterior annular walkway Z differs")
        projection, _ = P.mesh_projection(meshes[deck]["vertices"], meshes[deck]["triangles"])
        return {"object": deck, "actual_top": P.compare_complete(surface(deck, True)[0], annulus, "actual annular walkway top"),
                "actual_bottom": P.compare_complete(surface(deck, False)[0], annulus, "actual annular walkway bottom"),
                "whole_projection": P.compare_complete(projection, annulus, "actual annular walkway projection"),
                "expected_interior_holes": 1, "interior_floor_claimed": False}

    checks.append({"id": "FW-INVENTORY", "passed": True, "evidence": {"building_id": "fuwangge",
                   "source_part_id": b["registration"]["source_part_id"], "actual_meshes": 290,
                   "role_counts": {k: len(v) for k, v in c.items()}, "profile_sha256": digest(b["profile"]),
                   "foreign_identity_adapter_used": False}})
    run("FW-SOURCE-FLOOR", floor, floor_check)
    run("FW-ANNULUS", deck, walkway_check)
    for role in ("column_base", "core_pilaster", "open_veranda_column", "railing_post", "beam", "walkway_support_beam", "study_enclosure_wall"):
        for name in c[role]:
            run("FW-CAPS:" + name, name, lambda n=name: {"bottom": full(n, False)[2], "top": full(n, True)[2]})
    for name in c["column_base"]:
        run("FW-BASE:" + name, name, lambda n=name: on_domain(n, False, floor, True, "actual complete Fuwang base bottom"))
    columns = c["core_pilaster"] + c["open_veranda_column"]
    for name in columns:
        lower = props[name]["exterior_level_index"] == 0
        run("FW-COLUMN-BOTTOM:" + name, name,
            (lambda n=name: on_convex(n, False, c["column_base"], True, "actual complete lower Fuwang column bottom")) if lower else
            (lambda n=name: on_domain(n, False, deck, True, "actual complete upper Fuwang column bottom")))
        run("FW-COLUMN-TOP:" + name, name, lambda n=name: on_convex(n, True, c["beam"], False, "actual complete Fuwang column top"))
    for name in c["railing_post"]:
        run("FW-RAILING-POST:" + name, name, lambda n=name: on_domain(n, False, deck, True, "actual complete railing-post bottom"))
    for name in c["roof_bearing_post"]:
        run("FW-BEARING-BOTTOM:" + name, name, lambda n=name: on_convex(n, False, c["beam"], True, "actual complete roof-bearing bottom"))
    for name in c["study_enclosure_wall"]:
        support = floor if props[name]["exterior_level_index"] == 0 else deck
        run("FW-WALL-BOTTOM:" + name, name, lambda n=name, s=support: on_domain(n, False, s, True, "actual complete enclosure-wall bottom"))
    for name in c["study_roof_closure_wall"]:
        side = name.rsplit("_", 1)[1]
        support = [n for n in c["study_enclosure_wall"] if props[n].get("wall_id") == "s1_"+side]
        run("FW-CLOSURE-BOTTOM:" + name, name, lambda n=name, ss=support: on_convex(n, False, ss, True, "actual complete closure bottom"))

    def beam_check(name):
        bottom, z, evidence = full(name, False)
        supporting = []
        for column in columns:
            cap, top_z, _ = full(column, True)
            if abs(top_z-z) <= P.EPS and cap.difference(bottom.buffer(P.EPS)).area < P.AREA_EPS:
                supporting.append((column, cap))
        require(len(supporting) >= 2, "Actual beam lacks at least two complete column-cap supports: " + name)
        separation = max(a.centroid.distance(bb.centroid) for _, a in supporting for _, bb in supporting)
        require(separation > 2*d["column_radius_m"], "Actual beam supports not spatially distinct: " + name)
        return {"object": name, "whole_bottom_cap": evidence, "whole_top_cap": full(name, True)[2],
                "complete_supporting_column_caps": [n for n, _ in supporting],
                "maximum_support_centroid_separation_m": separation, "spanning_beam_not_continuous_bottom_support": True}

    beams = c["beam"] + c["walkway_support_beam"]
    for name in beams:
        run("FW-BEAM:" + name, name, lambda n=name: beam_check(n))

    def deck_bearings():
        domain, z = surface(deck, False)
        contacts, patches = [], []
        for name in beams:
            top, top_z, _ = full(name, True)
            if abs(top_z-z) > P.EPS:
                continue
            cut = domain.intersection(top)
            expected = annulus.intersection(top)
            require(cut.area > P.AREA_EPS, "Actual walkway beam has no deck contact: " + name)
            missing = expected.difference(cut.buffer(P.EPS)).area
            extra = cut.difference(expected.buffer(P.EPS)).area
            require(missing < P.AREA_EPS and extra < P.AREA_EPS, "Complete actual walkway/beam contact domain differs: " + name)
            contacts.append({"support_object": name, "complete_actual_contact_area_m2": cut.area,
                             "actual_z_gap_m": abs(z-top_z), "missing_outside100um_m2": missing, "extra_outside100um_m2": extra})
            patches.append(cut)
        require(len(contacts) == 12, "Complete 4 perimeter/8 spanning deck supports omitted")
        union = unary_union(patches)
        return {"object": deck, "actual_support_contacts": contacts, "complete_contact_union_area_m2": union.area,
                "actual_annular_bottom_area_m2": domain.area, "geometric_spanning_area_m2": domain.difference(union).area,
                "continuous_full_deck_bottom_support_claimed": False, "structural_load_capacity_proven": False}

    run("FW-WALKWAY-BEARINGS", deck, deck_bearings)
    passed, failed = sum(row["passed"] for row in checks), sum(not row["passed"] for row in checks)
    return {"schema": "v19-formal-fuwang-complete-support-CPU/1", "passed": failed == 0,
            "summary": {"passed": passed, "failed": failed}, "checks": checks,
            "actual_meshes": 290, "xy_tolerance_m": P.EPS, "horizontal_z_tolerance_m": P.EPS,
            "area_epsilon_m2": P.AREA_EPS, "frozen_full_cap_helper_sha256": FROZEN_SHA,
            "scope": "complete actual base/column/railing-post caps; beams and deck-bearing domains; enclosure/closure bottoms; full source floor and annular walkway",
            "separate_scope": "curved roof-contact upper faces use the parent's complete actual triangle-plane checker at200um; railing-bar side attachments and roof/ridge structural capacity are not certified here",
            "Blender_started": False, "builder_imported": False, "native_opened": False, "native_saved": False,
            "third_party_cost": 0, "human_approval": "pending", "whole_city_complete": False}


def negative_hole_control(doc):
    """Fill only the copied actual deck's top hole, using its existing vertices."""
    original = digest(doc)
    mutant = copy.deepcopy(doc)
    b, meshes, _ = context(mutant)
    name = b["components"]["exterior_walkway"][0]
    row = next(o for o in mutant["objects"] if o["name"] == name)
    z = G.zrange(meshes[name])[1]
    cap = G.horizontal(meshes[name], z, True)
    require(cap.geom_type == "Polygon" and len(cap.interiors) == 1, "Actual positive deck must have exactly one hole")
    loop = list(cap.interiors[0].coords)[:-1]
    if not Polygon(loop).exterior.is_ccw:
        loop.reverse()
    lookup = {(v[0], v[1], v[2]): i for i, v in enumerate(row["vertices_world"])}
    ids = [lookup[(x, y, z)] for x, y in loop]
    require(len(ids) == 4, "Expected four actual exported inner-rim vertices")
    added = [[ids[0], ids[i], ids[i+1]] for i in range(1, len(ids)-1)]
    for tri in added:
        row["triangles_with_material_index"].append([tri, 0])
        row["faces"].append(tri)
        row["raw_faces"].append(tri)
    result = check_fuwang(mutant)
    failures = [r for r in result["checks"] if not r["passed"]]
    require(not result["passed"] and any(r["id"] == "FW-ANNULUS" and "hole count differs" in r["error"] for r in failures),
            "Actual-export-derived blocked annular hole was not rejected by the same checker")
    require(digest(doc) == original, "Private blocked-hole control mutated original document")
    positive = check_fuwang(doc)
    require(positive["passed"], "Original actual positive failed after blocked-hole control")
    return {"id": "EXTRA-FW-01", "passed": True, "input": "deep copy of the formal actual WORLD walkway export",
            "operation": "append two cap triangles joining only four existing actual hole-rim vertices; unchanged profile/identity/labels",
            "expected": "the same check_fuwang rejects complete annular-hole loss",
            "same_actual_checker_rejected": True, "mutated_object": name, "added_actual_vertex_derived_triangles": added,
            "rejected_checks": failures, "original_doc_digest_unchanged": True, "original_positive_rechecked": True,
            "Blender_started": False, "ideal_mesh_rebuilt": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--readout", type=Path, default=ROOT / "work/restoration-v19/formal-factory-run-03/actual-world-geometry.json")
    parser.add_argument("--readout-sha256", default=EXPECTED_READOUT_SHA)
    parser.add_argument("--output", type=Path, default=HERE / "fuwang-support-CPU-01.json")
    args = parser.parse_args()
    require(not args.output.exists() and args.output.resolve().parent == HERE, "Fresh dedicated Fuwang report required")
    require(sha(args.readout) == args.readout_sha256, "Formal actual readout SHA differs")
    doc = json.loads(args.readout.read_text())
    result = check_fuwang(doc)
    try:
        result["negative_hole_control"] = negative_hole_control(doc)
    except Exception as exc:
        result["negative_hole_control"] = {"passed": False, "error": str(exc), "traceback": traceback.format_exc()}
        result["passed"] = False
    result["actual_readout"] = str(args.readout)
    result["actual_readout_sha256"] = args.readout_sha256
    result["checker_sha256"] = sha(__file__)
    result["reference_v18_checker_sha256"] = sha(V18)
    result["protected_input_sha256"] = doc["inputs_sha256"]
    result["actual_readout_unchanged"] = sha(args.readout) == args.readout_sha256
    result["protected_inputs_unchanged"] = all(sha(ROOT / p) == expected for p, expected in doc["inputs_sha256"].items())
    require(result["actual_readout_unchanged"] and result["protected_inputs_unchanged"], "Protected actual input changed during CPU review")
    with args.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print("FORMAL_FUWANG_SUPPORT", result["summary"], "negative", result["negative_hole_control"]["passed"], flush=True)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
