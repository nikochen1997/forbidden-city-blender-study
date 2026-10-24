"""Save four verified source-bounded progress studies on the accepted V18 city.

This is a progress native, with Bamboo explicitly pending. Historical accuracy,
human approval and whole-city completion are never inferred from this save.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
for directory in (ROOT / 'work', HERE, HERE / 'biluo-pavilion-prep', HERE / 'saved-audit'):
    sys.path.insert(0, str(directory))

BASE = ROOT / 'outputs/紫禁城现存格局-南三所第十八阶段/紫禁城现存格局-南三所第十八阶段.blend'
BASE_SHA = '1b3d14372e4756432c1f6513e59217a0410afe85b53ca69849cec338be502122'
BASE_MANIFEST_SHA = '0ec36629f96f40bedc87d0c24ed2360550f5e08ef28ea35d83c32c5fce729b23'
MODEL_NAME = '紫禁城现存格局-乾隆花园第十九阶段-局部进度.blend'
FIVE = ['fuwangge', 'juanqinzhai', 'yucuixuan', 'zhuxiangguan', 'biluoting']
FOUR = set(FIVE) - {'zhuxiangguan'}
ACTORS = {'fuwangge': 'way-40629261-p0_原轮廓主体',
          'juanqinzhai': 'way-1341826246-p0_原轮廓主体',
          'yucuixuan': 'way-40629263-p0_原轮廓主体',
          'biluoting': 'way-43525093-p0_原轮廓主体'}
HELPERS = {'work/build_forbidden_city_restoration_v11.py':
           '1ccce3fcca040d311f6c48fc52cd38cf053d484e627e20f03ad2f4a1c9eeb130',
           'work/build_forbidden_city_restoration_v15.py':
           '9fe1cf52edcf77508c2271ec150d58a7e79266ee09ebd2c664e8f553296935b1'}


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4194304), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(canonical(value) + '\n')


def load_helpers():
    namespace = {'hashlib': hashlib, 'json': json}
    roles = [{'visibility', 'material_state', 'mesh_fingerprint'},
             {'nonmesh_state', 'mesh_relations', 'camera_state'}]
    for (relative, digest), names in zip(HELPERS.items(), roles):
        path = ROOT / relative
        require(sha(path) == digest, 'frozen pure state helper changed')
        nodes = [n for n in ast.parse(path.read_text()).body
                 if isinstance(n, ast.FunctionDef) and n.name in names]
        require({n.name for n in nodes} == names, 'state helper inventory differs')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def validate_ready(ready):
    require(ready['schema'] == 'v19-four-progress-independent-readiness/1', 'wrong readiness schema')
    require(ready['stage19_targets'] == FIVE and len(ready['modeled_this_progress']) == 4
            and set(ready['modeled_this_progress']) == FOUR
            and ready['pending_registration'] == ['zhuxiangguan'], 'five-subject scope lost')
    require(ready['all_required_actual_factory_and_CPU_checks_passed'] is True,
            'actual factory and full-domain CPU checks required')
    for key in ('third_party_cost', 'paid_service_calls'):
        require(type(ready[key]) is int and ready[key] == 0, 'strict integer zero budget required')
    require(ready['human_approval'] == 'pending' and ready['whole_city_complete'] is False,
            'approval or completion promoted')
    required = {'formal_factory': 3, 'formal_source': 5, 'formal_roof_contact': 100,
                'formal_support': 10, 'biluo_factory': 11, 'biluo_full_domains': 6,
                'source_qualification': 9}
    require(set(ready['checks']) == set(required), 'missing required actual check group')
    for key, count in required.items():
        row = ready['checks'][key]
        require(all(type(row[k]) is int for k in ('passed', 'failed', 'actual_terminal_exit_code'))
                and row['passed'] == count and row['failed'] == 0 and row['actual_terminal_exit_code'] == 0,
                'unpassed actual check group: ' + key)
        require(ready['protected_inputs'].get(row['path']) == row['sha256'],
                'unbound actual report: ' + key)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--readiness', type=Path, required=True)
    parser.add_argument('--readiness-sha256', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    dest = args.output_dir.resolve()
    require(dest.parent == ROOT / 'outputs' and not dest.exists(), 'fresh direct output directory required')
    require(sha(BASE) == BASE_SHA and sha(BASE.parent / 'restoration-manifest.json') == BASE_MANIFEST_SHA,
            'accepted base native/manifest changed')
    require(sha(args.readiness) == args.readiness_sha256, 'readiness SHA differs')
    ready = read(args.readiness)
    validate_ready(ready)
    protected = {str(BASE): BASE_SHA, str(BASE.parent / 'restoration-manifest.json'): BASE_MANIFEST_SHA,
                 str(args.readiness.resolve()): args.readiness_sha256,
                 str(Path(__file__).resolve()): sha(__file__)}
    for relative, digest in ready['protected_inputs'].items():
        path = (ROOT / relative).resolve()
        require(path.is_relative_to(ROOT) and sha(path) == digest, 'protected input changed: ' + str(path))
        protected[str(path)] = digest
    for role in ('source_probe', 'source_qualification', 'factory_three', 'factory_biluo'):
        require(str((ROOT / ready[role]).resolve()) in protected, 'unbound actual input: ' + role)
    for relative in ('work/restoration-v19/scene_assemblies.py',
                     'work/restoration-v19/saved-audit/evaluated_geometry_fingerprint.py', *HELPERS):
        require(str((ROOT / relative).resolve()) in protected, 'unbound imported helper: ' + relative)
    for key, row in ready['checks'].items():
        report = read(ROOT / row['path'])
        summary = report.get('summary', report)
        require(summary.get('passed') == row['passed'] and summary.get('failed') == row['failed'],
                'actual report/readiness results differ: ' + key)
    documents = {}
    for role in ('hall_profiles', 'hall_palette', 'fuwang_profiles', 'fuwang_registry',
                 'fuwang_palette', 'biluo_profile', 'biluo_palette'):
        path = (ROOT / ready['documents'][role]).resolve()
        require(str(path) in protected, 'unbound profile/palette document: ' + role)
        documents[role] = read(path)
    qualification = read(ROOT / ready['source_qualification'])
    require(qualification['source_probe_native_sha256'] == BASE_SHA
            and set(qualification['proposed_replace_actor_names']) == set(ACTORS.values())
            and qualification['this_mapping_count'] == 4 and qualification['not_equal_to_five_complete'] is True
            and qualification['absolute_historical_identity_approved'] is False
            and qualification['hide_permission_granted_by_this_package'] is False,
            'four reversible progress-source qualification differs')
    probe = read(ROOT / ready['source_probe'])
    factory_three = read(ROOT / ready['factory_three'])
    factory_biluo = read(ROOT / ready['factory_biluo'])
    f = load_helpers()
    import bpy
    import forbidden_city_geometry as F
    from scene_assemblies import build_four
    from evaluated_geometry_fingerprint import evaluated_batch, capture_evaluated, evaluated_fingerprint
    print('V19_PREFLIGHT_OK', flush=True)
    bpy.ops.wm.open_mainfile(filepath=str(BASE), load_ui=False, use_scripts=False)
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    require(not bpy.data.libraries and not any(i.source == 'FILE' and not i.packed_file for i in bpy.data.images),
            'external dependency found')
    old_objects = [o for o in scene.objects if o.type == 'MESH']
    old = {o.name: {'visibility': f['visibility'](o), 'fingerprint': f['mesh_fingerprint'](o)} for o in old_objects}
    old_other = {o.name: f['nonmesh_state'](o) for o in bpy.data.objects if o.type != 'MESH'}
    old_mat = {m.name: f['material_state'](m) for m in bpy.data.materials}
    old_rel = {o.name: f['mesh_relations'](o) for o in old_objects}
    old_cam = {o.name: f['camera_state'](o) for o in bpy.data.objects if o.type == 'CAMERA'}
    old_scene = {'camera': scene.camera.name if scene.camera else None,
                 'visible_mesh_names': sorted(o.name for o in old_objects if not o.hide_render and o.visible_get())}
    require(len(old) == 14502 and len(old_cam) == 136, 'accepted base mesh/camera inventory differs')
    print('V19_BASE_RAW_SNAPSHOT_OK', len(old), flush=True)
    with evaluated_batch(old_objects) as graph:
        for i, obj in enumerate(old_objects):
            old[obj.name]['evaluated_fingerprint'] = evaluated_fingerprint(capture_evaluated(obj, graph))
            if i % 3000 == 0:
                print('V19_BASE_EVALUATED', i, flush=True)
    # Preflight the exact actual actors against the independently captured probe.
    with evaluated_batch([bpy.data.objects[n] for n in ACTORS.values()]) as graph:
        for name in ACTORS.values():
            obj, evidence = bpy.data.objects[name], probe['actor_evidence'][name]
            actual = capture_evaluated(obj, graph)
            require([list(v.co) for v in obj.data.vertices] == evidence['raw_vertices']
                    and [list(p.vertices) for p in obj.data.polygons] == evidence['raw_faces']
                    and [p.material_index for p in obj.data.polygons] == evidence['raw_face_material_indices']
                    and [list(r) for r in obj.matrix_world] == evidence['matrix_world']
                    and actual['vertices_world'] == evidence['evaluated_world_vertices']
                    and actual['faces'] == evidence['evaluated_world_faces']
                    and dict(obj.items()) == evidence['custom_properties'], 'source actor/probe differs: ' + name)
            require(old[name]['visibility'] == {'hide_render': False, 'global_hide_viewport': False, 'hide_get': False},
                    'source replacement actor already hidden')
    for label, value in [('base-mesh-fingerprints', old), ('base-nonmesh-state', old_other),
                         ('base-material-state', old_mat), ('base-mesh-relations', old_rel),
                         ('base-camera-state', old_cam), ('base-scene-state', old_scene)]:
        path = dest / ('evidence/' + label + '.json')
        write(path, value)
        protected[str(path)] = sha(path)
    require('restoration_v19_乾隆花园局部进度' not in bpy.data.collections, 'new collection already exists')
    collection = F.ensure_collection('restoration_v19_乾隆花园局部进度')
    results = build_four(documents, collection)
    for result in results:
        print('V19_BUILT', result['profile']['building_id'], len(result['objects']), flush=True)
    records = []
    by_factory = {r['building_id']: r for r in factory_three['buildings']}
    for result in results:
        ident = result['profile']['building_id']
        if ident == 'biluoting':
            data = {'root': result['root'].name, 'objects': [o.name for o in result['objects']],
                    'profile': result['profile'], 'components': {k: [o.name for o in v] for k, v in result['components'].items()},
                    'roofs': [o.name for o in result['roofs']], 'reference_floor': result['reference_floor'].name}
            factory = ready['factory_biluo']
        else:
            data = dict(by_factory[ident])
            require(data['root'] == result['root'].name and data['objects'] == [o.name for o in result['objects']],
                    'formal factory object identity differs')
            factory = ready['factory_three']
        records.append({**data, 'building_id': ident,
                        'name_zh': next(row['name_zh'] for row in qualification['entries'] if row['building_id'] == ident),
                        'builder': result['builder'], 'source_actor': ACTORS[ident],
                        'factory_source': {'path': factory, 'sha256': protected[str((ROOT / factory).resolve())]},
                        'complete_reconstruction_proven': False})
    changes = []
    for name in sorted(ACTORS.values()):
        obj = bpy.data.objects[name]
        obj.hide_render = True
        obj.hide_set(True)
        changes.append({'object': name, 'before': old[name]['visibility'], 'after': f['visibility'](obj)})
    bpy.context.view_layer.update()
    names = {o.name for o in scene.objects if o.type == 'MESH'} - set(old)
    require(len(names) == 474 and names == {n for r in records for n in r['objects']}, 'new mesh ownership differs')
    with evaluated_batch(old_objects) as graph:
        for i, obj in enumerate(old_objects):
            require(evaluated_fingerprint(capture_evaluated(obj, graph)) == old[obj.name]['evaluated_fingerprint'],
                    'old evaluated geometry changed: ' + obj.name)
            if i % 3000 == 0:
                print('V19_PRESERVED_EVALUATED', i, flush=True)
    for obj in old_objects:
        require(f['mesh_fingerprint'](obj) == old[obj.name]['fingerprint']
                and f['mesh_relations'](obj) == old_rel[obj.name], 'old raw geometry/relations changed: ' + obj.name)
        wanted = dict(old[obj.name]['visibility'])
        if obj.name in ACTORS.values():
            wanted.update(hide_render=True, hide_get=True)
        require(f['visibility'](obj) == wanted, 'old visibility changed outside four exceptions')
    require(all(f['nonmesh_state'](bpy.data.objects[n]) == row for n, row in old_other.items()), 'old nonmesh state changed')
    require(all(f['material_state'](bpy.data.materials[n]) == row for n, row in old_mat.items()), 'old material changed')
    require(all(f['camera_state'](bpy.data.objects[n]) == row for n, row in old_cam.items()), 'old camera changed')
    require((scene.camera.name if scene.camera else None) == old_scene['camera'], 'scene camera binding changed')
    require({o.name for o in bpy.data.objects if o.type == 'CAMERA'} == set(old_cam), 'native camera population changed')
    require(sum(bool(o.get('source_building_id')) for o in scene.objects if o.type == 'MESH') == 2845, 'original sources changed')
    targets = sorted((set(old_scene['visible_mesh_names']) - set(ACTORS.values())) | names)
    require(set(targets) == {o.name for o in scene.objects if o.type == 'MESH' and not o.hide_render and o.visible_get()},
            'whole-city visible render targets differ')
    vertex_count = sum(len(o.data.vertices) for o in scene.objects if o.type == 'MESH')
    require(vertex_count <= 10000000, 'vertex budget exceeded')
    scene['restoration_v19_stage'] = '乾隆花园四处来源限定局部研究；竹香馆精确配准、山石桥梁与未测立面仍待补充。'
    scene['whole_city_objective_complete'], scene['absolute_accuracy_claim'] = False, False
    scene['third_party_cost'], scene['paid_service_calls'] = 0, 0
    bpy.context.preferences.filepaths.save_version = 0
    native = dest / MODEL_NAME
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    require(native.stat().st_size <= 1500000000, 'native file budget exceeded')
    manifest = {'schema': 'forbidden-city-restoration-study/v19', 'model_file': MODEL_NAME, 'model_sha256': sha(native),
                'base_native_sha256': BASE_SHA, 'base_mesh_count': 14502, 'new_mesh_count': 474,
                'scene_mesh_count': 14976, 'original_source_mesh_count': 2845, 'vertex_count': vertex_count,
                'protected_inputs': protected, 'restorations': records, 'visibility_changes': changes,
                'whole_city_camera': 'R11_Whole_City', 'stage19_targets': FIVE,
                'modeled_this_progress': sorted(FOUR), 'pending_registration': ['zhuxiangguan'],
                'renders': [{'role': 'final_whole_city', 'file': 'outputs/紫禁城全宫高清图/01-全宫鸟瞰-第十九阶段-局部进度.png',
                             'camera': 'R11_Whole_City', 'width': 6144, 'height': 4608,
                             'only_selected': False, 'target_objects': targets}],
                'human_approval': 'pending', 'goal_status': 'active', 'whole_city_objective_complete': False,
                'claimed_absolute_accuracy': False, 'third_party_cost': 0, 'paid_service_calls': 0,
                'limitations': ['Entire city remains incomplete, with many inherited gray source placeholders.',
                                'Four source identities are conditional progress mappings, not a measured historical survey.',
                                'All metric dimensions and internal support grids are unmeasured study controls.',
                                'Bamboo main/ear/gallery exact WORLD boundaries remain unknown; no bamboo source hidden.',
                                'Biluo neutral support prism is not the reconstructed mountain; bridge, carvings, painting and finial remain unbuilt.',
                                'Fuwang has two modeled exterior levels; three internal occupied floors are not reconstructed.',
                                'Yucui factual facing remains unknown; its east-facing frame is only plan inference.',
                                'Native still requires independent saved-readout CPU and visual rendering before delivery promotion.'],
                'final_user_deliverable': 'One high-resolution image; no ZIP or duplicated source tree',
                'attribution': '© OpenStreetMap contributors ODbL; architectural reference: Palace Museum official sources.'}
    write(dest / 'restoration-manifest.json', manifest)
    require(all(sha(p) == digest for p, digest in protected.items()), 'protected input bytes changed')
    print('V19_NATIVE_SAVED', manifest['model_sha256'], 'MESHES', 14976, flush=True)


if __name__ == '__main__':
    main()
