"""Add ten source-qualified Nansansuo exterior studies to accepted V17.

Root runs this only after the independent actual factory and complete-domain
checks. A saved progress native never grants historical or human approval.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'restoration-v18'))
import forbidden_city_geometry as F
import courtyard_hall_buildings as G
from caller_material_overrides import apply_front_reference_paint
from gate_wall_connections import build_gate_wall_connections
from build_forbidden_city_restoration_v11 import mesh_fingerprint, material_state, visibility
from build_forbidden_city_restoration_v15 import nonmesh_state, mesh_relations, camera_state

BASE = ROOT / 'outputs/紫禁城现存格局-漱芳宝华第十七阶段-配准修正版/紫禁城现存格局-漱芳宝华第十七阶段.blend'
BASE_SHA = '7d20ca54b3e10efb9ad2ea98d750f78530c2e47325d2a0fda4d7002024a25782'
BASE_MANIFEST_SHA = '467f34ba527d32ee428e203e6a381dbcae46eb27e9f559cf8179e8d4cad828fd'
MODEL_NAME = '紫禁城现存格局-南三所第十八阶段.blend'
TARGETS = {'nansansuo_' + group + '_' + row + '_hall'
           for group in ('east', 'middle', 'west') for row in ('front', 'middle', 'rear')}
TARGETS.add('nansansuo_common_gate')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4194304), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(doc, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--readiness', type=Path, required=True)
    parser.add_argument('--readiness-sha256', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    dest = args.output_dir.resolve()
    assert dest.parent == ROOT / 'outputs' and not dest.exists()
    assert sha(BASE) == BASE_SHA and sha(BASE.parent / 'restoration-manifest.json') == BASE_MANIFEST_SHA
    assert sha(args.readiness) == args.readiness_sha256
    ready = read(args.readiness)
    assert ready['schema'] == 'v18-independent-factory-readiness/1'
    assert ready['all_required_actual_factory_and_CPU_checks_passed'] is True
    assert ready['factory_execution']['actual_terminal_exit_code'] == 0
    assert ready['full_domain_CPU_passed'] is True and ready['independent_source_registration_CPU_passed'] is True
    assert ready['gate_context_actual_and_CPU_passed'] is True
    assert type(ready['third_party_cost']) is int and ready['third_party_cost'] == 0
    expected = {str(BASE): BASE_SHA, str(BASE.parent / 'restoration-manifest.json'): BASE_MANIFEST_SHA,
                str(args.readiness.resolve()): args.readiness_sha256, str(Path(__file__).resolve()): sha(__file__)}
    docs = {}
    for role in ('profiles', 'registry', 'palette', 'gate_connections'):
        row = ready[role]
        path = ROOT / row['path']
        assert path.resolve().is_relative_to(ROOT) and sha(path) == row['sha256']
        docs[role] = read(path)
        expected[str(path.resolve())] = row['sha256']
    for source in (ready['input_files_sha256'], docs['profiles']['source_files'],
                   docs['registry']['source_files_sha256'], docs['palette']['source_files_sha256']):
        for rel, digest in source.items():
            path = ROOT / rel
            assert sha(path) == digest, 'Frozen input changed: ' + rel
            expected[str(path.resolve())] = digest
    for relative in ('forbidden_city_geometry.py', 'restoration_buildings.py', 'courtyard_hall_buildings.py',
                     'four_hall_buildings.py', 'build_forbidden_city_restoration_v11.py',
                     'build_forbidden_city_restoration_v15.py', 'restoration-v18/caller_material_overrides.py',
                     'restoration-v18/gate_wall_connections.py'):
        path = HERE / relative
        expected[str(path)] = sha(path)
    profiles = docs['profiles']['buildings']
    registered = {p['building_id']: p for p in docs['registry']['buildings']}
    assert len(profiles) == 10 and {p['building_id'] for p in profiles} == set(registered) == TARGETS
    assert docs['registry']['base_native_sha256'] == BASE_SHA
    assert docs['registry']['base_manifest_sha256'] == BASE_MANIFEST_SHA
    for p in profiles:
        assert p['builder'] == 'hall' and registered[p['building_id']]['source_actor_geometry_verified'] is True
        assert all(p[k] == registered[p['building_id']][k] for k in
                   ('source_part_id', 'source_polygon_world', 'source_holes_world', 'anchor', 'rotation_z_rad'))
        G._validate(p)
    print('V18_PREFLIGHT_OK', flush=True)
    bpy.ops.wm.open_mainfile(filepath=str(BASE), load_ui=False, use_scripts=False)
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    old = {o.name: {'visibility': visibility(o), 'fingerprint': mesh_fingerprint(o)}
           for o in scene.objects if o.type == 'MESH'}
    old_other = {o.name: nonmesh_state(o) for o in bpy.data.objects if o.type != 'MESH'}
    old_mat = {m.name: material_state(m) for m in bpy.data.materials}
    old_rel = {o.name: mesh_relations(o) for o in scene.objects if o.type == 'MESH'}
    old_cam = {o.name: camera_state(o) for o in bpy.data.objects if o.type == 'CAMERA'}
    previous = read(BASE.parent / 'restoration-manifest.json')
    assert len(old) == previous['scene_mesh_count'] == 13995
    assert not bpy.data.libraries and not any(i.source == 'FILE' and not i.packed_file for i in bpy.data.images)
    materials = {}
    keys = {key for p in profiles for key in p['material_scheme'].values()}
    keys.update(p['caller_front_columns_material_key'] for p in profiles if p.get('caller_front_columns_material_key'))
    for key in sorted(keys):
        state = docs['palette']['materials'][key]
        material = bpy.data.materials.new('R18_' + key)
        material.use_nodes = True
        material.diffuse_color = state['rgba']
        material.metallic, material.roughness = state['metallic'], state['roughness']
        shader = material.node_tree.nodes.get('Principled BSDF')
        for socket, value in (('Base Color', state['rgba']), ('Metallic', state['metallic']), ('Roughness', state['roughness'])):
            shader.inputs[socket].default_value = value
        materials[key] = material
    collection = F.ensure_collection('restoration_v18_南三所来源限定研究')
    records, contexts, cache = [], [], {}
    for p in profiles:
        result = G.build_hall(p, collection, materials, cache)
        overrides = apply_front_reference_paint(result, materials)
        for obj in [result['root']] + result['objects']:
            if 'restoration_v14_building_id' in obj:
                del obj['restoration_v14_building_id']
            obj['restoration_v18_building_id'] = p['building_id']
            obj['third_party_cost'] = 0
            obj['human_approval'] = 'pending'
            obj['absolute_accuracy_claim'] = False
        records.append({'building_id': p['building_id'], 'name_zh': p['name_zh'], 'root': result['root'].name,
                        'profile': p, 'objects': [o.name for o in result['objects']],
                        'components': {k: [o.name for o in objects] for k, objects in result['components'].items()},
                        'openings': result['openings'], 'roofs': result['roofs'],
                        'reference_floor': result['reference_floor'].name, 'roof_contacts': result.get('roof_contacts', []),
                        'caller_material_overrides': overrides, 'complete_reconstruction_proven': False})
        if p['building_id'] == 'nansansuo_common_gate':
            connection = build_gate_wall_connections(result, materials, docs['gate_connections'])
            assert len(connection['objects']) == len(connection['components']) == 2
            contexts.extend(connection['components'])
            for obj in connection['objects']:
                obj['restoration_v18_building_id'] = p['building_id']
                obj['third_party_cost'] = 0
                obj['human_approval'] = 'pending'
                obj['absolute_accuracy_claim'] = False
        print('V18_BUILT', p['building_id'], len(records[-1]['objects']), flush=True)
    allowed = sorted({n for p in profiles for n in p['allowed_hidden_source_actor_names']})
    assert len(allowed) == 10 and allowed == sorted(docs['registry']['allowed_hidden_source_actor_names'])
    changes = []
    for name in allowed:
        obj = bpy.data.objects[name]
        assert name in old and not obj.hide_render and not obj.hide_get()
        obj.hide_render = True
        obj.hide_set(True)
        changes.append({'object': name, 'before': old[name]['visibility'], 'after': visibility(obj)})
    bpy.context.view_layer.update()
    names = {o.name for o in scene.objects if o.type == 'MESH'} - set(old)
    body_names = {n for row in records for n in row['objects']}
    context_names = {n for row in contexts for n in row['objects']}
    assert len(body_names) == 505 and len(context_names) == 2 and not body_names.intersection(context_names)
    assert names == body_names | context_names
    assert all(mesh_fingerprint(bpy.data.objects[n]) == row['fingerprint'] for n, row in old.items())
    assert all(visibility(bpy.data.objects[n]) == row['visibility'] for n, row in old.items() if n not in allowed)
    assert all(nonmesh_state(bpy.data.objects[n]) == row for n, row in old_other.items())
    assert all(material_state(bpy.data.materials[n]) == row for n, row in old_mat.items())
    assert all(mesh_relations(bpy.data.objects[n]) == row for n, row in old_rel.items())
    assert all(camera_state(bpy.data.objects[n]) == row for n, row in old_cam.items())
    assert sum(bool(o.get('source_building_id')) for o in scene.objects if o.type == 'MESH') == 2845
    for name, value in [('base-mesh-fingerprints', old), ('base-nonmesh-state', old_other),
                        ('base-material-state', old_mat), ('base-mesh-relations', old_rel), ('base-camera-state', old_cam)]:
        write(dest / ('evidence/' + name + '.json'), value)
    camera = bpy.data.objects['R11_Whole_City']
    targets = sorted({n for n in previous['renders'][0]['target_objects'] if not bpy.data.objects[n].hide_render} | names)
    points = [world_to_camera_view(scene, camera, bpy.data.objects[n].matrix_world @ Vector(v))
              for n in targets for v in bpy.data.objects[n].bound_box]
    assert all(0 <= p.x <= 1 and 0 <= p.y <= 1 and camera.data.clip_start <= p.z <= camera.data.clip_end for p in points)
    count = sum(len(o.data.vertices) for o in scene.objects if o.type == 'MESH')
    assert count <= 10000000
    scene['restoration_v18_stage'] = '南三所九座主殿与共用宫门；配殿、井亭、后罩房及未知立面继续保留来源占位。'
    scene['whole_city_objective_complete'] = False
    scene['absolute_accuracy_claim'] = False
    scene['third_party_cost'] = 0
    bpy.context.preferences.filepaths.save_version = 0
    native = dest / MODEL_NAME
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    assert native.stat().st_size <= 1500000000
    write(dest / 'restoration-manifest.json', {
        'schema': 'forbidden-city-restoration-study/v18', 'model_file': MODEL_NAME, 'model_sha256': sha(native),
        'base_native_sha256': BASE_SHA, 'protected_inputs': expected, 'base_mesh_count': len(old),
        'new_mesh_count': len(names), 'scene_mesh_count': len(old) + len(names), 'vertex_count': count,
        'original_source_mesh_count': 2845, 'restorations': records, 'context_components': contexts,
        'gate_wall_connection_proposal': ready['gate_connections'], 'visibility_changes': changes,
        'whole_city_camera': camera.name, 'new_material_palette': docs['palette'],
        'renders': [{'role': 'final_whole_city', 'file': 'outputs/紫禁城全宫高清图/01-全宫鸟瞰-第十八阶段.png',
                     'camera': camera.name, 'width': 6144, 'height': 4608, 'only_selected': False, 'target_objects': targets}],
        'third_party_cost': 0, 'paid_service_calls': 0, 'human_approval': 'pending', 'goal_status': 'active',
        'whole_city_objective_complete': False, 'claimed_absolute_accuracy': False,
        'limitations': ['The entire city remains incomplete; inherited gray attachments and unverified facades remain unresolved.',
                        'Ten separate complete source polygons are qualified to the official diagram, not a measured current asbuilt survey.',
                        'All metric dimensions, bay spacings, support grids and rendered aperture sizes are unmeasured study controls.',
                        'Nine hall factual depth-bay counts, occupied storeys, exact leaf counts and poses remain unknown.',
                        'Five middle-hall facade holes express bay categories, not a surveyed physical opening census.',
                        'Two gray gate-wall connections inherit unmeasured source-wall controls and join only the source-internal endcap region; they are not historical attachments.',
                        'Gate ramps, side halls, well pavilions and rear-cover houses remain unfinished.'],
        'final_user_deliverable': 'One high-resolution image; no ZIP or duplicated source tree',
        'attribution': '© OpenStreetMap contributors ODbL; architectural descriptions and reference diagrams: Palace Museum official sources.'})
    assert all(sha(path) == digest for path, digest in expected.items())
    print('V18_NATIVE_SAVED', sha(native), 'MESHES', len(old) + len(names), flush=True)


if __name__ == '__main__':
    main()
