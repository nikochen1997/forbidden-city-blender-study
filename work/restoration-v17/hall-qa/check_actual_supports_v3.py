"""CPU-only complete-area checks on actual factory readout, never Blender/native IO."""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import traceback

from shapely.geometry import MultiPoint, Polygon
from shapely.ops import triangulate, unary_union

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LEGACY = ROOT / "work/restoration-v14/saved-audit/saved-projection/check_saved_projection.py"
LEGACY_SHA = "f4b46285d64ffd899888c2ea9b6bd31a047bc25fba6e860ada399adc273c323c"
PROFILE_SHA = "6bfd22e012990bf49d074ad7df0846ee2d7e4393b469b12cf4b00aed2efcc0c4"
REGISTRY_SHA = "0ff859b0e1434e9ee1c0501aa2f301fd6b8416e85e32a5c2b525f9e3c18479bc"
IDS = {"shufang_front_hall", "shufang_rear_hall", "baohuadian_main"}


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


require(sha(LEGACY) == LEGACY_SHA, "Frozen independent projection helper drift")
_spec = importlib.util.spec_from_file_location("v17_complete_projection_helper", LEGACY)
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)
EPS, AREA_EPS = P.EPS, P.AREA_EPS


def horizontal(mesh, z, upward):
    selected = []
    for tri in mesh["triangles"]:
        points = [mesh["vertices"][i] for i in tri]
        require(len(points) == 3 and all(len(p) == 3 and all(math.isfinite(float(x)) for x in p) for p in points), "Invalid actual triangle")
        if not all(abs(p[2] - z) < 1e-6 for p in points):
            continue
        a, b, c = points
        normal = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if (normal > 1e-12) if upward else (normal < -1e-12):
            selected.append(Polygon([(p[0], p[1]) for p in points]))
    require(selected, "Actual horizontal cap absent")
    cap = unary_union(selected)
    require(cap.is_valid and not cap.is_empty, "Invalid actual cap domain")
    return cap


def zrange(mesh):
    require(mesh["vertices"] and mesh["triangles"], "Empty actual geometry")
    return min(v[2] for v in mesh["vertices"]), max(v[2] for v in mesh["vertices"])


def full_cap(mesh, upward):
    lo, hi = zrange(mesh)
    z = hi if upward else lo
    cap = horizontal(mesh, z, upward)
    # Independent full actual rim: compare each cap separately, never redundant
    # top/bottom union overlays with different triangulation roundoff.
    points = [(v[0], v[1]) for v in mesh["vertices"] if abs(v[2] - z) < 1e-6]
    rim = MultiPoint(points).convex_hull
    require(rim.geom_type == "Polygon", "Actual support rim has no area")
    evidence = P.compare_complete(cap, rim, "full actual support cap vs entire rim")
    return cap, z, evidence


def supported(cap, z, supports, support_top, label):
    surfaces = []
    for mesh in supports:
        lo, hi = zrange(mesh)
        level = hi if support_top else lo
        if abs(level - z) <= EPS:
            surface, _, _ = full_cap(mesh, support_top)
            surfaces.append(surface)
    require(surfaces, label + ": actual support Z contact missing")
    domain = unary_union(surfaces)
    outside = cap.difference(domain.buffer(EPS)).area
    require(outside < AREA_EPS, label + ": complete cap leaves actual support area " + repr(outside))
    return {"actual_complete_cap_area_m2": cap.area, "outside_actual_support_buffer_m2": outside,
            "complete_actual_support_surfaces": len(surfaces), "z_m": z, "bbox_used": False}


def slab_check(b):
    p = b["profile"]
    mesh = b["geometry"][b["reference_floor"]]
    expected = P.polygon(p["source_polygon_world"], p["source_holes_world"])
    lo, hi = zrange(mesh)
    require(abs(lo - p["anchor"][2] - p["dimensions"]["source_reference_slab_bottom_z_m"]) <= EPS, "Actual slab bottom Z differs")
    require(abs(hi - p["anchor"][2] - p["dimensions"]["floor_z_m"]) <= EPS, "Actual slab top Z differs")
    top = horizontal(mesh, hi, True)
    bottom = horizontal(mesh, lo, False)
    projection, _ = P.mesh_projection(mesh["vertices"], mesh["triangles"])
    return {"id": b["id"], "actual_top": P.compare_complete(top, expected, "complete source-shaped slab top"),
            "actual_bottom": P.compare_complete(bottom, expected, "complete source-shaped slab bottom"),
            "all_triangle_projection": P.compare_complete(projection, expected, "all actual slab triangles vs complete source polygon/holes"),
            "absolute_survey_height_proven": False}


def check_building(b):
    comps, geometry, p = b["components"], b["geometry"], b["profile"]
    column_names = comps.get("column", []) + comps.get("pilaster", [])
    expected_columns = 2 * (p["bays_x"] + p["bays_y"])
    require(len(comps["column_base"]) == len(column_names) == expected_columns, "Actual full column/base inventory omitted")
    require(len(comps["roof_bearing_post"]) == expected_columns and len(comps["beam"]) == 4, "Actual bearing/beam inventory omitted")
    require(len(set(comps["column_base"] + column_names + comps["roof_bearing_post"])) == 3 * expected_columns, "Duplicate actual support identity")
    selected = set(comps["column_base"] + column_names + comps["roof_bearing_post"] + comps["beam"] + [b["reference_floor"]])
    require(selected <= set(geometry), "Actual support geometry omitted from export")
    evidence = {"slab": slab_check(b), "bases": [], "columns": [], "bearings": []}
    slab = geometry[b["reference_floor"]]
    beams = [geometry[n] for n in comps["beam"]]
    for name in comps["column_base"]:
        mesh = geometry[name]
        require(mesh["support_object"] == b["reference_floor"], "Base actual source support identity differs")
        cap, z, cap_evidence = full_cap(mesh, False)
        # Source slab may be concave/holed: do not use convex full_cap on it.
        _, top = zrange(slab)
        require(abs(z - top) <= EPS, "Actual base/slab Z contact differs")
        support_domain = horizontal(slab, top, True)
        outside = cap.difference(support_domain.buffer(EPS)).area
        require(outside < AREA_EPS, "Complete base cap leaves actual slab area")
        _, _, upper_cap = full_cap(mesh, True)
        evidence["bases"].append({"object": name, "complete_bottom": cap_evidence, "complete_top": upper_cap,
                                  "outside_actual_slab_buffer_m2": outside, "actual_z_gap_m": abs(z - top)})
    for name in column_names:
        mesh = geometry[name]
        require(mesh["support_object"] in comps["column_base"], "Column support base omitted")
        cap, z, _ = full_cap(mesh, False)
        low = supported(cap, z, [geometry[mesh["support_object"]]], True, "actual column bottom")
        cap, z, _ = full_cap(mesh, True)
        upper = supported(cap, z, beams, False, "actual column top")
        evidence["columns"].append({"object": name, "bottom": low, "top": upper})
    for name in comps["roof_bearing_post"]:
        cap, z, _ = full_cap(geometry[name], False)
        evidence["bearings"].append({"object": name, **supported(cap, z, beams, True, "actual roof bearing bottom")})
    return evidence


def check(doc, profiles):
    require(doc["schema"] == "v17-three-hall-actual-factory-geometry/1", "Wrong actual readout schema")
    require(doc["profiles_sha256"] == PROFILE_SHA, "Actual readout profile binding differs")
    require({b["id"] for b in doc["buildings"]} == IDS and len(doc["buildings"]) == 3, "Exact three actual halls required")
    byid = {p["building_id"]: p for p in profiles["buildings"] if p["builder"] == "hall"}
    for b in doc["buildings"]:
        require(b["profile"] == byid[b["id"]], "Actual exported full profile differs")
    return [check_building(b) for b in doc["buildings"]]


def reject(fn, reason):
    try:
        fn()
    except AssertionError as exc:
        require(reason in str(exc), "Unrelated rejection: " + str(exc))
        return {"same_actual_checker_rejected": True, "reason": str(exc)}
    raise AssertionError("Negative control accepted")


def synthetic_mesh(polygon, low=0, high=.35):
    vertices, triangles = [], []
    for triangle in triangulate(polygon):
        if not polygon.covers(triangle):
            continue
        points = list(triangle.exterior.coords)[:3]
        if Polygon(points).exterior.is_ccw is False:
            points.reverse()
        for level, reverse in ((low, True), (high, False)):
            offset = len(vertices)
            vertices.extend([[x, y, level] for x, y in points])
            triangles.append([offset + i for i in ([2, 1, 0] if reverse else [0, 1, 2])])
    return {"vertices": vertices, "triangles": triangles}


def self_tests():
    outer = [(0, 0), (6, 0), (6, 6), (0, 6)]
    hole = [(2, 2), (2, 4), (4, 4), (4, 2)]
    shape = P.polygon(outer, [hole])
    mesh = synthetic_mesh(shape)
    cases = []
    for upward, z in ((True, .35), (False, 0)):
        evidence = P.compare_complete(horizontal(mesh, z, upward), shape, "synthetic holed cap")
        cases.append({"input": "complete holed cap", "operation": "union all actual triangles", "expected": "hole retained", "passed": True, "evidence": evidence})
    filled = synthetic_mesh(Polygon(outer))
    cases.append({"id": "EXTRA-MATH-01", "passed": True, **reject(lambda: P.compare_complete(horizontal(filled, .35, True), shape, "synthetic hole fill"), "hole count differs")})
    missing = copy.deepcopy(mesh)
    missing["triangles"].pop(next(i for i, t in enumerate(missing["triangles"]) if all(missing["vertices"][k][2] == .35 for k in t)))
    cases.append({"id": "EXTRA-MATH-02", "passed": True, **reject(lambda: P.compare_complete(horizontal(missing, .35, True), shape, "missing cap"), "missing cap:")})
    wrong = P.polygon([(0, 0), (5, 0), (5, 6), (0, 6)], [hole])
    cases.append({"id": "EXTRA-MATH-03", "passed": True, **reject(lambda: P.compare_complete(horizontal(mesh, .35, True), wrong, "wrong source"), "full boundary/hole difference")})
    cap = Polygon([(1, 1), (1.2, 1), (1.2, 1.2), (1, 1.2)])
    support = synthetic_mesh(Polygon(outer))
    # Convex support's rim and its single top cap are independently complete.
    cases.append({"id": "MATH-04", "passed": True, "evidence": supported(cap, .35, [support], True, "synthetic support")})
    cases.append({"id": "EXTRA-MATH-05", "passed": True, **reject(lambda: supported(cap, .36, [support], True, "synthetic lifted support"), "Z contact missing")})
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--readout", type=Path)
    parser.add_argument("--readout-sha256")
    parser.add_argument("--profiles", type=Path, default=ROOT / "work/restoration-v17/profiles/building-profiles-v3.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(args.output.resolve().is_relative_to(HERE) and not args.output.exists(), "Fresh hall-qa CPU report required")
    checks = []
    def case(ident, fn):
        try:
            evidence = fn()
            checks.append({"id": ident, "input": "actual readout / frozen profile, or separately labelled math fixture", "operation": "complete cap area/domain/Z support", "expected": "unchanged independent thresholds", "passed": True, "evidence": evidence})
            print("PASS", ident, flush=True)
        except Exception as exc:
            checks.append({"id": ident, "passed": False, "error": str(exc), "traceback": traceback.format_exc()})
            print("FAIL", ident, str(exc), flush=True)
    if args.self_test:
        case("CPU-MATH", self_tests)
    else:
        require(args.readout and args.readout_sha256 and sha(args.readout) == args.readout_sha256, "Actual readout SHA mismatch")
        require(sha(args.profiles) == PROFILE_SHA, "Frozen profile SHA mismatch")
        require(sha(ROOT / "work/restoration-v17/registration/registered-buildings.json") == REGISTRY_SHA, "Frozen registry SHA mismatch")
        doc, profiles = json.loads(args.readout.read_text()), json.loads(args.profiles.read_text())
        for path, expected in doc["inputs_sha256"].items():
            require(sha(path) == expected, "Actual readout source input drift: " + path)
        case("CPU-ACTUAL-COMPLETE", lambda: check(doc, profiles))
        if all(c["passed"] for c in checks):
            original = json.dumps(doc, sort_keys=True, allow_nan=False)
            def changed(fn):
                clone = copy.deepcopy(doc)
                fn(clone)
                return clone
            def omit_cap(d):
                b = d["buildings"][0]
                slab = b["geometry"][b["reference_floor"]]
                hi = zrange(slab)[1]
                slab["triangles"].pop(next(i for i, t in enumerate(slab["triangles"]) if all(abs(slab["vertices"][k][2] - hi) < 1e-6 for k in t)))
            def lift_base(d):
                b = d["buildings"][0]
                mesh = b["geometry"][b["components"]["column_base"][0]]
                for v in mesh["vertices"]:
                    v[2] += .01
            def wrong_source(d):
                b = d["buildings"][0]
                b["profile"]["source_polygon_world"][0][0] += .01
            def omit_base(d):
                d["buildings"][0]["components"]["column_base"].pop()
            for ident, mutate, checker, reason in (
                ("EXTRA-CPU-01", omit_cap, lambda d: slab_check(d["buildings"][0]), "complete source-shaped slab top:"),
                ("EXTRA-CPU-02", lift_base, lambda d: check(d, profiles), "Actual base/slab Z contact differs"),
                ("EXTRA-CPU-03", wrong_source, lambda d: slab_check(d["buildings"][0]), "full boundary/hole difference"),
                ("EXTRA-CPU-04", omit_base, lambda d: check(d, profiles), "column/base inventory omitted"),
            ):
                case(ident, lambda mutate=mutate, checker=checker, reason=reason: reject(lambda: checker(changed(mutate)), reason))
            case("EXTRA-CPU-05-HOLED-SOURCE", self_tests)
            def final_guard():
                require(json.dumps(doc, sort_keys=True, allow_nan=False) == original, "Private CPU mutations changed original readout")
                require(sha(args.readout) == args.readout_sha256, "Actual readout SHA changed during CPU audit")
                require(sha(args.profiles) == PROFILE_SHA, "Caller profile SHA changed during CPU audit")
                require(sha(LEGACY) == LEGACY_SHA, "Frozen full-domain helper changed during CPU audit")
                for path, expected in doc["inputs_sha256"].items():
                    require(sha(path) == expected, "Protected input SHA changed during CPU audit: " + path)
                return {"actual_readout_restored": True, "actual_readout_sha_unchanged": True,
                        "all_protected_input_SHA_unchanged": True}
            case("CPU-FINAL-GUARD", final_guard)
    report = {"schema": "v17-three-hall-full-area-tests/1", "passed": sum(c["passed"] for c in checks), "failed": sum(not c["passed"] for c in checks),
              "checks": checks, "EPS_m": EPS, "AREA_EPS_m2": AREA_EPS, "legacy_helper_sha256": LEGACY_SHA,
              "actual_readout_sha256": args.readout_sha256, "math_only": args.self_test,
              "scope": "Complete actual caps/source polygon/holes/support areas; roof 3D contacts remain factory BVH, saved-city remains pending", "third_party_cost": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print("CPU-QA", report["passed"], report["failed"], flush=True)
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
