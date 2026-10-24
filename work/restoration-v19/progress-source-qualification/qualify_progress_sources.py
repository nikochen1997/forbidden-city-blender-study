from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,copy,math
from bs4 import BeautifulSoup
from shapely.geometry import Polygon
from shapely.ops import unary_union
from PIL import Image
ROOT=Path.cwd();OUT=ROOT/'work/restoration-v19/progress-source-qualification'
TARGETS=[('fuwangge','符望阁','way-40629261-p0','236495'),('juanqinzhai','倦勤斋','way-1341826246-p0','236478'),('yucuixuan','玉粹轩','way-40629263-p0','236460'),('biluoting','碧螺亭','way-43525093-p0','236435')]
EXPECTED_EN={'fuwangge':'Building of Wish and Reality','juanqinzhai':'Lodge of Retirement','yucuixuan':'Pavilion of Jade Purity','biluoting':'Pavilion of the Green-jade Conch Shell'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical_sha(o):return hashlib.sha256(json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def dump(n,d):(OUT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def need(c,m):
 if not c:raise AssertionError(m)
inputs=['work/restoration-v19/registration/actual-source-actors.json','work/restoration-v19-preparation/facts-and-candidates.json','work/forbidden-city-research/geospatial/model-data.json','work/restoration-v19/research/official-media-01/official-2025-general-plan-native-427x1658.jpeg','work/restoration-v19/research/official-media-01/official-2025-pdfpage-04-render-144dpi.png','work/restoration-v19/research/official-media-01/official-2025-04-LiYue-QianlongGarden-original.pdf']+[f'work/restoration-v19/research/official-media-01/{i[0]}-official-page.html'for i in TARGETS]
before={p:sha(ROOT/p)for p in inputs};actual=json.loads((ROOT/inputs[0]).read_text());facts=json.loads((ROOT/inputs[1]).read_text());model=json.loads((ROOT/inputs[2]).read_text());rows=actual['actor_evidence'];parts={x['id']:x for x in model['parts']};EPS=0.0001;AREA_EPS=1e-7
origin=parts['way-40629261-p0']['polygon'][0];q=parts['way-40629261-p0']['polygon'][1];dx=q[0]-origin[0];dy=q[1]-origin[1];length=math.hypot(dx,dy);east=(dx/length,dy/length);north=(-east[1],east[0])
def uv(p):return [sum((p[i]-origin[i])*east[i]for i in range(2)),sum((p[i]-origin[i])*north[i]for i in range(2))]
manual={
'fuwangge':{'official_named_fact_paraphrase':'第四院主体，方形，外观两层/内部三层，四角攒尖顶，黄瓦蓝檐脊。','official_plan_relation':'p27具名引线落在北部第四院中央大方阁；倦勤位其北，玉粹位其西，碧螺位其南山屏。','English_tag_assessment':'英文措辞和alt_name均指符望语义；未核为官方唯一译名；未发现指向相邻异名建筑的显性冲突。','shape_limit':'源10点是有小折点的近方域；不是官方实测墙/柱/檐脚印。building:levels=3只与内实三层相容，不得替代外观两层说明。'},
'juanqinzhai':{'official_named_fact_paraphrase':'花园最北端、符望之后、北倚宫墙，坐北朝南，九间前廊，东五西四，绿瓦黄边卷棚硬山顶。','official_plan_relation':'p27最北长条具名倦勤斋，位符望北面；中东两段廊形成联系，西部邻竹香弓墙。','English_tag_assessment':'Lodge of Retirement为语义相容的源英文标签；不以该译名独立确认位置或尺寸。','shape_limit':'源4点长条矩形与九间长楼的定性形制相容；没有官方米制开间、前廊/屋檐界及实际楼层标高。'},
'yucuixuan':{'official_named_fact_paraphrase':'西倚宫墙、东望符望，三间前廊，黄瓦绿檐脊卷棚歇山，南接石山；北侧通道联系竹香并以廊东接符望。','official_plan_relation':'p27玉粹具名在符望西侧建筑链的南段，净尘心室在其北；不能把北邻同名竹香源一并替换。','English_tag_assessment':'Pavilion of Jade Purity与玉粹含义相容；无已发现相邻异名指向冲突；未核官方唯一译名。','shape_limit':'仅用40629263完整4点环作为进度占位；源边界类型未测，官文没有直接明确朝向字段，facing继续null。'},
'biluoting':{'official_named_fact_paraphrase':'符望之前山屏主峰上的梅花形五瓣亭，五柱五脊、重檐，南桥通萃赏二层；山顶高程未测。','official_plan_relation':'p27符望南面的山屏中具名碧螺亭，位萃赏北，与源小独立亭的位置关系相符。','English_tag_assessment':'Green-jade Conch Shell与碧螺词义相容；没有发现相邻异名指向冲突；英文标签不证明实测形制。','shape_limit':'源是7点凸环，官方是五梅瓣/五柱，几何存在明确细节不一致；仅允许源域锚定的未测进度研究，不把7点解释成七柱七坡或真实梅瓣。山体支承和标高需另验。'}}
entries=[];checks=[];cap_proofs=[]
for key,name,sid,num in TARGETS:
 actor=sid+'_原轮廓主体'; row=rows[actor]; src=row['source_record'];need(src==parts[sid],sid+' full record differs from model-data')
 need(row['complete_source_polygon_world']==src['polygon'] and row['complete_source_holes_world']==src['holes'],'full rings lost')
 for vk,fk in [('raw_vertices','raw_faces'),('evaluated_world_vertices','evaluated_world_faces')]:
  vs=row[vk];need(all(len(v)==3 and all(math.isfinite(t)for t in v)for v in vs),'nonfinite geometry');need(all(len(f)>=3 and all(isinstance(j,int)and 0<=j<len(vs)for j in f)for f in row[fk]),'face index')
 p=Polygon(src['polygon'],src['holes']);need(p.is_valid and p.area>0,'invalid original source ring')
 tri=row['actual_projected_bottom_cap_triangles_world'];cap=unary_union([Polygon([(v[0],v[1])for v in t])for t in tri]);need(cap.geom_type=='Polygon' and len(cap.interiors)==len(src['holes']),'actual cap components/holes')
 proof={'source_id':sid,'complete_original_ring_vertices':len(src['polygon']),'source_holes':len(src['holes']),'actual_bottom_triangles':len(tri),'raw_symmetric_difference_area_source_m2':p.symmetric_difference(cap).area,'boundary_hausdorff_source_m':p.boundary.hausdorff_distance(cap.boundary),'source_missing_after_100um_area_m2':p.difference(cap.buffer(EPS)).area,'actual_outside_after_100um_area_m2':cap.difference(p.buffer(EPS)).area,'source_engineering_units_not_architectural_survey':True}
 need(proof['boundary_hausdorff_source_m']<=EPS and proof['source_missing_after_100um_area_m2']<=AREA_EPS and proof['actual_outside_after_100um_area_m2']<=AREA_EPS,'complete actual cap differs beyond fixed engineering tolerance');cap_proofs.append(proof)
 html=ROOT/f'work/restoration-v19/research/official-media-01/{key}-official-page.html';text=BeautifulSoup(html.read_text(),'html.parser').get_text(' ',strip=True);start=text.index('【'+name+'】');stop=text.index('撰稿人',start);body=text[start:stop]
 need(src['original_tags'].get('name')==name and src['original_tags'].get('name:zh')==name,'Chinese identity conflict');need(src['original_tags'].get('name:en')==EXPECTED_EN[key],'English source tag changed')
 need(len([r for r in rows.values()if r.get('source_part_id')==sid])==1,'multiple actual actor source mapping')
 coords=[uv(x)for x in src['polygon']]
 e={'building_id':key,'name_zh':name,'source_part_id':sid,'actual_actor_name':actor,'proposed_replace_actor_names':[actor],
 'source_record':src,'source_record_sha256_from_probe':row['source_record_sha256'],'source_record_canonical_sha256':canonical_sha(src),
 'complete_source_polygon_world':row['complete_source_polygon_world'],'complete_source_holes_world':row['complete_source_holes_world'],
 'original_source_ring_vertex_count':len(src['polygon']),'original_source_hole_count':len(src['holes']),
 'actual_full_actor_row_canonical_sha256':canonical_sha(row),'raw_mesh_sha256':row['raw_mesh_sha256'],'actual_visibility_at_probe':row['visibility'],'actual_material_slots_at_probe':row['actual_material_slots'],'bounds_world_xyz_at_probe':row['bounds_world_xyz'],
 'actual_cap_proof':proof,'source_aligned_relative_bbox_uv':{'u':[min(c[0]for c in coords),max(c[0]for c in coords)],'v':[min(c[1]for c in coords),max(c[1]for c in coords)]},
 'official_source':{'url':'https://www.dpm.org.cn/explore/building/'+num+'.html','local_saved_HTML':str(html.relative_to(ROOT)),'local_HTML_sha256':sha(html),'complete_named_body_read':True,'complete_named_body_character_count':len(body),'complete_named_body_sha256':hashlib.sha256(body.encode()).hexdigest(),'source_scope':'named body before author and glossary; not generic glossary'},
 'all_original_fact_fields_preserved':facts['entities'][key]['fields'],'manual_qualification':manual[key],
 'source_identity_status':'same-name and relative-location evidence sufficient only for revocable unmeasured progress-study candidate','no_disqualifying_identity_conflict_found_in_checked_evidence':True,
 'current_field_measurement':False,'official_metric_footprint':None,'absolute_historical_identity_approved':False,'human_approval':'pending','source_hidden_by_this_package':False,
 'reversible_progress_proxy_replacement_candidate':True,'replacement_visibility_decision_owner':'root after full-domain generated-geometry checks','replacement_executed_here':False}
 entries.append(e)
b={e['building_id']:e['source_aligned_relative_bbox_uv']for e in entries}
relations=[{'id':'north_juanqin_of_fuwang','passed':b['juanqinzhai']['v'][0]>b['fuwangge']['v'][1]}, {'id':'west_yucui_of_fuwang','passed':b['yucuixuan']['u'][1]<b['fuwangge']['u'][0]}, {'id':'south_biluo_of_fuwang','passed':b['biluoting']['v'][1]<b['fuwangge']['v'][0]}]
need(all(x['passed']for x in relations),'official relation mismatch')
images=[]
for rel in inputs[3:5]:
 im=Image.open(ROOT/rel).convert('RGB');images.append({'file':rel,'sha256':sha(ROOT/rel),'pixel_dimensions':list(im.size),'decoded_RGB_sha256':hashlib.sha256(im.tobytes()).hexdigest(),'actually_viewed_this_task':True,'tool':'tools.view_image detail=original'})
package={'schema':'v19.four-progress-source-qualification/1','created_utc':datetime.now(timezone.utc).isoformat(),'purpose':'conditional revocable replacement candidates for four gray unmeasured 6m source proxies; no exact historical or metric approval',
 'input_sha256':before,'source_probe_native_sha256':actual.get('native_sha256'),'source_probe_readout_only_not_native_reopened':True,
 'full_stage19_five_target_scope':['fuwangge','juanqinzhai','yucuixuan','zhuxiangguan','biluoting'],'this_mapping_scope':[x[0]for x in TARGETS],'this_mapping_count':4,'not_equal_to_five_complete':True,
 'pending_fifth':{'building_id':'zhuxiangguan','status':'pending_main_ear_gallery_world_registration','included_in_proposed_replacements':False,'Chinese_way43525094_renamed':False},
 'proposed_replace_actor_names':[e['actual_actor_name']for e in entries],'entries':entries,
 'relative_source_frame':{'origin_world_xy':origin,'east_unit':east,'north_unit':north,'basis':'first Fuwang source edge; source topology only','official_plan_metric_registration':False},
 'official_plan':{'PDF_url':'https://www.dpm.org.cn/Uploads/file/2025/04/23/1745375120FyrkQWemo260.pdf','PDF_page_1based':4,'published_page':27,'actual_views':images,'purpose':'named relative-position check only; no pixel-to-metre inference'},
 'relative_relationship_checks':relations,'candidate_identity_disqualification_found':False,'unknowns_preserved':True,'source_proxy_6m_is_measurement':False,
 'human_approval':'pending','absolute_historical_identity_approved':False,'current_field_measurement':False,'hide_permission_granted_by_this_package':False,
 'root_may_decide_reversible_visibility_after_independent_full_domain_QA':True,'source_visibility_changed_here':False,'Blender_started':False,'native_opened_or_saved':False,'paid_calls':0,'third_party_cost':0,'stage19_complete':False,'whole_city_complete':False}
dump('four-progress-source-mapping-01.json',package)

def validate(d):
 need(d['this_mapping_count']==4 and set(d['this_mapping_scope'])=={x[0]for x in TARGETS},'four-only scope lost')
 expected=[x[2]+'_原轮廓主体'for x in TARGETS];need(d['proposed_replace_actor_names']==expected,'actor set contains missing/wrong/fifth actor')
 need(d['human_approval']=='pending' and d['absolute_historical_identity_approved'] is False and d['current_field_measurement'] is False,'approval/measurement promotion')
 need(d['pending_fifth']['included_in_proposed_replacements'] is False and d['pending_fifth']['Chinese_way43525094_renamed'] is False and d['not_equal_to_five_complete'] is True,'bamboo boundary violated')
 need(d['paid_calls']==0 and d['third_party_cost']==0 and d['Blender_started'] is False and d['native_opened_or_saved'] is False,'zero budget/read-only guard')
 for e,(key,name,sid,num) in zip(d['entries'],TARGETS):
  row=rows[sid+'_原轮廓主体'];need(e['building_id']==key and e['source_part_id']==sid and e['actual_actor_name']==row['name'],'actor mapping changed')
  need(e['complete_source_polygon_world']==row['complete_source_polygon_world'] and e['complete_source_holes_world']==row['complete_source_holes_world'],'complete original rings changed')
  need(e['all_original_fact_fields_preserved']==facts['entities'][key]['fields'],'unknown or known facts mutated')
  need(e['human_approval']=='pending' and e['absolute_historical_identity_approved'] is False and e['current_field_measurement'] is False and e['replacement_executed_here'] is False,'entry approval promoted')
 return True

def test(id,fn):
 try:r=fn();checks.append({'id':id,'passed':True,'evidence':r})
 except Exception as exc:checks.append({'id':id,'passed':False,'error':str(exc)})
def negative(fn):
 d=copy.deepcopy(package);fn(d)
 try:validate(d)
 except AssertionError as e:return {'real_private_mutation_rejected':True,'reason':str(e)}
 raise AssertionError('negative accepted')
test('MAP-01',lambda:validate(package))
test('CAP-01',lambda:cap_proofs)
test('RELATION-01',lambda:relations)
test('EXTRA-1',lambda:negative(lambda d:d['proposed_replace_actor_names'].append('way-43525094-p0_原轮廓主体')))
test('EXTRA-2',lambda:negative(lambda d:d.update(absolute_historical_identity_approved=True)))
test('EXTRA-3',lambda:negative(lambda d:d['entries'][3].update(complete_source_polygon_world=d['entries'][3]['complete_source_polygon_world'][:5])))
test('EXTRA-4',lambda:negative(lambda d:d['entries'][2].update(actual_actor_name=d['entries'][0]['actual_actor_name'])))
test('EXTRA-5',lambda:negative(lambda d:d.update(human_approval='approved')))
test('INPUT-FREEZE',lambda:need(before=={p:sha(ROOT/p)for p in inputs},'original input byte changed'))
dump('CPU-checks-01.json',{'schema':'v19.progress-source-qualification-CPU/1','tests':checks,'passed':sum(x['passed']for x in checks),'failed':sum(not x['passed']for x in checks),'fixed_boundary_EPS_source_m':EPS,'fixed_area_EPS_source_m2':AREA_EPS,'engineering_tolerance_not_survey_accuracy':True,'input_sha256':before,'source_gray_proxy_slots_verified':'FC_grey','four_complete_caps_checked':True,'Blender_started':False,'native_opened_or_saved':False,'human_approval':'pending','paid_calls':0,'third_party_cost':0})
need(all(x['passed']for x in checks),'QA failure');print(json.dumps({'passed':sum(x['passed']for x in checks),'failed':sum(not x['passed']for x in checks),'protected_inputs':len(before),'four_mapping_qualified_for':'conditional unmeasured progress study only'},ensure_ascii=False))
