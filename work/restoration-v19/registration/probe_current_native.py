"""One read-only accepted-V18 source probe. Root runs Blender serially.

Complete raw/evaluated target and neighbour data, strict original source IDs,
and before/after fingerprints of all current accepted meshes. No save, render or builder.
"""
from array import array
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from probe_contract import validate_request, is_original_source_mesh


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4194304), b''):
            h.update(block)
    return h.hexdigest()


def write(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        stream.write('\n')


def load_functions(relative, expected, wanted):
    path = ROOT / relative
    assert sha(path) == expected
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert {n.name for n in nodes} == wanted
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), globals())
    return path


H1 = load_functions('work/restoration-v8/module-research/copy-boolean/test_copy_boolean.py',
    '57e52b7bddf5de246a3b31e3c2c2916ed07bbfeda579104d0bf11d741907e2ed',
    {'safe', 'digest', 'mesh_digest', 'material_digest', 'slots', 'source_fingerprints'})
H2 = load_functions('work/restoration-v12/registration/probe_saved_v11.py',
    '001745cdd60cac927eb248304a84ee550ab291810bde7e359115afb2e9cc404c',
    {'visibility', 'bounds', 'evaluated', 'record_actor', 'material_record', 'durable_state', 'guard_rows', 'durable_guard'})
H3 = load_functions('work/build_forbidden_city_restoration_v15.py',
    '9fe1cf52edcf77508c2271ec150d58a7e79266ee09ebd2c664e8f553296935b1',
    {'mesh_relations', 'nonmesh_state', 'camera_state'})


def identifiers(obj):
    found = set()
    for key in ['source_building_id', 'osm_part_id', 'source_reference_part_id', 'source_part_id', 'source_record', 'derived_original_source_record']:
        value = obj.get(key)
        if key.endswith('source_record'):
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    continue
            if hasattr(value, 'get') and value.get('id'):
                found.add(str(value['id']))
        elif value:
            found.add(str(value))
    return found


def all_durable_ids():
    result = {}
    for prop in bpy.data.bl_rna.properties:
        if prop.type != 'COLLECTION':
            continue
        values = [{'name': value.name_full, 'type': value.bl_rna.identifier,
                   'library': value.library.filepath if value.library else None,
                   'custom_properties_sha256': digest(dict(value.items()))}
                  for value in getattr(bpy.data, prop.identifier) if isinstance(value, bpy.types.ID)]
        result[prop.identifier] = sorted(values, key=lambda row: (row['type'], row['name']))
    return result


def all_layer_state():
    def row(layer):
        return {'collection': layer.collection.name, 'exclude': bool(layer.exclude),
                'hide_viewport': bool(layer.hide_viewport), 'is_visible': bool(layer.is_visible),
                'holdout': bool(layer.holdout), 'indirect_only': bool(layer.indirect_only),
                'children': [row(child) for child in layer.children]}
    return [{'scene': scene.name, 'name': view.name, 'use': bool(view.use),
             'collections': row(view.layer_collection)} for scene in bpy.data.scenes for view in scene.view_layers]


def complete_actor(obj):
    actor = record_actor(obj)
    actor.update(object_type=obj.type, data_name=obj.data.name_full,
                 raw_mesh_sha256=mesh_digest(obj.data),
                 raw_world_vertices=[list(obj.matrix_world @ v.co) for v in obj.data.vertices],
                 raw_edges=[list(edge.vertices) for edge in obj.data.edges],
                 evaluated_material_slots=slots(obj.evaluated_get(bpy.context.evaluated_depsgraph_get())),
                 matrix_basis=safe(obj.matrix_basis), matrix_parent_inverse=safe(obj.matrix_parent_inverse),
                 children=sorted(o.name for o in obj.children),
                 relations=mesh_relations(obj), data_users=obj.data.users,
                 same_data_object_names=sorted(o.name for o in bpy.data.objects if o.type == 'MESH' and o.data == obj.data),
                 all_source_identifiers=sorted(identifiers(obj)))
    # Preserve the full actual minimum-Z cap, including all separate components.
    # CPU union of these triangles will classify outer/inner rings independently;
    # source_record polygon/holes are separately exported and never substituted.
    actor['actual_projected_bottom_cap_triangles_world'] = actor['bottom_world_triangles']
    actor['actual_cap_outer_hole_classification'] = 'pending_independent_complete_triangle_union_CPU'
    return actor


def main():
    assert all(not (HERE / name).exists() for name in
               ['actual-source-actors.json', 'full-mesh-state-guard.json', 'durable-state-guard.json'])
    request_file = HERE / 'source-probe-requests.json'
    request = json.loads(request_file.read_text())
    native = Path(request['native_file'])
    manifest_file = ROOT / request['accepted_manifest_file']
    assert sha(manifest_file) == request['accepted_manifest_sha256'], 'Accepted manifest SHA differs'
    assert request['inputs_sha256'][str(native.relative_to(ROOT))] == request['native_sha256'], 'Native pin coverage differs'
    manifest = json.loads(manifest_file.read_text())
    inputs = {**request['inputs_sha256'], str(request_file.relative_to(ROOT)): sha(request_file),
              str(Path(__file__).relative_to(ROOT)): sha(__file__),
              **{str(path.relative_to(ROOT)): sha(path) for path in [H1, H2, H3]}}
    assert all(sha(ROOT / name) == expected for name, expected in inputs.items()), 'Input changed before open'
    model = json.loads((ROOT / 'work/forbidden-city-research/geospatial/model-data.json').read_text())
    parts = {row['id']: row for row in model['parts']}
    walls = {row['id']: row for row in model['inner_walls']}
    validate_request(request, model, manifest)
    for sid, expected in request['source_record_sha256'].items():
        assert hashlib.sha256(json.dumps(parts[sid], sort_keys=True, separators=(',', ':')).encode()).hexdigest() == expected
    for sid, expected in request['source_wall_record_sha256'].items():
        assert hashlib.sha256(json.dumps(walls[sid], sort_keys=True, separators=(',', ':')).encode()).hexdigest() == expected
    assert bpy.ops.wm.open_mainfile(filepath=str(native), load_ui=False, use_scripts=False) == {'FINISHED'}
    bpy.context.view_layer.update()
    meshes = sorted((obj for obj in bpy.context.scene.objects if obj.type == 'MESH'), key=lambda o: o.name)
    assert len(meshes) == request['expected_mesh_count']
    assert sum(bool(obj.get('source_building_id')) for obj in meshes) == request['expected_source_mesh_count'] == 2845
    assert not bpy.data.libraries
    ids_before, durable_before, layer_before = all_durable_ids(), durable_state(), all_layer_state()
    relations_before = {obj.name: mesh_relations(obj) for obj in meshes}
    nonmesh_before = {obj.name: nonmesh_state(obj) for obj in bpy.data.objects if obj.type != 'MESH'}
    cameras_before = {obj.name: camera_state(obj) for obj in bpy.data.objects if obj.type == 'CAMERA'}
    assert len(cameras_before) == request['expected_camera_count'], 'Actual camera population differs'
    before = source_fingerprints(meshes, 'V19-before-all-' + str(request['expected_mesh_count']))
    sids = request['selected_part_ids'] + request['nearby_source_part_ids'] + request['anchor_part_ids']
    assert len(sids) == len(set(sids))
    metadata_ids = {obj.name: identifiers(obj) for obj in bpy.context.scene.objects}
    reference_mapping = {sid: sorted(name for name, ids in metadata_ids.items() if sid in ids) for sid in sids}
    mapping = {sid: [name for name in names if is_original_source_mesh(bpy.data.objects[name], sid)]
               for sid, names in reference_mapping.items()}
    assert all(mapping.values()), 'Missing strictly original source mesh'
    assert all(len(mapping[sid]) == 1 and bpy.data.objects[mapping[sid][0]].get('semantic_role') == 'osm_part_body'
               for sid in request['selected_part_ids']), 'Selected exact original body actor differs'
    reference_evidence = {}
    actors = {}
    for sid, names in reference_mapping.items():
        for name in names:
            obj = bpy.data.objects[name]
            reference_evidence[name] = {'name': name, 'object_type': obj.type,
                'custom_properties': safe(dict(obj.items())), 'all_source_identifiers': sorted(identifiers(obj)),
                'is_original_source_mesh_for_matched_ID': is_original_source_mesh(obj, sid),
                'reference_is_not_hide_permission': True, 'matrix_world': safe(obj.matrix_world),
                'parent': obj.parent.name if obj.parent else None, 'visibility': visibility(obj)}
        for name in mapping[sid]:
            obj = bpy.data.objects[name]
            raw = obj.get('source_record')
            raw = json.loads(raw) if isinstance(raw, str) else safe(raw)
            assert raw == parts[sid], 'Original source record differs: ' + name
            actor = complete_actor(obj)
            actor.update(source_record=raw, source_record_sha256=request['source_record_sha256'][sid],
                         complete_source_polygon_world=parts[sid]['polygon'],
                         complete_source_holes_world=parts[sid].get('holes', []),
                         source_geometry_and_actual_mesh_are_separate_evidence=True)
            actors[name] = actor
        print('V19_SOURCE', sid, mapping[sid], flush=True)
    wall_mapping = {}
    for sid in request['source_wall_line_ids']:
        name = '院墙_' + sid
        obj = bpy.data.objects.get(name)
        assert obj and obj.type == 'MESH' and not obj.get('source_building_id'), 'Wrong original wall actor'
        refs = obj.get('source_refs')
        refs = json.loads(refs) if isinstance(refs, str) else safe(refs)
        assert refs == walls[sid]['source_refs'], 'Original wall refs differ'
        actor = complete_actor(obj)
        actor.update(source_wall_record=walls[sid], source_wall_record_sha256=request['source_wall_record_sha256'][sid],
                     complete_source_line_world=walls[sid]['points'], not_a_building_source=True)
        actors[name] = actor
        wall_mapping[sid] = name
    context_mapping = {}
    for row in request['context_surface_requests']:
        layer, sid, name = row['layer'], row['source_id'], row['recipe_actor_name']
        source = next(r for r in model[layer] if r['id'] == sid)
        obj = bpy.data.objects.get(name)
        assert obj and obj.type == 'MESH' and not obj.get('source_building_id'), 'Wrong context recipe actor: ' + name
        refs = obj.get('source_refs')
        refs = json.loads(refs) if isinstance(refs, str) else safe(refs)
        assert refs == source['source_refs'], 'Context source refs differ: ' + name
        if layer == 'paths':
            assumptions = obj.get('assumptions')
            assumptions = json.loads(assumptions) if isinstance(assumptions, str) else safe(assumptions)
            assert assumptions == source['assumptions'], 'Path source assumptions differ'
        else:
            assert obj.get('representation') == 'mapped_polygon_with_provisional_surface_material', 'Wrong garden surface recipe'
        actor = complete_actor(obj)
        actor.update(source_context_layer=layer, source_context_record=source,
                     source_context_record_sha256=row['source_record_sha256'],
                     not_a_building_source=True, recipe_name_and_source_refs_verified=True,
                     architectural_route_or_measured_boundary_identity_confirmed=False)
        if layer == 'paths':
            actor.update(complete_source_points_world=source.get('source_points', source['points']),
                         processed_display_points_world=source['points'],
                         mapped_path_is_not_verified_bridge_or_doorway=True)
        else:
            actor.update(complete_source_polygon_world=source['polygon'],
                         complete_source_holes_world=source.get('holes', []),
                         mapped_garden_polygon_is_not_terrain_or_official_survey=True)
        actors[name] = actor
        context_mapping[sid] = {'layer': layer, 'actor': name}
        print('V19_CONTEXT', layer, sid, name, flush=True)
    after = source_fingerprints(meshes, 'V19-after-all-' + str(request['expected_mesh_count']))
    assert before == after, 'An old raw/evaluated mesh, material, transform, metadata or visibility changed'
    assert relations_before == {obj.name: mesh_relations(obj) for obj in meshes}
    assert nonmesh_before == {obj.name: nonmesh_state(obj) for obj in bpy.data.objects if obj.type != 'MESH'}
    assert cameras_before == {obj.name: camera_state(obj) for obj in bpy.data.objects if obj.type == 'CAMERA'}
    assert durable_before == durable_state() and ids_before == all_durable_ids() and layer_before == all_layer_state()
    assert len([obj for obj in bpy.context.scene.objects if obj.type == 'MESH']) == request['expected_mesh_count']
    assert sum(bool(obj.get('source_building_id')) for obj in meshes) == 2845
    assert all(sha(ROOT / name) == expected for name, expected in inputs.items()), 'Input/native changed after probe'
    write('full-mesh-state-guard.json', {'schema': 'v19-readonly-all-current-mesh-guard/1',
          'scene_mesh_count': len(meshes), 'source_mesh_count': 2845, 'all_before_after_fields_equal': True,
          'coverage_fields': list(before[0]['parts']), 'rows': guard_rows(before, after),
          'before_sha256': digest(before), 'after_sha256': digest(after),
          'all_mesh_relations_equal': True, 'all_nonmesh_equal': True, 'all_cameras_including_DOF_equal': True})
    write('durable-state-guard.json', {'schema': 'v19-readonly-all-durable-ID-state-guard/1',
          'before_sha256': digest(durable_before), 'after_sha256': digest(durable_state()),
          'all_full_values_equal': True, 'sections': durable_guard(durable_before, durable_state()),
          'all_durable_id_inventory': ids_before, 'all_layer_states': layer_before})
    materials = {slot[1] for actor in actors.values() for slot in actor['actual_material_slots'] if slot[1]}
    write('actual-source-actors.json', {'schema': 'v19-readonly-accepted-V18-actual-source-actors/1',
          'input_files_sha256': inputs, 'native_file': str(native), 'native_sha256': request['native_sha256'],
          'native_mesh_count': request['expected_mesh_count'], 'original_source_mesh_count': 2845,
          'native_camera_count': len(cameras_before), 'actual_camera_count_verified': True,
          'part_actor_mapping': mapping, 'source_wall_actor_mapping': wall_mapping,
          'source_context_actor_mapping': context_mapping,
          'metadata_reference_mapping': reference_mapping, 'metadata_reference_evidence': reference_evidence,
          'requested_target_part_ids': request['selected_part_ids'],
          'requested_nearby_part_ids': request['nearby_source_part_ids'], 'position_anchor_part_ids': request['anchor_part_ids'],
          'actor_evidence': actors, 'material_evidence': {name: material_record(bpy.data.materials[name]) for name in sorted(materials)},
          'all_mesh_raw_evaluated_fields_unchanged': True, 'all_relations_and_durable_states_unchanged': True,
          'open_mainfile_calls': 1, 'use_scripts': False, 'native_saved': False,
          'geometry_created': False, 'renderer_called': False, 'producer_imported': False,
          'old_actor_visibility_changed': False, 'individual_hall_identity_confirmed': False,
          'source_heights_are_current_field_measurements': False, 'third_party_cost': 0,
          'paid_service_calls': 0, 'human_approval': 'pending', 'whole_city_complete': False})
    print('V19_READONLY_PROBE_COMPLETE', len(mapping), len(wall_mapping), len(context_mapping), len(actors), request['expected_mesh_count'], 'UNCHANGED', flush=True)


if __name__ == '__main__':
    main()
