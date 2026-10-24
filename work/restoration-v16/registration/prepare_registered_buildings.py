"""Small source geometry bases; actual actor permissions require terminal probe proof."""
import argparse,hashlib,json,math
from pathlib import Path
from shapely.geometry import Polygon,box,mapping
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
TARGETS=[('huifengting','惠风亭','40627622','south'),('linxiting','临溪亭','40543883','south'),('xianruoguan','咸若馆','40543884','south'),('baoxianglou','宝相楼','40543911','west'),('jiyunlou_cininggarden','吉云楼（慈宁宫花园）','40543910','east'),('ciyinlou','慈荫楼','40543909','south')]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def local(q,a,t):
 x,y=q[0]-a[0],q[1]-a[1];c,s=math.cos(t),math.sin(t);return[c*x+s*y,-s*x+c*y]
def world(q,a,t):
 c,s=math.cos(t),math.sin(t);return[a[0]+c*q[0]-s*q[1],a[1]+s*q[0]+c*q[1]]
def frame(poly,facing):
 ring=list(poly.minimum_rotated_rectangle.exterior.coords)[:-1];target={'south':0,'west':-math.pi/2,'east':math.pi/2}[facing];angles=[math.atan2(b[1]-a[1],b[0]-a[0])for a,b in zip(ring,ring[1:]+ring[:1])];angle=min(angles,key=lambda t:abs(math.atan2(math.sin(t-target),math.cos(t-target))));return[poly.centroid.x,poly.centroid.y,0.],angle

def component(ident,poly,facing,square=False):
 a,t=frame(poly,facing);ring=list(poly.exterior.coords)[:-1];holes=[list(q.coords)[:-1]for q in poly.interiors];lo=[local(q,a,t)for q in ring];lh=[[local(q,a,t)for q in r]for r in holes];q=Polygon(lo,lh);inset=.12;inner=q.buffer(-inset,join_style=2);xmin,ymin,xmax,ymax=q.bounds;hx,hy=min(-xmin,xmax),min(-ymin,ymax);low,high=0.,1.
 for _ in range(64):
  z=(low+high)/2;candidate=box(-hx*z,-hy*z,hx*z,hy*z)
  if inner.covers(candidate):low=z
  else:high=z
 safe=box(-hx*low*(1-1e-7),-hy*low*(1-1e-7),hx*low*(1-1e-7),hy*low*(1-1e-7));assert poly.is_valid and safe.area>1 and q.covers(safe)
 sw,sd=safe.bounds[2]-safe.bounds[0],safe.bounds[3]-safe.bounds[1];reserve=.5;bw,bd=sw-2*reserve,sd-2*reserve
 if square:bw=bd=min(bw,bd)
 body=box(-bw/2,-bd/2,bw/2,bd/2);support=body.buffer(reserve,join_style=2);assert bw>0 and bd>0 and q.covers(support)
 return{'component_id':ident,'source_polygon_world':ring,'source_holes_world':holes,'source_polygon_local':lo,'source_holes_local':lh,'anchor':a,'rotation_z_rad':t,'semantic_front':'negative-y','study_front_cardinal':facing,'frame_method':'Fullcomponentcentroid and sourceMRR edge nearest declaredqualifiedfront; no measuredazimuth.','study_body_width_m':bw,'study_body_depth_m':bd,'study_body_square':square,'study_roof_reference_envelope_width_m':sw,'study_roof_reference_envelope_depth_m':sd,'parameter_scope':'ALL metricvalues unmeasured studies derived from sourcecontext; not publishedmeasurements or sourceflat6mheight.','source_containment_proof':{'method':'Wholearea sourcepolygon/holes covers fullbody plus .5m all-side supportreserve; notbbox/point sampling','coordinate_clearance_inset_m':inset,'reserved_support_margin_m':reserve,'safe_rectangle_local':list(safe.exterior.coords)[:-1],'body_rectangle_local':list(body.exterior.coords)[:-1],'complete_body_plus_support_envelope_local':list(support.exterior.coords)[:-1],'body_plus_support_outside_source_area_m2':support.difference(q).area,'full_source_covers_body_plus_support':True}}
def main():
 pa=argparse.ArgumentParser();pa.add_argument('--actual',action='store_true');pa.add_argument('--probe-session',type=int);pa.add_argument('--probe-exit-code',type=int);args=pa.parse_args();out=HERE/('registered-buildings.json'if args.actual else'registered-geometry-preview.json');assert not out.exists(),'preserveearlierpayload'
 modelpath=ROOT/'work/forbidden-city-research/geospatial/model-data.json';analysispath=HERE/'source-candidate-analysis.json';invpath=HERE/'candidate-inventory.json';m=json.loads(modelpath.read_text());parts={p['id']:p for p in m['parts']};split=json.loads(analysispath.read_text())['source_xianruo_partition'];actualpath=HERE/'actual-source-actors.json';actual=None
 if args.actual:
  assert args.probe_session and args.probe_exit_code==0,'Require root actual terminal0 confirmation';actual=json.loads(actualpath.read_text());assert actual['native_sha256']=='54a09df9df1030494bf354d06b9dfd96c05023e1f289c8c123579a8c1e673b38'and actual['native_mesh_count']==13115 and actual['target_mesh_fingerprints_unchanged']and actual['all_durable_IDs_and_display_state_unchanged']
 facts_paths=[ROOT/'work/restoration-v16/research/huifeng/facts.json',ROOT/'work/restoration-v16/research/cininggarden/facts.json'];factentities={k:v for p in facts_paths for k,v in json.loads(p.read_text())['entities'].items()};buildings=[]
 for ident,name,oid,facing in TARGETS:
  sid=f'way-{oid}-p0';record=parts[sid];source=Polygon(record['polygon'],record.get('holes',[]));body=Polygon(split['north_main_candidate']['polygon'])if ident=='xianruoguan'else source;main=component('main',body,facing,square=ident in('huifengting','linxiting'));a,t=main['anchor'],main['rotation_z_rad'];components=[main]
  if ident=='xianruoguan':components.append(component('south_baoxia',Polygon(split['south_lobe_candidate']['polygon']),'south'))
  names=actual['part_actor_mapping'][sid]if actual else[]
  if actual:
   assert names and all(actual['actor_evidence'][n]['source_record']==record for n in names)
  buildings.append({'building_id':ident,'name_zh':name,'source_part_id':sid,'original_source_record':record,'source_record_sha256':hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'source_polygon_world':record['polygon'],'source_holes_world':record.get('holes',[]),'source_polygon_local':[local(q,a,t)for q in record['polygon']],'source_holes_local':[[local(q,a,t)for q in h]for h in record.get('holes',[])],'anchor':a,'rotation_z_rad':t,'semantic_front':'negative-y','study_front_cardinal':facing,'source_components':components,'body_study_component_id':'main','study_body_width_m':main['study_body_width_m'],'study_body_depth_m':main['study_body_depth_m'],'source_containment_proof':main['source_containment_proof'],'source_actual_actor_names':names,'allowed_hidden_source_actor_names':names,'source_actor_geometry_verified':args.actual,'historical_identity_confirmed':False,'typed_factual_source_fields':factentities[ident]['fields'],'source_mapping_scope':'Qualifiedofficialname/relativepositionjoin; source3Dandallmetriccontrol notmuseumcurrentfieldmeasurements.','metric_scope':'unmeasured_study','source6m_proxy_height_is_real_building_height':False,'occupied_storeys_must_follow_facts_not_source_height':True,'measured_world_azimuth':None,'third_party_cost':0,'human_approval':'pending'})
 files=[modelpath,analysispath,invpath,*facts_paths,Path(__file__)]+([actualpath]if args.actual else[]);pins={str(p.relative_to(ROOT)):sha(p)for p in files};output={'schema':'v16-six-target-source-registered-geometry-bases/1','status':'actual_readonly_source_verified_studies_not_fullprofiles'if args.actual else'source_only_preview_pending_actual_probe','base_native_sha256':'54a09df9df1030494bf354d06b9dfd96c05023e1f289c8c123579a8c1e673b38','base_manifest_sha256':'3c045304a3cb653b0db496ead776909a8471e427e7698119ecef71a5b7a51059','source_files_sha256':pins,'buildings':buildings,'source_xianruo_partition':split,'allowed_hidden_source_actor_names':sorted({n for b in buildings for n in b['allowed_hidden_source_actor_names']}),'deferred_entities':['linxi_east_peidian_no_confirmed_source_mapping','linxi_west_peidian_no_confirmed_source_mapping','Hanqing_Yanshou_compound_roof_fragments_unregistered','cining_pond_sourcegeometry_missing'],'external_context_source':str(invpath.relative_to(ROOT)),'native_probe_session':args.probe_session,'native_probe_terminal_exit_code':args.probe_exit_code,'native_opened_by_this_script':False,'native_saved':False,'geometry_created':False,'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False};out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n');assert all(sha(ROOT/p)==v for p,v in pins.items());print(json.dumps({'path':str(out),'sha256':sha(out),'buildings':[b['building_id']for b in buildings],'actual':args.actual,'allowed_hide_count':len(output['allowed_hidden_source_actor_names'])},ensure_ascii=False))
if __name__=='__main__':main()
