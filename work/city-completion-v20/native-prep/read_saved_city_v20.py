"""Prepared independent V20 reader: opens saved native once, never constructs.

No producer, scene module, geometry builder, profile builder, or factory runner
is imported. The ready builder paths are read and hashed only. Full new WORLD
is exported for subsequent complete source/roof/support/Boolean CPU replay.
"""
import argparse,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage20_contract as C

def capture_saved_source_for_cpu(bpy,h,E):
 obj=bpy.data.objects[C.SOURCE_ACTOR];before=h['visibility'](obj)
 with E.evaluated_batch([obj],bpy)as graph:
  row=C.capture_mesh(obj,graph,h,E)
 require_visibility=h['visibility'](obj)
 C.require(require_visibility==before,'source capture did not restore saved visibility')
 row['temporarily_enabled_capture_visibility']=row['visibility']
 row['visibility']=before
 return row

def main():
 p=argparse.ArgumentParser()
 for name in ('native','manifest','readiness','output-dir'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('native-sha256','manifest-sha256','readiness-sha256'):p.add_argument('--'+name,required=True)
 a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=a.output_dir.resolve();C.require(out.is_relative_to(C.ROOT/'work')and not out.exists(),'fresh work-only saved audit directory required')
 out.mkdir(parents=True);checks=[]
 def case(ident,fn):
  try:detail=fn();checks.append({'id':ident,'passed':True,'detail':detail})
  except BaseException:checks.append({'id':ident,'passed':False,'traceback':traceback.format_exc()});raise
 opened=False
 try:
  r,docs,factory=C.load_ready(a.readiness,a.readiness_sha256)
  C.require(C.sha(a.native)==a.native_sha256 and C.sha(a.manifest)==a.manifest_sha256,'saved native/manifest SHA differs')
  m=C.read(a.manifest);C.require(m['schema']=='forbidden-city-restoration-study/v20'and m['model_sha256']==a.native_sha256 and m['base_native_sha256']==C.BASE_SHA and m['base_manifest_sha256']==C.BASE_MANIFEST_SHA,'wrong saved stage/base')
  C.zero_scope(m);C.require(m['source_geometry_retained']is True and m['source_95_97_modified']is False and m['south_of_wumen_expansion']is False and m['claimed_absolute_accuracy']is False,'saved scope flags differ');C.require(m['readiness_sha256']==a.readiness_sha256 and m['protected_inputs']==r['protected_inputs'],'manifest/readiness binding differs')
  C.require(m['model_file']==a.native.name and a.native.parent==a.manifest.parent,'selected saved file differs')
  C.require(m['factory_state_binding']==r['bindings']['factory_state']and C.equal(m['profile'],factory['profile'])and m['mesh_names']==factory['mesh_names']and m['root_names']==factory['root_names']and m['roles']==factory['roles'],'manifest/factory population differs')
  C.require(m['visibility_changes']==r['allowed_visibility_changes'],'manifest exact visibility mapping differs')
  snap=C.pinned_path(m['base_snapshot']['path']);C.require(C.sha(snap)==m['base_snapshot']['sha256'],'base snapshot changed');base=C.read(snap)
  C.require(base['schema']=='v20.base-state/1'and base['base_native_sha256']==C.BASE_SHA and base['base_manifest_sha256']==C.BASE_MANIFEST_SHA,'wrong base snapshot source')
  C.require(len(base['meshes'])==C.BASE_MESHES and len(base['cameras'])==C.BASE_CAMERAS and all('evaluated_fingerprint'in x for x in base['meshes'].values()),'incomplete old full raw/evaluated/camera baseline')
  h=C.load_helpers();E=C.load_eval()
  import bpy
  C.require(bpy.app.version_string==factory['blender_version']and bpy.app.build_hash.decode()==factory['blender_build_hash'],'factory/saved-reader Blender identity differs')
  bpy.ops.wm.open_mainfile(filepath=str(a.native.resolve()),load_ui=False,use_scripts=False);opened=True;bpy.context.view_layer.update()
  def old():
   C.compare_base(bpy,base,r['allowed_visibility_changes'],h,E);return {'meshes':len(base['meshes']),'cameras':len(base['cameras']),'complete_raw_eval_material_relation_nonmesh_camera':True,'exact_visibility_exceptions':[v['object']for v in r['allowed_visibility_changes']]}
  case('V20-OLD',old)
  actual={}
  def fresh():
   actual.update(C.compare_new(bpy,base,factory,h,E))
   C.require(m['new_mesh_count']==len(actual)and m['scene_mesh_count']==C.BASE_MESHES+len(actual)and m['original_source_mesh_count']==C.BASE_SOURCES and m['camera_count']==C.BASE_CAMERAS,'manifest actual inventory differs')
   return {'meshes':len(actual),'factory_full_geometry_match':True,'actual_used_materials':sorted(factory['materials']),'unused_declared_palette_need_not_persist':True}
  case('V20-NEW',fresh)
  def vis():
   names=sorted(o.name for o in bpy.context.scene.objects if o.type=='MESH'and not o.hide_render and o.visible_get());expect=sorted((set(base['visible_mesh_names'])-{v['object']for v in r['allowed_visibility_changes']})|set(factory['mesh_names']))
   C.require(names==expect==m['render_target_objects'],'whole-palace visible target set differs')
   return {'visible_mesh_count':len(names),'global_hide_viewport_never_authorized':True}
  case('V20-VISIBILITY',vis)
  def export():
   C.require(set(actual)==set(factory['mesh_names']),'partial saved WORLD cannot export')
   record={'schema':'v20.shouan79.actual-saved-world/1','capture_kind':'actual_saved_native','native_opened':True,'native_saved':False,'native_open_mainfile_calls':1,'saved_native_read_only':True,'producer_or_builder_imported':False,'geometry_constructed':False,'native_sha256':a.native_sha256,'manifest_sha256':a.manifest_sha256,'readiness_sha256':a.readiness_sha256,'factory_state_sha256':r['protected_inputs'][r['bindings']['factory_state']],'source_part_id':C.SOURCE_ID,'subject_id':'shouan79','profile':factory['profile'],'mesh_names':factory['mesh_names'],'root_names':factory['root_names'],'roles':factory['roles'],'meshes':actual,'roots':{n:h['nonmesh_state'](bpy.data.objects[n])for n in factory['root_names']},'materials':{n:h['material_state'](bpy.data.materials[n])for n in factory['materials']},'actual_source_actor_raw_and_evaluated':None,'source_visibility_changes':r['allowed_visibility_changes'],'saved_complete_domain_CPU':'pending','human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0}
   record['actual_source_actor_raw_and_evaluated']=capture_saved_source_for_cpu(bpy,h,E)
   C.write_new(out/'actual-saved-new-world.json',record);return {'complete_exported_meshes':len(actual),'source_full11point_actor_exported':True,'CPU_replay_still_required':True}
  case('V20-EXPORT',export)
  def final():
   for rel,digest in r['protected_inputs'].items():C.require(C.sha(C.pinned_path(rel))==digest,'immutable input changed')
   C.require(C.sha(a.native)==a.native_sha256 and C.sha(a.manifest)==a.manifest_sha256 and C.sha(snap)==m['base_snapshot']['sha256']and C.sha(a.readiness)==a.readiness_sha256,'saved/readiness/snapshot bytes changed')
   C.require(Path(bpy.data.filepath).resolve()==a.native.resolve(),'reader selected native changed')
   changed={v['object']:v['after']for v in r['allowed_visibility_changes']}
   for n,row in base['meshes'].items():C.require(h['visibility'](bpy.data.objects[n])==changed.get(n,row['visibility']),'final old visibility leaked')
   for n in factory['mesh_names']:C.require(h['visibility'](bpy.data.objects[n])==factory['meshes'][n]['visibility'],'final new visibility leaked')
   return {'native_saved':False,'all_pinned_bytes_unchanged':True,'temporary_own_hide_restored_by_frozen_finally':True}
  case('V20-FINAL',final)
 except BaseException:
  if not checks or checks[-1]['passed']:checks.append({'id':'V20-PREFLIGHT-OR-RUNTIME','passed':False,'traceback':traceback.format_exc()})
 finally:
  report={'schema':'v20.independent-saved-native-audit/1','checks':checks,'passed':sum(x['passed']for x in checks),'failed':sum(not x['passed']for x in checks),'native_opened':opened,'native_saved':False,'native_open_mainfile_calls':int(opened),'producer_or_builder_imported':False,'geometry_constructed':False,'human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0,'saved_complete_domain_CPU':'pending'}
  C.write_new(out/'actual-saved-tests.json',report);print('SAVED-V20',report['passed'],report['failed'],flush=True)
 if report['failed']:raise SystemExit(1)

if __name__=='__main__':main()
