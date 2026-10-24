"""Independent full-domain CPU checks on actual WORLD readout; no builder import."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SUPPORT = ROOT / "work/restoration-v17/hall-qa/check_actual_supports_v3.py"
SUPPORT_SHA = "65e4663f3caa3724103357fde71e0fd5d2db9c561e71798a4a45775ac5f769cf"
IDS = {"nansansuo_" + g + "_" + r + "_hall" for g in ("east", "middle", "west") for r in ("front", "middle", "rear")} | {"nansansuo_common_gate"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise AssertionError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


require(sha(SUPPORT) == SUPPORT_SHA, "Frozen complete-cap primitives drift")
G = load("v18_frozen_complete_caps", SUPPORT)
K = load("v18_null_preserving_fixture_contract", HERE / "fixture_profile_contract_v2.py")
P = G.P
from shapely.geometry import Polygon
from shapely.ops import unary_union


def projection(geometry, names):
    require(names and len(names) == len(set(names)), "Complete nonduplicated actual object population required")
    domains = []
    for name in names:
        mesh = geometry[name]
        require(mesh.get("hidden") is False, "Actual exterior geometry hidden: " + name)
        domain, _ = P.mesh_projection(mesh["vertices"], mesh["triangles"])
        domains.append(domain)
    combined = unary_union(domains)
    require(combined.is_valid and not combined.is_empty, "Actual projection union invalid")
    return combined


def contained(actual, source, label):
    require(actual.is_valid and source.is_valid, label + ": invalid full domain")
    outside = actual.difference(source.buffer(P.EPS))
    require(outside.is_empty, label + ": actual full triangle area crosses source or source hole beyond100um")
    return {"actual_projected_area_m2": actual.area, "raw_area_outside_source_m2": actual.difference(source).area,
            "outside100um_empty": True, "linear_tolerance_m": P.EPS, "whole_triangle_union_checked": True, "bbox_or_vertex_only_proof": False}


def supports(building):
    components, geometry, profile = building["components"], building["geometry"], building["profile"]
    count = 2 * (K.reference_count(profile, "x") + K.reference_count(profile, "y"))
    columns = components.get("column", []) + components.get("pilaster", [])
    require(len(columns) == len(components["column_base"]) == len(components["roof_bearing_post"]) == count, "Complete actual reference support population omitted")
    require(len(components["beam"]) == 4, "Actual perimeter beams omitted")
    require(len(set(columns + components["column_base"] + components["roof_bearing_post"])) == count * 3, "Actual support identity duplicated")
    slab = geometry[building["reference_floor"]]
    slabtop = G.horizontal(slab, G.zrange(slab)[1], True)
    beams = [geometry[n] for n in components["beam"]]
    evidence = {"complete_source_floor": G.slab_check(building), "bases": [], "columns": [], "bearings": []}
    for name in components["column_base"]:
        mesh = geometry[name]
        require(mesh["support_object"] == building["reference_floor"], "Actual base support identity differs")
        cap, z, capcheck = G.full_cap(mesh, False)
        require(abs(z - G.zrange(slab)[1]) <= P.EPS, "Actual base floor Z gap")
        contact = contained(cap, slabtop, "complete actual base bottom")
        G.full_cap(mesh, True)
        evidence["bases"].append({"object": name, "wholecap": capcheck, "contact": contact})
    for name in columns:
        mesh = geometry[name]
        require(mesh["support_object"] in components["column_base"], "Actual column base omitted")
        cap, z, _ = G.full_cap(mesh, False)
        bottom = G.supported(cap, z, [geometry[mesh["support_object"]]], True, "actual complete column bottom")
        cap, z, _ = G.full_cap(mesh, True)
        top = G.supported(cap, z, beams, False, "actual complete column top")
        evidence["columns"].append({"object": name, "bottom": bottom, "top": top})
    for name in components["roof_bearing_post"]:
        cap, z, _ = G.full_cap(geometry[name], False)
        evidence["bearings"].append({"object": name, **G.supported(cap, z, beams, True, "actual complete roof-bearing bottom")})
    return evidence


def check(doc, profiles, registry, expectations):
    require(doc["schema"] == "v18-ten-exterior-actual-factory-geometry/1" and doc["coordinate_space"] == "WORLD", "Actual V18 WORLD readout required")
    require(doc["native_opened"] is False and doc["native_saved"] is False, "This contract is isolated factory, not saved-native proof")
    rows = doc["buildings"]
    require(len(rows) == 10 and {b["id"] for b in rows} == IDS, "Exact ten actual exteriors required")
    byprofile = {b["building_id"]: b for b in profiles["buildings"]}
    registered = {b["building_id"]: b for b in registry["buildings"]}
    expected = {b["building_id"]: b for b in expectations["buildings"]}
    require(set(byprofile) == set(expected) == IDS, "Profile/independent expectation inventory differs")
    result = []
    for row in rows:
        ident, profile, geometry = row["id"], row["profile"], row["geometry"]
        require(profile == byprofile[ident], "Exported full profile differs")
        for key in ("source_polygon_world", "source_holes_world", "source_polygon_local", "source_holes_local", "anchor", "rotation_z_rad", "source_part_id"):
            require(profile[key] == registered[ident][key], "Actual profile/complete registry binding differs: " + key)
        require(profile["source_part_id"] == expected[ident]["source_part_id"], "Independent entity/source mapping differs")
        K.check_profile_intent(profile, expected[ident])
        require(set(row["objects"]) == set(geometry) and len(row["objects"]) == len(geometry), "Complete actual mesh export omitted or duplicated")
        source = P.polygon(profile["source_polygon_world"], profile["source_holes_world"])
        sourcefloor = supports(row)
        all_names = sorted(geometry)
        roof_names = sorted({n for r in row["roofs"] for n in r["objects"]})
        support_names = sorted({n for role in ("column_base", "column", "pilaster", "beam", "roof_bearing_post", "roof_closure_wall") for n in row["components"].get(role, [])})
        result.append({"id": ident, "actual_meshes": len(all_names), "full_cap_supports": sourcefloor,
                       "complete_roof_skin_ridge_tiles_projection": contained(projection(geometry, roof_names), source, ident + " complete actual roof"),
                       "complete_support_projection": contained(projection(geometry, support_names), source, ident + " complete actual supports"),
                       "all_actual_objects_projection": contained(projection(geometry, all_names), source, ident + " all actual objects")})
    return {"schema":"v18.actual-exterior-full-source-and-cap-CPU/1", "passed":True, "building_count":10, "results":result,
            "linear_tolerance_m":P.EPS, "every_original_source_holes_and_full_floor_checked":True,
            "nine_distinct_sources_plus_gate_shared_cutline_expected":False, "facts_nulls_not_filled":True,
            "complete_source_and_roof_cap_support_scope":True, "3D_roof_skin_contacts_scope":"actual fixture BVH report",
            "saved_native_verified":False, "Blender_started":False, "builder_imported":False, "whole_city_complete":False, "third_party_cost":0}


def self_test():
    outcomes = []
    def reject(label, actual, source):
        try:
            contained(actual, source, label)
        except AssertionError as error:
            outcomes.append({"id":label,"passed":True,"same_checker_rejected":True,"reason":str(error)})
            return
        raise AssertionError("Adversarial full-area domain accepted")
    outer = Polygon([(0,0),(4,0),(4,4),(0,4)])
    contained(Polygon([(1,1),(3,1),(3,3),(1,3)]), outer, "baseline")
    outcomes.append({"id":"CPU-BASELINE","passed":True})
    # All four corners remain in source while their complete face covers its hole.
    holed = Polygon([(0,0),(4,0),(4,4),(0,4)], [[(1,1),(3,1),(3,3),(1,3)]])
    reject("EXTRA-AREA-01-filled-hole", outer, holed)
    concave = Polygon([(0,0),(4,0),(4,4),(3,4),(3,1),(1,1),(1,4),(0,4)])
    bridge = Polygon([(.5,3),(3.5,3),(2,.5)])
    require(all(concave.covers(__import__('shapely').geometry.Point(p)) for p in bridge.exterior.coords), "Private bridge vertices must all be inside")
    reject("EXTRA-AREA-02-inside-vertices-bridge-outside", bridge, concave)
    reject("EXTRA-AREA-03-101um-overhang", Polygon([(0,0),(4.000101,0),(4.000101,4),(0,4)]), outer)
    return outcomes


def main():
    parser = argparse.ArgumentParser()
    for key in ("readout", "profiles", "registry", "expectations"):
        parser.add_argument("--"+key, type=Path)
        parser.add_argument("--"+key+"-sha256")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists() and args.output.resolve().is_relative_to(HERE), "Fresh local CPU output required")
    try:
        if args.self_test:
            result={"schema":"v18.numeric-complete-projection-counterexamples/1","checks":self_test(),"actual_V18_geometry_verified":False,"Blender_started":False,"third_party_cost":0}
            result['summary']={'passed':len(result['checks']),'failed':0}
        else:
            paths = [getattr(args,k) for k in ("readout","profiles","registry","expectations")]
            require(all(paths), "Actual input files all required")
            for key,path in zip(("readout","profiles","registry","expectations"),paths):require(sha(path)==getattr(args,key+"_sha256"), "Actual input SHA differs: "+key)
            doc,p,r,e=[json.loads(p.read_text()) for p in paths]
            require(doc['profiles_sha256']==args.profiles_sha256 and doc['registry_sha256']==args.registry_sha256 and doc['expectations_sha256']==args.expectations_sha256,'Readout final input binding differs')
            result=check(doc,p,r,e)
            result['actual_readout_sha256']=args.readout_sha256
        result['checker_sha256']=sha(Path(__file__))
        result['frozen_complete_cap_primitives_sha256']=SUPPORT_SHA
    except Exception as error:
        result={'schema':'v18.actual-exterior-full-source-and-cap-CPU/1','passed':False,'error':str(error),'traceback':traceback.format_exc(),'Blender_started':False,'actual_geometry_pass_not_claimed':True}
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        raise
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('PASS',result.get('summary',result.get('building_count')))


if __name__ == "__main__":main()
