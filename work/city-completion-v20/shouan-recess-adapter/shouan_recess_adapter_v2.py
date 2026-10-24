"""New-object-only G14 caller v2: replacement-wall Booleans near the origin.

No native I/O, production registration, render or source visibility operation.
Existing roof, four original closures, side/north walls, floor and column/beam
meshes stay byte-identical. The front closure remains on the full front beam;
three new closures close the recessed central wall and its two return walls.
"""
import copy
import hashlib
import json

import bpy
from mathutils import Matrix, Vector

import courtyard_hall_buildings as G
import forbidden_city_geometry as F
import northern_court_towers as T

from recess_contract import plan_geometry, require, validate_private


def _matrix_rows(matrix):
    return tuple(tuple(float(value) for value in row) for row in matrix)


def _cut_near_origin(wall, schedule, collection, root, replacement_wall_pointers):
    """Only a newly created replacement wall may temporarily leave its root.

    Keep the building-local basis near the origin while frozen F applies its
    Exact Boolean. The cutter inherits wall.parent=None. Restore all original
    parent transforms in finally, including a failing modifier application.
    """
    require(wall.as_pointer() in replacement_wall_pointers and wall.parent == root,
            'near-origin Boolean is limited to this caller new replacement walls')
    parent = wall.parent
    basis, inverse = wall.matrix_basis.copy(), wall.matrix_parent_inverse.copy()
    saved_basis, saved_inverse = _matrix_rows(basis), _matrix_rows(inverse)
    try:
        wall.parent = None
        wall.matrix_parent_inverse = Matrix.Identity(4)
        wall.matrix_basis = basis
        bpy.context.view_layer.update()
        result = F.cut_opening(wall, schedule, collection)
    finally:
        wall.parent = parent
        wall.matrix_parent_inverse = inverse
        wall.matrix_basis = basis
        bpy.context.view_layer.update()
        require(wall.parent == parent and _matrix_rows(wall.matrix_basis) == saved_basis and
                _matrix_rows(wall.matrix_parent_inverse) == saved_inverse,
                'near-origin Boolean failed to restore exact parent/basis/parent inverse')
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def object_signature(obj):
    return digest({'name': obj.name, 'vertices': [list(v.co) for v in obj.data.vertices],
                   'faces': [list(f.vertices) for f in obj.data.polygons],
                   'material_indices': [f.material_index for f in obj.data.polygons],
                   'materials': [m.name if m else None for m in obj.data.materials],
                   'matrix_basis': [list(r) for r in obj.matrix_basis],
                   'parent': obj.parent.name if obj.parent else None,
                   'visibility': [obj.hide_viewport, obj.hide_get(), obj.hide_render],
                   'properties': {k: str(obj[k]) for k in obj.keys()}})


def build_private_shouan(profile, collection, materials, mesh_cache=None, *, intent,
                          observe_generated=None):
    """Build only a reviewed private fixture; observer is read-only test evidence."""
    validate_private(profile, intent)
    before = {o.as_pointer() for o in bpy.data.objects}
    result = G.build_hall(profile, collection, materials, mesh_cache)
    if observe_generated is not None:
        observe_generated(result)
    result = recess_geometry(result, before, materials)
    result['build_intent'] = 'private_fixture'
    result['manifest']['build_intent'] = 'private_fixture'
    result['root']['caller_build_intent'] = 'private_fixture'
    return result


def recess_geometry(result, new_object_scope, materials):
    """Adapt one new result; caller must capture object pointers before G14 build.

    This lower geometry API grants no historical/source/production qualification.
    A qualified production caller must separately bind its own input evidence.
    """
    owned = {o.as_pointer() for o in result['objects']}
    created = {o.as_pointer() for o in bpy.data.objects} - set(new_object_scope)
    require(created == owned | {result['root'].as_pointer()}, 'G14 returned inventory differs from this call new objects')
    require(all(o.parent == result['root'] for o in result['objects']), 'every adaptable mesh must belong to this new root')
    p, root, collection = result['profile'], result['root'], result['collection']
    d, spec = p['dimensions'], plan_geometry(p)
    old_wall = result['walls']['south']
    south = [r for r in result['openings'] if r['wall_side'] == 'south']
    require(len(south) == 5 and {r['bay_index'] for r in south} == set(range(5)), 'complete generated front openings required')
    central = next(r for r in south if r['bay_index'] == 2)
    move_names = central['frame_names'] + central['leaf_reference_names'] + central['infill_proxy_names']
    require(len(central['leaf_reference_names']) == 4 and not central['infill_proxy_names'], 'four real generated central leaf-reference meshes required')
    by_name = {o.name: o for o in result['objects']}
    changed_names = set(move_names) | {old_wall.name}
    require(all(by_name[n].as_pointer() in owned for n in changed_names), 'cannot edit any object outside this new G14 result')
    retained = {o.name: object_signature(o) for o in result['objects'] if o.name not in changed_names}
    old_wall_name, old_wall_signature = old_wall.name, object_signature(old_wall)
    source_profile_sha = digest(p)
    wall_material = materials[p['material_scheme']['wall']]

    def add(obj, role):
        obj.parent = root
        for key, value in [('semantic_role', role), ('building_id', p['building_id']),
                           ('restoration_v14_building_id', p['building_id']), ('source_reference_part_id', p['source_part_id']),
                           ('profile_sha256', source_profile_sha), ('third_party_cost', 0), ('human_approval', 'pending'),
                           ('scope', 'unmeasured caller-owned study; no qualification granted')]:
            obj[key] = value
        result['objects'].append(obj); result['components'].setdefault(role, []).append(obj)
        return obj

    new_walls = {}
    for label, (xmin, ymin, xmax, ymax) in spec['wall_bounds_local'].items():
        wall = add(F.box('V20_shouan_' + label, ((xmin+xmax)/2, (ymin+ymax)/2, (d['floor_z_m']+d['wall_top_z_m'])/2),
                         (xmax-xmin, ymax-ymin, d['wall_top_z_m']-d['floor_z_m']), wall_material, collection), 'wall')
        wall['wall_side'], wall['wall_segment'] = 'south_recess', label
        wall['wall_thickness_m'] = d['wall_thickness_m']
        new_walls[label] = wall
    updated = {}
    for old in south:
        record = copy.deepcopy(old); i = record['bay_index']
        wall = new_walls[spec['wall_for_bay'][i]]
        center = list(record['center_local'])
        if i == 2:
            center[1] += spec['setback_m_private_study']
        schedule = {k: record[k] for k in ('id', 'type', 'destination', 'width', 'height', 'depth', 'normal_axis')}
        schedule['center'] = center
        actual = _cut_near_origin(wall, schedule, collection, root,
                                  {o.as_pointer() for o in new_walls.values()})
        record.update(actual); record['center_local'] = center
        record['center_world'] = list(root.matrix_world @ Vector(center))
        record['wall_segment_names'] = [wall.name]
        record['opening_method'] = 'new caller near-origin Exact Boolean on replacement wall; original dimensions and parent transforms preserved'
        if i == 2:
            for name in move_names:
                obj = by_name[name]
                require(obj.as_pointer() in owned and obj.parent == root, 'only caller-owned central frames/leaves may move')
                obj.location.y += spec['setback_m_private_study']
                obj['caller_central_recess_m_private_study'] = spec['setback_m_private_study']
            for name in central['leaf_reference_names']:
                by_name[name]['leaf_pose_scope'] = 'neutral four reference panels; spacing carving opening angle unknown'
            record['leaf_pose'] = 'neutral_unmeasured_reference_not_known_open_state'
        updated[record['id']] = record

    roofs = result['roofs']; require(len(roofs) == 1, 'one private roof required')
    roof = by_name[roofs[0]['roof_object']]
    require(all(abs(roof.matrix_basis[i][j]-Matrix.Identity(4)[i][j]) < 1e-12 for i in range(4) for j in range(4)),
            'contact helper requires actual common local roof frame')
    new_closures = []
    for label in spec['additional_roof_closure_segments']:
        xmin, ymin, xmax, ymax = spec['wall_bounds_local'][label]
        footprint = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
        surface = T._contact_surface(roof, footprint, d['wall_top_z_m'])
        obj = add(F._object('V20_shouan_closure_' + label,
                           F._new_mesh('V20_shouan_recess_closure', surface.vertices, surface.faces, wall_material),
                           collection, 'roof_closure_wall'), 'roof_closure_wall')
        T._fixed(obj)
        obj['roof_contact_object'], obj['wall_side'] = roof.name, label
        obj['roof_tier_index'], obj['closure_bottom_z_m'] = 0, d['wall_top_z_m']
        obj['support_object'] = new_walls[label].name
        obj['support_footprint_local'] = json.dumps(footprint)
        obj['contact_scope'] = 'complete actual downward roof triangles; unmeasured caller-owned closure'
        new_closures.append(obj.name)

    result['objects'] = [o for o in result['objects'] if o != old_wall]
    result['components']['wall'] = [o for o in result['components']['wall'] if o != old_wall]
    result['walls'] = {k: v for k, v in result['walls'].items() if k != 'south'}
    result['walls'].update(new_walls)
    result['openings'] = [updated.get(r['id'], r) for r in result['openings']]
    result['opening_records'] = result['openings']
    require(old_wall.as_pointer() in owned, 'deletion limited to caller new south wall')
    bpy.data.objects.remove(old_wall, do_unlink=True)
    bpy.context.view_layer.update()
    require(all(object_signature(bpy.data.objects[name]) == value for name, value in retained.items()),
            'roof/side/north/floor/column/beam or other preserved new object changed')
    records = {'scope': 'caller_owned_new_geometry_only', 'production_qualification_granted_by_adapter': False,
               'replacement_wall_boolean_frame': 'near origin during frozen F.cut_opening; exact parent/basis/parent inverse restored in finally',
               'plan': spec, 'removed_new_south_wall': old_wall_name,
               'removed_wall_signature': old_wall_signature,
               'new_wall_names': {k: o.name for k, o in new_walls.items()},
               'new_roof_closure_names': new_closures, 'moved_central_frame_leaf_names': move_names,
               'retained_objects_before_sha256': retained,
               'retained_objects_after_sha256': {n: object_signature(bpy.data.objects[n]) for n in retained},
               'south_original_closure_retained_on_full_front_beam': True,
               'original_south_closure_support_proof_pending_full_actual_domain_CPU': True,
               'only_original_new_south_wall_deleted': True, 'old_source_operations': [],
               'occupied_storeys': None, 'additional_reference_or_occupied_floors': 0}
    result['caller_recess_adapter'] = records
    result['manifest']['objects'] = [o.name for o in result['objects']]
    result['manifest']['caller_recess_adapter'] = records
    result['assumptions'].append('Unmeasured caller-owned central recess; geometry adapter grants no source/production qualification, occupied-storey count or historic dimensional claim.')
    root['openings'] = json.dumps(result['openings'], ensure_ascii=False)
    root['assumptions'] = json.dumps(result['assumptions'], ensure_ascii=False)
    root['caller_recess_adapter'] = json.dumps(records, ensure_ascii=False)
    return result
