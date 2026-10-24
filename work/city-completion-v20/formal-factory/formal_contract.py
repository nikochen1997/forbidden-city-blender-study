"""Pure production-source contract. Never imports Blender or geometry builders."""
import copy
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
PROFILE_PACKAGE='work/city-completion-v20/shouan-production-profile/production-profiles.json'
PROFILE_PACKAGE_SHA='44fd1d4f5b0383494c44db3b8883b560e0230565635fbefe891ea9c20a0d4504'
PALETTE='work/city-completion-v20/shouan-production-profile/production-palette.json'
PALETTE_SHA='b07f48e00b17d80d127ac914dc85804fdcc6d1fde2c3b1ffb0fb6dc7ad288b85'
QUALIFICATION='work/city-completion-v20/plan-registration/shouan79-source-bounded-qualification-proposal-02.json'
QUALIFICATION_SHA='af9cd952bd51fa5eb7f512a7b2544ebb3ab25c88d2943cc047e152b400d78872'
PROBE='work/city-completion-v20/shouan-registration/run-01/actual-source-actors.json'
PROBE_SHA='7f22e6c002a86d856ebdcc10af1784b94444d9d433b4ac2d55f7eade7f31c54b'
SOURCE_CPU='work/city-completion-v20/shouan-registration/run-01/actual-source-domain-CPU-01.json'
SOURCE_CPU_SHA='69f6002e258e48ed86e20902db84497643f7bfd137ec36e81c4ba3043999665e'
SUBJECT='way-40624979-p0'
ACTOR=SUBJECT+'_原轮廓主体'
BASE_SHA='c2e981596258654e9f15ff9ab60f065d5b068a7f72b4a1cd39cf343203f1f125'


def require(ok,message):
    if not ok:raise AssertionError(message)


def canonical(doc):return json.dumps(doc,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def equal(a,b):return canonical(a)==canonical(b)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())


def zero_scope(doc):
    for key in('third_party_cost','paid_service_calls'):require(type(doc[key])is int and doc[key]==0,'strict integer zero: '+key)
    require(doc['human_approval']=='pending'and doc['whole_city_complete']is False,'scope promotion')


def path(rel):
    require(isinstance(rel,str)and rel,'nonempty workspace path required')
    p=(ROOT/rel).resolve();require(p.is_relative_to(ROOT),'workspace path escape');return p


def load_evidence():
    for rel,h in{PROFILE_PACKAGE:PROFILE_PACKAGE_SHA,PALETTE:PALETTE_SHA,QUALIFICATION:QUALIFICATION_SHA,PROBE:PROBE_SHA,SOURCE_CPU:SOURCE_CPU_SHA}.items():require(sha(path(rel))==h,'source qualification/input changed: '+rel)
    package=read(path(PROFILE_PACKAGE));require(package['schema']=='v20-source-bounded-shouan79-production-study/1'and len(package['buildings'])==1,'exact production one-profile schema required')
    profile=package['buildings'][0];validate_profile(profile,profile)
    q=read(path(QUALIFICATION));probe=read(path(PROBE));cpu=read(path(SOURCE_CPU))
    require(q['qualified_for_conditional_source_bounded_study']is True and q['subject_source_id']==SUBJECT,'real source79 study qualification required')
    require(cpu['summary']=={'passed':7,'failed':0}and cpu['native_sha256']==probe['native_sha256']==BASE_SHA,'actual source7/0 proof missing')
    source=probe['actor_evidence'][ACTOR]['source_record']
    require(equal(source,profile['original_source_record'])and equal(source['polygon'],profile['source_polygon_world'])and equal(source['holes'],profile['source_holes_world']),'full actual source differs')
    require(len(source['polygon'])==11 and source['holes']==[],'all11point ring required')
    require(probe['all_mesh_raw_evaluated_material_relations_camera_guards_equal']is True and probe['native_mesh_count']==14976 and probe['original_source_mesh_count']==2845 and probe['camera_count']==136,'actual full-scene source guards required')
    return profile,read(path(PALETTE)),q,probe,cpu


def validate_profile(profile,expected):
    require(equal(profile,expected),'production profile differs from exact pinned qualified profile')
    zero_scope(profile)
    require(profile['preparation_scope']=='qualified_source_bounded_unmeasured_study'and profile['production_use_allowed']is True,'cannot promote private fixture or pending draft')
    require(profile['source_part_id']==SUBJECT and profile['source_actual_actor_names']==[ACTOR]and profile['source_actor_geometry_verified']is True,'actual source actor missing')
    require(profile['allowed_hidden_source_actor_names']==[]and profile['historical_identity_confirmed']is False and profile['generated_geometry_verified']is False,'no hide/history/generated permission')
    require(profile['facing']is None and profile['eaves_tiers']is None and profile['occupied_storeys']is None and profile['factual_height_m']is None and profile['factual_floor_z_m']is None and profile['source6m_is_actual_height']is False,'factual unknown promoted')
    require(type(profile['bays_x'])is int and profile['bays_x']==5 and type(profile['bays_y'])is int and profile['bays_y']==3,'documented 5x3 required')
    spans=profile['column_bay_widths_y_m'];d=profile['dimensions']['body_depth_m']
    require(len(spans)==3 and all(abs(a/d-b)<1e-12 for a,b in zip(spans,[49/189,86/189,54/189])),'pixel north-to-south must reverse for local south-to-north Y')
    return True


def construction_profile(profile):
    """G14 construction copy only; never replaces source registration evidence."""
    q=copy.deepcopy(profile);q['anchor']=[0.,0.,0.];q['rotation_z_rad']=0.
    q['source_polygon_world']=copy.deepcopy(profile['source_polygon_local'])
    q['source_holes_world']=copy.deepcopy(profile['source_holes_local'])
    return q


def stable_mesh_name(owner_name):
    return 'V20_SHOUAN79_MESH_'+hashlib.sha256(owner_name.encode()).hexdigest()[:24]


def check_bound_files(binding):
    require(binding['schema']=='v20-shouan79-formal-factory-binding/1','formal source-bound binding required')
    zero_scope(binding)
    require(binding['production_build_allowed']is True and binding['native_open_allowed']is False and binding['source_hide_allowed']==[],'formal factory scope differs')
    pins=binding['inputs_sha256'];require(isinstance(pins,dict)and pins,'complete input pins required')
    for rel,h in pins.items():require(isinstance(h,str)and len(h)==64 and sha(path(rel))==h,'bound input drift: '+rel)
    for rel,h in{PROFILE_PACKAGE:PROFILE_PACKAGE_SHA,PALETTE:PALETTE_SHA,QUALIFICATION:QUALIFICATION_SHA,PROBE:PROBE_SHA,SOURCE_CPU:SOURCE_CPU_SHA}.items():require(pins.get(rel)==h,'mandatory actual qualification pin missing')
    require(binding['adapter_module'].endswith('/shouan_recess_adapter_v2.py')and binding['adapter_module']in pins,'explicit reviewed adapter_v2 required; pending old adapter forbidden')
    require(binding['single_profile']in pins and binding['scene_builder']in pins,'single profile/scene builder unbound')
    profile,palette,*_=load_evidence();validate_profile(read(path(binding['single_profile'])),profile)
    return profile,palette


def validate_world_header(doc,binding,profile):
    require(doc['schema']=='v20-source-bounded-shouan-recess-actual-world/1'and doc['coordinate_space']=='WORLD','source-bound actual WORLD schema required')
    require(doc['native_opened']is False and doc['native_saved']is False and doc['rendered']is False and doc['production_build']is True,'isolated real production study factory required')
    zero_scope(doc);validate_profile(doc['profile'],profile)
    require(doc['occupied_storeys']is None and doc['source_visibility_changes']==[],'no occupied/hide authorization')
    require(equal(doc['inputs_sha256'],binding['inputs_sha256']),'actual factory input pins differ')
    require(equal(doc['construction_frame_transform'],{'method':'G14 near-origin full-source working copy, restore original p and unique newroot WORLD before observer/adapter','original_anchor':profile['anchor'],'original_rotation_z_rad':profile['rotation_z_rad'],'working_anchor':[0.,0.,0.],'working_rotation_z_rad':0.,'full_source_rings_retained':True,'original_profile_unchanged':True}),'construction/WORLD restoration not disclosed')
    require(doc['protected_global_before']==doc['protected_global_after']and len(doc['protected_global_before'])==3,'all default3 global objects must be unchanged')
    return True
