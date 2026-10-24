"""Pure CPU readiness assembly from exact real reports and observed receipts.

No Blender, scene-builder import, native write, count invention, or permission
promotion. Any missing/red/cross-linked input refuses final readiness.
"""
import argparse,copy,hashlib,importlib.util,json,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
NATIVE='work/city-completion-v20/native-v2'
NATIVE_PINS={'stage20_contract.py':'af118e605cab9df1def2ec19424bd94b77daac9f26eb57b2b81f0c159a544e17','produce_city_progress_v20.py':'619761f6374861b60ed451397cb894de65341e13f4b20b11144a1fcbaeb8033c','read_saved_city_v20.py':'e4c31186a41d162ddfbcbcc46a3060dbe068365679491bb64f18e8d268bedfa0'}
BINDING_SHA='f995bac5b5e806ea190fef953ba16e86f33481e047449487c2bde971cf6da87d'
INPUT_ROLES={'binding','factory_state','actual_world','factory_tests','factory_execution','formal_cpu','formal_cpu_execution','factory_acceptance','acceptance_execution','display_qualification','display_execution','root_display_choice'}
CORE_SHA='3f2e4464d1983777b50a96a952c00d36eff9ddb9ecf99b5f506d9293e730c535'
DISPLAY_PINS={'work/city-completion-v20/source-display-qualification/check_source79_display.py':CORE_SHA,'work/city-completion-v20/source-display-qualification/check_source79_display_v3.py':'6194d3d3aed8e3b88cf9c8de2d6308f9ea457702eb67c68e490ba8bfabbacbe9','work/city-completion-v20/source-display-qualification/projected_domain_v3.py':'75cbd87c9202775e293c4ef74feafd4e4851c5a684be2020b94421e3685b5e49','work/city-completion-v20/source-display-qualification/capture_chain_v2.py':'f7459f47a06b225fc50297e30ff7daff491bb4d012478e5cd3d4b9915923059f'}
CPU_PINS={'work/city-completion-v20/formal-factory/check_actual_production_v4.py':'e9495036de1015b7f521ff44876ee14470ae5c5272a70efc1a9f2b1f4a91ed5d','work/city-completion-v20/formal-factory/centered_source_projection.py':'c95194f00001e5b82236ba0e97ed93eee07852a7499201c1002689309a40d6b3'}
def require(ok,msg):
 if not ok:raise AssertionError(msg)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def path(rel):
 require(isinstance(rel,str)and rel,'nonempty path required');p=(ROOT/rel).resolve();require(p.is_relative_to(ROOT),'path outside workspace');return p
def rel(p):return str(Path(p).resolve().relative_to(ROOT))
def load_contract():
 for n,h in NATIVE_PINS.items():require(sha(path(NATIVE+'/'+n))==h,'frozen active native-v2 changed: '+n)
 p=path(NATIVE+'/stage20_contract.py');s=importlib.util.spec_from_file_location('readiness_native_v2',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def green(d,label):
 s=d['summary'];require(type(s['passed'])is int and s['passed']>0 and type(s['failed'])is int and s['failed']==0,label+' not positive strict-integer green')
 if 'checks'in d:require(s['passed']==len(d['checks'])and all(x['passed']is True for x in d['checks']),label+' check rows not all true')
 return s['passed']
def terminal(r,label):
 require(type(r['terminal_exit_code'])is int and r['terminal_exit_code']==0 and r['terminal_confirmed_complete']is True,label+' terminal not confirmed zero')
 sid=r.get('session_id');chunk=r.get('terminal_chunk');require(type(sid)is int and sid>0 and isinstance(chunk,str)and chunk,label+' observed session/chunk required')
 return 'session:'+str(sid)+' chunk:'+chunk
def report_receipt(report,receipt,report_rel,report_sha,factory_sha,label):
 green(report,label);terminal(receipt,label)
 require(receipt['report']==report_rel and receipt['report_sha256']==report_sha,label+' receipt/report path or SHA cross-link differs')
 require(receipt['factory_state_sha256']==factory_sha and receipt['summary']==report['summary'],label+' receipt canonical SHA or counts differ')

def validate_chains(d,records,C):
 b=d['binding'];f=d['factory_state'];w=d['actual_world'];ft=d['factory_tests'];fe=d['factory_execution'];cpu=d['formal_cpu'];ce=d['formal_cpu_execution'];fa=d['factory_acceptance'];ae=d['acceptance_execution'];disp=d['display_qualification'];de=d['display_execution']
 fh=records['factory_state']['sha256'];wh=records['actual_world']['sha256'];bh=records['binding']['sha256'];ch=records['formal_cpu']['sha256']
 require(bh==BINDING_SHA and b['schema']=='v20-shouan79-formal-factory-binding/2','exact reviewed binding02 required')
 C.validate_factory(f)
 require(w['factory_state_sha256']==fh and w['binding_sha256']==bh,'WORLD chain differs')
 require(len(w['objects'])==len(f['mesh_names'])and {r['name']for r in w['objects']}==set(f['mesh_names']),'WORLD complete mesh names differ')
 for row in w['objects']:require(C.equal({k:row[k]for k in C.MESH_KEYS},f['meshes'][row['name']]),'WORLD complete canonical differs: '+row['name'])
 require(C.equal(f['profile'],read(path(b['single_profile']))),'single profile differs')
 green(ft,'factory actual capture');terminal(fe,'actual factory')
 require(fe['factory_state_sha256']==fh and fe['factory_tests_sha256']==records['factory_tests']['sha256']and fe['actual_readout_sha256']==wh and fe['actual_mesh_count']==len(f['mesh_names']),'real factory receipt export SHA/count chain differs')
 require(ft['actual_factory_build_completed']is True and ft['full_raw_evaluated_material_profile_capture']is True and ft['binding_sha256']==bh,'real factory capture incomplete')
 successful=[x for x in ft['checks']if x['passed']is True and x.get('factory_state_sha256')==fh and x.get('actual_mesh_count')==len(f['mesh_names'])and x.get('full_raw_evaluated_material_profile_capture')is True]
 require(len(successful)==1,'canonical factory capture success row missing; top runner SHA is not canonical')
 report_receipt(cpu,ce,records['formal_cpu']['path'],ch,fh,'formal full CPU')
 require(cpu['schema']=='v20-source-bound-shouan-actual-complete-CPU/1'and cpu['summary']=={'passed':13,'failed':0},'reviewed complete13 CPU required')
 require(cpu['factory_state_sha256']==fh and cpu['actual_readout_sha256']==wh and cpu['binding_sha256']==bh,'formal CPU export chain differs')
 require(cpu['checker_sha256']==CPU_PINS['work/city-completion-v20/formal-factory/check_actual_production_v4.py']and ce['checker_sha256']==cpu['checker_sha256'],'formal checker SHA differs')
 require(cpu['normalization_inputs_sha256']=={k:v for k,v in CPU_PINS.items()if k.endswith('centered_source_projection.py')},'formal common-origin helper SHA differs')
 require(cpu['actual_coverage_names']==sorted(f['mesh_names']),'formal CPU omitted actual mesh')
 for role,want in C.ROLE_SEMANTICS.items():
  if role=='factory':continue
  require(C.equal(cpu['semantic_proofs'][role],want),'formal semantic proof differs: '+role)
 report_receipt(fa,ae,records['factory_acceptance']['path'],records['factory_acceptance']['sha256'],fh,'factory acceptance aggregation')
 require(fa['schema']=='v20-actual-factory-canonical-acceptance/1'and fa['actual_coverage_names']==sorted(f['mesh_names']),'factory acceptance coverage differs')
 require(ae['actual_factory_terminal_receipt']==records['factory_execution']['path']and ae['new_Blender_execution']is False,'aggregation is not actual Blender terminal')
 for role in ('factory_state','factory_tests','formal_cpu','binding'):
  require(fa['evidence_inputs_sha256'].get(str(path(records[role]['path'])))==records[role]['sha256'],'acceptance evidence differs: '+role)
 report_receipt(disp,de,records['display_qualification']['path'],records['display_qualification']['sha256'],fh,'source display qualification')
 require(disp['schema']=='v20.source79-reversible-progress-display-qualification/3'and disp['factory_state_sha256']==fh and disp['actual_world_sha256']==wh and disp['actual_formal_CPU_sha256']==ch and disp['binding_sha256']==bh,'display formal chain differs')
 require(disp['checker_sha256']==DISPLAY_PINS['work/city-completion-v20/source-display-qualification/check_source79_display_v3.py']and de['checker_sha256']==disp['checker_sha256'],'display checker SHA differs')
 require(de['actual_world_sha256']==wh,'display receipt WORLD differs')
 for k,v in {'eligible_for_reversible_progress_visibility':True,'full_source_remainder_preserved_in_original_actor_and_actual_full_reference_slab':True,'human_permission_granted_by_this_package':False,'historical_absolute_accuracy_approved':False,'original_volume_rebuilt':False,'source95_97_or_other_source_changes_allowed':False,'combined_saved_native_verified_here':False}.items():require(disp[k]is v,'display scope differs: '+k)
 require(disp['coverage_names']==[C.SOURCE_ACTOR],'display coverage must only source79')
 audit=disp['analysis']['projection_frame_and_full_validity'];require(audit['exact_roundtrip_max_error_m']==0 and audit['triangle_XY_cross_changed_count']==0 and len(audit['all_actual_mesh_complete_projection_validity'])==len(f['mesh_names'])and all(x['complete_projection_valid']is True for x in audit['all_actual_mesh_complete_projection_validity']),'display complete centered validity missing')
 return True

def descriptor(report_rel,receipt_rel,report,receipt,coverage,semantic=None):
 out={'report':report_rel,'terminal_receipt':receipt_rel,'passed_path':['summary','passed'],'failed_path':['summary','failed'],'expected_pass_count':report['summary']['passed'],'terminal_exit_code_path':['terminal_exit_code'],'terminal_confirmed_path':['terminal_confirmed_complete'],'terminal_handle':terminal(receipt,report_rel),'factory_sha256_path':['factory_state_sha256'],'coverage_names_path':coverage,'assertions':[{'path':['native_saved'],'equals':False}]}
 if semantic is not None:out['semantic_paths']=semantic
 return out

def assemble(request,request_path,request_sha):
 C=load_contract();require(request['schema']=='v20.native-v2-readiness-inputs/1','wrong request schema')
 records=request['inputs'];require(set(records)==INPUT_ROLES,'complete explicit input role set required')
 protected={};d={}
 def pin(r,h):
  require(isinstance(h,str)and len(h)==64 and sha(path(r))==h,'required input bytes changed: '+r)
  require(r not in protected or protected[r]==h,'conflicting SHA for '+r);protected[r]=h
 for key,item in records.items():
  require(set(item)=={'path','sha256'},'path/SHA record required: '+key);pin(item['path'],item['sha256']);d[key]=read(path(item['path']))
 b=d['binding'];require(records['binding']['sha256']==BINDING_SHA,'binding02 SHA differs')
 for r,h in b['inputs_sha256'].items():pin(r,h)
 for r,h in {**CPU_PINS,**DISPLAY_PINS,**C.HELPERS,C.EVAL_REL:C.EVAL_SHA,C.BASE_REL:C.BASE_SHA,C.BASE_MANIFEST_REL:C.BASE_MANIFEST_SHA,**{NATIVE+'/'+n:h for n,h in NATIVE_PINS.items()}}.items():pin(r,h)
 for root,key in [('formal_cpu','inputs_sha256'),('formal_cpu','normalization_inputs_sha256'),('factory_acceptance','evidence_inputs_sha256'),('display_qualification','fixed_inputs_sha256')]:
  for r,h in d[root][key].items():pin(rel(path(r)),h)
 for key in ('factory_execution','formal_cpu_execution','display_execution'):
  if 'stdout'in d[key]:pin(d[key]['stdout'],d[key]['stdout_sha256'])
 for r,h in request.get('extra_protected_inputs',{}).items():pin(r,h)
 pin(rel(request_path),request_sha);pin(rel(__file__),sha(__file__))
 validate_chains(d,records,C)
 choice=d['root_display_choice'];require(choice['schema']=='v20-root-technical-reversible-display-choice/1'and choice['actual_display_report']==records['display_qualification']['path']and choice['actual_display_report_sha256']==records['display_qualification']['sha256']and choice['actual_terminal_receipt']==records['display_execution']['path'],'root technical choice proof chain differs')
 require(choice['original79_geometry_must_remain']is True and choice['other_source_changes_allowed']is False and choice['human_approval']=='pending'and choice['whole_city_complete']is False,'root technical choice scope differs')
 require(C.equal(choice['allowed_visibility_changes'],request['allowed_visibility_changes']),'request mapping differs from explicit root choice')
 f=d['factory_state'];mapping=request['allowed_visibility_changes'];C.validate_visibility(mapping)
 if mapping:require(C.equal(mapping,d['display_qualification']['proposed_exact_visibility_changes']),'explicit root mapping differs from technical display qualification')
 ready={'schema':'v20.shouan79.required-readiness/1','status':'ACTUAL_REPORTS_AND_TERMINALS_BOUND_READY_FOR_NATIVE_V2_EXECUTION','stage_subject':'shouan79','base_native_sha256':C.BASE_SHA,'base_manifest_sha256':C.BASE_MANIFEST_SHA,'base_mesh_count':C.BASE_MESHES,'base_source_count':C.BASE_SOURCES,'base_camera_count':C.BASE_CAMERAS,'collection_name':b['collection_name'],'model_file':request['model_file'],'builder_callable':'build_stage20','bindings':{'builder_module':b['scene_builder'],'factory_state':records['factory_state']['path'],'source_probe':'work/city-completion-v20/shouan-registration/run-01/actual-source-actors.json','source_domain_report':'work/city-completion-v20/shouan-registration/run-01/actual-source-domain-CPU-01.json','profile':b['single_profile'],'source_qualification':'work/city-completion-v20/plan-registration/shouan79-source-bounded-qualification-proposal-02.json','profile_package':b['profile_package'],'palette':b['palette'],'formal_binding':records['binding']['path']},'builder_import_files':sorted(r for r in b['inputs_sha256']if r.endswith('.py')),'checks':{},'allowed_visibility_changes':copy.deepcopy(mapping),'visibility_qualification':None,'protected_inputs':protected,'human_approval':'pending','whole_city_complete':False,'south_of_wumen_expansion':False,'third_party_cost':0,'paid_service_calls':0,'generator_metadata':{'request':rel(request_path),'request_sha256':request_sha,'generator_sha256':sha(__file__),'active_native_code_directory':NATIVE,'original_canonical_contract_retained':b['native_contract'],'readiness_does_not_claim_native_saved':True,'human_permission_granted':False}}
 fa=d['factory_acceptance'];ready['checks']['factory']=descriptor(records['factory_acceptance']['path'],records['factory_execution']['path'],fa,d['factory_execution'],['actual_coverage_names'],{k:[k]for k in C.ROLE_SEMANTICS['factory']})
 for role in C.CHECK_ROLES-{'factory'}:ready['checks'][role]=descriptor(records['formal_cpu']['path'],records['formal_cpu_execution']['path'],d['formal_cpu'],d['formal_cpu_execution'],['coverage_by_role',role],{k:['semantic_proofs',role,k]for k in C.ROLE_SEMANTICS[role]})
 if mapping:
  desc=descriptor(records['display_qualification']['path'],records['display_execution']['path'],d['display_qualification'],d['display_execution'],['coverage_names'])
  desc['full_source_remainder_preserved_path']=['full_source_remainder_preserved_in_original_actor_and_actual_full_reference_slab']
  desc['assertions']+=[{'path':[k],'equals':v}for k,v in {'eligible_for_reversible_progress_visibility':True,'human_permission_granted_by_this_package':False,'historical_absolute_accuracy_approved':False,'original_volume_rebuilt':False,'source95_97_or_other_source_changes_allowed':False}.items()]
  ready['visibility_qualification']=desc
 docs={r:read(path(r))for r in protected if path(r).suffix.lower()=='.json'}
 C.validate_ready_documents(ready,docs)
 return ready

def main():
 p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);p.add_argument('--request-sha256',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();audit=a.audit.resolve();require(out.is_relative_to(HERE)and audit.is_relative_to(HERE)and not out.exists()and not audit.exists()and out!=audit,'fresh separate readiness/audit paths under readiness-prep required')
 C=load_contract()
 try:
  require(sha(a.request)==a.request_sha256,'request SHA differs');r=assemble(read(a.request),a.request,a.request_sha256)
  C.write_new(out,r);C.load_ready(out,sha(out))
  result={'schema':'v20.native-v2-readiness-generation-audit/1','summary':{'passed':1,'failed':0},'readiness':rel(out),'readiness_sha256':sha(out),'active_contract_load_ready_passed':True,'native_opened':False,'native_saved':False,'Blender_started':False,'human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0}
 except BaseException:
  # If final contract validation fails, retain the rejected candidate under an
  # explicit red name and leave no runnable final-readiness filename.
  if out.exists():out.rename(out.with_name(out.stem+'.REJECTED'+out.suffix))
  result={'schema':'v20.native-v2-readiness-generation-audit/1','summary':{'passed':0,'failed':1},'final_readiness_written':False,'error':traceback.format_exc(),'native_opened':False,'native_saved':False,'Blender_started':False,'human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0}
 C.write_new(audit,result);print(json.dumps(result))
 if result['summary']['failed']:raise SystemExit(1)
if __name__=='__main__':main()
