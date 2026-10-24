"""CPU-only G14 caller profiles for two V19 halls; no native or visibility I/O.

Full source rings remain the floor domain. Rectangles below are controls fitted
inside that domain, never replacements for the source geometry or measurements.
"""
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

from shapely.geometry import Polygon, box
from shapely.ops import triangulate, unary_union

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TARGETS = {'juanqinzhai': 'way-1341826246-p0', 'yucuixuan': 'way-40629263-p0'}
PINS = {
    'work/courtyard_hall_buildings.py': '5123db7be8948e9bdb4dc6d8edb712d01ad98075e5e6a40251be5aa8f666a86d',
    'work/four_hall_buildings.py': '1d3267d25946ecf468da3a9d60103ef522c202452f60d0e500643d14ce9dcc1a',
    'work/restoration_buildings.py': 'aac18ca8c219b8de544dd78d8a7b99000a4d0fe83d40553614065e0c998aaf60',
    'work/forbidden_city_geometry.py': '23f815fc93057a0f69b66adc25536485fc05a33935f67fb1613073963e276efc',
    'work/restoration-v18/prepare_profiles_v1.py': 'c3994b2054fbe186f5be6263be121c67bb0fbbccc811062f31cb25fa4accc770',
    'work/build_forbidden_city_restoration_v18.py': '91fbadf405d1acc33eae9f9c25dcc136f7996747878c33a0f2abd763008329b9',
    'work/restoration-v19-preparation/facts-and-candidates.json': '1cd2f810ab3f910fa282abd46702eafc10e8c4d052311c89155f4e3954812f58',
    'work/restoration-v19/registration/actual-source-actors.json': '66918efad977a1def89dbf33462ab9549c9fe661a28bb7bdd6d1cc6bf513e96d',
    'work/restoration-v19/registration/actual-source-domain-checks-01.json': '3b9aeb8d72bab47da62f8397a4e3a70c199e60dd158cfd5b10509b20e95e1a33',
    'work/restoration-v19/registration/source-registration-evidence-01.json': '4df276dff1531b5faf09e989bba79a983e6add739a64a2880fb59241ad9a0b23',
    'work/restoration-v19/research/visual-facts-addon-01.json': 'f7fbe89a0459d106f68ca8d7dc308ca07e8ee917d9bcef134348b39b807bc982',
}
FACTS = 'work/restoration-v19-preparation/facts-and-candidates.json'
REGISTRY = 'work/restoration-v19/registration/source-registration-evidence-01.json'
ACTUAL = 'work/restoration-v19/registration/actual-source-actors.json'
DOMAINS = 'work/restoration-v19/registration/actual-source-domain-checks-01.json'
ADDON = 'work/restoration-v19/research/visual-facts-addon-01.json'
RESERVE = .5
ROOF_DECORATION_BUDGET = .09


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(relative):
    return json.loads((ROOT / relative).read_text())


def verify_inputs(pins=None):
    for relative, expected in (PINS if pins is None else pins).items():
        require(sha(ROOT / relative) == expected, 'Frozen input drift: ' + relative)


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def ast_functions(relative, names, scope):
    source = ROOT / relative
    nodes = [node for node in ast.parse(source.read_text()).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    require({node.name for node in nodes} == set(names), 'Frozen CPU interface changed')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)
    return SimpleNamespace(**{name: scope[name] for name in names})


def cpu_triangles(rings):
    """CPU geometry adapter only; not Blender's tessellator or runtime evidence."""
    domain = Polygon(rings[0], rings[1:])
    require(domain.is_valid and domain.area > 0, 'Invalid complete source domain')
    triangles = [t for t in triangulate(domain) if domain.covers(t)]
    require(domain.symmetric_difference(unary_union(triangles)).area <= 1e-8,
            'CPU tessellation omitted source area or holes')
    return [list(t.exterior.coords)[:-1] for t in triangles]


def frozen_g14_cpu_validator():
    # Execute the unchanged G14 validation AST. Only its planar tessellator uses
    # a named CPU adapter; imports, build_hall, bpy and native I/O are not run.
    f = ast_functions('work/forbidden_city_geometry.py',
                      ('_number', '_point', '_clean_ring', '_ring_area', '_clip_halfplane'),
                      {'math': math})
    f._triangulate_rings = cpu_triangles
    h = ast_functions('work/four_hall_buildings.py', ('_finite',), {'math': math})
    return ast_functions('work/courtyard_hall_buildings.py',
                         ('_count', '_axis_grid', '_enclosure_grid', '_upper_grid',
                          '_rectangle_outside_area', '_validate'),
                         {'math': math, 'F': f, 'H': h, 'SIDES': ('south', 'north', 'east', 'west')})


def source_domain(profile):
    domain = Polygon(profile['source_polygon_local'], profile['source_holes_local'])
    require(domain.is_valid and domain.area > 0, 'Invalid source domain')
    return domain


def fit_controls(row):
    domain = Polygon(row['source_polygon_local'], row['source_holes_local'])
    require(domain.is_valid and domain.area > 0, 'Invalid full registered source')
    xmin, ymin, xmax, ymax = domain.bounds
    # Bounds seed the search, but every accepted domain uses exact full-polygon
    # covers including holes. A bbox alone can never satisfy this test.
    width = 2 * min(-xmin, xmax) - 2 * RESERVE
    depth = 2 * min(-ymin, ymax) - 2 * RESERVE
    require(width > 0 and depth > 0, 'Source has no positive centered control seed')
    scale = 1.0
    while not domain.covers(box(-width * scale / 2 - RESERVE,
                               -depth * scale / 2 - RESERVE,
                               width * scale / 2 + RESERVE,
                               depth * scale / 2 + RESERVE)):
        scale *= .999
        require(scale > .25, 'Complete source cannot host this study safely')
    return width * scale, depth * scale


def unresolved_facades(count):
    item = {'kind': 'unresolved_wall', 'leaf_count': None, 'pattern_category': None,
            'category_scope': 'unknown_enclosure_reference_not_a_historic_solid_wall_fact'}
    return {side: {'schedule': [dict(copy.deepcopy(item), bay_index=i) for i in range(count)]}
            if side in ('south', 'north') else copy.deepcopy(item)
            for side in ('south', 'north', 'east', 'west')}


def prepare_profile(row, entity, addon):
    ident = row['candidate_building_id']
    require(ident in TARGETS and row['source_part_id'] == TARGETS[ident], 'Wrong exact hall identity')
    require(row['original_typed_factual_source_fields'] == entity['fields'], 'Facts drifted in source evidence')
    require(row['source_actor_geometry_verified'] is True, 'Source actor geometry is not verified')
    require(row['source_height6_is_real_building_height'] is False, 'Source proxy height promoted')
    width, depth = fit_controls(row)
    fields = copy.deepcopy(entity['fields'])
    p = {key: copy.deepcopy(row[key]) for key in
         ('name_zh', 'source_part_id', 'source_polygon_world', 'source_holes_world',
          'source_polygon_local', 'source_holes_local', 'anchor', 'rotation_z_rad',
          'source_actual_actor_names', 'original_source_record', 'source_record_sha256',
          'source_actor_geometry_verified', 'actual_complete_projection_proof',
          'frame_local_negative_y_reference_cardinal', 'documentary_facing',
          'frame_method', 'metric_scope', 'measured_world_azimuth')}
    p.update(building_id=ident, builder='hall', occupied_storeys=None,
             bays_x=fields['bays_x']['value'], bays_y=None, study_bays_x=fields['bays_x']['value'],
             study_bays_y=1, eaves_tiers=None, study_eaves_tiers=1,
             reference_floor_count=1, reference_support_id=None,
             facing=fields['facing']['value'], human_approval='pending',
             historical_identity_confirmed=False, allowed_hidden_source_actor_names=[],
             source_assemblies_approved_for_replacement=[], source6m_proxy_height_is_real_building_height=False,
             third_party_cost=0, paid_service_calls=0, generated_geometry_verified=False,
             complete_reconstruction_proven=False)
    p['original_typed_factual_source_fields'] = fields
    p['typed_factual_source_fields'] = copy.deepcopy(fields)
    p['known_facts'] = {key: copy.deepcopy(value['value']) for key, value in fields.items()}
    p['qualified_visual_reference'] = copy.deepcopy(addon['entities'][ident])
    p['registration_file'], p['registration_sha256'] = REGISTRY, PINS[REGISTRY]
    p['dimensions'] = {
        'body_width_m': width, 'body_depth_m': depth, 'floor_z_m': .35,
        'source_reference_slab_bottom_z_m': 0, 'source_reference_slab_top_z_m': .35,
        'slab_thickness_m': .35, 'wall_thickness_m': .18,
        'column_radius_m': .15, 'column_base_radius_m': .25, 'column_base_height_m': .15,
        'column_top_z_m': 4.37, 'beam_width_m': .34, 'beam_height_m': .28,
        'wall_top_z_m': 4.65, 'enclosure_x_min_m': -width / 2 + .09,
        'enclosure_x_max_m': width / 2 - .09,
        'enclosure_y_min_m': -depth / 2 + 1.10,
        'enclosure_y_max_m': depth / 2 - .09,
        'veranda_front_depth_m': 1.10, 'veranda_rear_depth_m': .09,
        'veranda_west_depth_m': .09, 'veranda_east_depth_m': .09,
        'door_height_m': 2.95, 'window_height_m': 1.90,
        'window_sill_height_above_floor_m': .85,
        'door_width_fraction_of_bay': .65, 'window_width_fraction_of_bay': .67,
        'opening_frame_width_m': .07, 'opening_frame_depth_m': .12,
        'leaf_panel_depth_m': .05,
    }
    p['roof_tiers'] = [{
        'tier_index': 0, 'roof_type': fields['roof_type']['value'],
        'outer_width_m': width if ident == 'juanqinzhai' else width + .55,
        'outer_depth_m': depth + .55, 'eave_z_m': 5.45, 'top_z_m': 7.45,
        'corner_lift_m': 0 if ident == 'juanqinzhai' else .12,
        'additional_overhang_m': 0, 'annular': False,
        'inner_width_m': None, 'inner_depth_m': None,
    }]
    p['material_scheme'] = {key: 'grey' for key in
                            ('base', 'column', 'beam', 'wall', 'frame', 'infill', 'roof_under')}
    p['material_scheme'].update(roof_main=fields['roof_main_colour']['value'],
                                roof_edge='yellow' if ident == 'juanqinzhai' else 'green')
    p['facades'] = unresolved_facades(p['bays_x'])
    if ident == 'juanqinzhai':
        # Local +X is east for the source-bound south-facing reference frame.
        # East five bays are indices 4..8; no opening is inferred for west four.
        for index in range(4, 9):
            p['facades']['south']['schedule'][index].update(
                kind='door' if index == 6 else 'window',
                pattern_category=None if index == 6 else 'bubujin_zhizhai_windows',
                category_scope='DPM-JUANQIN east-five bay category only; one study aperture per qualified bay; physical aperture census and all leaf counts unknown')
    p['parameter_evidence'] = {
        'all_metric_parameters': {'status': 'unmeasured_study',
                                 'numeric_dimensions': copy.deepcopy(p['dimensions']),
                                 'numeric_roof_controls': copy.deepcopy(p['roof_tiers']),
                                 'equal_bay_spans_are_study_only': True,
                                 'source6m_proxy_height_used': False,
                                 'current_field_measurement': False},
        'reference_frame': {'status': 'unmeasured_study',
                            'origin_and_rotation': 'complete source geometry registration only; not measured current world datum/azimuth',
                            'negative_y_cardinal_reference': row['frame_local_negative_y_reference_cardinal'],
                            'yucui_east_is_qualified_plan_inference_only': ident == 'yucuixuan',
                            'documentary_facing_unchanged': fields['facing']['value']},
        'eaves_tiers': {'factual': None, 'study_shell_count': 1, 'status': 'unmeasured_study'},
        'front_veranda': {'published_category': True, 'depth_m': 1.10, 'status': 'unmeasured_study'},
        'source_control_domains': {'body_all_side_reserve_m': RESERVE,
                                   'roof_decorative_half_extent_budget_m': ROOF_DECORATION_BUDGET,
                                   'proof': 'exact Polygon.covers of entire rectangles including holes; no sample/bbox domain substitute',
                                   'roof_budget_basis': 'frozen G14 gable tube radii <=.06m; R hip tube radii <=.065m; .09m conservative budget; closed skins shift Z only',
                                   'actual_generated_all_triangle_domain_test_required': True},
        'unknown_inert_opening_dimensions': {'status': 'required_API_controls_only',
                                             'unresolved_wall_produces_no_aperture': True},
        'colors_and_finishes': {'status': 'unmeasured_study',
                                'category_only': 'official green/yellow roof allocation; neutral grey for unqualified surfaces'},
    }
    p['unbuilt'] = [
        'Current measured dimensions, datum, azimuth, exact unequal bay spans, roof curve and tile details',
        'Actual occupied storeys, eave-tier census, all exact leaf counts, open states, joinery and exact lattice geometry',
        'All unqualified facade holes and through-route/destination verification',
        'Interiors, concealed roof structure, measured historic platform and physical tile cavity',
        'Gallery/rock/mountain/wall connections and their independent source binding',
    ]
    if ident == 'juanqinzhai':
        p['unbuilt'].append('West-four stage, east-five xianlou, Suzhou painting and curved wall/octagonal gate: facts retained, no dimensions invented')
    else:
        p['unbuilt'].append('Three interior rooms, Dexianshi/Buddhist-room fitout, north passage/gallery and south rocks/steps: facts retained, geometry unresolved')
    return p


def control_domains(profile):
    d, roof = profile['dimensions'], profile['roof_tiers'][0]
    w, dep = d['body_width_m'], d['body_depth_m']
    margin = max(d['column_base_radius_m'], d['beam_width_m'] / 2, d['wall_thickness_m'] / 2)
    return {
        'complete_source_floor_domain': source_domain(profile),
        'body_support_beam_wall_and_frame_envelope': box(-w / 2 - margin, -dep / 2 - margin, w / 2 + margin, dep / 2 + margin),
        'full_body_control_reserve': box(-w / 2 - RESERVE, -dep / 2 - RESERVE, w / 2 + RESERVE, dep / 2 + RESERVE),
        'whole_roof_skin_ridge_tile_envelope': box(-roof['outer_width_m'] / 2 - ROOF_DECORATION_BUDGET,
                                                 -roof['outer_depth_m'] / 2 - ROOF_DECORATION_BUDGET,
                                                 roof['outer_width_m'] / 2 + ROOF_DECORATION_BUDGET,
                                                 roof['outer_depth_m'] / 2 + ROOF_DECORATION_BUDGET),
    }


def validate_profile(profile, row, fields, validator):
    validator._validate(profile)
    require(profile['building_id'] in TARGETS and profile['source_part_id'] == TARGETS[profile['building_id']], 'Hall binding differs')
    require(profile['original_typed_factual_source_fields'] == fields == profile['typed_factual_source_fields'], 'Typed facts/nulls promoted')
    require(profile['known_facts'] == {key: value['value'] for key, value in fields.items()}, 'Known facts promoted')
    for key in ('source_polygon_local', 'source_polygon_world', 'source_holes_local', 'source_holes_world', 'anchor', 'rotation_z_rad', 'original_source_record', 'source_record_sha256'):
        require(profile[key] == row[key], 'Full source/frame replaced: ' + key)
    require(canonical(profile['original_source_record']) == profile['source_record_sha256'], 'Original source record digest differs')
    require(profile['facing'] == fields['facing']['value'] and profile['bays_y'] is None and profile['eaves_tiers'] is None, 'Unknown fact promoted')
    require(profile['source6m_proxy_height_is_real_building_height'] is False, '6m proxy height promoted')
    require(not profile['allowed_hidden_source_actor_names'] and not profile['source_assemblies_approved_for_replacement'], 'Visibility or replacement release invented')
    require(all(item['leaf_count'] is None for side, facade in profile['facades'].items()
                for item in (facade['schedule'] if side in ('south', 'north') else [facade])), 'Unknown leaf count promoted')
    expected = [('south', i, 'door' if i == 6 else 'window') for i in range(4, 9)] if profile['building_id'] == 'juanqinzhai' else []
    actual = [(side, item.get('bay_index', 0), item['kind']) for side, facade in profile['facades'].items()
              for item in (facade['schedule'] if side in ('south', 'north') else [facade])
              if item['kind'] in ('door', 'window', 'passage')]
    require(actual == expected, 'Qualified facade aperture categories differ')
    domain = source_domain(profile)
    proof = {}
    for name, control in control_domains(profile).items():
        require(domain.covers(control), 'Complete control projection leaves source or crosses a hole: ' + name)
        proof[name] = {'area_m2': control.area, 'outside_source_area_m2': control.difference(domain).area,
                       'exact_complete_domain_covers': True}
    c, s = math.cos(profile['rotation_z_rad']), math.sin(profile['rotation_z_rad'])
    pairs = [(profile['source_polygon_local'], profile['source_polygon_world'])] + list(zip(profile['source_holes_local'], profile['source_holes_world']))
    for local, world in pairs:
        require(len(local) == len(world), 'Source ring vertex count differs')
        require(all(math.dist((profile['anchor'][0] + c*x - s*y, profile['anchor'][1] + s*x + c*y), p) < 1e-8
                    for (x, y), p in zip(local, world)), 'Complete ring frame round trip differs')
    return proof


def make_package():
    verify_inputs()
    facts, registry, actual, domains, addon = map(read, (FACTS, REGISTRY, ACTUAL, DOMAINS, ADDON))
    require(domains['summary'] == {'passed': 6, 'failed': 0}, 'Actual full-domain input is not green')
    require(domains['readout_sha256'] == PINS[ACTUAL], 'Actual probe readout differs')
    require(registry['base_native_sha256'] == actual['native_sha256'] == domains['native_sha256'], 'Actual source native identity differs')
    require(registry['allowed_hidden_source_actor_names'] == registry['source_assemblies_approved_for_replacement'] == [], 'Input replacement permissions changed')
    rows = {row['candidate_building_id']: row for row in registry['candidate_buildings'] if row['candidate_building_id'] in TARGETS}
    require(set(rows) == set(TARGETS), 'Two exact candidate hall rows required')
    validator = frozen_g14_cpu_validator()
    profiles, checks = [], []
    for ident in TARGETS:
        row, fields = rows[ident], facts['entities'][ident]['fields']
        require(row['source_actual_actor_names'] == actual['part_actor_mapping'][TARGETS[ident]], 'Actual source actor binding differs')
        p = prepare_profile(row, facts['entities'][ident], addon)
        proof = validate_profile(p, row, fields, validator)
        checks.append({'building_id': ident, 'passed': True, 'input': 'frozen actual V18 source + documentary typed fields',
                       'operation': 'unchanged G14 validation AST with named CPU planar adapter; complete domains and all-ring round trip',
                       'expected': 'direct build_hall-compatible study controls, complete source-floor domain, unknowns preserved',
                       'full_control_domains': proof, 'actual_generated_geometry_checked': False})
        profiles.append(p)
    source = ast.parse((ROOT / 'work/forbidden_city_geometry.py').read_text())
    colors = next(ast.literal_eval(n.value) for n in source.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'PALETTE' for t in n.targets))
    palette = {'schema': 'v19-two-hall-caller-palette/1',
               'materials': {key: {'rgba': [*colors[key][0], 1], 'metallic': colors[key][1], 'roughness': colors[key][2],
                                   'numeric_status': 'unmeasured_study'} for key in ('grey', 'green', 'yellow')},
               'source_files_sha256': {'work/forbidden_city_geometry.py': PINS['work/forbidden_city_geometry.py']},
               'scope': 'Official roof color categories; numeric RGB/finish unmeasured_study; all unqualified surfaces neutral grey',
               'third_party_cost': 0, 'paid_service_calls': 0, 'human_approval': 'pending'}
    inputs = {**PINS, str(Path(__file__).relative_to(ROOT)): sha(__file__)}
    doc = {'schema': 'v19-two-source-qualified-G14-hall-caller-profiles/1', 'buildings': profiles,
           'source_files_sha256': inputs, 'source_files': inputs,
           'builder_contract': {'module': 'work/courtyard_hall_buildings.py',
                                'call': 'G.build_hall(profile, collection, materials, mesh_cache)',
                                'profile_building_ids': list(TARGETS), 'materials_source': 'palette-v1.json',
                                'shared_support_object': None,
                                'source_floor_behavior': 'G14 triangulates full source_polygon_local and all source_holes_local; exactly one reference slab',
                                'runtime_boolean_and_contact_validation_pending': True},
           'source_reference_floors_complete_original_shapes': True,
           'facts_are_not_metric_survey': True, 'actual_generated_geometry_verified': False,
           'native_opened': False, 'native_saved': False, 'Blender_started': False,
           'old_actor_visibility_changed': False, 'third_party_cost': 0, 'paid_service_calls': 0,
           'historical_identity_release': False, 'human_approval': 'pending', 'whole_city_objective_complete': False}
    return doc, palette, checks


def main():
    paths = [HERE / name for name in ('building-profiles-v1.json', 'palette-v1.json', 'preparation-math-report-01.json')]
    require(not any(path.exists() for path in paths), 'Preserve prior preparation output; no overwrite')
    doc, palette, checks = make_package()
    write_new(paths[0], doc)
    write_new(paths[1], palette)
    write_new(paths[2], {'schema': 'v19-two-hall-CPU-preparation/1', 'summary': {'passed': len(checks), 'failed': 0},
                         'checks': checks, 'source_files_sha256': doc['source_files_sha256'],
                         'profile_sha256': sha(paths[0]), 'palette_sha256': sha(paths[1]),
                         'scope': 'CPU interface and complete control domains only; no new Blender mesh, Boolean/contact, render or native assertion',
                         'Blender_started': False, 'native_saved': False, 'third_party_cost': 0,
                         'paid_service_calls': 0, 'human_approval': 'pending', 'whole_city_objective_complete': False})
    verify_inputs()
    print(json.dumps({'profiles': sha(paths[0]), 'palette': sha(paths[1]),
                      'CPU_profile_checks_passed': len(checks), 'Blender_started': False,
                      'third_party_cost': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
