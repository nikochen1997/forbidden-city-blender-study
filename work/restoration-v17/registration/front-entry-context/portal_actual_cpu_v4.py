"""Independent actual-triangle portal proof; three finite Z intervals, no Blender.

The immutable V16 helper supplies geometry measurements only. Its fixed two-
interval contract and its context profile adapter are never called here.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

from shapely.geometry import GeometryCollection, MultiPoint, Polygon

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
HELPER = ROOT / "work/restoration-v16/saved-audit/context_wall_cpu_v2.py"
HELPER_SHA = "fdb3fa02ef1886127d52cab85cd60d28a74df5acad1f99e3ab45dfa21764b26a"
BINDING = HERE / "concrete-profile-binding-v3.json"
BINDING_SHA = "5eba96383820c7a582ef2e75996de1f2c0391b4f393af8ddf76627681d076e46"
SOURCE = HERE / "source-context.json"
SOURCE_SHA = "65726e73a8cdf2a33b7f39cae30f60febd834bc55600fef108e9080f6d76337f"
EPS, AREA_EPS = 1e-4, 1e-7
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise AssertionError(message)


require(sha(HELPER) == HELPER_SHA, "immutable geometry helper hash drift")
spec = importlib.util.spec_from_file_location("immutable_v16_context_measurement", HELPER)
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)
require(G.EPS == EPS and G.AREA_EPS == AREA_EPS, "unchanged coordinate/area tolerances")


def signed_volume(mesh):
    # Translate to one actual vertex before summing to avoid large-world cancellation.
    origin = mesh["vertices"][0]
    total = 0
    for t in mesh["triangles"]:
        a, b, c = [[mesh["vertices"][i][j] - origin[j] for j in range(3)] for i in t]
        n = G.normal([0, 0, 0], b, c)
        total += sum(a[j] * n[j] for j in range(3)) / 6
    return total


def side_interval_proof(mesh, vertices, levels, expected_domains):
    """All points of all finite clipped side triangles, across arbitrary intervals."""
    require(len(expected_domains) == len(levels) - 1, "interval/domain count mismatch")
    classified, max_shift = [], 0
    for v in vertices:
        near = min(levels, key=lambda z: abs(v[2] - z))
        shift = abs(v[2] - near)
        require(shift <= EPS, "actual portal vertex outside classified Z tolerance")
        max_shift = max(max_shift, shift)
        classified.append([v[0], v[1], near])
    results, worst = [], 0
    for low, high, expected in zip(levels, levels[1:], expected_domains):
        boundary = expected.boundary
        tube = boundary.buffer(EPS, resolution=64)
        rows = []
        for index, tri in enumerate(mesh["triangles"]):
            pts = [classified[j] for j in tri]
            if max(v[2] for v in pts) == min(v[2] for v in pts):
                continue
            clipped = G._clip_plane(G._clip_plane(pts, low, True), high, False)
            if not clipped or max(v[2] for v in clipped) <= min(v[2] for v in clipped):
                continue
            projection = MultiPoint([(v[0], v[1]) for v in clipped]).convex_hull
            require(projection.difference(tube).is_empty, "full actual portal side projection leaves expected boundary tolerance tube")
            lower, upper = 0, EPS
            for _ in range(25):
                mid = (lower + upper) / 2
                if projection.difference(boundary.buffer(mid, resolution=64)).is_empty:
                    upper = mid
                else:
                    lower = mid
            worst = max(worst, upper)
            rows.append({"actual_triangle_index": mesh.get("original_triangle_indices", list(range(len(mesh["triangles"]))))[index], "entire_clipped_projection_type": projection.geom_type, "entire_clipped_projection_area_m2": projection.area, "complete_projection_distance_upper_bound_m": upper})
        require(rows, "actual portal interval has no finite sides")
        results.append({"nominal_Z_interval_m": [low, high], "complete_finite_side_count": len(rows), "all_finite_sides": rows})
    combined = math.hypot(worst, max_shift)
    require(combined <= EPS, "combined portal full-side XY and Z distance exceeds tolerance")
    return {"intervals": results, "maximum_certified_full_side_XY_boundary_distance_m": worst, "maximum_actual_Z_plane_offset_m": max_shift, "combined_3D_distance_upper_bound_m": combined, "actual_native_vertices_modified": False, "intervals_claimed_exact_constant": False}


def component_side_proof(original, replacement, a, b, levels, cutter):
    old, new = G.connected_components(original), G.connected_components(replacement)
    require(len(old) == len(new), "source connected-component inventory changed")
    source_domains = [G.source_horizontal_domain(g, a, levels[-1]) for g in old]
    unused, rows = set(range(len(old))), []
    for j, group in enumerate(new):
        actual_cap, _ = G.horizontal(group, b, levels[-1])
        matches = []
        for i in unused:
            try:
                proof = G.compare(actual_cap, source_domains[i], "complete portal topcap/source component")
            except AssertionError:
                continue
            matches.append((i, proof))
        require(len(matches) == 1, "portal clone component not uniquely matched to complete original topcap")
        i, proof = matches[0]
        unused.remove(i)
        s = source_domains[i]
        rows.append({"source_component": i, "clone_component": j, "complete_topcap_match": proof, **side_interval_proof(group, b, levels, [s, s.difference(cutter), s])})
    require(not unused, "complete original component lost")
    return {"original_components": len(old), "replacement_components": len(new), "componentwise_three_interval_proof": rows}


def domains(original, replacement, binding):
    levels = binding["source_proxy_critical_Z_m"]
    require(levels == [0.0, .35, 3.6, 6.0], "four explicit proxy Z levels changed")
    a = G.local_vertices(original, binding["front_frame"])
    b = G.local_vertices(replacement, binding["front_frame"])
    original_volume, clone_volume = signed_volume(original), signed_volume(replacement)
    require(original_volume > 0 and clone_volume > 0, "original and new portal must retain positive signed volume")
    G.connected_components(original)
    G.connected_components(replacement)
    original_guard = G.vertical_prism_guard(original, a, [levels[0], levels[-1]])
    replacement_guard = G.vertical_prism_guard(replacement, b, levels)
    source = G.source_horizontal_domain(original, a, levels[-1])
    require(source.is_valid and not source.is_empty, "actual original full cap domain invalid")
    original_down, _ = G.horizontal(original, a, levels[-1])
    G.compare(original_down, source, "positive immutable source topcap")
    cut = Polygon(binding["cutter"]["polygon_local"])
    removed, middle = source.intersection(cut), source.difference(cut)
    require(removed.area > .1 and middle.area > 0, "finite portal cutter misses/erases source")
    intervals = []
    for low, high, expected in zip(levels, levels[1:], [source, middle, source]):
        z = (low + high) / 2
        endpoints = []
        # Stay outside actual float32 construction-plane offset, without changing EPS.
        offset = min(1e-6, (high - low) / 100)
        for endpoint in (low + offset, high - offset):
            endpoints.append({"section_Z_m": endpoint, **G.compare(G.section(replacement, b, endpoint), expected, "complete portal near-plane full-domain at " + str(endpoint))})
        intervals.append({"nominal_Z_interval_m": [low, high], "middle_section_Z_m": z, "middle_full_domain": G.compare(G.section(replacement, b, z), expected, "complete portal middle full-domain at " + str(z)), "near_plane_full_domains": endpoints, "interval_claimed_exact_constant": False})
    caps = []
    empty = GeometryCollection()
    for z, up_expected, down_expected in [(levels[0], empty, source), (levels[1], removed, empty), (levels[2], empty, removed), (levels[3], source, empty)]:
        up, down = G.horizontal(replacement, b, z)
        caps.append({"nominal_Z_m": z, "upward_signed_domain": G.compare(up, up_expected, "complete portal upward cap at " + str(z)), "downward_signed_domain": G.compare(down, down_expected, "complete portal downward cap at " + str(z))})
    side = component_side_proof(original, replacement, a, b, levels, cut)
    return {"original_signed_volume_m3": original_volume, "replacement_signed_volume_m3": clone_volume, "original_all_finite_face_guard": original_guard, "replacement_all_finite_face_guard": replacement_guard, "three_full_Z_interval_domains": intervals, "four_complete_signed_caps": caps, "complete_finite_sides": side, "removed_complete_XY_area_m2": removed.area, "coordinate_tolerance_m": EPS, "area_epsilon_m2": AREA_EPS, "bbox_or_sampling_used_as_domain_proof": False, "source_metrics_measured": False}


def check(doc):
    """Readout API; actual geometry must be exported by the independent saved reader."""
    require(sha(BINDING) == BINDING_SHA and sha(SOURCE) == SOURCE_SHA, "portal binding/source file drift")
    binding, source = json.loads(BINDING.read_text()), json.loads(SOURCE.read_text())
    for name, digest in binding["input_files_sha256"].items():
        require(sha(ROOT / name) == digest, "portal immutable input drift: " + name)
    row = doc["front_entry_context"]
    require(row["schema"] == "v17.actual-front-entry-context-world-geometry/1", "actual portal readout schema")
    require(row["binding_sha256"] == BINDING_SHA and row["binding"] == binding, "actual portal binding mismatch")
    o, r, e = row["original"], row["replacement"], source["actual_actor_evidence"]
    require(o["object"] == binding["original_object"] and r["object"] == binding["replacement_object"], "actual portal object identity mismatch")
    for key in ("raw_vertices", "raw_faces", "raw_face_material_indices", "matrix_world", "parent", "actual_material_slots", "custom_properties", "collections"):
        require(o[key] == e[key], "immutable original portal source changed: " + key)
    require(o["vertices"] == e["evaluated_world_vertices"] and o["triangles"] == e["evaluated_world_triangles"], "immutable original evaluated geometry changed")
    for key in ("matrix_world", "parent", "actual_material_slots"):
        require(r[key] == e[key], "portal clone original transform/material relation changed: " + key)
    require(r["mesh_users"] == 1 and not r["modifiers"], "portal clone must be single-user evaluated/no modifiers")
    require("source_building_id" not in r["custom_properties"], "portal clone duplicated original source identity")
    require(o["visibility"]["hide_render"] and o["visibility"]["hide_get"] and o["visibility"]["hide_viewport"] == e["visibility"]["hide_viewport"], "original portal exact display flags changed")
    require(not r["visibility"]["hide_render"] and not r["visibility"]["hide_viewport"] and not r["visibility"]["hide_get"], "actual portal replacement display hidden")
    opening = row["actual_front_opening_record"]
    control = binding["expected_front_opening_control"]
    for key in ("id", "wall_side", "bay_index", "kind"):
        require(opening[key] == control[key], "actual G14 south central opening identity differs")
    for key in ("clear_width_m", "clear_height_m", "bottom_z_m"):
        require(abs(opening[key] - control[key]) <= 1e-9, "actual G14 opening differs from expected control: " + key)
    require(abs(opening["center_local"][0]) <= 1e-9, "actual G14 central opening shifted off axis")
    return domains(o, r, binding)


def math_mesh(cut=False, fill=False, lose_leg=False):
    """Small exact rectangular-cell U fixture; no actual native geometry generated."""
    xs, ys = [-5, -4, -1, 1, 4, 5], [-6, -5, -1, 0]
    zs = [0, .35, 3.6, 6] if cut or fill else [0, 6]
    occupied = set()
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            for k in range(len(zs) - 1):
                x, y = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
                inside = y >= -1 or abs(x) >= 4
                if cut and k == 1 and abs(x) < 1 and y >= -1:
                    inside = False
                if fill and k == 1 and abs(x) < 1 and y >= -1:
                    inside = True
                if lose_leg and x < -4 and y < -1:
                    inside = False
                if inside:
                    occupied.add((i, j, k))
    vertices, triangles, vertex_ids = [], [], {}
    def vid(p):
        if p not in vertex_ids:
            vertex_ids[p] = len(vertices)
            vertices.append(list(p))
        return vertex_ids[p]
    for i, j, k in sorted(occupied):
        x0, x1, y0, y1, z0, z1 = xs[i], xs[i + 1], ys[j], ys[j + 1], zs[k], zs[k + 1]
        faces = [((-1, 0, 0), [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)]), ((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]), ((0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]), ((0, 1, 0), [(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)]), ((0, 0, -1), [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)]), ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])]
        for delta, quad in faces:
            if (i + delta[0], j + delta[1], k + delta[2]) in occupied:
                continue
            q = [vid(p) for p in quad]
            triangles.extend([q[:3], [q[0], q[2], q[3]]])
    return {"vertices": vertices, "triangles": triangles}


def self_test():
    source, clone = math_mesh(), math_mesh(cut=True)
    binding = {"front_frame": {"anchor": [0, 0, 0], "rotation_z_rad": 0}, "source_proxy_critical_Z_m": [0.0, .35, 3.6, 6.0], "cutter": {"polygon_local": [[-1, -1.25], [1, -1.25], [1, .25], [-1, .25]]}}
    results = []
    def case(ident, inp, op, expected, fn):
        try:
            evidence = fn()
            results.append({"id": ident, "input": inp, "operation": op, "expected": expected, "passed": True, "evidence": evidence})
        except Exception as exc:
            results.append({"id": ident, "input": inp, "operation": op, "expected": expected, "passed": False, "error": str(exc)})
    case("PORTAL-MATH-01", "Exact U-source and finite central portal mathematical meshes", "Same all-triangle three-interval/four-cap checker", "Complete domains, signedcaps, all finite sides pass", lambda: domains(source, clone, binding))
    def reject(mutant, reason):
        domains(source, clone, binding)
        try:
            domains(source, mutant, binding)
        except AssertionError as exc:
            require(reason in str(exc), "negative masked by unrelated baseline error: " + str(exc))
            domains(source, clone, binding)
            return {"baseline_passed": True, "mutant_rejected": True, "reason": str(exc), "baseline_restored_passed": True}
        raise AssertionError("invalid actual-domain fixture accepted")
    mutants = [("01", "Uncut complete U", source, "full-domain"), ("02", "Delete far west leg beyond finite cutter", math_mesh(cut=True, lose_leg=True), "full-domain"), ("03", "Fill finite passage", math_mesh(cut=True, fill=True), "full-domain")]
    missing_top = copy.deepcopy(clone)
    missing_top["triangles"] = [t for t in missing_top["triangles"] if not all(missing_top["vertices"][i][2] == 6 for i in t)]
    mutants.append(("04", "Remove whole topcap", missing_top, "not closed"))
    inward = copy.deepcopy(clone)
    inward["triangles"] = [list(reversed(t)) for t in inward["triangles"]]
    mutants.append(("05", "Reverse new clone winding/volume", inward, "positive signed volume"))
    for num, label, mutant, reason in mutants:
        case("EXTRA-PORTAL-" + num, label + " private mesh copy", "Green baseline -> same checker must reject -> original baseline green", "Reject actual geometric defect, no EPS relaxation", lambda m=mutant, r=reason: reject(m, r))
    return {"schema": "v17.portal-three-interval-mathematical-fixture-tests/1", "results": results, "summary": {"passed": sum(r["passed"] for r in results), "failed": sum(not r["passed"] for r in results)}, "actual_saved_geometry_executed": False, "mathematical_fixture_only": True, "native_opened": False, "native_saved": False, "third_party_cost": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--readout", type=Path)
    parser.add_argument("--readout-sha256")
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    require(not a.output.exists(), "preserve all previous evidence")
    if a.self_test:
        report = self_test()
    else:
        require(a.readout and sha(a.readout) == a.readout_sha256, "actual readout SHA binding")
        doc = json.loads(a.readout.read_text())
        try:
            evidence = check(doc)
            report = {"schema": "v17.actual-portal-CPU-full-domain/1", "summary": {"passed": 1, "failed": 0}, "evidence": evidence}
        except Exception as exc:
            report = {"schema": "v17.actual-portal-CPU-full-domain/1", "summary": {"passed": 0, "failed": 1}, "error": str(exc)}
        report.update({"actual_readout_sha256": a.readout_sha256, "native_sha256": doc.get("native_sha256"), "manifest_sha256": doc.get("manifest_sha256"), "native_opened": False, "native_saved": False, "third_party_cost": 0})
    report["checker_sha256"] = sha(__file__)
    report["helper_sha256"] = HELPER_SHA
    report["binding_sha256"] = BINDING_SHA
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report["summary"]))
    if report["summary"]["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
