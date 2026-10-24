"""Local V17 reference contexts. No native I/O, rendering or source mutation."""
import json
import math
import sys
from pathlib import Path

import bpy

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import forbidden_city_geometry as F
import imperial_monuments as M


def prism(name, outer, holes, low, high, collection, material, role):
    assert high > low
    rings = [F._clean_ring(outer)] + [F._clean_ring(r) for r in holes]
    surface = F._Surface()
    for triangle in F._triangulate_rings(rings):
        surface.face([(x, y, high) for x, y in triangle])
    F._volume_from_top(surface, low)
    obj = F._object(name, F._new_mesh(name + '_mesh', surface.vertices, surface.faces, material), collection, role)
    obj['restoration_v17_context'] = True
    obj['absolute_accuracy_claim'] = False
    obj['human_approval'] = 'pending'
    obj['third_party_cost'] = 0
    obj['metric_scope'] = 'unmeasured reference geometry, not archaeological dimensions'
    return obj


def build_components(registry, collection, materials):
    """Retain every registered remainder, with true open N/S neck ends."""
    records = []
    assert {c['component_id'] for c in registry['context_components']} == {
        'source_middle_neck', 'source_south_wide_body', 'source_north_baoxia'}
    for component in registry['context_components']:
        ident = component['owner_id']
        ring, holes = component['source_polygon_world'], component['source_holes_world']
        objects = []
        if component['component_id'] == 'source_middle_neck':
            floor = prism('R17_' + ident + '_floor', ring, holes, 0, .35,
                          collection, materials['white_stone'], 'reference_passage_floor')
            objects.append(floor)
            assert not holes, 'Neck clipping requires the registered hole-free convex polygon'
            clip_ring = list(ring)
            if F._ring_area(clip_ring) < 0:
                clip_ring.reverse()
            center = component['anchor'][:2]
            for i, (start, end) in enumerate(component['source_side_edges_world']):
                a, b = start, end
                dx, dy = b[0]-a[0], b[1]-a[1]
                length = math.hypot(dx, dy)
                assert length > .18
                nx, ny = -dy/length, dx/length
                if nx*(center[0]-(a[0]+b[0])/2) + ny*(center[1]-(a[1]+b[1])/2) < 0:
                    nx, ny = -nx, -ny
                inside_a = [a[0]+nx*.18, a[1]+ny*.18]
                inside_b = [b[0]+nx*.18, b[1]+ny*.18]
                wall_ring = [list(a), list(b), list(inside_b), list(inside_a)]
                for first, second in zip(clip_ring, clip_ring[1:]+clip_ring[:1]):
                    ex, ey = second[0]-first[0], second[1]-first[1]
                    plane = (-ey, ex, ey*first[0]-ex*first[1])
                    assert all(sum(k*v for k, v in zip(plane, [*p, 1])) >= -1e-8 for p in clip_ring), 'Registered neck must remain convex'
                    wall_ring = F._clip_halfplane(wall_ring, plane, tolerance=0)
                objects.append(prism('R17_' + ident + '_side_' + str(i), wall_ring, [], .35, 4.88,
                                     collection, materials['grey'], 'unmeasured_reference_passage_side'))
            cap = prism('R17_' + ident + '_overhead_reference', ring, holes, 4.88, 5.10,
                        collection, materials['grey'], 'unknown_roof_thin_reference_cap')
            cap['actual_historical_roof_type'] = 'unknown'
            cap['not_certified_flat_roof'] = True
            objects.append(cap)
        else:
            floor = prism('R17_' + ident, ring, holes, 0, 6,
                          collection, materials['grey'], 'retained_source_proxy_remainder')
            floor['source_6m_proxy_height_is_measured'] = False
            objects.append(floor)
        for obj in objects:
            obj['context_owner_id'] = ident
            obj['context_source_part_id'] = component['source_part_id']
            obj['context_source_component_id'] = component['component_id']
        records.append({'component': component, 'objects': [o.name for o in objects],
                        'reference_floor': floor.name, 'source_geometry_preserved': 'pending independent actual-world CPU',
                        'metric_values_measured': False, 'roof_category_proven': False})
    return records


def build_front_entry(binding, original, front_result, collection):
    """Single-user display copy with an applied finite reference passage."""
    assert binding['source_positive_orientation_requires_reversal'] is False
    assert original.name == binding['original_object'] and original.type == 'MESH'
    assert original.parent is None and not original.modifiers
    assert original.get('source_building_id')
    expected = binding['expected_front_opening_control']
    actual = next(row for row in front_result['openings'] if row['id'] == expected['id'])
    for key in ('id', 'wall_side', 'bay_index', 'kind'):
        assert actual[key] == expected[key], 'Actual front door differs: ' + key
    for key in ('clear_width_m', 'clear_height_m', 'bottom_z_m'):
        assert abs(actual[key] - expected[key]) < 1e-10, 'Actual front control differs: ' + key
    root = front_result['root']
    frame = binding['front_frame']
    assert max(abs(root.location[i] - frame['anchor'][i]) for i in range(3)) < 1e-4
    assert abs(root.rotation_euler.z - frame['rotation_z_rad']) < 1e-7
    name = binding['replacement_object']
    assert name not in bpy.data.objects
    obj = original.copy()
    obj.data = original.data.copy()
    obj.name = name
    collection.objects.link(obj)
    assert obj.data.users == 1 and obj.data is not original.data
    del obj['source_building_id']
    obj['semantic_role'] = binding['clone_identity_contract']['new_clone_semantic_role']
    obj['context_source_object'] = original.name
    obj['context_source_part_id'] = binding['source_part_id']
    obj['restoration_v17_context'] = True
    obj['third_party_cost'] = 0
    obj['absolute_accuracy_claim'] = False
    obj['human_approval'] = 'pending'
    obj['not_archaeological_door_measurement'] = True
    obj.hide_render = False
    obj.hide_viewport = False
    obj.hide_set(False)
    cutter_spec = binding['cutter']
    c, s = math.cos(frame['rotation_z_rad']), math.sin(frame['rotation_z_rad'])
    x, y, z = cutter_spec['center_local']
    center = (frame['anchor'][0] + c*x - s*y, frame['anchor'][1] + s*x + c*y, z + frame['anchor'][2])
    cutter = F.box('R17_TEMP_FRONT_CONTEXT_CUTTER', center,
                   (cutter_spec['width_m'], cutter_spec['depth_m'], cutter_spec['height_m']),
                   None, collection, None, 'temporary_context_reference_cutter')
    cutter.rotation_euler.z = frame['rotation_z_rad']
    cutter_data = cutter.data
    bpy.context.view_layer.update()
    M._apply_cutter(obj, cutter, 'R17_CONTEXT_EXACT_REFERENCE_PASSAGE')
    if cutter_data.users == 0:
        bpy.data.meshes.remove(cutter_data)
    obj['applied_reference_passage'] = json.dumps(binding['cutter'], ensure_ascii=False)
    assert obj.data.users == 1 and not obj.modifiers and 'source_building_id' not in obj
    return {'object': obj.name, 'original_object': original.name,
            'binding': binding, 'actual_front_opening_record': actual,
            'metric_values_measured': False, 'independent_actual_geometry_verified': False}
