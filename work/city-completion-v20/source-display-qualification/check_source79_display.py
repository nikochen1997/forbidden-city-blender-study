"""Source79 reversible progress-display qualification from complete actual meshes.

No Blender, generator, builder or native write. Full triangle XY unions and cap
unions preserve every component/hole; no plan remainder is treated as a mesh.
"""
import argparse,copy,hashlib,importlib.util,json,math,traceback
from pathlib import Path
from shapely.geometry import Polygon,MultiPoint,GeometryCollection,mapping
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
SOURCE_ID='way-40624979-p0';ACTOR=SOURCE_ID+'_原轮廓主体'
BASE='outputs/紫禁城现存格局-乾隆花园第十九阶段-局部进度/紫禁城现存格局-乾隆花园第十九阶段-局部进度.blend'
BASE_SHA='c2e981596258654e9f15ff9ab60f065d5b068a7f72b4a1cd39cf343203f1f125'
PROBE='work/city-completion-v20/shouan-registration/run-01/actual-source-actors.json';PROBE_SHA='7f22e6c002a86d856ebdcc10af1784b94444d9d433b4ac2d55f7eade7f31c54b'
SOURCE_CPU='work/city-completion-v20/shouan-registration/run-01/actual-source-domain-CPU-01.json';SOURCE_CPU_SHA='69f6002e258e48ed86e20902db84497643f7bfd137ec36e81c4ba3043999665e'
PROFILE='work/city-completion-v20/shouan-production-profile/production-profiles.json';PROFILE_SHA='44fd1d4f5b0383494c44db3b8883b560e0230565635fbefe891ea9c20a0d4504'
QUAL='work/city-completion-v20/plan-registration/shouan79-source-bounded-qualification-proposal-02.json';QUAL_SHA='af9cd952bd51fa5eb7f512a7b2544ebb3ab25c88d2943cc047e152b400d78872'
EPS=1e-4;AREA_EPS=1e-7;CAP_Z_EPS=1e-6
ROOF_ROLES={'roof','tile','ridge'}
MAIN_ROLES={'wall','column','column_base','pilaster','beam','roof_bearing_post','roof_closure_wall','opening_frame','door_leaf','window_set_infill_proxy','door_set_infill_proxy'}

def require(ok,msg):
 if not ok:raise AssertionError(msg)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def canonical(d):return json.dumps(d,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))
def equal(a,b):return canonical(a)==canonical(b)
def path(rel):
 p=(ROOT/rel).resolve();require(p.is_relative_to(ROOT),'path outside workspace');return p
def write(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x')as f:f.write(canonical(d)+'\n')
def shape_row(g):
 return {'type':g.geom_type,'is_empty':g.is_empty,'area_m2':g.area,'geometry':mapping(g)}
def poly_components(g):
 if g.is_empty:return []
 if g.geom_type=='Polygon':return [{'outer':[list(v)for v in list(g.exterior.coords)[:-1]],'holes':[[list(v)for v in list(r.coords)[:-1]]for r in g.interiors],'area_m2':g.area}]
 if hasattr(g,'geoms'):return [r for x in g.geoms for r in poly_components(x)]
 return []
def tri_rows(row):
 vv=row['vertices_world'];tt=row['triangles_with_material_index'];require(vv and tt,'complete vertices/triangles required: '+row['name'])
 require(all(len(v)==3 and all(isinstance(x,(float,int))and not isinstance(x,bool)and math.isfinite(x)for x in v)for v in vv),'nonfinite actual triangle vertices')
 out=[]
 for t,mi in tt:
  require(len(t)==3 and len(set(t))==3 and all(type(i)is int and 0<=i<len(vv)for i in t),'invalid complete triangle index')
  out.append([vv[i]for i in t])
 return out

def projected(row):
 # Includes degenerate projected lines/points, so a zero-area exterior sliver
 # cannot evade containment merely because its area is zero.
 shapes=[MultiPoint([(v[0],v[1])for v in t]).convex_hull for t in tri_rows(row)]
 return unary_union(shapes)
def top_cap(row):
 tri=tri_rows(row);z=max(v[2]for v in row['vertices_world']);caps=[]
 for t in tri:
  if all(abs(v[2]-z)<=CAP_Z_EPS for v in t):
   p=Polygon([(v[0],v[1])for v in t])
   if p.area>0:require(p.is_valid,'invalid actual top triangle');caps.append(p)
 require(caps,'actual full horizontal top-cap triangles missing: '+row['name'])
 return unary_union(caps),z,len(caps)
def within(g,p,label):
 outside=g.difference(p.buffer(EPS))
 require(outside.is_empty,label+' extends outside complete source, including line/point fragments')
 return {'outside_fixed_100um':shape_row(outside),'raw_outside_area_m2':g.difference(p).area}

def analyze_geometry(rows,source,floor_names,structural_roof_names,remainder_names):
 require(source.is_valid and not source.is_empty,'invalid complete source polygon')
 require(rows and len(rows)==len({r['name']for r in rows}),'complete unique actual objects required')
 by={r['name']:r for r in rows};allnames=set(by)
 require(len(floor_names)==1 and len(set(floor_names))==1 and set(floor_names)<=allnames,'exact actual source-reference slab required')
 require(remainder_names==[],'this floor-exposure proposal does not certify extra remainder prisms')
 roof_names={n for n,r in by.items()if r['role']in ROOF_ROLES};main_names={n for n,r in by.items()if r['role']in MAIN_ROLES}
 require(set(structural_roof_names)and set(structural_roof_names)<=roof_names,'all actual structural roofs required')
 require(roof_names and main_names,'actual main and roof geometry required')
 require(allnames==set(floor_names)|roof_names|main_names,'unknown/unclassified actual mesh cannot be omitted from domain analysis')
 require(all(by[n]['role']=='source_reference_slab'for n in floor_names),'floor is not actual source_reference_slab')
 projections={n:projected(r)for n,r in by.items()};containment={n:within(g,source,n)for n,g in projections.items()}
 floorcap,topz,ncaps=top_cap(by[floor_names[0]])
 within(floorcap,source,'actual complete floor top')
 missing=source.difference(floorcap.buffer(EPS));require(missing.is_empty,'actual floor cap omits complete source triangles/fragments')
 require(floorcap.boundary.hausdorff_distance(source.boundary)<=EPS,'actual floor boundary differs from full source beyond fixed100um')
 body=unary_union([projections[n]for n in sorted(main_names)]);roof=unary_union([projections[n]for n in sorted(roof_names)]);structroof=unary_union([projections[n]for n in structural_roof_names]);allshape=unary_union([projections[n]for n in sorted(main_names|roof_names)])
 require(allshape.area>0,'actual nonreference geometry absent')
 rem_body=source.difference(body);rem_roof=source.difference(roof);remaining=source.difference(allshape)
 missed_remainder=remaining.difference(floorcap.buffer(EPS));require(missed_remainder.is_empty,'source P minus actual Q not retained by actual reference-floor cap')
 inside_shape=source.intersection(allshape);recombine=inside_shape.union(remaining)
 require(recombine.symmetric_difference(source).area<=AREA_EPS,'full source split loses polygon fragments')
 require(inside_shape.intersection(remaining).area<=AREA_EPS,'source fragments overlap in area')
 return {'source_P':{**shape_row(source),'complete_components':poly_components(source)},'actual_reference_floor':{'objects':floor_names,'actual_top_z_m_unmeasured_control':topz,'complete_top_cap_triangle_count':ncaps,'top_cap':shape_row(floorcap),'complete_components':poly_components(floorcap),'raw_symmetric_difference_with_P_m2':floorcap.symmetric_difference(source).area,'full_P_covered_with_fixed_100um':True,'full_boundary_hausdorff_m':floorcap.boundary.hausdorff_distance(source.boundary)},'actual_main_Q':{'objects':sorted(main_names),**shape_row(body)},'actual_roof_union':{'objects':sorted(roof_names),**shape_row(roof),'structural_roof_objects':structural_roof_names,'structural_roof_union':shape_row(structroof)},'actual_all_nonreference_Q_union':shape_row(allshape),'source_P_minus_main_Q':{**shape_row(rem_body),'complete_fragments':poly_components(rem_body)},'source_P_minus_roof_union':{**shape_row(rem_roof),'complete_fragments':poly_components(rem_roof)},'source_P_minus_all_new_nonreference_geometry':{**shape_row(remaining),'complete_fragments':poly_components(remaining),'all_fragments_covered_by_actual_full_reference_slab':True,'unreconstructed_reference_floor_only':True,'original_6m_draft_volume_rebuilt':False},'all_actual_mesh_complete_XY_containment':containment,'all_components_holes_preserved':True,'bbox_or_centroid_or_plan_difference_only':False,'fixed_EPS_m':EPS,'fixed_AREA_EPS_m2':AREA_EPS,'cap_Z_EPS_m':CAP_Z_EPS}

def validate_source_records(profile,probe):
 a=probe['actor_evidence'][ACTOR];record=a['source_record']
 require(len(record['polygon'])==11 and record['holes']==[],'all11 source points required')
 require(equal(profile['source_polygon_world'],record['polygon'])and equal(profile['source_holes_world'],record['holes'])and equal(profile['original_source_record'],record),'complete authoritative source changed')
 require(equal(a['complete_source_polygon_world'],record['polygon'])and equal(a['complete_source_holes_world'],record['holes']),'probe full source ring differs')
 require(a['source_height_is_measured']is False and record['height']==6.0,'source6m must stay explicitly unmeasured draft')
 return Polygon(record['polygon'],record['holes'])
def proposed_mapping():return [{'object':ACTOR,'before':{'hide_render':False,'global_hide_viewport':False,'hide_get':False},'after':{'hide_render':True,'global_hide_viewport':False,'hide_get':True}}]
def validate_display_mapping(m):
 require(equal(m,proposed_mapping()),'only exact source79 own-hide/render reversible mapping possible;95/97/global hide forbidden')
 return True

def private_geometry_negatives(rows,source,floors,roofs):
 result=[]
 missing=copy.deepcopy(rows);fr=next(r for r in missing if r['name']==floors[0]);maxz=max(v[2]for v in fr['vertices_world'])
 caps=[i for i,(t,_)in enumerate(fr['triangles_with_material_index'])if all(abs(fr['vertices_world'][j][2]-maxz)<=CAP_Z_EPS for j in t)and Polygon([(fr['vertices_world'][j][0],fr['vertices_world'][j][1])for j in t]).area>0]
 require(caps,'negative requires actual full cap triangle')
 # Remove the largest actual top triangle, not an irrelevant tiny edge.
 idx=max(caps,key=lambda i:Polygon([(fr['vertices_world'][j][0],fr['vertices_world'][j][1])for j in fr['triangles_with_material_index'][i][0]]).area)
 fr['triangles_with_material_index'].pop(idx)
 try:analyze_geometry(missing,source,floors,roofs,[]);result.append({'id':'EXTRA-ACTUAL-MISSING-FLOOR-TRIANGLE','passed':False,'error':'actual-derived missing top triangle accepted'})
 except AssertionError as e:result.append({'id':'EXTRA-ACTUAL-MISSING-FLOOR-TRIANGLE','passed':'floor' in str(e),'rejected':str(e)})
 outside=copy.deepcopy(rows);target=next(r for r in outside if r['name']not in floors);target['vertices_world'][0][0]=source.bounds[2]+1
 try:analyze_geometry(outside,source,floors,roofs,[]);result.append({'id':'EXTRA-ACTUAL-OUTSIDE-NEW-SHAPE','passed':False,'error':'actual-derived outside triangle accepted'})
 except AssertionError as e:result.append({'id':'EXTRA-ACTUAL-OUTSIDE-NEW-SHAPE','passed':'outside complete source'in str(e),'rejected':str(e)})
 for obj in ('way-40624995-p0_原轮廓主体','way-40624997-p0_原轮廓主体'):
  mm=proposed_mapping();mm[0]['object']=obj
  try:validate_display_mapping(mm);result.append({'id':'EXTRA-FORBID-'+obj,'passed':False,'error':'other source display allowed'})
  except AssertionError as e:result.append({'id':'EXTRA-FORBID-'+obj,'passed':True,'rejected':str(e)})
 return result

def load_pure(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def actual_qualification(args):
 files={k:Path(getattr(args,k.replace('-','_'))).resolve()for k in ('factory_state','world','formal_cpu','factory_tests','binding')}
 for key,p in files.items():require(sha(p)==getattr(args,key+'_sha256'),'required actual input SHA differs: '+key)
 binding=read(files['binding']);pins=binding['inputs_sha256']
 for rel,h in pins.items():require(sha(path(rel))==h,'bound formal input changed: '+rel)
 for rel,h in{PROBE:PROBE_SHA,SOURCE_CPU:SOURCE_CPU_SHA,PROFILE:PROFILE_SHA,QUAL:QUAL_SHA}.items():require(pins.get(rel)==h and sha(path(rel))==h,'mandatory qualified source/profile pin missing')
 require(sha(path(BASE))==BASE_SHA,'original native changed before source display qualification')
 krel='work/city-completion-v20/formal-factory/formal_contract.py';require(krel in pins,'formal pure source contract unbound');K=load_pure('v20_display_formal_pure',path(krel));profile,_=K.check_bound_files(binding)
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
 require(cpu['actual_coverage_names']==sorted(f['mesh_names']),'formal CPU actual complete coverage differs')
 source=validate_source_records(profile,read(path(PROBE)));roles=f['roles'];analysis=analyze_geometry(rows,source,roles['reference_floor'],roles['roofs'],roles['source_remainders'])
 validate_display_mapping(proposed_mapping());neg=private_geometry_negatives(rows,source,roles['reference_floor'],roles['roofs']);require(all(c['passed']is True for c in neg),'actual-derived negative control failed')
 changed=copy.deepcopy(profile);changed['source_polygon_world'][0][0]+=.1
 try:validate_source_records(changed,read(path(PROBE)));raise RuntimeError('changed full source accepted')
 except AssertionError as e:neg.append({'id':'EXTRA-ACTUAL-CHANGED-COMPLETE-SOURCE','passed':True,'rejected':str(e)})
 require(all(sha(p)==getattr(args,k+'_sha256')for k,p in files.items()),'actual input changed during audit')
 require(all(sha(path(rel))==h for rel,h in pins.items())and sha(path(BASE))==BASE_SHA,'qualified input/baseline bytes changed during audit')
 checks=[
  {'id':'DISPLAY-01-QUALIFIED-ORIGINAL-SOURCE','passed':True,'evidence':'Exact pinned V19 native, original full11point source7/0, profile44fd and conditional qualificationaf9cd.'},
  {'id':'DISPLAY-02-ACTUAL-FORMAL-FACTORY-AND-CPU','passed':True,'evidence':{'factory_capture_summary':tests['summary'],'formal_full_geometry_summary':cpu['summary']}},
  {'id':'DISPLAY-03-COMPLETE-CANONICAL-WORLD','passed':True,'evidence':{'actual_full_meshes':len(rows),'full_MESH_KEYS_compared':True}},
  {'id':'DISPLAY-04-FULL-P-ACTUAL-FLOOR-CAP','passed':True,'evidence':{'top_cap_triangles':analysis['actual_reference_floor']['complete_top_cap_triangle_count'],'boundary_hausdorff_m':analysis['actual_reference_floor']['full_boundary_hausdorff_m']}},
  {'id':'DISPLAY-05-ALL-NEW-FULL-PROJECTED-DOMAINS','passed':True,'evidence':{'covered_meshes':len(analysis['all_actual_mesh_complete_XY_containment']),'degenerate_lines_and_points_included':True}},
  {'id':'DISPLAY-06-MAIN-ROOF-ALL-FRAGMENTS','passed':True,'evidence':{'main_remainder_fragments':len(analysis['source_P_minus_main_Q']['complete_fragments']),'roof_remainder_fragments':len(analysis['source_P_minus_roof_union']['complete_fragments']),'all_nonreference_remainder_fragments':len(analysis['source_P_minus_all_new_nonreference_geometry']['complete_fragments'])}},
  {'id':'DISPLAY-07-EXACT-ONLY79-REVERSIBLE-MAPPING','passed':True,'evidence':proposed_mapping()},
  {'id':'DISPLAY-08-FINAL-IMMUTABLE-BYTES','passed':True,'evidence':'All formal pins, five actual inputs and original V19 native rehashed unchanged.'},
 ]+neg
 return {'schema':'v20.source79-reversible-progress-display-qualification/1','status':'actual-geometry-eligible-for-root-technical-display-choice','checks':checks,'summary':{'passed':sum(c['passed']for c in checks),'failed':sum(not c['passed']for c in checks)},'factory_state_sha256':sha(files['factory_state']),'actual_world_sha256':sha(files['world']),'actual_formal_CPU_sha256':sha(files['formal_cpu']),'binding_sha256':sha(files['binding']),'coverage_names':[ACTOR],'eligible_for_reversible_progress_visibility':True,'full_source_remainder_preserved_in_original_actor_and_actual_full_reference_slab':True,'original_actor_evidence_location':'Unchanged SHA-bound V19 baseline and complete actual source 7/0; combined future V20 original-object preservation still requires producer plus independent saved-reader verification.','original_actor_geometry_must_remain_forever':True,'original_volume_rebuilt':False,'source6m_is_actual_height':False,'proposed_exact_visibility_changes':proposed_mapping(),'human_permission_granted_by_this_package':False,'historical_absolute_accuracy_approved':False,'human_approval_granted':False,'source95_97_or_other_source_changes_allowed':False,'analysis':analysis,'actual_export_derived_private_CPU_controls':neg,'actual_geometry_verified_in_factory':True,'combined_saved_native_verified_here':False,'required_after_integration':'Read saved V20 independently; retain old79 raw/eval/material/relations exactly and verify sole allowed own-hide/render exception.','source_floor_scope':'Full11point reference slab represents unmeasured spatial remainder, not reconstructed 6m walls or all architectural features.','input_files_sha256':{str(p.relative_to(ROOT)):getattr(args,k+'_sha256')for k,p in files.items()},'fixed_inputs_sha256':{PROBE:PROBE_SHA,SOURCE_CPU:SOURCE_CPU_SHA,PROFILE:PROFILE_SHA,QUAL:QUAL_SHA,BASE:BASE_SHA},'checker_sha256':sha(__file__),'native_opened':False,'native_saved':False,'Blender_started':False,'human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0}

def main():
 p=argparse.ArgumentParser()
 for key in ('factory-state','world','formal-cpu','factory-tests','binding'):
  p.add_argument('--'+key,type=Path,required=True);p.add_argument('--'+key+'-sha256',required=True)
 p.add_argument('--report',type=Path,required=True);a=p.parse_args();report=a.report.resolve();require(report.is_relative_to(HERE)and not report.exists(),'fresh source-display report path required')
 try:r=actual_qualification(a)
 except BaseException:r={'schema':'v20.source79-reversible-progress-display-qualification/1','status':'red-or-missing-actual-input-no-display-eligibility','summary':{'passed':0,'failed':1},'eligible_for_reversible_progress_visibility':False,'coverage_names':[ACTOR],'error':traceback.format_exc(),'native_opened':False,'native_saved':False,'Blender_started':False,'human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0}
 write(report,r);print(json.dumps({'summary':r['summary'],'eligible_for_reversible_progress_visibility':r['eligible_for_reversible_progress_visibility']}))
 if r['summary']['failed']:raise SystemExit(1)

if __name__=='__main__':main()
