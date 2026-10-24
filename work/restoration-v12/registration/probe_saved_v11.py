"""Single read-only saved-V11 inventory. Run only after root permits the native job."""
from array import array
import argparse
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[2]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda:handle.read(4194304),b''):h.update(block)
    return h.hexdigest()


def write(path,data):
    with Path(path).open('x') as handle:
        json.dump(data,handle,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        handle.write('\n')


def load_measurements():
    path=PROJECT/'work/restoration-v8/module-research/copy-boolean/test_copy_boolean.py'
    wanted={'safe','digest','mesh_digest','material_digest','slots','source_fingerprints','world_bvh','ray'}
    nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in wanted]
    assert {n.name for n in nodes}==wanted
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),globals())
    return path


def visibility(obj):
    return {'hide_render':bool(obj.hide_render),'hide_viewport':bool(obj.hide_viewport),'hide_get':bool(obj.hide_get()),'visible_get':bool(obj.visible_get())}


def bounds(points):
    return [[min(p[k] for p in points) for k in range(3)],[max(p[k] for p in points) for k in range(3)]]


def evaluated(obj):
    deps=bpy.context.evaluated_depsgraph_get();ev=obj.evaluated_get(deps);mesh=ev.to_mesh(preserve_all_data_layers=True,depsgraph=deps)
    try:
        mesh.calc_loop_triangles()
        return [ev.matrix_world@v.co for v in mesh.vertices],[list(p.vertices) for p in mesh.polygons],[list(t.vertices) for t in mesh.loop_triangles]
    finally:ev.to_mesh_clear()


def record_actor(obj):
    points,faces,triangles=evaluated(obj);bb=bounds(points)
    bottom=[t for t in triangles if all(abs(points[i].z-bb[0][2])<=1e-4 for i in t)]
    edges=Counter(tuple(sorted((a,b))) for face in faces for a,b in zip(face,face[1:]+face[:1]))
    return {'name':obj.name,'source_part_id':obj.get('source_building_id'),'semantic_role':obj.get('semantic_role'),
            'parent':obj.parent.name if obj.parent else None,'matrix_world':[list(r) for r in obj.matrix_world],
            'visibility':visibility(obj),'collections':[{'name':c.name,'hide_render':bool(c.hide_render),'hide_viewport':bool(c.hide_viewport)} for c in obj.users_collection],
            'custom_properties':safe(dict(obj.items())),'object_rgba':list(obj.color),'actual_material_slots':slots(obj),
            'raw_vertices':[list(v.co) for v in obj.data.vertices],'raw_faces':[list(p.vertices) for p in obj.data.polygons],
            'raw_face_material_indices':[p.material_index for p in obj.data.polygons],
            'evaluated_world_vertices':[list(p) for p in points],'evaluated_world_faces':faces,'evaluated_world_triangles':triangles,
            'bounds_world_xyz':bb,'bottom_world_triangles':[[list(points[i]) for i in t] for t in bottom],
            'topology':{'vertices':len(points),'faces':len(faces),'boundary_edges':sum(n==1 for n in edges.values()),'overfull_edges':sum(n>2 for n in edges.values())}}


def material_record(material):
    colours=[]
    if material.node_tree:
        for node in material.node_tree.nodes:
            for socket in node.inputs:
                if socket.name in ['Base Color','Color'] and hasattr(socket,'default_value'):
                    colours.append({'node':node.name,'node_type':node.bl_idname,'socket':socket.name,'default_value':safe(socket.default_value)})
    return {'name':material.name_full,'diffuse_rgba':list(material.diffuse_color),'metallic':material.metallic,
            'roughness':material.roughness,'use_nodes':material.use_nodes,'node_colour_inputs':colours,
            'full_effective_shader_sha256':material_digest(material),
            'scope':'Actual saved visualization settings only; not measured pigment, material identification or rendered-colour accuracy.'}


def durable_state():
    kinds=('objects','meshes','collections','materials','curves','cameras','images','node_groups','worlds','scenes','lights','actions','texts')
    ids={kind:[{'name':v.name_full,'custom_properties_sha256':digest(dict(v.items()))}
               for v in sorted(getattr(bpy.data,kind),key=lambda v:v.name_full)] for kind in kinds}
    objects=[{'name':o.name,'type':o.type,'data':o.data.name_full if o.data else None,'parent':o.parent.name if o.parent else None,
              'world_matrix':safe(o.matrix_world),'basis':safe(o.matrix_basis),'parent_inverse':safe(o.matrix_parent_inverse),
              'visibility':visibility(o),'rgba':list(o.color)} for o in sorted(bpy.data.objects,key=lambda o:o.name)]
    collections=[{'name':c.name,'objects':sorted(o.name for o in c.objects),'children':sorted(v.name for v in c.children),
                  'hide_render':bool(c.hide_render),'hide_viewport':bool(c.hide_viewport)} for c in sorted(bpy.data.collections,key=lambda c:c.name)]
    cameras=[{'name':c.name,'values':{k:safe(getattr(c,k)) for k in ['type','lens','ortho_scale','sensor_width','sensor_height','clip_start','clip_end','shift_x','shift_y']}}
             for c in sorted(bpy.data.cameras,key=lambda c:c.name)]
    scenes=[{'name':s.name,'camera':s.camera.name if s.camera else None,'world':s.world.name if s.world else None,
             'engine':s.render.engine,'resolution':[s.render.resolution_x,s.render.resolution_y,s.render.resolution_percentage],
             'view':{k:safe(getattr(s.view_settings,k)) for k in ['view_transform','look','exposure','gamma']}}
            for s in sorted(bpy.data.scenes,key=lambda s:s.name)]
    return {'IDs':ids,'objects':objects,'collections':collections,'cameras':cameras,'scenes':scenes,
            'scope':'Every durable ID and full custom-property digest; object matrices, visibility and colour, collection membership, cameras and scenes. All used meshes and effective shader/slots separately guarded.'}


def box_distance(a,b):
    return math.hypot(max(a[0][0]-b[1][0],b[0][0]-a[1][0],0),max(a[0][1]-b[1][1],b[0][1]-a[1][1],0))


def guard_rows(before,after):
    assert [r['name'] for r in before]==[r['name'] for r in after]
    return [{'name':a['name'],'data_name':a['data_name'],'before_sha256':a['sha256'],'after_sha256':b['sha256']}
            for a,b in zip(before,after)]


def durable_guard(before,after):
    result={}
    for section in ['objects','collections','cameras','scenes']:
        aa={r['name']:r for r in before[section]};bb={r['name']:r for r in after[section]};assert set(aa)==set(bb)
        result[section]=[{'name':name,'before_sha256':digest(aa[name]),'after_sha256':digest(bb[name])} for name in sorted(aa)]
    result['IDs']={}
    for kind,records in before['IDs'].items():
        aa={r['name']:r for r in records};bb={r['name']:r for r in after['IDs'][kind]};assert set(aa)==set(bb)
        result['IDs'][kind]=[{'name':name,'before_sha256':digest(aa[name]),'after_sha256':digest(bb[name])} for name in sorted(aa)]
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    assert args.output.parent.resolve()==HERE and not args.output.exists()
    reserved=['mesh-state-guard.json','durable-state-guard.json']
    assert all(not (HERE/n).exists() for n in reserved),'Preserve earlier actual probe artifacts'
    request=HERE/'source-probe-requests.json';r=json.loads(request.read_text());native=Path(r['native_file']);helper=load_measurements()
    appendix=json.loads(Path(r['street_gate_appendix_file']).read_text())
    inputs={**r['input_files_sha256'],str(request):sha(request),str(helper):sha(helper),str(Path(__file__)):sha(__file__),str(native):r['native_sha256']}
    assert all(sha(p)==v for p,v in inputs.items())
    assert bpy.ops.wm.open_mainfile(filepath=str(native),load_ui=False,use_scripts=False)=={'FINISHED'}
    bpy.context.view_layer.update()
    meshes=sorted((o for o in bpy.context.scene.objects if o.type=='MESH'),key=lambda o:o.name)
    assert len(meshes)==r['expected_native_meshes']==11556
    assert sum(bool(o.get('source_building_id')) for o in meshes)==r['expected_original_source_meshes']==2845
    state_before=durable_state()
    before=source_fingerprints(meshes,'before')
    by_source={}
    for obj in meshes:
        if obj.get('source_building_id'):by_source.setdefault(obj['source_building_id'],[]).append(obj)
    parts={p['source_part_id']:p for t in r['targets'] for p in t['source_part_candidates']}
    lines={w['source_line_id']:w for t in r['targets'] for w in t['source_wall_line_candidates']}
    for t in appendix['targets']:
        item=t['source_part'];parts[item['source_part_id']]=item
        for line in t['source_wall_line_candidates']:lines[line['source_line_id']]=line
    actor_evidence={};part_mapping={};line_mapping={}
    for sid,item in sorted(parts.items()):
        selected=by_source.get(sid,[])
        assert {o.name for o in selected}==set(item['expected_actor_names']) and selected, 'Source actors missing: '+sid
        for obj in selected:
            record=obj.get('source_record');record=json.loads(record) if isinstance(record,str) else record
            assert record==item['original_record'],'Original source record differs: '+obj.name
            actor_evidence[obj.name]=record_actor(obj)
        part_mapping[sid]=sorted(o.name for o in selected)
    print('SOURCE_PARTS_PROBED',len(parts),len(actor_evidence),flush=True)
    wall_samples=[]
    for sid,item in sorted(lines.items()):
        obj=bpy.data.objects.get(item['expected_actor_name'])
        assert obj and obj.type=='MESH','Source wall actor missing: '+sid
        actor_evidence[obj.name]=record_actor(obj);line_mapping[sid]=obj.name
        expected_refs=item['original_record']['source_refs'];actual_refs=json.loads(obj['source_refs'])
        assert actual_refs==expected_refs,'Wall raw source refs differ'
        tree=world_bvh(obj);bb=actor_evidence[obj.name]['bounds_world_xyz'];z=(bb[0][2]+bb[1][2])/2
        for sample in item['selected_query_samples']:
            a,b=sample['a'],sample['b'];dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
            if length==0:continue
            normal=[-dy/length,dx/length];mid=sample['midpoint'];reach=max(item['original_record']['width'],1.)
            start=[mid[k]-normal[k]*reach for k in [0,1]]+[z]
            hit=ray(tree,start,normal+[0],2*reach)
            wall_samples.append({'source_line_id':sid,'actor':obj.name,'raw_segment_index':sample['segment_index'],
                                 'raw_midpoint':mid,'world_z':z,'from':start,'direction':normal+[0],'range_m':2*reach,'actual_hit':hit,
                                 'scope':'Current source-wall mesh cross-section only; no historical wall identity/metric confirmation.'})
    print('SOURCE_WALLS_PROBED',len(lines),'CROSS_SECTION_SAMPLES',len(wall_samples),flush=True)
    boxes={o.name:bounds([o.matrix_world@Vector(p) for p in o.bound_box]) for o in meshes}
    stage_names=set(r['prior_study_actor_names']);contexts=[]
    for t in r['targets']:
        selected=sorted({n for p in t['source_part_candidates'] for n in part_mapping[p['source_part_id']]})
        related_study=set(t['front_study_actor_names']+t['rear_study_actor_names'])
        relations=[]
        for name in selected:
            near=[{'name':n,'bounds_world_xyz':boxes[n],'distance_of_world_bboxes_m':box_distance(boxes[name],boxes[n]),
                   'XY_bbox_overlap_not_solid_intersection':box_distance(boxes[name],boxes[n])==0}
                  for n in related_study if n in boxes and box_distance(boxes[name],boxes[n])<=4]
            relations.append({'actor':name,'nearby_own_hall_studies':near,'prior_study_tagged':name in stage_names,
                              'custom_stage_tags':{k:safe(v) for k,v in bpy.data.objects[name].items() if k.startswith('restoration_v')}})
        contexts.append({'palace_id':t['palace_id'],'source_actor_names':selected,'wall_actor_names':[line_mapping[w['source_line_id']] for w in t['source_wall_line_candidates']],
                         'own_hall_study_relations':relations,'historical_identity_confirmed':False,'complete_courtyard_boundary':None})
    after=source_fingerprints(meshes,'after')
    state_after=durable_state()
    write(HERE/'mesh-state-guard.json',{'schema':'v12-complete-mesh-state-digests/1','coverage_fields':list(before[0]['parts']),
                                    'full_field_dictionaries_compared_in_memory':True,'rows':guard_rows(before,after)})
    write(HERE/'durable-state-guard.json',{'schema':'v12-complete-durable-state-digests/1','full_values_compared_in_memory':True,
                                       'before_full_state_sha256':digest(state_before),'after_full_state_sha256':digest(state_after),
                                       'coverage':state_before['scope'],'sections':durable_guard(state_before,state_after)})
    assert before==after,'Saved original mesh/material/source/visibility state changed'
    assert state_before==state_after,'Durable datablock state changed'
    assert all(sha(p)==v for p,v in inputs.items()),'Frozen input/native changed'
    report={'schema':'v12-courtyard-readonly-saved-probe/1','input_files_sha256':inputs,'native_file':str(native),'native_sha256':r['native_sha256'],
            'open_mainfile_calls':1,'use_scripts':False,'native_meshes':len(meshes),'original_source_meshes':2845,
            'actor_evidence':actor_evidence,'part_actor_mapping':part_mapping,'source_wall_actor_mapping':line_mapping,
            'material_evidence':{name:material_record(bpy.data.materials[name]) for name in sorted({slot[1] for record in actor_evidence.values() for slot in record['actual_material_slots'] if slot[1]})},
            'wall_cross_section_samples':wall_samples,'palace_contexts':contexts,
            'street_gate_contexts':[{'street_gate_id':t['street_gate_id'],'source_part_id':t['source_part']['source_part_id'],
                                    'actual_actor_names':part_mapping[t['source_part']['source_part_id']],
                                    'actual_wall_actor_names':[line_mapping[w['source_line_id']] for w in t['source_wall_line_candidates']],
                                    'historical_identity_confirmed':False} for t in appendix['targets']],
            'all_original_mesh_fingerprints_unchanged':True,'all_durable_datablocks_unchanged':True,
            'mesh_state_guard_sha256':sha(HERE/'mesh-state-guard.json'),'durable_state_guard_sha256':sha(HERE/'durable-state-guard.json'),
            'full_mesh_states_sha256_before':digest(before),'full_mesh_states_sha256_after':digest(after),
            'durable_states_sha256_before':digest(state_before),'durable_states_sha256_after':digest(state_after),
            'builder_imported':False,'geometry_created':False,'native_saved':False,'old_actor_visibility_changed':False,
            'historical_source_identity_confirmed':False,'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending'}
    write(args.output,report)
    print('V12_READONLY_PROBE_COMPLETE',len(contexts),len(parts),len(lines),len(meshes),'UNCHANGED',flush=True)


if __name__=='__main__':main()
