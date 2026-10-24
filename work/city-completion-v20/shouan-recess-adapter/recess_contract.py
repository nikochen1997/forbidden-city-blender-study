"""Private-fixture-only plan. No Blender, source visibility or production entry."""
import copy
import math


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_geometry_profile(p):
    require(p['building_id'] == 'shouangong' and p['source_part_id'] == 'way-40624979-p0', 'exact Shouan source/type required')
    require(p['occupied_storeys'] is None and type(p['reference_floor_count']) is int and p['reference_floor_count'] == 1,
            'reference floor is not occupied-storey evidence')
    require(p['human_approval'] == 'pending', 'human approval remains pending')
    for key in ('third_party_cost', 'paid_service_calls'):
        require(type(p[key]) is int and p[key] == 0, key + ' must be integer zero')
    require(p['bays_x'] == 5 and p['bays_y'] == 3 and p['eaves_tiers'] is None and p['study_eaves_tiers'] == 1,
            'documentary bays and unknown eave count must be preserved')
    require(len(p['roof_tiers']) == 1 and p['roof_tiers'][0]['roof_type'] == 'xieshan', 'one caller xieshan study shell required')
    schedule = p['facades']['south']['schedule']
    require([r['kind'] for r in schedule] == ['window', 'window', 'door', 'window', 'window'] and
            [r['leaf_count'] for r in schedule] == [None, None, 4, None, None], 'exact front categories and four central leaf references required')
    d = p['dimensions']
    require(abs(d['enclosure_y_min_m'] + d['body_depth_m']/2) < 1e-9 and d['veranda_front_depth_m'] == 0,
            'a full-width veranda cannot substitute the central recess')
    for axis, key in (('x', 'body_width_m'), ('y', 'body_depth_m')):
        spans = p['column_bay_widths_' + axis + '_m']
        require(len(spans) == (5 if axis == 'x' else 3) and all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in spans) and
                abs(sum(spans)-d[key]) < 1e-6, 'explicit positive private bay spans required')
    return p


def validate_private(p, intent):
    require(intent == 'private_fixture', 'private fixture cannot be used for production')
    validate_geometry_profile(p)
    require(p['preparation_scope'] == 'private_fixture' and p['production_use_allowed'] is False, 'private scope cannot be promoted')
    require(p['source_geometry_qualification'] == 'pending' and p['source_actor_geometry_verified'] is False and
            p['historical_identity_confirmed'] is False and not p['source_actual_actor_names'], 'production/source registration is not supplied by this adapter')
    require(not p['allowed_hidden_source_actor_names'] and not p['source_assemblies_approved_for_replacement'], 'no old source hide/replacement authorization')
    require(p['requires_central_recess_caller_adapter'] is True, 'central recess caller requirement missing')
    return p


def plan_geometry(p):
    validate_geometry_profile(p)
    d = p['dimensions']; structural_x = [-d['body_width_m']/2]
    for span in p['column_bay_widths_x_m']:
        structural_x.append(structural_x[-1]+span)
    indices = p.get('enclosure_column_indices_x')
    if indices is None:
        lo, hi = d['enclosure_x_min_m'], d['enclosure_x_max_m']
        xs = [lo+(hi-lo)*i/5 for i in range(6)]
    else:
        require(len(indices) == 6, 'five complete enclosure bays required')
        xs = [structural_x[i] for i in indices]
    front = d['enclosure_y_min_m']; setback = p['column_bay_widths_y_m'][0]
    rear = front + setback; t = d['wall_thickness_m']; x0, x1 = xs[2:4]
    # Bounds are construction controls only, not a substitute for source rings.
    walls = {
        'south_west_two_bays': [d['enclosure_x_min_m']-t/2, front-t/2, x0+t/2, front+t/2],
        'south_east_two_bays': [x1-t/2, front-t/2, d['enclosure_x_max_m']+t/2, front+t/2],
        'recessed_central_bay': [x0-t/2, rear-t/2, x1+t/2, rear+t/2],
        'return_west': [x0-t/2, front-t/2, x0+t/2, rear+t/2],
        'return_east': [x1-t/2, front-t/2, x1+t/2, rear+t/2],
    }
    return {'scope': 'caller_owned_new_geometry_only', 'production_qualification_granted_by_adapter': False,
            'front_y': front, 'central_y': rear, 'setback_m_private_study': setback,
            'central_bay': [x0, x1], 'wall_bounds_local': walls,
            'wall_for_bay': ['south_west_two_bays', 'south_west_two_bays', 'recessed_central_bay',
                             'south_east_two_bays', 'south_east_two_bays'],
            'additional_roof_closure_segments': ['recessed_central_bay', 'return_west', 'return_east'],
            'reference_floor_count': 1, 'new_occupied_floors': 0,
            'occupied_storeys': None, 'old_source_operations': [],
            'metric_status': 'unmeasured caller-owned study; no qualification granted',
            'metric_source_profile_scope': p.get('preparation_scope', 'caller_supplied_profile'),
            'documentary_front_recess_bays': 1, 'documentary_front_central_leaf_count': 4,
            'known_facts': copy.deepcopy(p['known_facts'])}
