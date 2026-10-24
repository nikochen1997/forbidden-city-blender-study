"""Root-only lightweight factory: four new slabs and captured unchanged contexts."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PINS = {
    'work/restoration-v17/source_support_alignment.py': '00dbf32b52ec67f2e8b82fa4902af1ab2e5561fe55eaefc65c19bb0fb01cc251',
    'work/restoration-v17/profiles/building-profiles-v3.json': '6bfd22e012990bf49d074ad7df0846ee2d7e4393b469b12cf4b00aed2efcc0c4',
    'work/restoration-v17/profiles/qa-palette.json': '8b834bfb063095211841f569427209d0c787f252d018295c7237074918ee914b',
    'work/restoration-v17/registration/registered-buildings.json': '0ff859b0e1434e9ee1c0501aa2f301fd6b8416e85e32a5c2b525f9e3c18479bc',
    'work/restoration-v17/context-qa/run-01/actual-context-geometry.json': 'd3ec1f4b90dddc288a02733daafdb1160e24e9d8dca70162cacd3f513762c8b2',
    'work/forbidden_city_geometry.py': '23f815fc93057a0f69b66adc25536485fc05a33935f67fb1613073963e276efc',
    'work/restoration-v17/stage-qa/check_saved_source_assemblies.py': '70abaf225b2f83d3c398911f4c245d03ce5ccedfc1ffb01686a2d5a73bd61c80',
}


def need(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-dir', type=Path)
    ap.add_argument('--prepare-only', action='store_true')
    args = ap.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:])
    for path, digest in PINS.items():
        need(sha(ROOT/path) == digest, 'immutable input drift '+path)
    if args.prepare_only:
        print(json.dumps({'status': 'READY_FOR_ROOT_FACTORY_ALIGNMENT_EXECUTION', 'pins': len(PINS),
                          'Blender_launched': False, 'actual_alignment_verified': False}, indent=2))
        return
    import bpy
    from mathutils import Matrix
    need(not bpy.data.filepath, 'factory startup only; no native open')
    out = args.output_dir.resolve()
    need(out.is_relative_to(HERE) and not out.exists(), 'fresh independent stage-qa directory required')
    out.mkdir(parents=True)
    sys.path.insert(0, str(ROOT/'work'))
    import forbidden_city_geometry as F
    spec = importlib.util.spec_from_file_location('alignment_helper_under_test', ROOT/'work/restoration-v17/source_support_alignment.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    collection = F.ensure_collection('V17_LIGHT_ALIGNMENT_FACTORY_ONLY')
    palette = read(ROOT/'work/restoration-v17/profiles/qa-palette.json')['materials']
    materials = {}
    for key, value in palette.items():
        m = bpy.data.materials.new('R17_'+key)
        m.diffuse_color = value['rgba']; m.use_nodes = True
        node = m.node_tree.nodes.get('Principled BSDF')
        node.inputs['Base Color'].default_value = value['rgba']
        node.inputs['Metallic'].default_value = value['metallic']
        node.inputs['Roughness'].default_value = value['roughness']
        materials[m.name] = m

    def safe(value):
        if hasattr(value, 'to_dict'):
            return {k: safe(v) for k, v in value.to_dict().items()}
        if hasattr(value, 'to_list'):
            return [safe(v) for v in value.to_list()]
        if isinstance(value, (list, tuple)):
            return [safe(v) for v in value]
        return value

    def capture(obj):
        bpy.context.view_layer.update()
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ev.to_mesh()
        try:
            mesh.calc_loop_triangles()
            return {'object': obj.name, 'role': obj.get('semantic_role'),
                    'vertices': [list(ev.matrix_world@v.co) for v in mesh.vertices],
                    'triangles': [list(t.vertices) for t in mesh.loop_triangles],
                    'raw_vertices': [list(v.co) for v in obj.data.vertices],
                    'raw_faces': [list(p.vertices) for p in obj.data.polygons],
                    'raw_face_material_indices': [p.material_index for p in obj.data.polygons],
                    'matrix_world': [list(row) for row in obj.matrix_world],
                    'parent': obj.parent.name if obj.parent else None,
                    'actual_material_slots': [[s.link, s.material.name if s.material else None] for s in obj.material_slots],
                    'custom_properties': {k: safe(obj[k]) for k in obj.keys()},
                    'collections': [{'name': c.name, 'hide_render': c.hide_render, 'hide_viewport': c.hide_viewport} for c in obj.users_collection],
                    'visibility': {'hide_render': obj.hide_render, 'hide_viewport': obj.hide_viewport, 'hide_get': obj.hide_get()},
                    'hidden': bool(obj.hide_render or obj.hide_viewport or obj.hide_get()),
                    'mesh_users': obj.data.users, 'modifiers': [m.type for m in obj.modifiers]}
        finally:
            ev.to_mesh_clear()

    prior = read(ROOT/'work/restoration-v17/context-qa/run-01/actual-context-geometry.json')
    contexts = copy.deepcopy(prior['context_components'])
    for row in contexts:
        for name, m in row['geometry'].items():
            need(m['parent'] is None and not m['modifiers'], 'only original direct-world context capture supported')
            data = bpy.data.meshes.new(name+'_captured_raw')
            data.from_pydata(m['raw_vertices'], [], m['raw_faces']); data.update()
            for link, material in m['actual_material_slots']:
                need(link == 'DATA', 'original context material link')
                data.materials.append(materials[material])
            for face, index in zip(data.polygons, m['raw_face_material_indices']):
                face.material_index = index
            obj = bpy.data.objects.new(name, data)
            for c in m['collections']:
                col = F.ensure_collection(c['name']); col.hide_render = c['hide_render']; col.hide_viewport = c['hide_viewport']; col.objects.link(obj)
            obj.matrix_world = Matrix(m['matrix_world'])
            for key, value in m['custom_properties'].items():
                obj[key] = value
            obj.hide_render = m['visibility']['hide_render']; obj.hide_viewport = m['visibility']['hide_viewport']; obj.hide_set(m['visibility']['hide_get'])
            actual = capture(obj)
            for key in ('vertices', 'triangles', 'raw_vertices', 'raw_faces', 'raw_face_material_indices', 'matrix_world', 'parent', 'actual_material_slots', 'custom_properties'):
                need(actual[key] == m[key], 'context reconstruction differs '+name+' '+key)
            row['geometry'][name] = actual
    before_contexts = copy.deepcopy(contexts)
    profiles = read(ROOT/'work/restoration-v17/profiles/building-profiles-v3.json')['buildings']
    results, before = {}, {}
    for p in profiles:
        ident = p['building_id']; root = bpy.data.objects.new('LIGHT_'+ident+'_root', None); collection.objects.link(root)
        root.location = p['anchor']; root.rotation_euler.z = p['rotation_z_rad']
        rings = [p['source_polygon_local']] + p['source_holes_local']; d = p['dimensions']
        bottom = d['slab_bottom_z_m'] if p['builder'] == 'stage' else d['source_reference_slab_bottom_z_m']
        surface = F._Surface()
        for tri in F._triangulate_rings(rings):
            surface.face([(x, y, d['floor_z_m']) for x, y in tri])
        F._volume_from_top(surface, bottom)
        slab = F._object('LIGHT_'+ident+'_source_reference_slab', F._new_mesh('LIGHT_'+ident, surface.vertices, surface.faces, materials['R17_white_stone']), collection, 'source_reference_slab')
        slab.parent = root
        for key, value in {'restoration_v17_building_id': ident, 'source_reference_part_id': p['source_part_id'],
                           'human_approval': 'pending', 'third_party_cost': 0, 'absolute_accuracy_claim': False}.items():
            slab[key] = value
        results[ident] = {'root': root, 'reference_floor': slab.name if p['builder'] == 'stage' else slab, 'objects': [slab]}
        before[ident] = capture(slab)
    checks = []
    def case(ident, operation, fn):
        try:
            checks.append({'id': ident, 'operation': operation, 'passed': True, 'evidence': fn()})
        except Exception as exc:
            checks.append({'id': ident, 'operation': operation, 'passed': False, 'error': str(exc), 'traceback': traceback.format_exc()})
        print(('PASS' if checks[-1]['passed'] else 'FAIL'), ident, flush=True)
    def negative_shared_data():
        p = profiles[0]; result = results[p['building_id']]; slab = result['reference_floor']
        extra = bpy.data.objects.new('LIGHT_NEGATIVE_SHARED_DATA', slab.data); collection.objects.link(extra)
        rejected = False
        try:
            module.align_new_reference_floor(p, result)
        except AssertionError:
            rejected = True
        finally:
            bpy.data.objects.remove(extra, do_unlink=True)
        need(rejected and capture(slab) == before[p['building_id']], 'shared-data negative must reject without mutation')
        return {'actual_shared_data_negative_rejected': True, 'original_exactly_restored': True}
    case('EXTRA-ALIGNMENT-01', 'actual extra object shares input floor data -> helper rejects; original unchanged', negative_shared_data)
    records = []
    for p in profiles:
        ident = p['building_id']; result = results[ident]
        def align_one(p=p, result=result, ident=ident):
            record = module.align_new_reference_floor(p, result)
            slab = bpy.data.objects[record['object']]
            actual = capture(slab); old = before[ident]
            need(slab.parent is None and slab.matrix_world == Matrix.Identity(4), 'exact parentNone/worldI required')
            need(actual['actual_material_slots'] == old['actual_material_slots'] and actual['collections'] == old['collections'], 'material/collection changed')
            need(all(actual['custom_properties'][k] == v for k, v in old['custom_properties'].items()), 'old source-study metadata changed')
            need(actual['custom_properties']['logical_building_root'] == result['root'].name, 'logical root lost')
            records.append({'id': ident, 'profile': p, 'reference_floor': slab.name,
                            'geometry': {slab.name: actual}, 'alignment': record,
                            'input_reference_type': 'string' if p['builder'] == 'stage' else 'object'})
            return record
        case('ALIGNMENT-'+ident, 'align complete reference floor; retain name/material/metadata, detach parent', align_one)
    def unchanged_contexts():
        for row in contexts:
            row['geometry'] = {n: capture(bpy.data.objects[n]) for n in row['objects']}
        need(contexts == before_contexts, 'captured original three contexts changed')
        return {'all_three_contexts_exactly_unchanged': True}
    case('ALIGNMENT-CONTEXT-GUARD', 'all six original context meshes before/after -> exact equality', unchanged_contexts)
    doc = {'schema': 'v17.actual-lightweight-alignment-factory-world-geometry/1', 'coordinate_space': 'WORLD',
           'buildings': records, 'context_components': contexts,
           'registry_file': 'work/restoration-v17/registration/registered-buildings.json', 'registry_sha256': PINS['work/restoration-v17/registration/registered-buildings.json'],
           'alignment_helper_sha256': PINS['work/restoration-v17/source_support_alignment.py'],
           'context_actual_source_readout_sha256': PINS['work/restoration-v17/context-qa/run-01/actual-context-geometry.json'],
           'saved_native_read_only': False, 'native_opened': False, 'native_saved': False, 'rendered': False}
    (out/'actual-alignment-world-geometry.json').write_text(json.dumps(doc, ensure_ascii=False)+'\n')
    report = {'schema': 'v17.actual-lightweight-alignment-factory-tests/1', 'checks': checks,
              'passed': sum(x['passed'] for x in checks), 'failed': sum(not x['passed'] for x in checks),
              'fixture_sha256': sha(__file__), 'pins': PINS, 'actual_world_readout_sha256': sha(out/'actual-alignment-world-geometry.json'),
              'complete_source_assembly_CPU_pending': True, 'native_opened': False, 'native_saved': False, 'rendered': False}
    (out/'actual-alignment-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    need(report['failed'] == 0, 'light alignment actual red preserved')


if __name__ == '__main__':
    main()
