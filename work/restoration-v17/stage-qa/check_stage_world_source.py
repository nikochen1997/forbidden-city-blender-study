"""Read direct evaluated world vertices; never import Blender or a generator."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

from shapely.geometry import Polygon
from shapely.ops import unary_union

sys.dont_write_bytecode = True
TOLERANCE_M = 0.0001


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def polygon(outer, holes):
    need(len(outer) >= 3, 'complete exterior ring required')
    need(all(len(v) == 2 and all(type(x) in (int, float) and math.isfinite(x) for x in v)
             for ring in [outer] + holes for v in ring), 'finite XY rings required')
    p = Polygon(outer, holes)
    need(p.is_valid and not p.is_empty and p.area > 0, 'invalid source polygon; no repair/buffer(0) allowed')
    return p


def parts(shape):
    if shape.geom_type == 'Polygon':
        return [shape]
    need(shape.geom_type == 'MultiPolygon', 'polygonal domain required')
    return list(shape.geoms)


def compare_domains(expected, actual, label):
    """Bidirectional complete domains and every boundary/hole at fixed <=100um."""
    need(expected.is_valid and actual.is_valid and not actual.is_empty, label + ': invalid/empty domain')
    ep, ap = parts(expected), parts(actual)
    need(len(ep) == len(ap), label + ': component count differs')
    eh = [Polygon(r) for p in ep for r in p.interiors]
    ah = [Polygon(r) for p in ap for r in p.interiors]
    need(len(eh) == len(ah), label + ': hole count differs')
    missing = expected.difference(actual.buffer(TOLERANCE_M))
    excess = actual.difference(expected.buffer(TOLERANCE_M))
    boundary_distance = expected.boundary.hausdorff_distance(actual.boundary)
    need(missing.is_empty, label + ': expected domain missing beyond 100um')
    need(excess.is_empty, label + ': actual domain exceeds source beyond 100um')
    need(boundary_distance <= TOLERANCE_M, label + ': full boundary distance exceeds 100um')
    hole_records = []
    unmatched = list(ah)
    for h in eh:
        need(bool(unmatched), label + ': unmatched expected hole')
        j = min(range(len(unmatched)), key=lambda i: h.boundary.hausdorff_distance(unmatched[i].boundary))
        other = unmatched.pop(j)
        hd = h.boundary.hausdorff_distance(other.boundary)
        need(hd <= TOLERANCE_M and h.difference(other.buffer(TOLERANCE_M)).is_empty
             and other.difference(h.buffer(TOLERANCE_M)).is_empty, label + ': hole domain/boundary differs')
        hole_records.append({'boundary_hausdorff_m': hd})
    return {'tolerance_m': TOLERANCE_M, 'expected_area_m2': expected.area,
            'actual_area_m2': actual.area, 'raw_missing_area_m2': expected.difference(actual).area,
            'raw_excess_area_m2': actual.difference(expected).area,
            'symmetric_difference_m2': expected.symmetric_difference(actual).area,
            'missing_beyond_tolerance_empty': True, 'excess_beyond_tolerance_empty': True,
            'boundary_hausdorff_m': boundary_distance, 'components': len(ap),
            'holes': len(ah), 'hole_checks': hole_records}


def captured_domain(actor, z):
    vertices, faces = actor['evaluated_world_vertices'], actor['evaluated_world_triangles']
    triangles = [Polygon([vertices[i][:2] for i in f]) for f in faces
                 if all(abs(vertices[i][2] - z) < 1e-8 for i in f)]
    need(bool(triangles), 'original capture has no actual cap triangles')
    return unary_union(triangles)


def validate_inputs(bindings):
    for key in ('module', 'profile', 'source_support', 'palette'):
        need(digest(bindings[key + '_path']) == bindings[key + '_sha256'], key + ' SHA drift')
    for path, sha in bindings['transitive_source_sha256'].items():
        need(digest(path) == sha, 'transitive source drift ' + path)
    if 'fixture_path' in bindings:
        need(digest(bindings['fixture_path']) == bindings['fixture_sha256'], 'fixture SHA drift')
    if 'kernel_path' in bindings:
        need(digest(bindings['kernel_path']) == bindings['kernel_sha256'], 'kernel SHA drift')
    if 'strict_checker_path' in bindings:
        need(digest(bindings['strict_checker_path']) == bindings['strict_checker_sha256'], 'strict checker SHA drift')
    p = read(bindings['profile_path'])
    for key in bindings['profile_selector']:
        p = p[key]
    s = read(bindings['source_support_path'])
    need(s['source_status'] == 'actual_source_capture_not_official_measurement'
         and s['source_part_id'] == p['source_part_id'] == 'way-40632241-p0'
         and s['source_component'] == p['source_component_id'] == 'source_north_projection', 'registered stage identity')
    need(digest(s['provenance_path']) == s['provenance_sha256'], 'source provenance SHA drift')
    v = read(s['provenance_path'])
    need(digest(v['registry_path']) == v['registry_sha256'], 'registry SHA drift')
    need(digest(v['actual_capture_path']) == v['actual_capture_sha256'], 'original actual capture SHA drift')
    registry, capture = read(v['registry_path']), read(v['actual_capture_path'])
    registered = next(x for x in registry['buildings'] if x['building_id'] == 'shufang_large_stage')
    for sk, pk in [('outer_world_xy', 'source_polygon_world'), ('holes_world_xy', 'source_holes_world'),
                   ('outer_local_xy', 'source_polygon_local'), ('holes_local_xy', 'source_holes_local'),
                   ('anchor', 'anchor'), ('rotation_z_rad', 'rotation_z_rad')]:
        need(s[sk] == p[pk] == registered[pk], 'complete source/profile/registry mismatch ' + sk)
    need(s['floor_z_m'] == p['dimensions']['floor_z_m']
         and s['slab_bottom_z_m'] == p['dimensions']['slab_bottom_z_m'], 'declared reference Z mismatch')
    need(s['strict_world_domain_tolerance_m'] == TOLERANCE_M == v['coordinate_tolerance_m'], '100um limit must not be weakened')
    c, sine = math.cos(s['rotation_z_rad']), math.sin(s['rotation_z_rad'])
    ax, ay, az = s['anchor']
    for local_ring, world_ring in zip([s['outer_local_xy']] + s['holes_local_xy'],
                                       [s['outer_world_xy']] + s['holes_world_xy']):
        need(len(local_ring) == len(world_ring), 'complete local/world ring lengths')
        need(all(math.dist([ax + c*x - sine*y, ay + sine*x + c*y], w) < 1e-9
                 for (x, y), w in zip(local_ring, world_ring)), 'registered local/world frame transform')
    expected = polygon(s['outer_world_xy'], s['holes_world_xy'])
    assembly = next(x for x in registry['source_assemblies'] if x['source_part_id'] == s['source_part_id'])
    need(v['original_full_source_world'] == assembly['source_polygon_world']
         and v['original_full_source_holes_world'] == assembly['source_holes_world']
         and v['shared_cutlines'] == assembly['shared_cutlines'], 'original complete T-source/cutline provenance')
    all_parts = [polygon(x['source_polygon_world'], x['source_holes_world']) for x in assembly['components']]
    whole = polygon(assembly['source_polygon_world'], assembly['source_holes_world'])
    need(unary_union(all_parts).symmetric_difference(whole).area < 1e-10
         and sum(x.area for x in all_parts) - whole.area < 1e-10, 'stage/south source partition incomplete or overlaps')
    actor_name = v['actual_capture_actor_name']
    need(capture['part_actor_mapping'][s['source_part_id']] == v['actual_capture_part_actor_mapping']
         and actor_name in v['actual_capture_part_actor_mapping'], 'original actual actor mapping')
    actor = capture['actor_evidence'][actor_name]
    canonical = hashlib.sha256(json.dumps(actor, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    need(canonical == v['actual_capture_actor_record_sha256'] and actor['matrix_world'] == v['actual_capture_actor_matrix_world']
         and actor['raw_mesh_sha256'] == v['actual_capture_actor_raw_mesh_sha256'], 'original actual actor geometry/matrix record drift')
    capture_whole = captured_domain(actor, min(x[2] for x in actor['evaluated_world_vertices']))
    original_comparison = compare_domains(whole, capture_whole, 'registered full T vs original actual cap')
    mapping = v['component_vertex_to_actual_capture_mapping']
    need(len(mapping) == len(s['outer_world_xy']), 'complete component/capture vertex mapping')
    mapped = []
    for i, row in enumerate(mapping):
        actual_vertex = actor['evaluated_world_vertices'][row['actual_capture_world_vertex_index']]
        need(row['registered_component_vertex_index'] == i and row['registered_world_xy'] == s['outer_world_xy'][i]
             and actual_vertex == row['actual_capture_world_xyz']
             and math.dist(actual_vertex[:2], s['outer_world_xy'][i]) <= TOLERANCE_M, 'mapped actual original source corner mismatch')
        mapped.append(actual_vertex[:2])
    original_component_comparison = compare_domains(expected, polygon(mapped, []), 'registered stage vs actual mapped component')
    for path, sha in read(bindings['palette_path']).get('source_files_sha256', {}).items():
        # Paths in the caller palette are repository-relative, not CWD-dependent provenance guesses.
        resolved = Path(v['registry_path']).parents[3] / path
        need(digest(resolved) == sha, 'caller palette source drift ' + path)
    return p, s, expected, {'original_full_source': original_comparison,
                            'mapped_original_stage_component': original_component_comparison,
                            'source_part_id': s['source_part_id'], 'source_component_id': s['source_component'],
                            'new_stage_geometry_verified': False}


def mesh_domains(mesh, top_z, bottom_z):
    vertices, faces = mesh['vertices'], mesh['triangles']
    need(vertices and faces and mesh.get('hidden') is False, 'actual source floor absent/hidden')
    need(all(len(v) == 3 and all(type(x) in (int, float) and math.isfinite(x) for x in v)
             for v in vertices), 'finite direct world vertices required')
    need(all(len(f) == 3 and all(type(i) is int and 0 <= i < len(vertices) for i in f) for f in faces), 'actual loop triangles required')
    need(abs(min(v[2] for v in vertices) - bottom_z) <= TOLERANCE_M
         and abs(max(v[2] for v in vertices) - top_z) <= TOLERANCE_M, 'actual slab full Z extent differs')
    projected, top, bottom = [], [], []
    for f in faces:
        points = [vertices[i] for i in f]
        tri = Polygon([v[:2] for v in points])
        if tri.area <= 1e-14:
            continue
        need(tri.is_valid, 'actual triangle projection invalid')
        projected.append(tri)
        if all(abs(v[2] - top_z) <= TOLERANCE_M for v in points):
            top.append(tri)
        if all(abs(v[2] - bottom_z) <= TOLERANCE_M for v in points):
            bottom.append(tri)
    need(top and bottom and projected, 'actual top/bottom/projected domains required')
    return {'top_cap': unary_union(top), 'bottom_cap': unary_union(bottom),
            'complete_mesh_XY_projection': unary_union(projected)}


def verify_world(bindings, world):
    p, s, expected, provenance = validate_inputs(bindings)
    need(world['schema'] == 'v17-stage-direct-evaluated-world-baseline/1'
         and world['coordinate_space'] == 'world'
         and world['capture_method'] == 'direct_evaluated_matrix_world_times_mesh_vertex_not_local_reprojection', 'direct evaluated world export required')
    need(world['building_id'] == p['building_id'] and world['source_part_id'] == s['source_part_id']
         and world['source_component_id'] == s['source_component'], 'actual capture target mismatch')
    for k in ('module', 'profile', 'source_support', 'palette'):
        need(world['input_sha256'][k] == bindings[k + '_sha256'], 'actual world input SHA differs ' + k)
    if 'fixture_sha256' in bindings:
        need(world['fixture_sha256'] == bindings['fixture_sha256'], 'actual capture fixture SHA differs')
    if 'kernel_sha256' in bindings:
        need(world['kernel_sha256'] == bindings['kernel_sha256'], 'actual capture kernel SHA differs')
    slab = world['meshes'][world['reference_floor_object']]
    domains = mesh_domains(slab, s['floor_world_z_m'], s['slab_bottom_world_z_m'])
    measurements = {key: compare_domains(expected, value, key) for key, value in domains.items()}
    return {'provenance': provenance, 'actual_source_domains': measurements,
            'actual_floor_object': world['reference_floor_object'],
            'actual_floor_vertices': len(slab['vertices']), 'actual_floor_triangles': len(slab['triangles'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bindings', type=Path, required=True)
    parser.add_argument('--world-baseline', type=Path)
    parser.add_argument('--stage-report', type=Path)
    parser.add_argument('--output-path', type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    b = read(args.bindings)
    if args.preflight_only:
        evidence = validate_inputs(b)[3]
        print(json.dumps({'status': 'INPUTS_AND_ORIGINAL_CAPTURE_VERIFIED_NEW_STAGE_PENDING',
                          'evidence': evidence, 'actual_production_source_verified': False,
                          'Blender_launched': False}, ensure_ascii=False, indent=2))
        return
    need(args.world_baseline is not None and args.output_path is not None, 'actual world baseline and fresh output required')
    need(not args.output_path.exists(), 'never overwrite an original red result')
    result = {'schema': 'v17-stage-direct-world-strict-source-qa/1', 'tolerance_m': TOLERANCE_M,
              'actual_production_source_verified': False, 'module_geometry_plus_source_verified': False,
              'city_native_integration_verified': False, 'render_verified': False,
              'Blender_launched': False, 'generator_imported': False,
              'bindings_sha256': digest(args.bindings), 'world_baseline_sha256': digest(args.world_baseline),
              'checker_sha256': digest(__file__)}
    try:
        result['evidence'] = verify_world(b, read(args.world_baseline))
        result['actual_production_source_verified'] = True
        if args.stage_report:
            r = read(args.stage_report)
            need(r['failed'] == 0 and r['passed'] == 14 and r['module_geometry_verified'] is True,
                 'factory stage report must contain all 14 actual checks')
            expected_ids = {'ACTUAL-' + str(i).zfill(2) for i in range(6)} | {
                'EXTRA-GEO-' + str(i).zfill(2) for i in range(1, 7)} | {'RESTORE-GUARD', 'INPUT-GUARD'}
            need(len(r['checks']) == 14 and {x['id'] for x in r['checks']} == expected_ids
                 and all(x['passed'] is True for x in r['checks'])
                 and all(x.get('negative_rejected') is True for x in r['checks'] if x['id'].startswith('EXTRA-')),
                 'factory stage actual rows/negative controls incomplete')
            need(r['direct_world_baseline_sha256'] == digest(args.world_baseline)
                 and r['input_sha256'] == read(args.world_baseline)['input_sha256']
                 and r['fixture_sha256'] == b['fixture_sha256'], 'factory report/world export not linked')
            result['stage_report_sha256'] = digest(args.stage_report)
            result['module_geometry_plus_source_verified'] = True
        result['passed'] = True
    except Exception as exc:
        result['passed'] = False
        result['actual_production_source_verified'] = False
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc()
    args.output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'evidence'}, ensure_ascii=False, indent=2))
    need(result['passed'], 'strict source validation failed; original red preserved')


if __name__ == '__main__':
    main()
