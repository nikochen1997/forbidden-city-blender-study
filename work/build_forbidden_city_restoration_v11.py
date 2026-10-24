"""Compose reversible residential rear-hall studies into the frozen city; local renders only."""
import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
BASE_SHA = '2388f5e1ce23525b62037c58a22d86796f3c28567700e97120c1ab902cbb3cde'
PROFILE_SHA = 'fe762b811545d7eaf5e214443749c9ec8ac84c0926f9867f51d6104067b490d8'
MODEL_NAME = '紫禁城现存格局-六宫后殿第十一阶段.blend'
CORE_SOURCES = {
    'forbidden_city_geometry.py': '23f815fc93057a0f69b66adc25536485fc05a33935f67fb1613073963e276efc',
    'restoration_buildings.py': 'aac18ca8c219b8de544dd78d8a7b99000a4d0fe83d40553614065e0c998aaf60',
    'imperial_monuments.py': '5af7e855072559b74e5b05964cad0a50420b04e152de8fc04428049ee993f47e',
    'city_gate_buildings.py': '4dd3d67f9c8c0c82cf544925cd55eccc5d2eabc79938d5c1fc5e3e5590af6675',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def visibility(obj):
    return {'hide_render': obj.hide_render, 'global_hide_viewport': obj.hide_viewport, 'hide_get': obj.hide_get()}


def material_state(material):
    if material is None:
        return None
    state = {'name': material.name, 'use_nodes': material.use_nodes,
             'diffuse_color': list(material.diffuse_color), 'metallic': material.metallic,
             'roughness': material.roughness, 'backface_culling': material.use_backface_culling}
    if material.use_nodes and material.node_tree:
        nodes = []
        for node in material.node_tree.nodes:
            inputs = []
            for socket in node.inputs:
                if not hasattr(socket, 'default_value'):
                    continue
                value = socket.default_value
                if not isinstance(value, (str, int, float, bool)):
                    try:
                        value = list(value)
                    except TypeError:
                        value = value.name if hasattr(value, 'name') else str(value)
                inputs.append((socket.identifier, value))
            nodes.append({'name': node.name, 'type': node.bl_idname, 'inputs': inputs,
                          'image': getattr(getattr(node, 'image', None), 'name', None),
                          'node_group': getattr(getattr(node, 'node_tree', None), 'name', None),
                          'operation': getattr(node, 'operation', None), 'blend_type': getattr(node, 'blend_type', None)})
        state['nodes'] = sorted(nodes, key=lambda n: n['name'])
        state['links'] = sorted((link.from_node.name, link.from_socket.identifier,
                                 link.to_node.name, link.to_socket.identifier) for link in material.node_tree.links)
    return state


def mesh_fingerprint(obj):
    # Actual saved geometry, transforms, slots and source properties, not object counts.
    data = obj.data
    content = {'vertices': [list(v.co) for v in data.vertices],
               'edges': [list(e.vertices) for e in data.edges],
               'faces': [list(p.vertices) for p in data.polygons],
               'face_material': [p.material_index for p in data.polygons],
               'matrix_world': [list(row) for row in obj.matrix_world],
               'data_materials': [material_state(m) for m in data.materials],
               'object_material_slots': [{'link': slot.link, 'material': material_state(slot.material)} for slot in obj.material_slots],
               'object_color': list(obj.color),
               'source_custom_properties': {k: str(obj[k]) for k in obj.keys()}}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def corners(objects):
    return [obj.matrix_world @ Vector(point) for obj in objects for point in obj.bound_box]


def camera_fit(scene, collection, name, objects, size, direction):
    points = corners(objects)
    low = Vector([min(p[i] for p in points) for i in range(3)])
    high = Vector([max(p[i] for p in points) for i in range(3)])
    center = (low + high) / 2
    data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, data)
    collection.objects.link(camera)
    camera.location = center + Vector(direction).normalized() * max(150, (high - low).length * 3)
    camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
    data.type, data.clip_end = 'ORTHO', 15000
    data.ortho_scale = max(high - low) * 1.4
    scene.render.resolution_x, scene.render.resolution_y = size
    for unused in range(8):
        bpy.context.view_layer.update()
        projected = [world_to_camera_view(scene, camera, p) for p in points]
        factor = max(max(abs(p.x - .5), abs(p.y - .5)) for p in projected) / .44
        if factor <= 1:
            break
        data.ortho_scale *= factor * 1.02
    return camera


def build(args, protected):
    spec = read(args.profiles)
    F = importlib.import_module('forbidden_city_geometry')
    R = importlib.import_module('restoration_buildings')
    module = importlib.import_module('rear_hall_buildings')
    previous = read(args.base.parent / 'restoration-manifest.json')
    assert previous['model_sha256'] == BASE_SHA and previous['scene_mesh_count'] == 10515
    bpy.ops.wm.open_mainfile(filepath=str(args.base.resolve()), load_ui=False, use_scripts=False)
    scene = bpy.context.scene
    old = {obj.name: {'visibility': visibility(obj), 'fingerprint': mesh_fingerprint(obj)}
           for obj in scene.objects if obj.type == 'MESH'}
    assert len(old) == 10515
    source_count = sum(bool(o.get('source_building_id')) for o in scene.objects if o.type == 'MESH')
    assert source_count == 2845
    collection = F.ensure_collection('restoration_v11_六宫后殿研究')
    review = F.ensure_collection('restoration_v11_审阅镜头')
    materials = R.restoration_materials(F.create_materials('R11_'))
    cache, results, records = {}, {}, []
    for profile in spec['buildings']:
        identifier = profile['building_id']
        result = module.build_hall(profile, collection, materials, cache)
        root = result['root']
        objects = result['objects']
        assert root.type == 'EMPTY' and objects and all(o.type == 'MESH' and o.name not in old for o in objects)
        for obj in [root] + objects:
            obj['restoration_v11_building_id'] = identifier
            obj['building_id'] = identifier
            obj['profiles_sha256'] = PROFILE_SHA
            obj['source_reference_part_id'] = profile['source_part_id']
            obj['absolute_accuracy_claim'] = False
            obj['human_approval'] = 'pending'
            obj['third_party_cost'] = 0
        root['residential_rear_hall_profile'] = json.dumps(profile, ensure_ascii=False)
        root['occupied_storeys_status'] = 'unknown'
        results[identifier] = result
        def names(value):
            if isinstance(value, bpy.types.Object):
                return value.name
            if isinstance(value, dict):
                return {key: names(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [names(item) for item in value]
            return value
        records.append({'building_id': identifier, 'name_zh': profile['name_zh'], 'root': root.name,
                        'profile': profile, 'objects': [o.name for o in objects],
                        'components': names(result['components']), 'openings': names(result['openings']),
                        'roofs': names(result['roofs']),
                        'assumptions': result['assumptions'], 'unbuilt_features': result['unbuilt_features'],
                        'complete_reconstruction_proven': False, 'interior_complete': False})
        print('V11_BUILT', identifier, len(objects), flush=True)
    new_names = {obj.name for result in results.values() for obj in result['objects']}
    assert len(new_names) == sum(len(result['objects']) for result in results.values())
    assert {o.name for o in scene.objects if o.type == 'MESH'} == set(old) | new_names
    allowed = [n for p in spec['buildings'] for n in p['allowed_hidden_source_actor_names']]
    assert len(allowed) == len(set(allowed)) and len(allowed) >= len(spec['buildings'])
    changes = []
    for name in allowed:
        obj = bpy.data.objects[name]
        assert name in old and not obj.hide_render and not obj.hide_get()
        obj.hide_render = True
        obj.hide_set(True)
        changes.append({'object': name, 'before': old[name]['visibility'], 'after': visibility(obj),
                        'reason': 'Reversible display replacement of this named OSM proxy by an explicitly unmeasured typological study.'})
    bpy.context.view_layer.update()
    assert all(mesh_fingerprint(bpy.data.objects[name]) == row['fingerprint'] for name, row in old.items())
    assert all(visibility(bpy.data.objects[name]) == row['visibility'] for name, row in old.items() if name not in allowed)
    assert sum(bool(o.get('source_building_id')) for o in scene.objects if o.type == 'MESH') == 2845
    write(args.output_dir / 'evidence/base-mesh-fingerprints.json', old)
    jobs = []

    def job(prefix, title, targets, size, direction, only=False, camera=None, engineering=False):
        camera = camera or camera_fit(scene, review, 'R11_' + prefix + '_' + title, targets, size, direction)
        visible = targets if only else [o for o in scene.objects if o.type == 'MESH' and not o.hide_render]
        jobs.append({'file': 'renders/' + prefix + '-' + title + '.png', 'camera': camera.name,
                     'width': size[0], 'height': size[1], 'only_selected': only, 'engineering_display': engineering,
                     'target_objects': [o.name for o in targets], 'visibility_objects': [o.name for o in visible],
                     'projection_source': 'actual_meshes', 'human_approval': 'pending'})

    whole_camera = bpy.data.objects['Camera_Whole_City'].copy()
    whole_camera.data = whole_camera.data.copy()
    whole_camera.name = 'R11_Whole_City'
    review.objects.link(whole_camera)
    whole = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render
             and (o.get('source_building_id') or any(o.get('restoration_v' + str(v) + '_building_id') for v in range(2, 12)))]
    job('01', '全宫鸟瞰-第十一阶段', whole, (6144, 4608), (1, -1, 1), camera=whole_camera)
    for prefix, region in [('02', 'east'), ('03', 'west')]:
        targets = [o for p in spec['buildings'] if p['region'] == region for o in results[p['building_id']]['objects']]
        palaces = {p['palace_id'] for p in spec['buildings'] if p['region'] == region}
        targets += [bpy.data.objects[n] for r in previous['restorations'] if r['building_id'] in palaces for n in r['objects']]
        targets += [bpy.data.objects[n] for p in spec['buildings'] if p['region'] == region for n in p['review_context_source_actor_names']]
        title = ('东六宫' if region == 'east' else '西六宫') + '-现存前后殿来源限定研究'
        job(prefix, title, targets, (3600, 2700), (.45, -1.55, 1.7), only=True)
    for index, profile in enumerate(spec['buildings'], 4):
        identifier = profile['building_id']
        theta = profile['rotation_z_rad']
        def direction(front=True):
            x, y, z = .55, -1.65 if front else 1.65, .85
            return (x * math.cos(theta) - y * math.sin(theta), x * math.sin(theta) + y * math.cos(theta), z)
        targets = results[identifier]['objects'] + [bpy.data.objects[n] for n in profile.get('review_context_source_actor_names', [])]
        job(str(index).zfill(2), profile['name_zh'] + '-前檐独立研究', targets, (3200, 2400), direction(), only=True)
        job(str(index + len(spec['buildings'])).zfill(2), profile['name_zh'] + '-后檐独立研究', targets, (2800, 2100), direction(False), only=True)
    for prefix, region in [('26', 'east'), ('27', 'west')]:
        targets = [o for p in spec['buildings'] if p['region'] == region for o in results[p['building_id']]['objects']
                   if o.get('semantic_role') not in {'roof', 'ridge', 'tile', 'upper_band_wall', 'gable_wall', 'roof_bearing_post'} and not o.get('roof_type')]
        job(prefix, ('东六宫' if region == 'east' else '西六宫') + '-下层实际网格工程投影', targets,
            (3200, 3200), (0, 0, 1), only=True, engineering=True)
    stage_targets = [bpy.data.objects[n] for p in spec['buildings'] for n in p['review_context_source_actor_names']]
    assert len(stage_targets) == 1 and stage_targets[0].get('source_building_id') == 'way-1205187964-p0'
    job('28', '长春宫戏台-保留独立源体量子型未核', stage_targets, (3200, 2400), (.6, -1.6, 1.3), only=True)
    tongshun = results['tongshunzhai']
    detail = [o for o in tongshun['objects'] if o.get('semantic_role') in
              {'door_leaf', 'window_set_infill_proxy', 'lattice_reference', 'opening_frame', 'winddoor_set_infill_proxy'}
              or (o.get('semantic_role') == 'wall_segment' and o.get('wall_side') == 'south')]
    angle = tongshun['profile']['rotation_z_rad']
    job('29', '同顺斋-前檐门窗分段与外风门研究', detail, (4000, 1600),
        (math.sin(angle), -math.cos(angle), .02), only=True)
    profile = results['tiyuandian']['profile']
    angle = profile['rotation_z_rad']
    job('30', '体元殿-硬山山墙与承托研究', results['tiyuandian']['objects'], (3200, 2400),
        (1.8 * math.cos(angle) + .25 * math.sin(angle), 1.8 * math.sin(angle) - .25 * math.cos(angle), .7), only=True)
    preflight = []
    for item in jobs:
        scene.render.resolution_x, scene.render.resolution_y = item['width'], item['height']
        camera = bpy.data.objects[item['camera']]
        points = [world_to_camera_view(scene, camera, p) for p in corners([bpy.data.objects[n] for n in item['target_objects']])]
        passed = bool(points) and all(camera.data.clip_start <= p.z <= camera.data.clip_end and 0 <= p.x <= 1 and 0 <= p.y <= 1 for p in points)
        preflight.append({'file': item['file'], 'passed': passed,
                          'x': [min(p.x for p in points), max(p.x for p in points)],
                          'y': [min(p.y for p in points), max(p.y for p in points)],
                          'target_mesh_count': len(item['target_objects'])})
    write(args.output_dir / 'evidence/camera-preflight.json', preflight)
    assert all(row['passed'] for row in preflight)
    scene.camera = whole_camera
    scene.render.resolution_x, scene.render.resolution_y = 6144, 4608
    scene.render.resolution_percentage = 100
    scene['restoration_v11_stage'] = '东、西六宫11现存后殿研究；同道堂采用有来源的歇山研究方案但官网冲突未解，戏台仅保留源体量。尺寸未测，非完整全宫复原。'
    scene['whole_city_objective_complete'] = False
    scene['absolute_accuracy_claim'] = False
    scene['third_party_cost'] = 0
    scene['restoration_v11_profiles_sha256'] = PROFILE_SHA
    scene['restoration_v11_module_sha256'] = args.module_sha256
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
                area.spaces.active.shading.type = 'SOLID'
                area.spaces.active.shading.color_type = 'MATERIAL'
                area.spaces.active.overlay.show_overlays = False
    bpy.context.preferences.filepaths.save_version = 0
    destination = args.output_dir / MODEL_NAME
    bpy.ops.wm.save_as_mainfile(filepath=str(destination))
    manifest = {'schema': 'forbidden-city-restoration-study/v11', 'model_file': MODEL_NAME,
                'model_sha256': sha(destination), 'base_native_sha256': BASE_SHA,
                'profiles_sha256': PROFILE_SHA, 'module_sha256': args.module_sha256,
                'protected_inputs': protected, 'base_mesh_count': 10515, 'new_mesh_count': len(new_names),
                'scene_mesh_count': 10515 + len(new_names), 'original_source_mesh_count': 2845,
                'restorations': records, 'visibility_changes': changes, 'renders': jobs,
                'third_party_cost': 0, 'paid_service_calls': 0, 'human_approval': 'pending',
                'goal_status': 'active', 'whole_city_objective_complete': False, 'claimed_absolute_accuracy': False,
                'limitations': spec['policy'], 'attribution': '© OpenStreetMap contributors, ODbL; descriptive facts: Palace Museum official website.'}
    write(args.output_dir / 'restoration-manifest.json', manifest)
    assert all(sha(Path(path)) == digest for path, digest in protected.items())
    print('V11_NATIVE_SAVED', manifest['model_sha256'], len(new_names), flush=True)


def render(args, protected):
    manifest = read(args.output_dir / 'restoration-manifest.json')
    native = args.output_dir / manifest['model_file']
    assert sha(native) == manifest['model_sha256']
    assert manifest['module_sha256'] == args.module_sha256 and manifest['profiles_sha256'] == PROFILE_SHA
    assert protected == manifest['protected_inputs'], 'Render sources differ from the saved build inputs.'
    assert all(sha(Path(path)) == digest for path, digest in manifest['protected_inputs'].items()), 'A saved build input changed.'
    bpy.ops.wm.open_mainfile(filepath=str(native.resolve()), load_ui=False, use_scripts=False)
    scene = bpy.context.scene
    baseline = {o: o.hide_render for o in scene.objects if o.type == 'MESH'}
    directory = args.output_dir / ('previews' if args.mode == 'preview' else 'renders')
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for job in manifest['renders']:
        names = set(job['visibility_objects'])
        for obj, state in baseline.items():
            desired = obj.name not in names if job['only_selected'] else state
            if obj.hide_render != desired:
                obj.hide_render = desired
        assert {o.name for o in baseline if not o.hide_render} == names
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
        scene.eevee.taa_render_samples = 12 if args.mode == 'preview' else 32
        old_colors = {}
        old_world = tuple(scene.world.color)
        old_view = (scene.view_settings.view_transform, scene.view_settings.look,
                    scene.view_settings.exposure, scene.view_settings.gamma)
        shading = scene.display.shading
        old_shading = {k: getattr(shading, k) for k in ('light', 'color_type', 'background_type',
                                                       'show_shadows', 'show_cavity', 'show_object_outline')}
        if job['engineering_display']:
            scene.render.engine = 'BLENDER_WORKBENCH'
            shading.light, shading.color_type, shading.background_type = 'FLAT', 'OBJECT', 'WORLD'
            shading.show_shadows, shading.show_cavity, shading.show_object_outline = False, True, True
            scene.world.color = (1, 1, 1)
            scene.view_settings.view_transform, scene.view_settings.look = 'Standard', 'None'
            scene.view_settings.exposure, scene.view_settings.gamma = 0, 1
            for name in names:
                obj = bpy.data.objects[name]
                old_colors[obj] = tuple(obj.color)
                gray = .94 if obj.get('semantic_role') == 'source_reference_slab' else .12
                obj.color = (gray, gray, gray, 1)
        scale = min(1, 1400 / max(job['width'], job['height'])) if args.mode == 'preview' else 1
        scene.render.resolution_x, scene.render.resolution_y = round(job['width'] * scale), round(job['height'] * scale)
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format, scene.render.image_settings.color_mode = 'PNG', 'RGB'
        scene.camera = bpy.data.objects[job['camera']]
        path = directory / Path(job['file']).name
        assert not path.exists(), 'Preserve earlier renders.'
        scene.render.filepath = str(path)
        print('V11_RENDER_START', args.mode, path.name, flush=True)
        bpy.ops.render.render(write_still=True)
        records.append({'file': str(path), 'sha256': sha(path), 'width': scene.render.resolution_x,
                        'height': scene.render.resolution_y, 'actual_visible_mesh_count': len(names),
                        'only_selected': job['only_selected'], 'native_saved': False})
        for obj, color in old_colors.items():
            obj.color = color
        scene.world.color = old_world
        scene.view_settings.view_transform, scene.view_settings.look, scene.view_settings.exposure, scene.view_settings.gamma = old_view
        for key, value in old_shading.items():
            setattr(shading, key, value)
    for obj, state in baseline.items():
        if obj.hide_render != state:
            obj.hide_render = state
    assert sha(native) == manifest['model_sha256']
    assert all(sha(Path(path)) == digest for path, digest in protected.items())
    write(args.output_dir / 'evidence' / ('preview-renders.json' if args.mode == 'preview' else 'actual-renders.json'),
          {'model_sha256': manifest['model_sha256'], 'renders': records, 'native_saved': False})
    print('V11_RENDER_DONE', args.mode, len(records), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['build', 'preview', 'render'], required=True)
    for key in ['base', 'profiles', 'output-dir']:
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--module-sha256', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    assert sha(args.base) == BASE_SHA and sha(args.profiles) == PROFILE_SHA
    assert sha(HERE / 'rear_hall_buildings.py') == args.module_sha256
    for name, digest in CORE_SOURCES.items():
        assert sha(HERE / name) == digest
    protected_paths = [args.base, args.profiles, Path(__file__).resolve(), HERE / 'rear_hall_buildings.py']
    base_manifest = args.base.parent / 'restoration-manifest.json'
    assert sha(base_manifest) == 'b160fbb25deb1873907d8092422fcadcfcf6d86bc09b8f80ad49474309eeaf6e'
    protected_paths.append(base_manifest)
    protected_paths += [HERE / name for name in CORE_SOURCES]
    spec = read(args.profiles)
    for relative, expected in spec['source_files'].items():
        path = HERE.parent / relative
        assert sha(path) == expected, 'Source evidence changed: ' + relative
        protected_paths.append(path)
    protected_paths.append(HERE / 'forbidden-city-research/geospatial/model-data.json')
    protected = {str(path.resolve()): sha(path) for path in protected_paths}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.mode == 'build':
        assert not (args.output_dir / MODEL_NAME).exists() and not (args.output_dir / 'restoration-manifest.json').exists()
        build(args, protected)
    else:
        render(args, protected)


if __name__ == '__main__':
    main()
