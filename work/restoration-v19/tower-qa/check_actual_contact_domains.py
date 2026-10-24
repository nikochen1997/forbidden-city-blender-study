"""Independent complete-contact CPU check of exported actual WORLD triangles."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

AREA_TOL = 2e-7
Z_TOL = 2e-4


def require(value, message):
    if not value:
        raise AssertionError(message)


def triangles(row, upward):
    vertices = row["vertices_world"]
    result = []
    for ids, _ in row["triangles_with_material_index"]:
        a, b, c = [vertices[i] for i in ids]
        u, v = [[p[i]-a[i] for i in range(3)] for p in (b, c)]
        n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        if n[2] * (1 if upward else -1) <= 1e-10:
            continue
        poly = Polygon([(vertices[i][0], vertices[i][1]) for i in ids])
        require(poly.is_valid and poly.area > 0, "invalid actual contact triangle")
        result.append((poly, a, n))
    return result


def height(a, normal, x, y):
    return a[2]-(normal[0]*(x-a[0])+normal[1]*(y-a[1]))/normal[2]


def check_one(cap, roof, cached=None):
    if cached is None:
        faces = triangles(roof, False)
        tree = STRtree([f[0] for f in faces])
    else:
        faces, tree = cached
    top = triangles(cap, True)
    require(top, "actual cap has no positive projected top faces")
    maximum_gap = maximum_z = 0
    for poly, point, normal in top:
        patches = []
        for index in tree.query(poly, predicate="intersects"):
            other, rpoint, rnormal = faces[int(index)]
            cut = poly.intersection(other)
            if cut.area < 1e-12:
                continue
            patches.append(cut)
            parts = [cut] if cut.geom_type == "Polygon" else list(cut.geoms)
            for part in parts:
                if part.geom_type != "Polygon":
                    continue
                for x, y in part.exterior.coords:
                    dz = abs(height(point, normal, x, y)-height(rpoint, rnormal, x, y))
                    maximum_z = max(maximum_z, dz)
                    require(dz <= Z_TOL, "actual full cap/roof plane height gap " + cap["name"])
        gap = poly.difference(unary_union(patches)).area
        maximum_gap = max(maximum_gap, gap)
        require(gap < AREA_TOL, "actual full cap projected domain uncovered " + cap["name"])
    return {"name": cap["name"], "roof": roof["name"], "top_triangles": len(top),
            "maximum_uncovered_triangle_area_m2": maximum_gap, "maximum_affine_height_gap_m": maximum_z}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--readout", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    require(not args.report.exists(), "preserve prior CPU report")
    raw = args.readout.read_bytes()
    original_sha = hashlib.sha256(raw).hexdigest()
    doc = json.loads(raw)
    require(doc["schema"] == "v19-two-exterior-actual-factory-world/1", "unsupported actual readout")
    by_name = {row["name"]: row for row in doc["objects"]}
    caps = [row for row in doc["objects"] if row["props"].get("roof_contact_object")]
    require(caps, "no actual roof-contact solids")
    cache = {}
    evidence = []
    for cap in caps:
        roof = by_name[cap["props"]["roof_contact_object"]]
        if roof["name"] not in cache:
            faces = triangles(roof, False)
            cache[roof["name"]] = (faces, STRtree([face[0] for face in faces]))
        evidence.append(check_one(cap, roof, cache[roof["name"]]))
    mutant = copy.deepcopy(caps[0])
    for vertex in mutant["vertices_world"]:
        vertex[2] += .01
    roof = by_name[mutant["props"]["roof_contact_object"]]
    try:
        check_one(mutant, roof, cache[roof["name"]])
    except AssertionError as exc:
        reason = str(exc)
    else:
        raise AssertionError("actual-export-derived private lifted cap was accepted")
    check_one(caps[0], roof, cache[roof["name"]])
    require(hashlib.sha256(args.readout.read_bytes()).hexdigest() == original_sha, "actual readout changed")
    report = {"schema": "v19-actual-complete-contact-CPU/1", "summary": {"passed": 3, "failed": 0},
              "actual_readout": str(args.readout), "actual_readout_sha256": original_sha,
              "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "actual_contacts": evidence, "area_tolerance_m2": AREA_TOL, "height_tolerance_m": Z_TOL,
              "EXTRA_CPU_01": {"type": "in-memory actual-export-derived private mutant, not another Blender run",
                               "operation": "lift all first contact vertices by1cm; same complete checker",
                               "rejected_reason": reason, "original_positive_rechecked": True},
              "model_generator_imported": False, "input_unchanged": True, "native_opened": False,
              "scope": "all exported actual roof-contact upper faces only; no source/floor/base support or historical approval",
              "third_party_cost": 0, "human_approval": "pending", "whole_city_complete": False}
    with args.report.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print("ACTUAL_COMPLETE_CONTACT_CPU", len(evidence), "contacts,3/0")


if __name__ == "__main__":
    main()
