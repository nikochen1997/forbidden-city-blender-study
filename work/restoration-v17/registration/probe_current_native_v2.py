"""One readonly saved-V16 probe. Complete target and neighbour source meshes, all durable IDs; no save/render."""
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


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(4194304), b''): h.update(b)
    return h.hexdigest()


def write(name,value):
    with (HERE/name).open('x') as f:
        json.dump(value,f,ensure_ascii=False,separators=(',',':'),allow_nan=False); f.write('\n')


def load_functions(rel,expected,wanted):
    path = ROOT/rel; assert sha(path) == expected
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in wanted]
    assert {n.name for n in nodes} == wanted
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),globals())
    return path


H1 = load_functions('work/restoration-v8/module-research/copy-boolean/test_copy_boolean.py',
    '57e52b7bddf5de246a3b31e3c2c2916ed07bbfeda579104d0bf11d741907e2ed',
    {'safe','digest','mesh_digest','material_digest','slots','source_fingerprints'})
H2 = load_functions('work/restoration-v12/registration/probe_saved_v11.py',
    '001745cdd60cac927eb248304a84ee550ab291810bde7e359115afb2e9cc404c',
    {'visibility','bounds','evaluated','record_actor','material_record','durable_state','guard_rows','durable_guard'})


def all_durable_ids():
    result = {}
    for prop in bpy.data.bl_rna.properties:
        if prop.type != 'COLLECTION': continue
        items = getattr(bpy.data,prop.identifier)
        values = [{'name':v.name_full,'type':v.bl_rna.identifier,'library':v.library.filepath if v.library else None,
                   'custom_properties_sha256':digest(dict(v.items()))} for v in items if isinstance(v,bpy.types.ID)]
        result[prop.identifier] = sorted(values,key=lambda v:(v['type'],v['name']))
    return result


def all_layer_state():
    def record(x):
        return {'collection':x.collection.name,'exclude':bool(x.exclude),'hide_viewport':bool(x.hide_viewport),
                'is_visible':bool(x.is_visible),'holdout':bool(x.holdout),'indirect_only':bool(x.indirect_only),
                'children':[record(c) for c in x.children]}
    return [{'scene':s.name,'name':v.name,'use':bool(v.use),'collections':record(v.layer_collection)}
            for s in bpy.data.scenes for v in s.view_layers]


def identifiers(o):
    found=set()
    for k in ('source_building_id','osm_part_id','source_record'):
        v=o.get(k)
        if k=='source_record':
            if isinstance(v,str):
                try: v=json.loads(v)
                except json.JSONDecodeError: continue
            if hasattr(v,'get') and v.get('id'): found.add(str(v.get('id')))
        elif v: found.add(str(v))
    return found


def is_original_source_mesh(obj, sid):
    return obj.type=='MESH' and obj.get('source_building_id')==sid


def main():
    assert not (HERE/'actual-source-actors.json').exists(),'Preserve previous actual evidence'
    request_path=HERE/'source-probe-requests.json'; request=json.loads(request_path.read_text())
    native=Path(request['native_file'])
    inputs={**request['inputs_sha256'],str(request_path.relative_to(ROOT)):sha(request_path),
            str(Path(__file__).relative_to(ROOT)):sha(__file__),
            str(H1.relative_to(ROOT)):sha(H1),str(H2.relative_to(ROOT)):sha(H2)}
    assert all(sha(ROOT/p)==h for p,h in inputs.items()),'Frozen input changed before open'
    model=json.loads((ROOT/'work/forbidden-city-research/geospatial/model-data.json').read_text())
    parts={p['id']:p for p in model['parts']}
    for sid,h in request['source_record_sha256'].items():
        assert hashlib.sha256(json.dumps(parts[sid],sort_keys=True,separators=(',',':')).encode()).hexdigest()==h
    assert bpy.ops.wm.open_mainfile(filepath=str(native),load_ui=False,use_scripts=False)=={'FINISHED'}
    bpy.context.view_layer.update()
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    assert len(meshes)==request['expected_mesh_count']==13683
    assert sum(bool(o.get('source_building_id')) for o in meshes)==request['expected_source_mesh_count']==2845
    metadata={o.name:identifiers(o) for o in bpy.context.scene.objects}
    all_ids_before=all_durable_ids(); state_before=durable_state(); layers_before=all_layer_state()
    metadata_reference_mapping={sid:sorted(n for n,ids in metadata.items() if sid in ids) for sid in sorted(request['selected_part_ids']+request['nearby_source_part_ids'])}
    mapping={sid:[name for name in names if is_original_source_mesh(bpy.data.objects[name],sid)]
             for sid,names in metadata_reference_mapping.items()}
    metadata_reference_evidence={}
    for sid,names in metadata_reference_mapping.items():
        for name in names:
            o=bpy.data.objects[name]
            metadata_reference_evidence[name]={'name':name,'object_type':o.type,
                'all_source_identifiers':sorted(metadata[name]),'semantic_role':o.get('semantic_role'),
                'source_building_id':o.get('source_building_id'),'matrix_world':safe(o.matrix_world),
                'parent':o.parent.name if o.parent else None,'visibility':visibility(o),
                'collections':sorted(c.name for c in o.users_collection),'custom_properties':safe(dict(o.items())),
                'data_name':o.data.name_full if o.data else None,
                'is_original_source_mesh_for_matched_ID':is_original_source_mesh(o,sid),
                'reference_is_not_hide_permission':True}
    assert all(mapping.values()),'Source part has no metadata-matched actual actor'
    target_names=sorted({n for names in mapping.values() for n in names})
    selected=[bpy.data.objects[n] for n in target_names]
    assert all(o.type=='MESH' for o in selected)
    before=source_fingerprints(selected,'before-targets-only')
    actor_evidence={}
    for sid,names in mapping.items():
        for name in names:
            o=bpy.data.objects[name]; raw=o.get('source_record'); raw=json.loads(raw) if isinstance(raw,str) else safe(raw)
            assert raw==parts[sid],'Source record mismatch: '+name
            a=record_actor(o); a['object_type']=o.type; a['data_name']=o.data.name
            a['source_record']=raw; a['source_record_sha256']=request['source_record_sha256'][sid]
            a['all_source_identifiers']=sorted(metadata[name]); a['raw_mesh_sha256']=mesh_digest(o.data)
            a['raw_world_vertices']=[list(o.matrix_world@v.co) for v in o.data.vertices]
            a['raw_edges']=[list(e.vertices) for e in o.data.edges]
            a['evaluated_material_slots']=slots(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
            a['modifiers']=[{'name':m.name,'type':m.type,'show_render':bool(m.show_render),
                             'show_viewport':bool(m.show_viewport)} for m in o.modifiers]
            a['shape_keys']=o.data.shape_keys.name if o.data.shape_keys else None
            actor_evidence[name]=a
        print('V17_SOURCE',sid,names,flush=True)
    neighbours=[]
    for sid in request['nearby_source_part_ids']:
        names=mapping[sid]
        briefs=[]
        for n in names:
            o=bpy.data.objects[n]
            briefs.append({'name':n,'object_type':o.type,'semantic_role':o.get('semantic_role'),
                           'visibility':visibility(o),'matrix_world':safe(o.matrix_world),
                           'bounds_world_xyz':bounds([o.matrix_world@Vector(p) for p in o.bound_box]),
                           'custom_properties':safe(dict(o.items())),
                           'actual_material_slots':slots(o),'raw_mesh_sha256':mesh_digest(o.data) if o.type=='MESH' else None})
        neighbours.append({'source_part_id':sid,'source_record':parts[sid],
                           'source_record_sha256':request['source_record_sha256'][sid],
                           'actual_actor_names':names,'actual_actor_brief':briefs,
                           'historical_identity_confirmed':False})
    after=source_fingerprints(selected,'after-targets-only')
    state_after=durable_state(); all_ids_after=all_durable_ids(); layers_after=all_layer_state()
    assert before==after,'Target original/evaluated mesh or field changed'
    assert state_before==state_after and all_ids_before==all_ids_after and layers_before==layers_after
    assert all(sha(ROOT/p)==h for p,h in inputs.items()),'Frozen input changed after readonly probe'
    write('target-mesh-state-guard.json',{'schema':'v17-readonly-target-and-neighbour-guard/1',
        'target_mesh_count':len(selected),'scene_mesh_count':len(meshes),'rows':guard_rows(before,after),
        'before_sha256':digest(before),'after_sha256':digest(after),'full_field_values_equal':True,
        'coverage_fields':list(before[0]['parts']),
        'scope':'All metadata-matched requested targets AND neighbouring source-part meshes fully fingerprinted. Not a full-city geometry audit.'})
    write('durable-state-guard.json',{'schema':'v17-readonly-all-durable-id-guard/1',
        'before_sha256':digest(state_before),'after_sha256':digest(state_after),
        'sections':durable_guard(state_before,state_after),'all_durable_id_inventory':all_ids_before,
        'all_durable_id_inventory_sha256_before':digest(all_ids_before),
        'all_durable_id_inventory_sha256_after':digest(all_ids_after),
        'layer_state_before':layers_before,'layer_state_after':layers_after,'all_full_values_equal':True,
        'scope':'Every bpy.data ID name/type/library/custom-property digest, plus object transform/display/collection/camera/scene fields; all requested target and neighbour meshes separately. Not all-scene mesh-coordinate fingerprint.'})
    mats={s[1] for a in actor_evidence.values() for s in a['actual_material_slots'] if s[1]}
    write('actual-source-actors.json',{'schema':'v17-readonly-v16-actual-source-actors/1',
        'input_files_sha256':inputs,'native_file':str(native),'native_sha256':sha(native),
        'open_mainfile_calls':1,'use_scripts':False,'native_mesh_count':len(meshes),
        'original_source_mesh_count':2845,'requested_target_part_count':len(request['selected_part_ids']),'probed_part_count':len(mapping),'probed_actor_count':len(selected),
        'part_actor_mapping':mapping,'metadata_reference_mapping':metadata_reference_mapping,'metadata_reference_evidence':metadata_reference_evidence,'requested_target_part_ids':request['selected_part_ids'],'requested_nearby_part_ids':request['nearby_source_part_ids'],'actor_evidence':actor_evidence,
        'material_evidence':{n:material_record(bpy.data.materials[n]) for n in sorted(mats)},
        'nearby_unassigned_source_candidates':neighbours,
        'target_mesh_fingerprints_unchanged':True,'all_durable_IDs_and_display_state_unchanged':True,
        'full_scene_geometry_audited':False,'native_saved':False,'geometry_created':False,
        'renderer_called':False,'producer_imported':False,'old_actor_visibility_changed':False,
        'source_heights_are_current_field_measurements':False,'historical_identity_confirmed':False,
        'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False})
    print('V17_READONLY_PROBE_COMPLETE',len(mapping),len(selected),len(neighbours),len(meshes),'UNCHANGED',flush=True)


if __name__=='__main__': main()
