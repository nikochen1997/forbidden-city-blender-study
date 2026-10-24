"""Seven captured reference domains and three whole source assemblies, CPU only."""
import hashlib
import json
from pathlib import Path
import sys

from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, unary_union

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_stage_world_source as C

ROOT = HERE.parents[2]
REGISTRY_PATH = ROOT / 'work/restoration-v17/registration/registered-buildings.json'
REGISTRY_SHA = '0ff859b0e1434e9ee1c0501aa2f301fd6b8416e85e32a5c2b525f9e3c18479bc'


def mesh_world(mesh):
    m = dict(mesh)
    if 'hidden' not in m:
        if 'visibility' in m:
            v = m['visibility']
            m['hidden'] = bool(v['hide_render'] or v['hide_viewport'] or v['hide_get'])
        else:
            # Legacy factory hall readouts exported geometry only. This internal
            # cap adapter does not infer display state; visibility is separately audited.
            m['hidden'] = False
            m['display_state_not_reported_in_source_geometry'] = True
    return m


def shared_boundary(expected_line, first, second):
    length = expected_line.length
    C.need(length > .01, 'shared edge must be a real finite source cutline')
    interior = LineString([expected_line.interpolate(.001).coords[0],
                           expected_line.interpolate(length-.001).coords[0]])
    window = interior.buffer(.0003, cap_style=2)
    a = first.boundary.intersection(window)
    b = second.boundary.intersection(window)
    C.need(not a.is_empty and not b.is_empty, 'actual shared-edge boundary missing')
    C.need(interior.difference(a.buffer(.0001)).is_empty
           and interior.difference(b.buffer(.0001)).is_empty, 'shared-edge boundary does not cover complete interior')
    pair_distance = a.hausdorff_distance(b)
    C.need(pair_distance <= .0001, 'two actual shared-edge boundaries differ by over100um')
    endpoint_distances = []
    for xy in expected_line.coords:
        pa = nearest_points(Point(xy), first.boundary)[1]
        pb = nearest_points(Point(xy), second.boundary)[1]
        distance = pa.distance(pb)
        C.need(distance <= .0001, 'actual shared-edge endpoints differ by over100um')
        endpoint_distances.append(distance)
    return {'actual_pair_boundary_hausdorff_m': pair_distance,
            'actual_pair_endpoint_distances_m': endpoint_distances,
            'interior_trim_m': .001, 'full_endpoints_checked_separately': True,
            'fixed_tolerance_m': .0001}


def check(doc):
    C.need(C.digest(REGISTRY_PATH) == REGISTRY_SHA, 'frozen source registry changed')
    C.need(doc['coordinate_space'] == 'WORLD', 'direct WORLD readout required')
    registry = C.read(REGISTRY_PATH)
    wanted = {(s['source_part_id'], c['component_id']): c
              for s in registry['source_assemblies'] for c in s['components']}
    C.need(len(wanted) == 7, 'registered complete seven-component contract changed')
    actual = {}
    component_evidence = []
    for row in doc['buildings']:
        p = row['profile']
        key = p['source_part_id'], p['source_component_id']
        C.need(key in wanted and key not in actual, 'building source ownership missing/duplicated')
        mesh = mesh_world(row['geometry'][row['reference_floor']])
        d = p['dimensions']
        top = p['anchor'][2] + d['floor_z_m']
        bottom = p['anchor'][2] + d.get('slab_bottom_z_m', d.get('source_reference_slab_bottom_z_m'))
        source = C.polygon(wanted[key]['source_polygon_world'], wanted[key]['source_holes_world'])
        domains = C.mesh_domains(mesh, top, bottom)
        proof = {k: C.compare_domains(source, value, str(key) + ' ' + k) for k, value in domains.items()}
        actual[key] = domains['complete_mesh_XY_projection']
        component_evidence.append({'source_part_id': key[0], 'component_id': key[1], 'checks': proof})
    for row in doc['context_components']:
        p = row['component']
        key = p['source_part_id'], p['component_id']
        C.need(key in wanted and key not in actual, 'context source ownership missing/duplicated')
        mesh = mesh_world(row['geometry'][row['reference_floor']])
        top = .35 if key[1] == 'source_middle_neck' else 6
        source = C.polygon(wanted[key]['source_polygon_world'], wanted[key]['source_holes_world'])
        domains = C.mesh_domains(mesh, top, 0)
        proof = {k: C.compare_domains(source, value, str(key) + ' ' + k) for k, value in domains.items()}
        actual[key] = domains['complete_mesh_XY_projection']
        component_evidence.append({'source_part_id': key[0], 'component_id': key[1], 'checks': proof})
    C.need(set(actual) == set(wanted), 'not all seven complete actual source components supplied')
    assemblies = []
    for assembly in registry['source_assemblies']:
        sid = assembly['source_part_id']
        keys = [(sid, c['component_id']) for c in assembly['components']]
        expected = C.polygon(assembly['source_polygon_world'], assembly['source_holes_world'])
        united = unary_union([actual[k] for k in keys])
        # Topology stays strict: a narrow open crack is not hidden by the distance budget.
        union_proof = C.compare_domains(expected, united, sid + ' complete original source assembly')
        cutlines = []
        for row in assembly['shared_cutlines']:
            line = LineString(row['endpoints_world'])
            owners = [k for k in keys if line.difference(C.polygon(wanted[k]['source_polygon_world'],
                      wanted[k]['source_holes_world']).boundary.buffer(1e-8)).is_empty]
            C.need(len(owners) == 2, 'each complete shared cutline must have exactly two owners')
            proof = shared_boundary(line, actual[owners[0]], actual[owners[1]])
            cutlines.append({'owners': [k[1] for k in owners], 'endpoints_world': row['endpoints_world'], **proof})
        assemblies.append({'source_part_id': sid, 'component_count': len(keys),
                           'complete_union': union_proof, 'actual_shared_boundaries': cutlines})
    return {'schema': 'v17-seven-component-three-source-assembly-CPU/1', 'passed': True,
            'component_count': 7, 'original_source_assembly_count': 3,
            'components': component_evidence, 'assemblies': assemblies,
            'fixed_tolerance_m': .0001, 'checker_sha256': C.digest(__file__),
            'source_registry_sha256': REGISTRY_SHA,
            'readout_scope': doc.get('schema'),
            'saved_native_verified': doc.get('saved_native_read_only') is True,
            'visibility_state_proven_by_this_checker': False,
            'private_or_factory_readout_is_saved_native_proof': False,
            'builder_imported': False, 'Blender_launched': False,
            'official_measurements_or_whole_city_complete': False}
