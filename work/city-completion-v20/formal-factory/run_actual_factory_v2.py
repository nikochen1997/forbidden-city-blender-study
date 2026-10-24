"""Root-only actual source79 fresh-scene capture. No native I/O/save/render."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(ROOT/'work'),str(ROOT/'work/restoration-v19')]
import formal_contract_v2 as K


def load(name,rel):
    spec=importlib.util.spec_from_file_location(name,K.path(rel));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def write(path,doc):
    with Path(path).open('x')as f:json.dump(doc,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def main():
    import bpy
    parser=argparse.ArgumentParser();parser.add_argument('--binding-sha256',required=True);parser.add_argument('--output-dir',type=Path,required=True)
    a=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);binding_path=HERE/'factory-bindings-02.json'
    K.require(K.sha(binding_path)==a.binding_sha256,'formal binding SHA changed');b=K.read(binding_path);profile,palette=K.check_bound_files(b)
    out=a.output_dir.resolve();K.require(out.parent==HERE and not out.exists()and not bpy.data.filepath,'new formal-factory directory and unsaved fresh scene required')
    K.require({o.name:o.type for o in bpy.data.objects}=={'Cube':'MESH','Camera':'CAMERA','Light':'LIGHT'},'actual default3 startup objects required for preservation test')
    out.mkdir();checks=[]
    try:
        N=load('shouan20_native_contract',b['native_contract']);h=N.load_helpers();E=N.load_eval()
        F=load('shouan20_geometry_entry',b['geometry_module'])
        core=load('shouan20_topology_readonly',b['readonly_core'])
        scene=load('shouan20_production_scene',b['scene_builder'])
        def old_state(obj):
            v={'object':h['nonmesh_state'](obj)}
            if obj.type=='MESH':
                with E.evaluated_batch([obj],bpy)as graph:v['full_mesh']=N.capture_mesh(obj,graph,h,E)
            if obj.type=='CAMERA':v['camera']=h['camera_state'](obj)
            if obj.type=='LIGHT':v['light']={'type':obj.data.type,'color':list(obj.data.color),'energy':obj.data.energy}
            return v
        protected={o.name:old_state(o)for o in bpy.data.objects}
        old_materials={m.name:h['material_state'](m)for m in bpy.data.materials}
        old_camera=bpy.context.scene.camera.name if bpy.context.scene.camera else None
        original_scene=bpy.context.scene
        def export(objects,root=None):
            reader=core.MeshReader(bpy);reader.refresh([o.name for o in objects]);outrows=[]
            with E.evaluated_batch(objects,bpy)as graph:
                for obj in objects:
                    K.require(not obj.hide_viewport and not obj.hide_get()and obj.visible_get(),'actual production mesh hidden: '+obj.name)
                    full=N.capture_mesh(obj,graph,h,E);m=reader.mesh(obj.name)
                    evaluated=obj.evaluated_get(graph);mesh=evaluated.to_mesh()
                    try:
                        mesh.calc_loop_triangles();matrix=(root.matrix_world.inverted()@evaluated.matrix_world)if root else evaluated.matrix_world
                        local=[list(matrix@v.co)for v in mesh.vertices]
                        K.require([list(t.vertices)for t in mesh.loop_triangles]==[list(t)for t in m['triangles']],'actual WORLD/local triangulations differ')
                    finally:evaluated.to_mesh_clear()
                    # The independent geometry checker uses these historical
                    # field names. Full raw/evaluated canonical capture is also
                    # retained without reducing faces to selected triangles.
                    row={**full,'vertices_local':local,'triangles':[list(t)for t in m['triangles']],
                        'props':copy.deepcopy(full['properties']),'materials':full['material_slots'],'hidden':False,
                        'local_read_method':'actual evaluated mesh via root inverse times evaluated object matrix, not inverse WORLD float32 readout',
                        'raw_signature':K.canonical({k:full[k]for k in('raw_vertices','raw_edges','raw_faces','raw_face_material_indices','matrix_world','material_slots','properties','relations','visibility')}),
                        'closed_positive':core.closed_positive_topology(m)}
                    outrows.append(row)
            return outrows
        # Real frozen Boolean copy-on-write test on only new temporary walls.
        test_collection=F.ensure_collection('V20_SHOUAN79_BOOLEAN_SENTINEL')
        wall=F.box('V20_SHOUAN79_SENTINEL_CUT',(0,0,1.5),(4,.4,3),None,test_collection)
        partner=wall.copy();partner.data=wall.data;partner.name='V20_SHOUAN79_SENTINEL_PARTNER';test_collection.objects.link(partner)
        bpy.context.view_layer.update();shared_before=wall.data.as_pointer()==partner.data.as_pointer();partner_before=export([partner])[0];wall_before=export([wall])[0]
        record=F.cut_opening(wall,{'id':'formal-copy-on-write','type':'window','destination':'new-test-only',
            'center':[0,0,1.5],'width':1.2,'height':1.4,'depth':1.2,'normal_axis':'Y'},test_collection)
        wall_after=export([wall])[0];partner_after=export([partner])[0]
        K.require(shared_before and wall.data!=partner.data and K.equal(partner_before,partner_after),'real frozen Boolean copy test changed partner or failed unique data')
        sentinel={'scope':'actual frozen F.cut_opening copy-on-write experiment on two temporary new near-origin shared-mesh walls; no historical/native source modified',
            'shared_mesh_before':True,'unique_mesh_after':True,'wall_before':wall_before,'wall_after':wall_after,
            'partner_before':partner_before,'partner_after':partner_after,'opening':record,'temporary_objects_removed_before_canonical':True,
            'original_operands_preserved_scope':'the untouched shared-mesh partner and all3 pre-existing default objects; adapter intentionally replaces only its newly built G14 south wall'}
        temporary_meshes={o.data for o in(wall,partner)}
        for obj in(wall,partner):bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.collections.remove(test_collection)
        for mesh in temporary_meshes:
            if mesh.users==0:bpy.data.meshes.remove(mesh)
        generated={}
        def observe(result):
            generated.update({'objects':export(result['objects'],result['root']),
                'components':{k:[o.name for o in v]for k,v in result['components'].items()},
                'openings':copy.deepcopy(result['openings']),'reference_floor':result['reference_floor'].name})
        result=scene.build_geometry(profile,palette,b['collection_name'],observe)
        actual=export(result['objects'],result['root'])
        newnames={o.name for o in result['objects']}|{result['root'].name}
        K.require(set(bpy.data.objects.keys())==set(protected)|newnames,'unaccounted final object or cutter remains')
        protected_after={n:old_state(bpy.data.objects[n])for n in protected}
        K.require(K.equal(protected,protected_after),'unrelated default global object changed')
        K.require(all(n in bpy.data.materials and K.equal(h['material_state'](bpy.data.materials[n]),v)for n,v in old_materials.items()),'old full material changed')
        K.require((bpy.context.scene.camera.name if bpy.context.scene.camera else None)==old_camera,'old scene active camera changed')
        by={o.name:o for o in result['objects']}
        # Roof-contact roles contain actual structural roof skins only. Ridges
        # and tile ribs remain in all-mesh source-domain/canonical coverage;
        # this role never claims their engineering attachment was proven.
        roof_names=[r['roof_object']for r in result['roofs']]
        support_roles={'column_base','column','pilaster','beam','wall','roof_closure_wall','roof_bearing_post','source_reference_slab'}
        supports=[o.name for o in result['objects']if o.get('semantic_role')in support_roles]
        openings=sorted({n for r in result['openings']for key in('frame_names','leaf_reference_names','infill_proxy_names','wall_segment_names')for n in r[key]})
        roles={'roofs':roof_names,'supports':supports,'openings':openings,'reference_floor':[result['reference_floor'].name],'source_remainders':[]}
        # The canonical contract deliberately expects only subject meshes in its
        # current scene. Link the SAME new collection into one temporary scene;
        # object users_collection and all original default3 remain unchanged.
        temp=bpy.data.scenes.new('V20_SHOUAN79_CAPTURE_ONLY')
        temp.collection.children.link(result['outer_collection'])
        try:
            with bpy.context.temp_override(scene=temp,view_layer=temp.view_layers[0]):
                factory=N.capture_factory_state(bpy,profile,{'mesh_objects':result['objects'],'root_objects':[result['root']]},roles,result['declared_material_names'])
        finally:bpy.data.scenes.remove(temp)
        K.require(bpy.context.scene==original_scene,'temporary canonical capture scene leaked')
        K.require(K.equal(protected,{n:old_state(bpy.data.objects[n])for n in protected}),'temporary scene capture changed default3')
        factory.update({'input_files_sha256':b['inputs_sha256'],'binding_sha256':a.binding_sha256,
            'construction_frame_transform':result['construction_frame_transform']})
        write(out/'factory-state.json',factory);factory_sha=K.sha(out/'factory-state.json')
        doc={'schema':'v20-source-bounded-shouan-recess-actual-world/1','coordinate_space':'WORLD','profile':profile,
            'objects':actual,'generated_before_adapter':generated,'components':{k:[o.name for o in v]for k,v in result['components'].items()},
            'walls':{k:v.name for k,v in result['walls'].items()},'openings':result['openings'],'reference_floor':result['reference_floor'].name,
            'roofs':result['roofs'],'adapter':result['caller_recess_adapter'],'boolean_copy_experiment':sentinel,
            'construction_frame_transform':result['construction_frame_transform'],'protected_global_before':protected,
            'protected_global_after':protected_after,'protected_old_materials_before':old_materials,
            'protected_old_materials_after':{n:h['material_state'](bpy.data.materials[n])for n in old_materials},
            'root_matrix_world':[list(r)for r in result['root'].matrix_world],
            'factory_state':'factory-state.json','factory_state_sha256':factory_sha,'binding_sha256':a.binding_sha256,
            'inputs_sha256':b['inputs_sha256'],'native_opened':False,'native_saved':False,'rendered':False,
            'production_build':True,'occupied_storeys':None,'source_visibility_changes':[],
            'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False}
        K.validate_world_header(doc,b,profile)
        K.require(all(K.sha(K.path(rel))==digest for rel,digest in b['inputs_sha256'].items()),'formal factory changed pinned input')
        write(out/'actual-world.json',doc)
        checks.append({'id':'FORMAL-ACTUAL-01-CAPTURE','passed':True,'actual_mesh_count':len(actual),
            'all3_default_objects_preserved':True,'full_raw_evaluated_material_profile_capture':True,
            'full_domain_roof_support_Boolean_CPU_still_pending':True,'factory_state_sha256':factory_sha})
    except BaseException:
        checks.append({'id':'FORMAL-ACTUAL-01-CAPTURE','passed':False,'traceback':traceback.format_exc()})
    report={'schema':'v20-source-bounded-formal-factory-tests/1','checks':checks,
        'summary':{'passed':sum(c['passed']for c in checks),'failed':sum(not c['passed']for c in checks)},
        'factory_sha256':K.sha(__file__),'binding_sha256':a.binding_sha256,'actual_factory_build_completed':all(c['passed']for c in checks),
        'full_raw_evaluated_material_profile_capture':all(c['passed']for c in checks),'native_opened':False,'native_saved':False,
        'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False}
    write(out/'actual-factory-tests.json',report);print('FORMAL_SHOUAN_FACTORY',json.dumps(report['summary']),flush=True)
    if report['summary']['failed']:raise SystemExit(1)


if __name__=='__main__':main()
