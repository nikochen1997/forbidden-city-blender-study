"""Explicit source79 beam-width-v2 common-origin-v3 entry; old checkers frozen.

Only the exact profile-v2, formal-contract-v2 and binding02 pins below are
accepted. Complete triangle mathematics is reused without changing tolerance.
"""
import argparse,copy,hashlib,importlib.util,json,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent
CORE_SHA='3f2e4464d1983777b50a96a952c00d36eff9ddb9ecf99b5f506d9293e730c535'
CAPTURE_SHA='f7459f47a06b225fc50297e30ff7daff491bb4d012478e5cd3d4b9915923059f'
def load_frozen(name,path,expected):
 if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise AssertionError('frozen display dependency changed: '+str(path))
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
M=load_frozen('source79_frozen_display_v1',HERE/'check_source79_display.py',CORE_SHA)
CAPTURE=load_frozen('source79_capture_chain_v2',HERE/'capture_chain_v2.py',CAPTURE_SHA)
DOMAIN_SHA='75cbd87c9202775e293c4ef74feafd4e4851c5a684be2020b94421e3685b5e49'
D=load_frozen('source79_projected_domain_v3',HERE/'projected_domain_v3.py',DOMAIN_SHA)
ROOT=M.ROOT;SOURCE_ID=M.SOURCE_ID;ACTOR=M.ACTOR;BASE=M.BASE;BASE_SHA=M.BASE_SHA
PROBE=M.PROBE;PROBE_SHA=M.PROBE_SHA;SOURCE_CPU=M.SOURCE_CPU;SOURCE_CPU_SHA=M.SOURCE_CPU_SHA;QUAL=M.QUAL;QUAL_SHA=M.QUAL_SHA
PROFILE='work/city-completion-v20/shouan-production-profile/production-profiles-v2.json'
PROFILE_SHA='0d246f3c0b938d471ca0ad1500aa33696da7e9067c93f63f8ecdf9aa9a1a61e9'
FORMAL_CONTRACT_REL='work/city-completion-v20/formal-factory/formal_contract_v2.py'
FORMAL_CONTRACT_SHA='f94da3cf7d67e98de231e1ba95fe139a7b5f653d290b43e8116794b509bafd2f'
BINDING_SHA='f995bac5b5e806ea190fef953ba16e86f33481e047449487c2bde971cf6da87d'
require=M.require;sha=M.sha;read=M.read;equal=M.equal;path=M.path;load_pure=M.load_pure
analyze_geometry=M.analyze_geometry;validate_source_records=M.validate_source_records
proposed_mapping=M.proposed_mapping;validate_display_mapping=M.validate_display_mapping;private_geometry_negatives=M.private_geometry_negatives

def validate_version_binding(binding,binding_sha):
 require(binding_sha==BINDING_SHA and binding['schema']=='v20-shouan79-formal-factory-binding/2','exact reviewed binding02 required; old red binding01 forbidden')
 require(binding['profile_package']==PROFILE and binding['inputs_sha256'].get(PROFILE)==PROFILE_SHA,'only exact reviewed production-profile-v2 accepted')
 require(binding['inputs_sha256'].get(FORMAL_CONTRACT_REL)==FORMAL_CONTRACT_SHA,'only exact reviewed formal-contract-v2 accepted')
 return True

def actual_qualification(args):
 files={k:Path(getattr(args,k.replace('-','_'))).resolve()for k in ('factory_state','world','formal_cpu','factory_tests','binding')}
 for key,p in files.items():require(sha(p)==getattr(args,key+'_sha256'),'required actual input SHA differs: '+key)
 binding=read(files['binding']);validate_version_binding(binding,sha(files['binding']));pins=binding['inputs_sha256']
 for rel,h in pins.items():require(sha(path(rel))==h,'bound formal input changed: '+rel)
 for rel,h in{PROBE:PROBE_SHA,SOURCE_CPU:SOURCE_CPU_SHA,PROFILE:PROFILE_SHA,QUAL:QUAL_SHA}.items():require(pins.get(rel)==h and sha(path(rel))==h,'mandatory qualified source/profile pin missing')
 require(sha(path(BASE))==BASE_SHA,'original native changed before source display qualification')
 krel=FORMAL_CONTRACT_REL;require(pins.get(krel)==FORMAL_CONTRACT_SHA and sha(path(krel))==FORMAL_CONTRACT_SHA,'exact v2 formal pure contract unbound');K=load_pure('v20_display_formal_pure',path(krel));profile,_=K.check_bound_files(binding)
 crel=binding['native_contract'];require(crel in pins,'canonical contract unbound');C=load_pure('v20_display_canonical_pure',path(crel))
 f=read(files['factory_state']);w=read(files['world']);cpu=read(files['formal_cpu']);tests=read(files['factory_tests'])
 C.validate_factory(f);K.validate_world_header(w,binding,profile)
 require(w['factory_state_sha256']==sha(files['factory_state'])and w['binding_sha256']==sha(files['binding']),'actual WORLD/factory/binding chain differs')
 require(equal(f['profile'],profile),'factory exact production profile differs')
 rows=w['objects'];require(len(rows)==len(f['mesh_names'])and {r['name']for r in rows}==set(f['mesh_names']),'all actual WORLD objects required')
 for row in rows:require(equal({k:row[k]for k in C.MESH_KEYS},f['meshes'][row['name']]),'full canonical/actual WORLD mismatch: '+row['name'])
 require(cpu['schema']=='v20-source-bound-shouan-actual-complete-CPU/1'and type(cpu['summary']['failed'])is int and cpu['summary']['failed']==0 and type(cpu['summary']['passed'])is int and cpu['summary']['passed']==len(cpu['checks'])and all(c['passed']is True for c in cpu['checks']),'actual formal full-geometry CPU not green')
 required={'CPU-04-FULL-SUPPORT-AND-SOURCE','CPU-06-FULL-CANONICAL-CAPTURE','CPU-08-COMPLETE-11POINT-SOURCE-FLOOR'};require(required<={c['id']for c in cpu['checks']},'full-source/floor/canonical actual checks missing')
 require(cpu['actual_readout_sha256']==sha(files['world'])and cpu['factory_state_sha256']==sha(files['factory_state'])and cpu['binding_sha256']==sha(files['binding']),'formal CPU not bound to exact actual exports')
 require(tests['schema']=='v20-source-bounded-formal-factory-tests/1'and type(tests['summary']['failed'])is int and tests['summary']['failed']==0 and type(tests['summary']['passed'])is int and tests['summary']['passed']>0 and tests['actual_factory_build_completed']is True and tests['binding_sha256']==sha(files['binding']),'actual formal factory not completed')
 CAPTURE.validate_capture_chain(tests,sha(files['factory_state']),sha(files['binding']),len(f['mesh_names']))
 require(cpu['actual_coverage_names']==sorted(f['mesh_names']),'formal CPU actual complete coverage differs')
 source=validate_source_records(profile,read(path(PROBE)));roles=f['roles'];analysis=D.analyze_geometry(rows,source,roles['reference_floor'],roles['roofs'],roles['source_remainders'],profile['anchor'])
 validate_display_mapping(proposed_mapping());neg=D.private_geometry_negatives(rows,source,roles['reference_floor'],roles['roofs'],profile['anchor']);require(all(c['passed']is True for c in neg),'actual-derived negative control failed')
 changed=copy.deepcopy(profile);changed['source_polygon_world'][0][0]+=.1
 try:validate_source_records(changed,read(path(PROBE)));raise RuntimeError('changed full source accepted')
 except AssertionError as e:neg.append({'id':'EXTRA-ACTUAL-CHANGED-COMPLETE-SOURCE','passed':True,'rejected':str(e)})
 require(all(sha(p)==getattr(args,k+'_sha256')for k,p in files.items()),'actual input changed during audit')
 require(all(sha(path(rel))==h for rel,h in pins.items())and sha(path(BASE))==BASE_SHA,'qualified input/baseline bytes changed during audit')
 checks=[
  {'id':'DISPLAY-01-QUALIFIED-ORIGINAL-SOURCE','passed':True,'evidence':'Exact pinned V19 native, original full11point source7/0, profile-v2-0d246 and conditional qualificationaf9cd.'},
  {'id':'DISPLAY-02-ACTUAL-FORMAL-FACTORY-AND-CPU','passed':True,'evidence':{'factory_capture_summary':tests['summary'],'formal_full_geometry_summary':cpu['summary']}},
  {'id':'DISPLAY-03-COMPLETE-CANONICAL-WORLD','passed':True,'evidence':{'actual_full_meshes':len(rows),'full_MESH_KEYS_compared':True}},
  {'id':'DISPLAY-04-FULL-P-ACTUAL-FLOOR-CAP','passed':True,'evidence':{'top_cap_triangles':analysis['actual_reference_floor']['complete_top_cap_triangle_count'],'boundary_hausdorff_m':analysis['actual_reference_floor']['full_boundary_hausdorff_m']}},
  {'id':'DISPLAY-05-ALL-NEW-FULL-PROJECTED-DOMAINS','passed':True,'evidence':{'covered_meshes':len(analysis['all_actual_mesh_complete_XY_containment']),'degenerate_lines_and_points_included':True}},
  {'id':'DISPLAY-06-MAIN-ROOF-ALL-FRAGMENTS','passed':True,'evidence':{'main_remainder_fragments':len(analysis['source_P_minus_main_Q']['complete_fragments']),'roof_remainder_fragments':len(analysis['source_P_minus_roof_union']['complete_fragments']),'all_nonreference_remainder_fragments':len(analysis['source_P_minus_all_new_nonreference_geometry']['complete_fragments'])}},
  {'id':'DISPLAY-07-EXACT-ONLY79-REVERSIBLE-MAPPING','passed':True,'evidence':proposed_mapping()},
  {'id':'DISPLAY-08-FINAL-IMMUTABLE-BYTES','passed':True,'evidence':'All formal pins, five actual inputs and original V19 native rehashed unchanged.'},
 ]+neg
 return {'schema':'v20.source79-reversible-progress-display-qualification/3','status':'actual-geometry-eligible-for-root-technical-display-choice','checks':checks,'summary':{'passed':sum(c['passed']for c in checks),'failed':sum(not c['passed']for c in checks)},'factory_state_sha256':sha(files['factory_state']),'actual_world_sha256':sha(files['world']),'actual_formal_CPU_sha256':sha(files['formal_cpu']),'binding_sha256':sha(files['binding']),'coverage_names':[ACTOR],'eligible_for_reversible_progress_visibility':True,'full_source_remainder_preserved_in_original_actor_and_actual_full_reference_slab':True,'original_actor_evidence_location':'Unchanged SHA-bound V19 baseline and complete actual source 7/0; combined future V20 original-object preservation still requires producer plus independent saved-reader verification.','original_actor_geometry_must_remain_forever':True,'original_volume_rebuilt':False,'source6m_is_actual_height':False,'proposed_exact_visibility_changes':proposed_mapping(),'human_permission_granted_by_this_package':False,'historical_absolute_accuracy_approved':False,'human_approval_granted':False,'source95_97_or_other_source_changes_allowed':False,'analysis':analysis,'actual_export_derived_private_CPU_controls':neg,'actual_geometry_verified_in_factory':True,'combined_saved_native_verified_here':False,'required_after_integration':'Read saved V20 independently; retain old79 raw/eval/material/relations exactly and verify sole allowed own-hide/render exception.','source_floor_scope':'Full11point reference slab represents unmeasured spatial remainder, not reconstructed 6m walls or all architectural features.','input_files_sha256':{str(p.relative_to(ROOT)):getattr(args,k+'_sha256')for k,p in files.items()},'fixed_inputs_sha256':{PROBE:PROBE_SHA,SOURCE_CPU:SOURCE_CPU_SHA,PROFILE:PROFILE_SHA,QUAL:QUAL_SHA,BASE:BASE_SHA},'accepted_profile_package':{'path':PROFILE,'sha256':PROFILE_SHA},'accepted_formal_contract':{'path':FORMAL_CONTRACT_REL,'sha256':FORMAL_CONTRACT_SHA},'accepted_binding_sha256':BINDING_SHA,'geometry_core_sha256':CORE_SHA,'projection_domain_helper_sha256':DOMAIN_SHA,'capture_chain_helper_sha256':CAPTURE_SHA,'checker_sha256':sha(__file__),'native_opened':False,'native_saved':False,'Blender_started':False,'human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0}

def main():
 p=argparse.ArgumentParser()
 for key in ('factory-state','world','formal-cpu','factory-tests','binding'):
  p.add_argument('--'+key,type=Path,required=True);p.add_argument('--'+key+'-sha256',required=True)
 p.add_argument('--report',type=Path,required=True);a=p.parse_args();report=a.report.resolve();require(report.is_relative_to(HERE)and not report.exists(),'fresh source-display report path required')
 try:r=actual_qualification(a)
 except BaseException:r={'schema':'v20.source79-reversible-progress-display-qualification/3','status':'red-or-missing-actual-v3-input-no-display-eligibility','summary':{'passed':0,'failed':1},'eligible_for_reversible_progress_visibility':False,'coverage_names':[ACTOR],'error':traceback.format_exc(),'native_opened':False,'native_saved':False,'Blender_started':False,'human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0}
 M.write(report,r);print(json.dumps({'summary':r['summary'],'eligible_for_reversible_progress_visibility':r['eligible_for_reversible_progress_visibility']}))
 if r['summary']['failed']:raise SystemExit(1)

if __name__=='__main__':main()
