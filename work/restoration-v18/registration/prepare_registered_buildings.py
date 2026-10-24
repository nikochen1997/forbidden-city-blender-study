"""After root terminal0: verify actual full source domains and register ten rows.

CPU only. Uses the existing qualified coordinate helper; does not create profiles
or native geometry and never imports an old builder/main.
"""
import argparse
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EPS = 1e-4
AREA_EPS = 1e-7
COORDINATES = ROOT / 'work/restoration-v16/registration/prepare_registered_buildings.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_actual_source(actual, request, model):
    parts = {r['id']: r for r in model['parts']}
    assert actual['native_sha256'] == request['native_sha256'] == '7d20ca54b3e10efb9ad2ea98d750f78530c2e47325d2a0fda4d7002024a25782'
    assert actual['native_mesh_count'] == 13995 and actual['original_source_mesh_count'] == 2845
    assert actual['all_13995_mesh_raw_evaluated_fields_unchanged'] is True
    assert actual['all_relations_and_durable_states_unchanged'] is True
    assert set(actual['part_actor_mapping']) == set(request['source_record_sha256'])
    assert set(actual['source_wall_actor_mapping']) == set(request['source_wall_line_ids'])
    for sid, names in actual['part_actor_mapping'].items():
        assert names
        for name in names:
            a = actual['actor_evidence'][name]
            assert a['object_type'] == 'MESH' and a['source_part_id'] == sid
            assert a['source_record'] == parts[sid] and a['source_record_sha256'] == canonical(parts[sid])
            assert a['complete_source_polygon_world'] == parts[sid]['polygon']
            assert a['complete_source_holes_world'] == parts[sid]['holes']
    guard = read(HERE / 'full-mesh-state-guard.json')
    durable = read(HERE / 'durable-state-guard.json')
    assert guard['scene_mesh_count'] == len(guard['rows']) == 13995
    assert guard['source_mesh_count'] == 2845 and guard['before_sha256'] == guard['after_sha256']
    assert all(r['before_sha256'] == r['after_sha256'] for r in guard['rows'])
    assert guard['all_before_after_fields_equal'] and guard['all_mesh_relations_equal']
    assert guard['all_nonmesh_equal'] and guard['all_cameras_including_DOF_equal']
    assert durable['all_full_values_equal'] and durable['before_sha256'] == durable['after_sha256']


def actual_domain(actual, sid, source):
    names = actual['part_actor_mapping'][sid]
    assert len(names) == 1, 'Only exact original body is expected for these flat source proxies'
    a = actual['actor_evidence'][names[0]]
    assert a['semantic_role'] == 'osm_part_body'
    points, faces, triangles = a['evaluated_world_vertices'], a['evaluated_world_faces'], a['evaluated_world_triangles']
    assert all(len(p) == 3 and all(math.isfinite(v) for v in p) for p in points)
    edges = Counter(tuple(sorted((u, v))) for face in faces for u, v in zip(face, face[1:] + face[:1]))
    assert edges and all(n == 2 for n in edges.values()), 'Actual target source body is not closed'
    volume = 0.0
    for tri in triangles:
        p, q, r = [points[i] for i in tri]
        volume += (p[0] * (q[1] * r[2] - q[2] * r[1])
                   + p[1] * (q[2] * r[0] - q[0] * r[2])
                   + p[2] * (q[0] * r[1] - q[1] * r[0])) / 6
    assert volume > 0, 'Actual target source volume is not positive'
    caps = [Polygon([[v[0], v[1]] for v in tri]) for tri in a['actual_projected_bottom_cap_triangles_world']]
    projected = unary_union([q for q in caps if q.area > 0])
    assert projected.is_valid and projected.geom_type == source.geom_type == 'Polygon'
    assert len(projected.interiors) == len(source.interiors), 'Actual target source cap holes differ'
    missing = source.difference(projected.buffer(EPS)).area
    extra = projected.difference(source.buffer(EPS)).area
    boundary = projected.boundary.hausdorff_distance(source.boundary)
    assert missing <= AREA_EPS and extra <= AREA_EPS and boundary <= EPS, 'Actual complete source projection differs'
    complete_faces = [Polygon([[points[i][0], points[i][1]] for i in tri]) for tri in triangles]
    full_projection = unary_union([q for q in complete_faces if q.area > 0])
    assert full_projection.is_valid and full_projection.geom_type == 'Polygon'
    assert len(full_projection.interiors) == len(source.interiors)
    full_missing = source.difference(full_projection.buffer(EPS)).area
    full_extra = full_projection.difference(source.buffer(EPS)).area
    full_boundary = full_projection.boundary.hausdorff_distance(source.boundary)
    assert full_missing <= AREA_EPS and full_extra <= AREA_EPS and full_boundary <= EPS, 'Actual whole mesh projects outside complete source'
    return {'actual_actor': names[0], 'actual_vertices': len(points), 'actual_triangles': len(triangles),
            'actual_signed_volume_m3': volume, 'actual_bottom_projection_area_m2': projected.area,
            'source_polygon_area_m2': source.area, 'missing_outside_EPS_band_m2': missing,
            'extra_outside_EPS_band_m2': extra, 'complete_boundary_hausdorff_m': boundary,
            'actual_projection_polygon_world': list(projected.exterior.coords)[:-1],
            'actual_projection_holes_world': [list(r.coords)[:-1] for r in projected.interiors],
            'all_actual_triangles_projection_area_m2': full_projection.area,
            'all_actual_triangles_missing_outside_EPS_band_m2': full_missing,
            'all_actual_triangles_extra_outside_EPS_band_m2': full_extra,
            'all_actual_triangles_boundary_hausdorff_m': full_boundary,
            'EPS_m': EPS, 'AREA_EPS_m2': AREA_EPS, 'full_domain_not_bbox_or_point_sample': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe-session', type=int, required=True)
    parser.add_argument('--probe-exit-code', type=int, required=True)
    parser.add_argument('--actual-sha256', required=True)
    args = parser.parse_args()
    assert args.probe_session > 0 and args.probe_exit_code == 0
    output = HERE / 'registered-buildings.json'
    assert not output.exists()
    actual_file = HERE / 'actual-source-actors.json'
    assert sha(actual_file) == args.actual_sha256
    actual, request = read(actual_file), read(HERE / 'source-probe-requests.json')
    source_file = ROOT / 'work/forbidden-city-research/geospatial/model-data.json'
    model = read(source_file)
    parts = {r['id']: r for r in model['parts']}
    facts_file = ROOT / 'work/restoration-v18/research/nansansuo/facts-v2.json'
    assert sha(facts_file) == '741024f7e7eaa0471485d7403847c7dae0e4c876b0b98ddb230c0f6a2dc09bb5'
    facts = read(facts_file)
    plan = read(HERE / 'qualified-plan-and-gate-analysis.json')
    preview = read(HERE / 'registered-geometry-preview.json')
    assert sha(COORDINATES) == preview['source_coordinate_helper_sha256'], 'Frozen coordinate helper changed'
    preview_by = {r['building_id']: r for r in preview['buildings']}
    validate_actual_source(actual, request, model)
    wanted = {'local', 'world', 'frame', 'component'}
    nodes = [n for n in ast.parse(COORDINATES.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert {n.name for n in nodes} == wanted
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(COORDINATES), 'exec'), globals())
    specs = [(row['descriptive_id'] + '_hall', row['source_part_id'], row) for row in facts['qualified_nine_hall_correspondence_candidates']]
    specs.append(('nansansuo_common_gate', facts['common_gate']['source_part_candidate'], facts['common_gate']))
    results, buildings, assemblies = [], [], []
    for bid, sid, fact in specs:
        record = parts[sid]
        source = Polygon(record['polygon'], record['holes'])
        try:
            proof = actual_domain(actual, sid, source)
            results.append({'id': bid, 'input': sid, 'operation': '实际完整底帽投影/孔/边界及闭体正体积',
                            'expected': '固定100µm/1e-7m²内完整匹配source', 'passed': True, 'evidence': proof})
        except AssertionError as exc:
            results.append({'id': bid, 'input': sid, 'operation': '实际完整source域',
                            'expected': '严格通过', 'passed': False, 'reason': str(exc)})
            continue
        geom = component('complete_original_footprint', source, 'south', square=False)
        for key in ['anchor', 'rotation_z_rad', 'source_polygon_world', 'source_holes_world',
                    'source_polygon_local', 'source_holes_local', 'study_body_width_m',
                    'study_body_depth_m', 'source_containment_proof']:
            assert canonical(geom[key]) == canonical(preview_by[bid][key]), 'Preview/actual study frame drift'
        names = actual['part_actor_mapping'][sid]
        name = '南三所共用宫门' if bid.endswith('common_gate') else '南三所' + {'west': '西', 'middle': '中', 'east': '东'}[fact['column']] + '列' + {'front': '前', 'middle': '中', 'rear': '后'}[fact['row']] + '殿（位置限定）'
        row = {'building_id': bid, 'name_zh': name, 'source_part_id': sid,
               'source_component_id': 'complete_original_footprint', 'original_source_record': record,
               'source_record_sha256': canonical(record), 'original_source_polygon_world': record['polygon'],
               'original_source_holes_world': record['holes'], 'source_polygon_world': record['polygon'],
               'source_holes_world': record['holes'], 'source_polygon_local': geom['source_polygon_local'],
               'source_holes_local': geom['source_holes_local'], 'anchor': geom['anchor'],
               'rotation_z_rad': geom['rotation_z_rad'], 'semantic_front': 'negative-y',
               'study_front_cardinal': 'south', 'source_component_geometry': geom,
               'study_body_width_m': geom['study_body_width_m'], 'study_body_depth_m': geom['study_body_depth_m'],
               'source_containment_proof': geom['source_containment_proof'],
               'source_actual_actor_names': names, 'allowed_hidden_source_actor_names': names,
               'qualified_factual_source_fields': fact, 'qualified_semantic_join_evidence': {
                   'facts_file': str(facts_file.relative_to(ROOT)), 'facts_sha256': sha(facts_file),
                   'location_diagram': facts['Sun2020_official_plan'],
                   'complete_source_order_comparison': plan['complete_relative_order_checks'],
                   'source_label_alone_identifies_hall': False, 'current_measured_world_azimuth': None},
               'source_actor_geometry_verified': True, 'actual_complete_projection_proof': proof,
               'historical_individual_name_confirmed': False, 'metric_scope': 'unmeasured_study',
               'source6m_proxy_height_is_real_building_height': False, 'measured_world_azimuth': None,
               'third_party_cost': 0, 'human_approval': 'pending'}
        if bid == 'nansansuo_common_gate':
            row['gate_full_eight_point_contract'] = plan['common_gate']['build_contract']
            row['optional_geometry_split_is_not_used'] = True
        buildings.append(row)
        assemblies.append({'source_part_id': sid, 'original_source_record': record,
                           'source_polygon_world': record['polygon'], 'source_holes_world': record['holes'],
                           'source_actual_actor_names': names, 'allowed_hidden_source_actor_names': names,
                           'components': [{**geom, 'owner_kind': 'building', 'owner_id': bid}],
                           'shared_cutlines': [], 'complete_union_symmetric_difference_m2': 0.0,
                           'complete_boundary_hausdorff_m': 0.0, 'all_source_lobes_owned': True,
                           'source_actor_geometry_verified': True})
    summary = {'passed': sum(r['passed'] for r in results), 'failed': sum(not r['passed'] for r in results)}
    write('actual-source-domain-checks-01.json', {'schema': 'v18-ten-actual-source-full-domain-checks/1',
          'summary': summary, 'results': results, 'readout_sha256': args.actual_sha256,
          'native_sha256': actual['native_sha256'], 'root_actual_probe_terminal': {'session': args.probe_session, 'exit_code': 0},
          'all_13995_old_meshes_and_2845_original_sources_unchanged': True,
          'Blender_started': False, 'source_dimensions_are_field_measurements': False})
    assert summary == {'passed': 10, 'failed': 0}, 'Actual source red preserved; no registration output'
    inputs = [source_file, facts_file, actual_file, HERE / 'candidate-inventory.json', HERE / 'source-probe-requests.json',
              HERE / 'probe_current_native.py', HERE / 'full-mesh-state-guard.json', HERE / 'durable-state-guard.json',
              HERE / 'qualified-plan-and-gate-analysis.json', HERE / 'actual-source-domain-checks-01.json',
              HERE / 'registered-geometry-preview.json',
              COORDINATES, Path(__file__)]
    doc = {'schema': 'v18-nine-qualified-halls-and-common-gate-source-registration/1',
           'base_native_sha256': actual['native_sha256'],
           'base_manifest_sha256': '467f34ba527d32ee428e203e6a381dbcae46eb27e9f559cf8179e8d4cad828fd',
           'base_mesh_count': 13995, 'original_source_mesh_count': 2845,
           'source_files_sha256': {str(p.relative_to(ROOT)): sha(p) for p in inputs},
           'buildings': buildings, 'source_assemblies': assemblies, 'context_components': [],
           'allowed_hidden_source_actor_names': sorted({name for r in buildings for name in r['allowed_hidden_source_actor_names']}),
           'all_other_61_review_enclosure_source_footprints_and_all_neighbours_retained': True,
           'source_walls_are_not_hide_permissions': True,
           'component_polygon_field_contract': 'Every target owns its complete original source polygon/holes. Gate retains all eight points; no half is discarded or named an annex.',
           'native_probe_session': args.probe_session, 'native_probe_terminal_exit_code': 0,
           'native_opened_by_this_script': False, 'native_saved': False, 'geometry_created': False,
           'profiles_written': False, 'third_party_cost': 0, 'paid_service_calls': 0,
           'human_approval': 'pending', 'whole_city_complete': False}
    write('registered-buildings.json', doc)
    print(json.dumps({'buildings': len(buildings), 'summary': summary, 'registry_sha256': sha(output)}), flush=True)


if __name__ == '__main__':
    main()
