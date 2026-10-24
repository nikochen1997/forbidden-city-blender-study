"""Independent complete-contact check of formal factory or saved WORLD rows."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import traceback

from shapely.strtree import STRtree


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--readout", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    assert not args.report.exists()
    reader = Path(__file__).parent / "tower-qa/check_actual_contact_domains.py"
    spec = importlib.util.spec_from_file_location("independent_contact_CPU", reader)
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    raw = args.readout.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    doc = json.loads(raw)
    assert doc["schema"] == "v19-three-formal-body-actual-world/1"
    by_name = {row["name"]: row for row in doc["objects"]}
    results, cache, pairs = [], {}, []
    for cap in by_name.values():
        props = json.loads(cap["props_json"])
        roof_name = props.get("roof_contact_object")
        if not roof_name:
            continue
        roof = by_name[roof_name]
        if roof_name not in cache:
            triangles = api.triangles(roof, False)
            cache[roof_name] = (triangles, STRtree([t[0] for t in triangles]))
        pairs.append((cap, roof))
        try:
            results.append({"passed": True, "evidence": api.check_one(cap, roof, cache[roof_name])})
        except Exception as exc:
            results.append({"passed": False, "object": cap["name"], "error": str(exc), "traceback": traceback.format_exc()})
    assert len(pairs) == 100, "all formal actual roof contacts required"
    cap, roof = pairs[0]
    lifted = copy.deepcopy(cap)
    for vertex in lifted["vertices_world"]:
        vertex[2] += .01
    try:
        api.check_one(lifted, roof, cache[roof["name"]])
    except AssertionError as exc:
        negative = str(exc)
    else:
        raise AssertionError("actual-export-derived lifted contact accepted")
    assert hashlib.sha256(args.readout.read_bytes()).hexdigest() == digest
    report = {"schema": "v19-three-formal-body-actual-full-roof-contacts/2",
              "actual_readout_sha256": digest, "independent_reader_sha256": hashlib.sha256(reader.read_bytes()).hexdigest(),
              "summary": {"passed": sum(r["passed"] for r in results), "failed": sum(not r["passed"] for r in results)},
              "contacts": results, "EXTRA_CPU_01": {"type": "private actual-export-derived1cm lift, not new Blender geometry", "rejected_reason": negative},
              "area_tolerance_m2": api.AREA_TOL, "affine_Z_tolerance_m": api.Z_TOL,
              "scope": "all formal actual contact upper triangle domains against actual roof undersides; base support separate",
              "generator_imported": False, "human_approval": "pending", "whole_city_complete": False, "third_party_cost": 0}
    with args.report.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(report["summary"]))
    if report["summary"]["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
