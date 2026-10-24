"""Prepared V19->V20 producer. Refuses missing real factory/readiness evidence.

Only the root supplies and runs a SHA-bound stage20_scene.py. No production
readiness is manufactured here. This preparation has never run Blender.
"""
import argparse,importlib.util,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage20_contract as C

def main():
 p=argparse.ArgumentParser();p.add_argument('--readiness',type=Path,required=True);p.add_argument('--readiness-sha256',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--failure-report',type=Path,required=True)
 a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);failure=a.failure_report.resolve();C.require(failure.is_relative_to(C.ROOT/'work')and not failure.exists(),'fresh failure report under work required')
 native_saved=False
 try:
  r,docs,factory=C.load_ready(a.readiness,a.readiness_sha256)
  dest=a.output_dir.resolve();C.require(dest.parent==C.ROOT/'outputs'and not dest.exists(),'fresh direct output directory required')
  base_path=C.pinned_path(C.BASE_REL);native=dest/r['model_file'];C.require(native!=base_path,'cannot overwrite base')
  h=C.load_helpers();E=C.load_eval()
  import bpy
  C.require(bpy.app.version_string==factory['blender_version']and bpy.app.build_hash.decode()==factory['blender_build_hash'],'factory/producer Blender identity differs')
  bpy.ops.wm.open_mainfile(filepath=str(base_path),load_ui=False,use_scripts=False)
  bpy.context.view_layer.update();C.require(not bpy.data.libraries and not any(i.source=='FILE'and not i.packed_file for i in bpy.data.images),'external asset dependency')
  base=C.capture_base(bpy,h,E);C.verify_source_probe(bpy,docs[r['bindings']['source_probe']],h,E)
  C.require(not set(factory['mesh_names']+factory['root_names'])&set(bpy.data.objects.keys()),'new factory name collision with base')
  C.require(not set(factory['declared_material_names'])&set(bpy.data.materials.keys()),'factory palette collides with old material')
  C.require(r['collection_name']not in bpy.data.collections,'new collection already exists')
  for row in r['allowed_visibility_changes']:C.require(base['meshes'][row['object']]['visibility']==row['before'],'actual source before visibility differs')
  snap={'schema':'v20.base-state/1','base_native_sha256':C.BASE_SHA,'base_manifest_sha256':C.BASE_MANIFEST_SHA,**base}
  snap_path=dest/'evidence/base-state.json';C.write_new(snap_path,snap)
  # Import alone must not create scene assets. Every local module is SHA-bound.
  before_names=set(bpy.data.objects.keys());before_mat=set(bpy.data.materials.keys());before_modules=set(sys.modules)
  module_path=C.pinned_path(r['bindings']['builder_module']);spec=importlib.util.spec_from_file_location('stage20_scene_actual',module_path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  C.require(set(bpy.data.objects.keys())==before_names and set(bpy.data.materials.keys())==before_mat,'builder import mutated scene')
  request={'collection_name':r['collection_name'],'profile':factory['profile'],'documents':{k:docs[v]for k,v in r['bindings'].items()if k!='builder_module'},'factory_contract':factory}
  result=getattr(module,r['builder_callable'])(request)
  C.require(set(result)=={'mesh_objects','root_objects'},'builder result must return explicit complete mesh/root object arrays')
  C.require([o.name for o in result['mesh_objects']]==factory['mesh_names']and [o.name for o in result['root_objects']]==factory['root_names'],'builder actual object names/order differ from factory')
  # Audit every imported local source, including dynamic imports performed in build.
  for name in set(sys.modules)-before_modules:
   mm=sys.modules[name];ff=getattr(mm,'__file__',None)
   if ff:
    file=Path(ff).resolve()
    if file.is_relative_to(C.ROOT)and not file.is_relative_to(C.ROOT/'work/Blender.app')and file.suffix=='.py':C.require(str(file.relative_to(C.ROOT))in r['protected_inputs'],'unbound imported local module: '+str(file))
  for row in r['allowed_visibility_changes']:
   o=bpy.data.objects[row['object']];o.hide_render=row['after']['hide_render'];o.hide_set(row['after']['hide_get'])
  bpy.context.view_layer.update();C.compare_base(bpy,base,r['allowed_visibility_changes'],h,E);actual=C.compare_new(bpy,base,factory,h,E)
  visible=sorted(o.name for o in bpy.context.scene.objects if o.type=='MESH'and not o.hide_render and o.visible_get())
  expected=sorted((set(base['visible_mesh_names'])-{v['object']for v in r['allowed_visibility_changes']})|set(factory['mesh_names']))
  C.require(visible==expected,'whole-palace target visibility differs')
  C.require(all(C.sha(C.pinned_path(rel))==digest for rel,digest in r['protected_inputs'].items()),'input changed before save')
  # Scope state is additive; old object/camera/geometry properties remain guarded.
  bpy.context.scene['restoration_v20_stage']='寿安宫正殿79源内有界未测绘局部研究；春禧后卷殿与全宫余区待完善。'
  bpy.context.scene['whole_city_objective_complete']=False;bpy.context.scene['absolute_accuracy_claim']=False
  bpy.context.scene['third_party_cost']=0;bpy.context.scene['paid_service_calls']=0
  bpy.context.preferences.filepaths.save_version=0
  bpy.ops.wm.save_as_mainfile(filepath=str(native));native_saved=True
  C.require(native.stat().st_size<=1500000000,'native file budget exceeded')
  manifest={'schema':'forbidden-city-restoration-study/v20','model_file':native.name,'model_sha256':C.sha(native),'base_native_sha256':C.BASE_SHA,'base_manifest_sha256':C.BASE_MANIFEST_SHA,'base_mesh_count':C.BASE_MESHES,'new_mesh_count':len(factory['mesh_names']),'scene_mesh_count':C.BASE_MESHES+len(factory['mesh_names']),'original_source_mesh_count':C.BASE_SOURCES,'camera_count':C.BASE_CAMERAS,'vertex_count':sum(len(o.data.vertices)for o in bpy.context.scene.objects if o.type=='MESH'),'readiness_file':str(a.readiness.resolve().relative_to(C.ROOT)),'readiness_sha256':a.readiness_sha256,'protected_inputs':r['protected_inputs'],'base_snapshot':{'path':str(snap_path.relative_to(C.ROOT)),'sha256':C.sha(snap_path)},'factory_state_binding':r['bindings']['factory_state'],'subject_id':'shouan79','profile':factory['profile'],'mesh_names':factory['mesh_names'],'root_names':factory['root_names'],'roles':factory['roles'],'visibility_changes':r['allowed_visibility_changes'],'render_target_objects':visible,'source_geometry_retained':True,'source_display_qualification':r['visibility_qualification'],'source_95_97_modified':False,'south_of_wumen_expansion':False,'human_approval':'pending','whole_city_complete':False,'claimed_absolute_accuracy':False,'goal_status':'active','third_party_cost':0,'paid_service_calls':0,'saved_readonly_audit':'pending','saved_domain_roof_support_boolean_CPU':'pending','render_and_pixel_review':'pending','limitations':['This is unmeasured source-bounded exterior progress, not surveyed historical reconstruction.','Official plan inference south is not official-text facing; roof single shell is a study control, not confirmed eave tier.','Profile unbuilt items, all inherited gray areas and Chunxi rear-juandian partition remain incomplete.','Source6m and OSM levels are not actual building height/storeys.','No area south of Wumen is added.']}
  C.write_new(dest/'restoration-manifest.json',manifest)
  C.require(all(C.sha(C.pinned_path(rel))==digest for rel,digest in r['protected_inputs'].items()),'protected bytes changed after save')
  C.require(C.sha(a.readiness)==a.readiness_sha256,'readiness changed after save')
  print('V20_NATIVE_SAVED',manifest['model_sha256'],'NEW',len(actual),flush=True)
 except BaseException:
  C.write_new(failure,{'schema':'v20.producer-red/1','native_saved':native_saved,'traceback':traceback.format_exc(),'human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0});raise

if __name__=='__main__':main()
