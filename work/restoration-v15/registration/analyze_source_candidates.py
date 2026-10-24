"""CPU raw-ring registration, exact concavity partition and evidence-source separation."""
import ast,copy,hashlib,json,math
from pathlib import Path
from shapely.geometry import Polygon
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def need(v,m='condition'):assert v,m
def reject(fn):
 try:fn()
 except (AssertionError,KeyError,ValueError):return
 raise AssertionError('Mutant accepted')
def load_helpers():
 p=ROOT/'work/restoration-v14/registration/analyze_actual_sources.py';tree=ast.parse(p.read_text());wanted={'reflex_indices','split_one_neck','frame'}
 nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in wanted];need(len(nodes)==3)
 from shapely.geometry import LineString
 ns={'math':math,'Polygon':Polygon,'LineString':LineString};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),ns);return ns
H=load_helpers()
def project(lon,lat,pr):
 a=pr['ellipsoid_a'];f=pr['ellipsoid_f'];e=f*(2-f)
 def ecef(lo,la):
  lo,la=map(math.radians,[lo,la]);n=a/math.sqrt(1-e*math.sin(la)**2)
  return[n*math.cos(la)*math.cos(lo),n*math.cos(la)*math.sin(lo),n*(1-e)*math.sin(la)]
 xyz=ecef(lon,lat);org=ecef(pr['originLon'],pr['originLat']);x,y,z=[a-b for a,b in zip(xyz,org)];lo,la=map(math.radians,[pr['originLon'],pr['originLat']])
 return[-math.sin(lo)*x+math.cos(lo)*y,-math.sin(la)*math.cos(lo)*x-math.sin(la)*math.sin(lo)*y+math.cos(la)*z]
def registration_guard(v):
 for row in v['targets']:
  w=row['source_record'];need(row['source_polygon_world']==w['polygon']and row['source_holes_world']==w.get('holes',[]),'raw ring changed')
  rr=row['raw_osm_way'];need(len(rr['node_lonlat'])==len(w['polygon'])+1,'all raw nodes retained')
  need(rr['node_lonlat'][0]==rr['node_lonlat'][-1],'raw ring closed')
  projected=[project(*ll,v['model_projection'])for ll in rr['node_lonlat'][:-1]]
  matched=[[i for i,q in enumerate(projected)if math.dist(p,q)<=.000001]for p in w['polygon']]
  need(all(len(ids)==1 for ids in matched)and len({ids[0]for ids in matched})==len(projected),'raw node ENU complete bijection; normalization may reverse winding')
  fr=row['source_frame'];a=fr['anchor'];c,s=math.cos(fr['rotation_z_rad']),math.sin(fr['rotation_z_rad'])
  need(len(fr['polygon_local'])==len(w['polygon']),'local ring count')
  for p,q in zip(w['polygon'],fr['polygon_local']):need(math.dist(p,[a[0]+c*q[0]-s*q[1],a[1]+s*q[0]+c*q[1]])<=1e-10,'local/world ring mapping')
def main():
 out=HERE/'source-candidate-analysis.json';checks=HERE/'source-candidate-checks.json';need(not out.exists()and not checks.exists(),'preserve prior run')
 invpath=HERE/'candidate-inventory.json';reqpath=HERE/'source-probe-requests.json';d=json.loads(invpath.read_text());r=json.loads(reqpath.read_text());before={str(p.relative_to(ROOT)):sha(p)for p in[invpath,reqpath,HERE/'analyze_source_candidates.py',ROOT/'work/restoration-v14/registration/analyze_actual_sources.py']};by={v['target_id']:v for v in d['targets']}
 ring=by['chongjingdian']['source_polygon_world'];idx,one,two=H['split_one_neck'](ring);pieces=sorted([one,two],key=lambda q:q.centroid.y)
 split={'source_part_id':'way-40632237-p0','strong_reflex_vertex_indices':idx,'all_original_reflex_vertex_indices':H['reflex_indices'](ring),'cut_endpoints':[ring[i]for i in idx],'south_porch_candidate':{'polygon':list(pieces[0].exterior.coords)[:-1],'area_m2':pieces[0].area,'source_frame':H['frame'](pieces[0])},'north_main_candidate':{'polygon':list(pieces[1].exterior.coords)[:-1],'area_m2':pieces[1].area,'source_frame':H['frame'](pieces[1])},'union_equals_original':one.union(two).equals(Polygon(ring)),'symmetric_difference_area_m2':one.union(two).symmetric_difference(Polygon(ring)).area,'overlap_area_m2':one.intersection(two).area,'historical_porch_roof_type':None,'historical_substructure_identity_confirmed':False,'scope':'Only exact complete raw-ring concavity split. Official frontporch relation can qualify this placement; no measured structural frame or porch roof is invented.'}
 maps=[]
 for rel in['work/forbidden-city-research/map/official_panorama_viewpoints_xy_m.json','work/forbidden-city-research/map/official_illustrated_map_hotspots_tc.json','work/forbidden-city-research/map/official_illustrated_map_hotspots_en.json']:
  p=ROOT/rel;v=json.loads(p.read_text());matched=[x for x in v if any(w in json.dumps(x,ensure_ascii=False)for w in['重华','重華','崇敬','葆中','浴德殿','翠云','翠雲','建福','抚辰','撫辰','惠风','惠風'])];maps.append({'path':rel,'sha256':sha(p),'records':matched,'scope':'Official panorama photo viewpoint or illustrated-map hotspot only; never a building footprint/center or geodetic control.'})
 result={'schema':'v15-complete-source-register-cpu-analysis/1','inputs_sha256':before,'source_chongjing_main_porch_partition':split,'source_frame_rows':d['targets'],'raw_node_order_note':'Model preprocessing normalizes ring winding while raw XML retains original order. Check full one-to-one coordinate bijection at unchanged1micrometre, preserving every original point; source rings are not rewritten.','official_map_context':maps,'classification':{'source_qualified_named_candidates':[x['target_id']for x in d['targets']],'buildable_if_official_roof_and_bays_joined':['chongjingdian','chonghuagong','baozhongdian','yudedian','cuiyunguan','jianfugong','fuchendian'],'register_only_retained':['huifengting','chonghuamen'],'chonghua_front_porch':'Official exists but raw main rectangle does not contain a separate front lobe. No geometry/proxy named without matching evidence.','source_material_and_height':'Unmeasured flat grey6m draft, not roof type/colour or actual elevation.','unknown_all_metric_control':True,'global_compound_completeness':False},'native_saved':False,'geometry_created':False,'third_party_cost':0,'human_approval':'pending'}
 out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');rows=[]
 def case(id,inp,op,expected,fn):
  try:fn();passed=True;error=None
  except Exception as e:passed=False;error=f'{type(e).__name__}: {e}'
  rows.append({'id':id,'input':inp,'operation':op,'expected':expected,'passed':passed,'error':error})
 case('REG15-C01','Pinned model/native/manifest/XML plus generatedrequest','Rehash full inputs','All source SHA match',lambda:need(all(sha(ROOT/p)==h for p,h in r['inputs_sha256'].items())))
 case('REG15-C02','All9 target complete raw ring/holes/node refs','Reproject original OSM lonlat and transform local/world everypoint','No original vertices lost; <=1micrometre ENU and1e-10 local registration',lambda:registration_guard(d))
 case('REG15-C03','Nine targetsourceparts/no groups','Compare exact requestedpartset/zero inheritedgroup and allnearby records','9singles including register-only; neighboursnotassigned',lambda:need(len(d['targets'])==9 and set(r['selected_part_ids'])=={s for t in d['targets']for s in t['source_part_ids']}and not d['all_keyword_named_groups']))
 case('REG15-C04','崇敬8point rawshape','Split strongreflex originalvertices','Two validlobes exact union with zeroareaoverlap',lambda:need(split['union_equals_original']and split['overlap_area_m2']==split['symmetric_difference_area_m2']==0 and len(idx)==2))
 case('REG15-C05','Mainrect vs southporch/fullshape','Check sourceactualgeometric ordering','南抱厦与北主体distinct; fullMRR notsubstitute',lambda:need(pieces[0].centroid.y<pieces[1].centroid.y and Polygon(ring).minimum_rotated_rectangle.difference(Polygon(ring)).area>1))
 case('REG15-C06','重华mainrectangle/officialcatalogmissingporch','Count rawvertices/strongconcavities','No fakeporch split or metriccontrol',lambda:need(len(by['chonghuagong']['source_polygon_world'])==4 and H['reflex_indices'](by['chonghuagong']['source_polygon_world'],True)==[] and by['chonghuagong']['official_current_geodetic_control']is None))
 case('REG15-C07','Sourceheight/roof/material fields','Inspect uncertainty flags','All9 unmeasured actualheight/originalflat6notpromoted',lambda:need(all(x['source_height_is_measured']is False and x['official_measured_dimensions_m']is None for x in d['targets'])))
 case('REG15-C08','Officialmapcontext records','Read semantics/coordinate types','Photo/hotspotcontext remains separate from footprint',lambda:need(all('never a building footprint' in x['scope']for x in maps)))
 rev=list(reversed(ring));a,b,c=H['split_one_neck'](rev)
 case('EXTRA-01','Reversed崇敬rawring','Split with winding-aware genuinecorners','Fulloriginalshape andexactzeroareaunion retained',lambda:need(b.union(c).equals(Polygon(ring))and b.intersection(c).area==0))
 case('EXTRA-02','Plain重华rectangle','Require two realconcave neckcorners','Reject inventedporch',lambda:reject(lambda:H['split_one_neck'](by['chonghuagong']['source_polygon_world'])))
 mutant=copy.deepcopy(d);mutant['targets'][0]['source_polygon_world']=mutant['targets'][0]['source_polygon_world'][:-1]
 case('EXTRA-03','One rawringpointdeleted privatecopy','Fulloriginalringguard','Reject',lambda:reject(lambda:registration_guard(mutant)))
 mutant2=copy.deepcopy(d);mutant2['targets'][0]['source_frame']['polygon_local'][0][0]+=.01
 case('EXTRA-04','Privatelocalpointshift1cm','Fullpointtransformguard','Reject',lambda:reject(lambda:registration_guard(mutant2)))
 mutant3=copy.deepcopy(d);mutant3['targets'][0]['raw_osm_way']['node_lonlat'][0][0]+=.0001
 case('EXTRA-05','Privaterawlongitudealtered','OriginalnodeENUguard','Reject',lambda:reject(lambda:registration_guard(mutant3)))
 case('EXTRA-06','AllinputsafterCPU','Rehashagain','No source/native changes',lambda:need(all(sha(ROOT/p)==h for p,h in before.items())and all(sha(ROOT/p)==h for p,h in r['inputs_sha256'].items())))
 summary={'passed':sum(x['passed']for x in rows),'failed':sum(not x['passed']for x in rows)}
 checks.write_text(json.dumps({'schema':'v15-cpu-source-registration-checks/1','test_spec':'TestSpec.md','rows':rows,'summary':summary,'native_opened_by_this_script':False,'native_saved':False},ensure_ascii=False,indent=2)+'\n');print(json.dumps({'summary':summary,'split':split,'mapmatching':[len(x['records'])for x in maps]},ensure_ascii=False));need(summary['failed']==0)
if __name__=='__main__':main()
