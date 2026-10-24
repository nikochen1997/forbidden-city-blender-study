"""V20 native-v2 pure contract and read-only state capture; visibility snapshots fixed. No producer/builder imports.

The saved reader imports only this module and frozen AST-extracted state helpers.
No bpy import, file opening, geometry construction, or writes occur on import.
"""
import ast,hashlib,importlib.util,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
BASE_REL='outputs/紫禁城现存格局-乾隆花园第十九阶段-局部进度/紫禁城现存格局-乾隆花园第十九阶段-局部进度.blend'
BASE_SHA='c2e981596258654e9f15ff9ab60f065d5b068a7f72b4a1cd39cf343203f1f125'
BASE_MANIFEST_REL='outputs/紫禁城现存格局-乾隆花园第十九阶段-局部进度/restoration-manifest.json'
BASE_MANIFEST_SHA='492b1882d4413a17a2a0613a3b68eac11f85fbd710ead55b69910386918d8b58'
SOURCE_ACTOR='way-40624979-p0_原轮廓主体'
SOURCE_ID='way-40624979-p0'
BASE_MESHES=14976;BASE_SOURCES=2845;BASE_CAMERAS=136
EVAL_REL='work/restoration-v19/saved-audit/evaluated_geometry_fingerprint.py'
EVAL_SHA='d9eda9b306d5d27f25ab9c21e30c9173ac01ad6084b974ecdcf94aad9808a97e'
HELPERS={'work/build_forbidden_city_restoration_v11.py':'1ccce3fcca040d311f6c48fc52cd38cf053d484e627e20f03ad2f4a1c9eeb130','work/build_forbidden_city_restoration_v15.py':'9fe1cf52edcf77508c2271ec150d58a7e79266ee09ebd2c664e8f553296935b1'}
CHECK_ROLES={'factory','source_domains','roof_contacts','support','boolean_openings'}
ROLE_SEMANTICS={
 'factory':{'actual_factory_build_completed':True,'full_raw_evaluated_material_profile_capture':True,'native_opened':False,'native_saved':False},
 'source_domains':{'complete_triangle_domains_checked':True,'all_components_and_holes_checked':True,'bbox_or_point_only':False,'all_new_outside_source_rejected':True},
 'roof_contacts':{'complete_bottom_and_roof_surfaces_checked':True,'bbox_or_point_only':False,'gap_and_penetration_limits_explicit':True},
 'support':{'complete_named_support_graph_checked':True,'complete_support_contact_domains_checked':True,'engineering_load_capacity_claimed':False},
 'boolean_openings':{'actual_boolean_copy_contract_checked':True,'full_actual_opening_geometry_checked':True,'original_operands_preserved':True}}

FACTORY_ROLES={'roofs','supports','openings','reference_floor','source_remainders'}
MESH_KEYS={'name','role','raw_vertices','raw_edges','raw_faces','raw_face_material_indices','matrix_world','vertices_world','faces','triangles_with_material_index','material_slots','material_slot_links','properties','relations','visibility','object_color'}

def require(ok,msg):
 if not ok:raise AssertionError(msg)
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))
def equal(a,b):return canonical(a)==canonical(b)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write_new(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as f:f.write(canonical(v)+'\n')
def pinned_path(rel):
 require(isinstance(rel,str) and rel,'empty path')
 p=(ROOT/rel).resolve();require(p.is_relative_to(ROOT),'path escapes workspace');return p
def get(v,path):
 require(isinstance(path,list) and bool(path),'nonempty JSON selector required')
 for k in path:v=v[k]
 return v
def plain(v):
 if v is None or isinstance(v,(str,bool,int)):return v
 if isinstance(v,float):require(math.isfinite(v),'nonfinite property');return v
 if hasattr(v,'to_dict'):return plain(v.to_dict())
 if isinstance(v,dict):return {str(k):plain(x) for k,x in v.items()}
 if hasattr(v,'to_list'):return plain(v.to_list())
 if isinstance(v,(list,tuple)):return [plain(x) for x in v]
 raise TypeError('unsupported property type '+type(v).__name__)
def zero_scope(d):
 for k in ('third_party_cost','paid_service_calls'):require(type(d[k])is int and d[k]==0,'strict integer zero: '+k)
 require(d['human_approval']=='pending' and d['whole_city_complete'] is False,'scope promotion')
def load_helpers():
 ns={'hashlib':hashlib,'json':json}
 for (rel,h),names in zip(HELPERS.items(),[{'visibility','material_state','mesh_fingerprint'},{'nonmesh_state','mesh_relations','camera_state'}]):
  p=pinned_path(rel);require(sha(p)==h,'frozen helper changed: '+rel)
  nodes=[n for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)and n.name in names]
  require({n.name for n in nodes}==names,'missing frozen pure functions');exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),ns)
 return ns
def load_eval():
 p=pinned_path(EVAL_REL);require(sha(p)==EVAL_SHA,'frozen eval helper changed')
 s=importlib.util.spec_from_file_location('v20_frozen_eval',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def validate_factory(f):
 require(f['schema']=='v20.shouan79.actual-factory-state/1' and f['capture_kind']=='actual_blender_factory','not actual canonical factory state')
 require(f['native_opened'] is False and f['native_saved'] is False,'factory must be isolated actual build')
 zero_scope(f);require(f['source_part_id']==SOURCE_ID and f['subject_id']=='shouan79','factory subject differs')
 names=f['mesh_names'];roots=f['root_names'];require(names and len(names)==len(set(names)) and set(names)==set(f['meshes']),'complete unique factory mesh names required')
 require(roots and len(roots)==len(set(roots)) and set(roots)==set(f['roots']) and not set(names)&set(roots),'complete distinct roots required')
 require(set(f['roles'])==FACTORY_ROLES,'factory role inventory differs')
 for role,nn in f['roles'].items():require(isinstance(nn,list)and len(nn)==len(set(nn))and set(nn)<=set(names),'invalid factory role: '+role)
 require(f['roles']['roofs'] and f['roles']['supports'] and f['roles']['openings'] and f['roles']['reference_floor'],'roof/support/opening/full-source-reference actual roles required')
 used=set()
 for name,row in f['meshes'].items():
  require(set(row)==MESH_KEYS and row['name']==name,'mesh capture schema differs: '+name)
  vv=row['vertices_world'];rv=row['raw_vertices'];require(vv and len(rv)==len(vv),'actual full vertices missing')
  require(all(len(v)==3 and all(isinstance(x,(int,float))and not isinstance(x,bool)and math.isfinite(x)for x in v)for v in vv+rv),'invalid full vertices')
  require(len(row['matrix_world'])==4 and all(len(x)==4 and all(isinstance(v,(int,float))and not isinstance(v,bool)and math.isfinite(v)for v in x)for x in row['matrix_world']),'matrix size/finite values')
  for edge in row['raw_edges']:require(len(edge)==2 and edge[0]!=edge[1]and all(type(i)is int and 0<=i<len(rv)for i in edge),'invalid raw edge')
  require(row['faces']==row['raw_faces'] and len(row['raw_face_material_indices'])==len(row['raw_faces']),'raw/eval full face mismatch')
  n=len(vv);slots=row['material_slots'];require(slots and len(row['material_slot_links'])==len(slots)and set(row['material_slot_links'])=={'DATA'},'actual DATA materials required')
  for face in row['raw_faces']:require(len(face)>=3 and all(type(i)is int and 0<=i<n for i in face),'invalid face indices')
  for tri,mi in row['triangles_with_material_index']:require(len(tri)==3 and len(set(tri))==3 and all(type(i)is int and 0<=i<n for i in tri)and type(mi)is int and 0<=mi<len(slots),'invalid triangles/material')
  require(row['triangles_with_material_index'],'no actual triangles')
  require(all(type(mi)is int and 0<=mi<len(slots)for mi in row['raw_face_material_indices']),'invalid raw material index')
  require(row['relations']['parent']in roots and row['relations']['modifiers']==[] and row['relations']['shape_keys_name']is None,'factory deformed/wrong owner')
  props=row['properties'];zero_scope(props);require(props['restoration_v20_subject']=='shouan79'and props['dimension_status']=='unmeasured_study'and props['absolute_accuracy_claim']is False,'new metadata scope')
  require(not props.get('source_building_id')and props.get('source_reference_part_id')==SOURCE_ID,'new mesh source attribution differs')
  require(row['visibility']=={'hide_render':False,'global_hide_viewport':False,'hide_get':False},'new factory geometry hidden')
  used.update(slots)
 require(None not in used and used==set(f['materials']),'actual used materials only; unused palette entries must not be mandatory')
 require(isinstance(f['declared_material_names'],list)and len(f['declared_material_names'])==len(set(f['declared_material_names']))and used<=set(f['declared_material_names']),'declared palette inventory required')
 for name,row in f['roots'].items():
  require(row['type']=='EMPTY'and row['data']is None and row['parent']is None,'actual root type/data/parent differs')
  pp=row['custom_properties'];require(pp.get('restoration_v20_subject')=='shouan79'and pp.get('dimension_status')=='unmeasured_study'and pp.get('third_party_cost')=='0'and pp.get('paid_service_calls')=='0'and pp.get('human_approval')=='pending'and pp.get('whole_city_complete')=='False'and pp.get('absolute_accuracy_claim')=='False','root unmeasured/scope flags missing')
 require(f['profile']['source_part_id']==SOURCE_ID and f['profile']['dimension_status']=='unmeasured_study','profile source/unmeasured status differs')
 return True

def validate_visibility(mapping):
 require(isinstance(mapping,list)and len(mapping)<=1,'only one qualified source exception possible')
 for row in mapping:
  require(set(row)=={'object','before','after'} and row['object']==SOURCE_ACTOR,'only source79 visibility may differ')
  require(row['before']=={'hide_render':False,'global_hide_viewport':False,'hide_get':False},'wrong source79 starting visibility')
  require(row['after']=={'hide_render':True,'global_hide_viewport':False,'hide_get':True},'only own hide/render toggle allowed')
 return True

def check_report(desc,docs,protected,expected_coverage,factory_sha,role=None):
 for k in ('report','terminal_receipt'):require(desc[k]in protected and desc[k]in docs,'unbound report/terminal: '+k)
 report=docs[desc['report']];receipt=docs[desc['terminal_receipt']]
 p=get(report,desc['passed_path']);bad=get(report,desc['failed_path']);n=desc['expected_pass_count']
 require(type(n)is int and n>0 and type(p)is int and p==n and type(bad)is int and bad==0,'actual report counts fail')
 exitcode=get(receipt,desc['terminal_exit_code_path']);require(type(exitcode)is int and exitcode==0,'actual terminal exit required')
 require(get(receipt,desc['terminal_confirmed_path'])is True,'terminal not confirmed complete')
 require(isinstance(desc['terminal_handle'],str)and bool(desc['terminal_handle']),'actual terminal handle not recorded')
 require(get(report,desc['factory_sha256_path'])==factory_sha,'check not on exact actual factory state')
 require(get(report,desc['coverage_names_path'])==sorted(expected_coverage),'actual complete role coverage differs')
 for x in desc['assertions']:require(equal(get(report,x['path']),x['equals']),'required actual report assertion differs')
 require(desc['assertions'],'actual semantic assertions required; count alone insufficient')
 if role is not None:
  require(set(desc['semantic_paths'])==set(ROLE_SEMANTICS[role]),'missing actual semantic proof selectors: '+role)
  for k,wanted in ROLE_SEMANTICS[role].items():require(equal(get(report,desc['semantic_paths'][k]),wanted),'actual semantic proof failed: '+role+'/'+k)

def validate_ready_documents(r,docs):
 require(r['schema']=='v20.shouan79.required-readiness/1','wrong readiness schema');zero_scope(r)
 require(r['stage_subject']=='shouan79'and r['south_of_wumen_expansion']is False,'stage/scope differs')
 require(r['base_native_sha256']==BASE_SHA and r['base_manifest_sha256']==BASE_MANIFEST_SHA,'base pins differ')
 require(r['base_mesh_count']==BASE_MESHES and r['base_source_count']==BASE_SOURCES and r['base_camera_count']==BASE_CAMERAS,'base inventory differs')
 require(isinstance(r['collection_name'],str)and r['collection_name'].startswith('restoration_v20_'),'new explicit collection required')
 require(isinstance(r['model_file'],str)and Path(r['model_file']).name==r['model_file']and r['model_file'].endswith('.blend'),'invalid output filename')
 require(set(r['checks'])==CHECK_ROLES,'missing actual factory/domain/roof/support/Boolean group')
 require(r['builder_callable']=='build_stage20','only declared scene builder API accepted')
 roles=r['bindings'];require({'factory_state','source_probe','source_domain_report','profile','source_qualification','builder_module'}<=set(roles),'missing core input binding')
 require(all(p in r['protected_inputs']and p in docs for k,p in roles.items()if k!='builder_module'),'unbound input document')
 require(roles['builder_module']in r['protected_inputs'],'unbound builder')
 f=docs[roles['factory_state']];validate_factory(f);fh=r['protected_inputs'][roles['factory_state']]
 require(equal(f['profile'],docs[roles['profile']]),'profile/factory differs')
 sq=docs[roles['source_qualification']];require(sq['qualified_for_conditional_source_bounded_study']is True and sq['subject_source_id']==SOURCE_ID,'source-bounded qualification missing')
 sr=docs[roles['source_domain_report']];require(sr['summary']=={'passed':7,'failed':0}and sr['native_sha256']==BASE_SHA,'actual source7/0 required')
 probe=docs[roles['source_probe']];require(probe['native_sha256']==BASE_SHA and SOURCE_ACTOR in probe['actor_evidence'],'actual source probe required')
 expected={'factory':set(f['mesh_names']),'source_domains':set(f['mesh_names']),'roof_contacts':set(f['roles']['roofs'])|set(f['roles']['supports']),'support':set(f['roles']['supports']),'boolean_openings':set(f['roles']['openings'])}
 for role in sorted(CHECK_ROLES):check_report(r['checks'][role],docs,r['protected_inputs'],expected[role],fh,role)
 validate_visibility(r['allowed_visibility_changes'])
 if r['allowed_visibility_changes']:
  desc=r['visibility_qualification'];require(desc is not None,'no exact source79 display qualification')
  check_report(desc,docs,r['protected_inputs'],{SOURCE_ACTOR},fh)
  rep=docs[desc['report']]
  require(get(rep,desc['full_source_remainder_preserved_path'])is True,'complete source/remainder preservation not qualified')
 else:require(r['visibility_qualification']is None,'unused display permission must not silently carry over')
 return f

def load_ready(path,digest):
 path=Path(path).resolve();require(sha(path)==digest,'readiness SHA changed');r=read(path);docs={}
 protected=r['protected_inputs'];require(isinstance(protected,dict)and protected,'protected file map required')
 for rel,h in protected.items():
  p=pinned_path(rel);require(isinstance(h,str)and len(h)==64 and sha(p)==h,'protected bytes changed: '+rel)
  if p.suffix.lower()=='.json':docs[rel]=read(p)
 for rel,h in {BASE_REL:BASE_SHA,BASE_MANIFEST_REL:BASE_MANIFEST_SHA,EVAL_REL:EVAL_SHA,**HELPERS}.items():require(protected.get(rel)==h,'mandatory frozen input unbound: '+rel)
 for rel in r['builder_import_files']:require(rel in protected and pinned_path(rel).suffix=='.py','unbound builder import file')
 require(r['bindings']['builder_module']in r['builder_import_files'],'builder module missing import inventory')
 for name in ('stage20_contract.py','produce_city_progress_v20.py','read_saved_city_v20.py'):
  p=Path(__file__).resolve().parent/name;rel=str(p.relative_to(ROOT));require(protected.get(rel)==sha(p),'unbound current native contract/producer/reader: '+name)
 f=validate_ready_documents(r,docs);return r,docs,f

def capture_mesh(obj,graph,helpers,E):
 require(obj.type=='MESH'and not obj.modifiers and obj.data.shape_keys is None,'capture only modifier-free meshes')
 ev=E.capture_evaluated(obj,graph)
 return {'name':obj.name,'role':obj.get('semantic_role'),'raw_vertices':[list(v.co)for v in obj.data.vertices],'raw_edges':[list(e.vertices)for e in obj.data.edges],'raw_faces':[list(p.vertices)for p in obj.data.polygons],'raw_face_material_indices':[p.material_index for p in obj.data.polygons],'matrix_world':[list(r)for r in obj.matrix_world],**ev,'material_slot_links':[s.link for s in obj.material_slots],'properties':plain(dict(obj.items())),'relations':helpers['mesh_relations'](obj),'visibility':helpers['visibility'](obj),'object_color':list(obj.color)}

def capture_base(bpy,h,E):
 scene=bpy.context.scene;objects=[o for o in scene.objects if o.type=='MESH'];old={}
 original_visibility={o.name:h['visibility'](o)for o in objects}
 require(len(objects)==BASE_MESHES and sum(bool(o.get('source_building_id'))for o in objects)==BASE_SOURCES,'base mesh/source count differs')
 with E.evaluated_batch(objects,bpy)as graph:
  for i,o in enumerate(objects):
   old[o.name]={'visibility':original_visibility[o.name],'fingerprint':h['mesh_fingerprint'](o),'evaluated_fingerprint':E.evaluated_fingerprint(E.capture_evaluated(o,graph)),'relations':h['mesh_relations'](o)}
   if i%3000==0:print('V20_BASE_CAPTURE',i,flush=True)
 cameras={o.name:{'object':h['nonmesh_state'](o),'camera':h['camera_state'](o)}for o in bpy.data.objects if o.type=='CAMERA'}
 require(len(cameras)==BASE_CAMERAS,'base camera count differs')
 return {'meshes':old,'nonmeshes':{o.name:h['nonmesh_state'](o)for o in bpy.data.objects if o.type!='MESH'},'materials':{m.name:h['material_state'](m)for m in bpy.data.materials},'cameras':cameras,'scene_camera':scene.camera.name if scene.camera else None,'visible_mesh_names':sorted(o.name for o in objects if not o.hide_render and o.visible_get())}

def compare_base(bpy,base,mapping,h,E):
 allowed={r['object']:r for r in mapping};require(set(base['meshes'])<=set(bpy.context.scene.objects.keys()),'old mesh missing')
 def check_saved_visibility(phase):
  for n,old in base['meshes'].items():
   wanted=allowed[n]['after']if n in allowed else old['visibility']
   require(h['visibility'](bpy.data.objects[n])==wanted,'old saved visibility changed '+phase+': '+n)
 check_saved_visibility('before evaluated batch')
 try:
  with E.evaluated_batch([bpy.data.objects[n]for n in base['meshes']],bpy)as graph:
   for i,(n,old)in enumerate(base['meshes'].items()):
    o=bpy.data.objects[n];require(o.type=='MESH'and h['mesh_fingerprint'](o)==old['fingerprint'],'old raw/material/matrix changed: '+n)
    require(E.evaluated_fingerprint(E.capture_evaluated(o,graph))==old['evaluated_fingerprint'],'old complete evaluated WORLD changed: '+n)
    require(equal(h['mesh_relations'](o),old['relations']),'old relations changed: '+n)
    if i%3000==0:print('V20_OLD_GUARD',i,flush=True)
 finally:
  check_saved_visibility('after evaluated batch/finally')
 for n,s in base['nonmeshes'].items():require(n in bpy.data.objects and equal(h['nonmesh_state'](bpy.data.objects[n]),s),'old nonmesh changed: '+n)
 for n,s in base['materials'].items():require(n in bpy.data.materials and equal(h['material_state'](bpy.data.materials[n]),s),'old full material changed: '+n)
 require({o.name for o in bpy.data.objects if o.type=='CAMERA'}==set(base['cameras']),'camera population changed')
 for n,s in base['cameras'].items():require(equal(h['nonmesh_state'](bpy.data.objects[n]),s['object'])and equal(h['camera_state'](bpy.data.objects[n]),s['camera']),'old camera transform/properties changed')
 require((bpy.context.scene.camera.name if bpy.context.scene.camera else None)==base['scene_camera'],'active camera changed')
 return True

def compare_new(bpy,base,factory,h,E):
 names=set(factory['mesh_names']);roots=set(factory['root_names']);scene_mesh={o.name for o in bpy.context.scene.objects if o.type=='MESH'}
 require(scene_mesh-set(base['meshes'])==names and len(scene_mesh)==BASE_MESHES+len(names),'new full mesh ownership/count differs')
 require({o.name for o in bpy.data.objects if o.type!='MESH'}==set(base['nonmeshes'])|roots,'new unaccounted nonmesh/camera')
 require(sum(bool(o.get('source_building_id'))for o in bpy.context.scene.objects if o.type=='MESH')==BASE_SOURCES,'original source population differs')
 actual={}
 with E.evaluated_batch([bpy.data.objects[n]for n in sorted(names)],bpy)as graph:
  for n in sorted(names):actual[n]=capture_mesh(bpy.data.objects[n],graph,h,E);require(equal(actual[n],factory['meshes'][n]),'actual factory/new complete geometry/state differs: '+n)
 for n in roots:require(equal(h['nonmesh_state'](bpy.data.objects[n]),factory['roots'][n]),'new root full state differs: '+n)
 used=set(factory['materials']);newmat=set(bpy.data.materials.keys())-set(base['materials'])
 require(used<=newmat<=set(factory['declared_material_names']),'used actual material missing or unexpected saved material; unused declared palette entries need not persist')
 for n in used:require(equal(h['material_state'](bpy.data.materials[n]),factory['materials'][n]),'actual full material state differs: '+n)
 return actual


def verify_source_probe(bpy,probe,h,E):
 o=bpy.data.objects[SOURCE_ACTOR];r=probe['actor_evidence'][SOURCE_ACTOR]
 with E.evaluated_batch([o],bpy)as graph:
  ev=E.capture_evaluated(o,graph)
  require(equal(ev,r['evaluated_complete_payload']),'actual complete source WORLD differs from pinned probe')
 require(equal([list(v.co)for v in o.data.vertices],r['raw_vertices'])and equal([list(e.vertices)for e in o.data.edges],r['raw_edges'])and equal([list(p.vertices)for p in o.data.polygons],r['raw_faces'])and equal([p.material_index for p in o.data.polygons],r['raw_face_material_indices'])and equal([list(x)for x in o.matrix_world],r['matrix_world'])and equal(plain(dict(o.items())),r['custom_properties']),'source raw/matrix/provenance differs from actual probe')
 require(len(r['complete_source_polygon_world'])==11 and r['complete_source_holes_world']==[] and r['source_height_is_measured']is False,'complete source79 or height status differs')
 return True

def capture_factory_state(bpy,profile,result,roles,declared_material_names):
 """Capture only after the root's real isolated build. Does not construct/write."""
 require(not bpy.data.filepath,'factory capture must not open any native')
 require(set(result)=={'mesh_objects','root_objects'},'exact real result arrays required')
 names=[o.name for o in result['mesh_objects']];roots=[o.name for o in result['root_objects']]
 require({o.name for o in bpy.context.scene.objects if o.type=='MESH'}==set(names),'isolated factory has unaccounted mesh')
 h=load_helpers();E=load_eval();meshes={}
 with E.evaluated_batch(result['mesh_objects'],bpy)as graph:
  for o in result['mesh_objects']:meshes[o.name]=capture_mesh(o,graph,h,E)
 used={n for m in meshes.values()for n in m['material_slots']}
 f={'schema':'v20.shouan79.actual-factory-state/1','capture_kind':'actual_blender_factory','native_opened':False,'native_saved':False,'subject_id':'shouan79','source_part_id':SOURCE_ID,'profile':profile,'blender_version':bpy.app.version_string,'blender_build_hash':bpy.app.build_hash.decode(),'mesh_names':names,'root_names':roots,'meshes':meshes,'roots':{o.name:h['nonmesh_state'](o)for o in result['root_objects']},'materials':{n:h['material_state'](bpy.data.materials[n])for n in sorted(used)},'declared_material_names':list(declared_material_names),'roles':roles,'human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0}
 validate_factory(f);return f
