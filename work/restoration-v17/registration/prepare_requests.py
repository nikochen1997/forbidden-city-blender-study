"""V17完整来源登记，只写小型JSON；不导入Blender或修改冻结输入。"""
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MODEL = ROOT / 'work/forbidden-city-research/geospatial/model-data.json'
NATIVE = ROOT / 'outputs/紫禁城现存格局-慈宁花园惠风第十六阶段/紫禁城现存格局-慈宁花园惠风第十六阶段.blend'
TARGETS = [
    ('shufang_named_compound', 'way-40632242-p0', '漱芳斋', 'named_H_outline_not_three_independent_source_actors'),
    ('theatre_named_compound', 'way-40632241-p0', '戏台', 'named_T_outline_may_include_stage_and_south_house_not_90m2_footprint'),
    ('front_court_U_source', 'way-42353090-p0', None, 'unnamed_U_source_not_independent_identified_east_west_halls'),
    ('west_rear_rectangle_candidate', 'way-40632236-p0', None, 'source_only_no_ear_room_identity'),
    ('west_rear_fivepoint_candidate', 'way-40632235-p0', None, 'source_only_no_west_rear_wing_identity'),
    ('east_attachment_candidate', 'way-42353094-p0', None, 'source_only_unidentified_attachment'),
    ('north_outbuilding_candidate', 'way-42311944-p0', None, 'source_only_unidentified_separate_building'),
    ('baohua_named_candidate', 'way-40627498-p0', '宝华殿', 'read_only_source_for_independent_Baohua_fact_agent_no_profile'),
]
PARTITIONS = {
    'way-40632242-p0': [('source_north_lobe', [0, 1, 2, 9, 10, 11]),
                         ('source_middle_neck', [2, 3, 8, 9]),
                         ('source_south_lobe', [3, 4, 5, 6, 7, 8])],
    'way-40632241-p0': [('source_north_projection', [0, 9, 10, 11]),
                         ('source_south_wide_body', list(range(10)))],
}
CUTS = {'way-40632242-p0': [[2, 9], [3, 8]], 'way-40632241-p0': [[0, 9]]}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(4194304), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def local(point, anchor, theta):
    x, y = point[0] - anchor[0], point[1] - anchor[1]
    c, s = math.cos(theta), math.sin(theta)
    return [c*x+s*y, -s*x+c*y]


def frame(poly):
    ring = list(poly.minimum_rotated_rectangle.exterior.coords)[:-1]
    edges = [(math.dist(a, b), a, b) for a, b in zip(ring, ring[1:] + ring[:1])]
    width, a, b = max(edges, key=lambda row: row[0])
    theta = math.atan2(b[1]-a[1], b[0]-a[0])
    while theta > math.pi/2:
        theta -= math.pi
    while theta <= -math.pi/2:
        theta += math.pi
    anchor = [poly.centroid.x, poly.centroid.y, 0.0]
    return {'anchor': anchor, 'rotation_z_rad': theta,
            'geometric_long_axis_m': width, 'geometric_short_axis_m': min(e[0] for e in edges),
            'polygon_local': [local(p, anchor, theta) for p in list(poly.exterior.coords)[:-1]],
            'holes_local': [[local(p, anchor, theta) for p in list(h.coords)[:-1]] for h in poly.interiors],
            'semantic_front': None, 'measured_world_azimuth': None,
            'scope': 'Unmeasured source coordinate frame only. MRR is not replacement geometry or historical frontage.'}


def partition(record):
    if record['id'] not in PARTITIONS:
        return None
    original = Polygon(record['polygon'], record.get('holes', []))
    rows = []
    for ident, indices in PARTITIONS[record['id']]:
        points = [record['polygon'][i] for i in indices]
        shape = Polygon(points)
        rows.append({'component_id': ident, 'original_vertex_indices': indices,
                     'polygon_world': points, 'holes_world': [], 'source_frame': frame(shape),
                     'area_source_units_m2': shape.area, 'official_entity_id': None,
                     'semantic_front': None, 'identity_status': 'geometric_component_only_not_historical_identity'})
    shapes = [Polygon(row['polygon_world']) for row in rows]
    combined = unary_union(shapes)
    return {'source_part_id': record['id'], 'components': rows,
            'cuts': [{'original_vertex_indices': indices, 'endpoints_world': [record['polygon'][i] for i in indices]}
                     for indices in CUTS[record['id']]],
            'full_source_symmetric_difference_m2': combined.symmetric_difference(original).area,
            'full_source_boundary_hausdorff_m': combined.boundary.hausdorff_distance(original.boundary),
            'pairwise_overlap_area_m2': sum(a.intersection(b).area for i, a in enumerate(shapes) for b in shapes[i+1:]),
            'holes_preserved': len(combined.interiors) == len(original.interiors),
            'native_geometry_verified': False, 'historical_component_identity_confirmed': False,
            'stage_90m2_used_for_boundary_or_scale': False}


def write(name, doc):
    with (HERE/name).open('x') as stream:
        json.dump(doc, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    xml_path = MODEL.parent / 'osm-map-complete.xml'
    manifest_path = NATIVE.parent / 'restoration-manifest.json'
    ledger_path = ROOT / 'work/whole-city-coverage/coverage-gap-ledger-v16-accepted.json'
    facts_dir = ROOT / 'work/restoration-v17/research/shufang'
    facts = json.loads((facts_dir/'facts.json').read_text())
    freeze = json.loads((facts_dir/'freeze-receipt.json').read_text())
    assert all(sha(facts_dir/row['path']) == row['sha256'] for row in freeze['files'])
    assert sha(MODEL) == '06dfa30cbd6401d2b555b842c03dd47fa055a4de6024b4904b39cc2652a2248e'
    assert sha(NATIVE) == '2d020dc62347fbaa84ec7466f40f2ddc9d2fa755c007ac7fc043ef6fd3d0aeb9'
    assert sha(manifest_path) == 'fd71595462662aa7f8bc24d61c0fda229ea39960c2c5b5484bd79eee43a48ead'
    manifest = json.loads(manifest_path.read_text())
    ledger = json.loads(ledger_path.read_text())
    assert manifest['scene_mesh_count'] == 13683 and manifest['original_source_mesh_count'] == 2845
    assert ledger['whole_city_objective_complete'] is False
    model = json.loads(MODEL.read_text())
    parts = {row['id']: row for row in model['parts']}
    shapes = {sid: Polygon(row['polygon'], row.get('holes', [])) for sid, row in parts.items()}
    raw = ET.parse(xml_path).getroot()
    ways = {way.attrib['id']: way for way in raw.findall('way')}
    nodes = {node.attrib['id']: node.attrib for node in raw.findall('node')}
    selected = {row[1] for row in TARGETS}
    near = {sid for sid, shape in shapes.items() if any(shape.distance(shapes[target]) <= 15 for target in selected)} - selected
    rows = []
    for ident, sid, name, note in TARGETS:
        record, poly = parts[sid], shapes[sid]
        assert poly.is_valid and record['name'] == name
        way = ways[record['osm_id']]
        refs = [node.attrib['ref'] for node in way.findall('nd')]
        tags = {tag.attrib['k']: tag.attrib['v'] for tag in way.findall('tag')}
        assert refs[0] == refs[-1] and tags == record['original_tags']
        rows.append({'target_id': ident, 'source_part_id': sid, 'source_record': record,
                     'source_record_sha256': canonical(record),
                     'source_polygon_world': record['polygon'], 'source_holes_world': record.get('holes', []),
                     'source_frame': frame(poly), 'source_geometry_partition': partition(record),
                     'raw_osm_way': {'id': record['osm_id'], 'node_ids': refs,
                                     'node_lonlat': [[float(nodes[n]['lon']), float(nodes[n]['lat'])] for n in refs], 'tags': tags},
                     'qualification': note, 'allowed_hidden_source_actor_names': [],
                     'official_entity_identity': None, 'historical_identity_confirmed': False,
                     'source_height_is_measured': False, 'native_actor_names_verified': False})
    shufang_ids = selected - {'way-40627498-p0'}
    area = unary_union([shapes[sid] for sid in selected]).buffer(15)
    context = {}
    for layer in ['inner_walls', 'water_polygons', 'path_polygons', 'paths', 'waterway_lines', 'landcover_polygons']:
        context[layer] = [record for record in model[layer]
                          if (Polygon(record['polygon'], record.get('holes', [])) if 'polygon' in record else LineString(record['points'])).intersects(area)]
    relations = []
    for i, first in enumerate(sorted(shufang_ids)):
        for second in sorted(shufang_ids)[i+1:]:
            a, b = shapes[first], shapes[second]
            relations.append({'source_ids': [first, second], 'distance_m': a.distance(b),
                              'intersection_area_m2': a.intersection(b).area,
                              'shared_boundary': a.boundary.intersection(b.boundary).__geo_interface__,
                              'shared_boundary_length_m': a.boundary.intersection(b.boundary).length,
                              'official_spatial_identity_confirmed': False})
    pins = [MODEL, xml_path, NATIVE, manifest_path, ledger_path, facts_dir/'facts.json',
            facts_dir/'sources.json', facts_dir/'freeze-receipt.json', HERE/'probe_current_native.py', Path(__file__)]
    inputs = {str(path.relative_to(ROOT)): sha(path) for path in pins}
    inventory = {'schema': 'v17-complete-source-ring-candidates/1', 'inputs_sha256': inputs,
                 'instruction_files_found': [], 'instruction_search_scope': 'cwd and every ancestor through /',
                 'model_projection': model['projection'], 'targets': rows,
                 'selected_part_ids': sorted(selected), 'nearby_source_parts': {sid: parts[sid] for sid in sorted(near)},
                 'source_pair_relations': relations, 'external_context_records': context,
                 'facts_spatial_relations': facts['spatial_relations'],
                 'facts_subspaces_not_independent_shells': facts['subspaces_not_independent_shells'],
                 'identity_gaps': ['No official georeferenced current plan join yet.',
                    'Do not swap official front/rear identities using source lobe aspect ratio or bay counts.',
                    'Named theatre T source may include south house; 90m2 is approximate stage surface, never footprint or scale.',
                    'U-shaped unnamed source does not independently identify east/west three-room flank halls or veranda.',
                    'Rear west rectangle/wing, east attachment and north outbuilding remain unnamed source candidates.',
                    'Indoor Fengyacuns small stage stays inside rear hall; never instantiate as second outdoor theatre.'],
                 'native_probe_status': 'pending_not_executed', 'allowed_hidden_source_actor_names': [],
                 'context_selection_buffer_m': 15, 'selection_buffer_is_not_generated_geometry_or_boundary': True,
                 'source_license': 'OpenStreetMap contributors ODbL source context, not Palace Museum measured survey.',
                 'native_opened': False, 'native_saved': False, 'geometry_created': False,
                 'third_party_cost': 0, 'paid_service_calls': 0, 'human_approval': 'pending', 'whole_city_complete': False}
    write('candidate-inventory.json', inventory)
    inventory_path = HERE/'candidate-inventory.json'
    request = {'schema': 'v17-readonly-current-V16-probe-request/1',
               'inputs_sha256': {**inputs, str(inventory_path.relative_to(ROOT)): sha(inventory_path)},
               'native_file': str(NATIVE), 'expected_mesh_count': 13683, 'expected_source_mesh_count': 2845,
               'selected_part_ids': sorted(selected), 'nearby_source_part_ids': sorted(near),
               'source_record_sha256': {sid: canonical(parts[sid]) for sid in sorted(selected | near)},
               'scope': 'One pending readonly V16 native open; full raw/evaluated geometry and metadata for targets AND neighbouring parts; all durable IDs; no save/render/producer import.'}
    write('source-probe-requests.json', request)
    assert all(sha(ROOT/path) == value for path, value in inputs.items())
    print(json.dumps({'targets': len(rows), 'nearby_parts': len(near), 'native_probe_status': 'pending_not_executed',
                      'inventory_sha256': sha(inventory_path), 'request_sha256': sha(HERE/'source-probe-requests.json'),
                      'probe_sha256': sha(HERE/'probe_current_native.py')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
