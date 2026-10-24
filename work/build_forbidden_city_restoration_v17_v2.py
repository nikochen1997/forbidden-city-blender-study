"""Compose source-qualified Shufang/Baohua studies onto the protected V16 native."""
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
sys.path.insert(0, str(HERE / 'restoration-v17'))
import forbidden_city_geometry as F
import restoration_buildings as R
import courtyard_hall_buildings as G
import theatre_stage_buildings as T
import context_geometry_v2 as C
import source_support_alignment as A
from build_forbidden_city_restoration_v11 import mesh_fingerprint, material_state, visibility
from build_forbidden_city_restoration_v15 import nonmesh_state, mesh_relations, camera_state

BASE = ROOT / 'outputs/紫禁城现存格局-慈宁花园惠风第十六阶段/紫禁城现存格局-慈宁花园惠风第十六阶段.blend'
BASE_SHA = '2d020dc62347fbaa84ec7466f40f2ddc9d2fa755c007ac7fc043ef6fd3d0aeb9'
BASE_MANIFEST_SHA = 'fd71595462662aa7f8bc24d61c0fda229ea39960c2c5b5484bd79eee43a48ead'
MODEL_NAME = '紫禁城现存格局-漱芳宝华第十七阶段.blend'
PROFILE = HERE / 'restoration-v17/profiles/building-profiles-v3.json'
PROFILE_SHA = '6bfd22e012990bf49d074ad7df0846ee2d7e4393b469b12cf4b00aed2efcc0c4'
TARGETS = {'shufang_front_hall', 'shufang_rear_hall', 'shufang_large_stage', 'baohuadian_main'}


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
    assert sha(PROFILE) == PROFILE_SHA and sha(args.readiness) == args.readiness_sha256
    ready = read(args.readiness)
    assert ready['schema'] == 'v17-independent-factory-readiness/1'
    assert ready['all_required_actual_factory_and_CPU_checks_passed'] is True
    assert ready['source_slab_alignment_actual_pending'] is True
    assert ready['profiles_sha256'] == PROFILE_SHA and ready['third_party_cost'] == 0
    doc = read(PROFILE)
    profiles = doc['buildings']
    assert len(profiles) == 4 and {p['building_id'] for p in profiles} == TARGETS
    registry_path = HERE / 'restoration-v17/registration/registered-buildings.json'
    binding_path = HERE / 'restoration-v17/registration/front-entry-context/concrete-profile-binding-v3.json'
    palette_path = HERE / 'restoration-v17/profiles/palette.json'
    registry, binding, palette = read(registry_path), read(binding_path), read(palette_path)
    assert binding['front_profile_sha256'] == PROFILE_SHA
    paths = [BASE, BASE.parent / 'restoration-manifest.json', PROFILE, registry_path, binding_path,
             palette_path, args.readiness.resolve(), Path(__file__).resolve(),
             HERE / 'restoration-v17/context_geometry_v2.py', HERE / 'restoration-v17/source_support_alignment.py', HERE / 'theatre_stage_buildings.py',
             HERE / 'imperial_monuments.py', HERE / 'forbidden_city_geometry.py',
             HERE / 'restoration_buildings.py', HERE / 'courtyard_hall_buildings.py',
             HERE / 'four_hall_buildings.py', HERE / 'build_forbidden_city_restoration_v11.py',
             HERE / 'build_forbidden_city_restoration_v15.py']
    expected = {str(p): sha(p) for p in paths}
    for source in (doc['source_files'], binding['input_files_sha256'], ready['inputs_sha256']):
        for rel, digest in source.items():
            path = ROOT / rel
            assert sha(path) == digest, 'Frozen input changed: ' + rel
            expected[str(path)] = digest
    for p in profiles:
        (T if p['builder'] == 'stage' else G)._validate(p)
    print('V17_PREFLIGHT_OK', flush=True)
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
    assert len(old) == previous['scene_mesh_count'] == 13683
    assert not bpy.data.libraries and not any(i.source == 'FILE' and not i.packed_file for i in bpy.data.images)
    materials = R.restoration_materials(F.create_materials('R17_'))
    for key, row in palette['custom'].items():
        material = bpy.data.materials.new('R17_' + key)
        material.use_nodes = True
        material.diffuse_color = (*row['color'], 1)
        shader = material.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = (*row['color'], 1)
        shader.inputs['Metallic'].default_value = row['metallic']
        shader.inputs['Roughness'].default_value = row['roughness']
        materials[key] = material
    collection = F.ensure_collection('restoration_v17_漱芳宝华来源限定研究')
    records, results, slab_exceptions = [], {}, []
    for p in profiles:
        ident = p['building_id']
        result = (T.build_stage if p['builder'] == 'stage' else G.build_hall)(p, collection, materials)
        results[ident] = result
        slab_exceptions.append(A.align_new_reference_floor(p, result))
        for obj in [result['root']] + result['objects']:
            if 'restoration_v14_building_id' in obj:
                del obj['restoration_v14_building_id']
            obj['restoration_v17_building_id'] = ident
            obj['third_party_cost'] = 0
            obj['human_approval'] = 'pending'
            obj['absolute_accuracy_claim'] = False
        floor = result['reference_floor']
        roofs = result['roofs']
        records.append({'building_id': ident, 'name_zh': p['name_zh'], 'root': result['root'].name,
                        'profile': p, 'objects': [o.name for o in result['objects']],
                        'components': {k: [o.name for o in objects] for k, objects in result['components'].items()},
                        'openings': result['openings'], 'roofs': roofs,
                        'reference_floor': floor.name if hasattr(floor, 'name') else floor,
                        'roof_contacts': result.get('roof_contacts', []), 'complete_reconstruction_proven': False})
        print('V17_BUILT', ident, len(result['objects']), flush=True)
    components = C.build_components(registry, collection, materials)
    portal = C.build_front_entry(binding, bpy.data.objects[binding['original_object']],
                                results['shufang_front_hall'], collection)
    allowed = sorted({n for p in profiles for n in p['allowed_hidden_source_actor_names']} |
                     set(binding['allowed_additional_hidden_original_objects']))
    assert len(allowed) == 4
    changes = []
    for name in allowed:
        obj = bpy.data.objects[name]
        assert name in old and not obj.hide_render and not obj.hide_get()
        obj.hide_render = True
        obj.hide_set(True)
        changes.append({'object': name, 'before': old[name]['visibility'], 'after': visibility(obj)})
    bpy.context.view_layer.update()
    names = {o.name for o in scene.objects if o.type == 'MESH'} - set(old)
    recorded = {n for r in records for n in r['objects']} | {n for r in components for n in r['objects']} | {portal['object']}
    assert names == recorded, 'Unaccounted new mesh or temporary cutter'
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
    scene['restoration_v17_stage'] = '漱芳前后殿、大戏台及宝华殿；南房/抱厦及未知屋顶仍为来源占位。'
    scene['whole_city_objective_complete'] = False
    scene['absolute_accuracy_claim'] = False
    scene['third_party_cost'] = 0
    bpy.context.preferences.filepaths.save_version = 0
    native = dest / MODEL_NAME
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    assert native.stat().st_size <= 1500000000
    write(dest / 'restoration-manifest.json', {
        'schema': 'forbidden-city-restoration-study/v17', 'model_file': MODEL_NAME, 'model_sha256': sha(native),
        'base_native_sha256': BASE_SHA, 'protected_inputs': expected, 'base_mesh_count': len(old),
        'new_mesh_count': len(names), 'scene_mesh_count': len(old) + len(names), 'vertex_count': count,
        'original_source_mesh_count': 2845, 'restorations': records,
        'retained_source_display_remainders': components, 'front_entry_context': portal,
        'new_world_source_slab_parent_exceptions': slab_exceptions,
        'visibility_changes': changes, 'whole_city_camera': camera.name, 'new_material_palette': palette,
        'renders': [{'role': 'final_whole_city', 'file': 'outputs/紫禁城全宫高清图/01-全宫鸟瞰-第十七阶段.png',
                     'camera': camera.name, 'width': 6144, 'height': 4608, 'only_selected': False, 'target_objects': targets}],
        'third_party_cost': 0, 'paid_service_calls': 0, 'human_approval': 'pending', 'goal_status': 'active',
        'whole_city_objective_complete': False, 'claimed_absolute_accuracy': False,
        'limitations': ['Whole city remains incomplete; gray areas are unfinished source proxies.',
                        'All metric dimensions unmeasured reference controls.',
                        'Shufang rear roof color/eave count and front veranda roof form remain unknown.',
                        'Stage side/rear enclosure, upper-band windows and concealed interiors unresolved.',
                        'South house/Baohua baoxia roof and the east-side garden route remain unbuilt.',
                        'Reference U passage is not an archaeological doorway measurement.'],
        'final_user_deliverable': 'One high-resolution image; no ZIP or duplicated source tree',
        'attribution': '© OpenStreetMap contributors ODbL; architectural descriptions: Palace Museum official sources.'})
    assert all(sha(path) == digest for path, digest in expected.items())
    print('V17_NATIVE_SAVED', sha(native), 'MESHES', len(old) + len(names), flush=True)


if __name__ == '__main__':
    main()
