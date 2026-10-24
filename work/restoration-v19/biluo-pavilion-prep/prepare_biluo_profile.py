"""CPU-only sourcefit/qualification and preparation for a root actual fixture."""
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

from shapely.geometry import Polygon, Point

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUTS = [
    'work/restoration-v19/five_petal_roofs.py',
    'work/restoration-v19/northern_court_towers.py',
    'work/forbidden_city_geometry.py', 'work/restoration_buildings.py',
    'work/restoration-v19-preparation/facts-and-candidates.json',
    'work/restoration-v19/registration/source-registration-evidence-01.json',
    'work/restoration-v19/registration/actual-source-actors.json',
    'work/restoration-v19/registration/actual-source-domain-checks-01.json',
    'work/restoration-v19/five-petal-qa/private-profile-v1.json',
    'work/restoration-v19/five-petal-qa/private-palette-v1.json',
    'work/restoration-v19/five-petal-qa/run-02/actual-five-petal-tests.json',
    'work/restoration-v19/five-petal-qa/run-02/actual-full-roof-domain-CPU-01.json',
    'work/restoration-v19/five-petal-qa/run-02/actual-execution-02.json',
    'work/restoration-v19/five-petal-qa/run-02/actual-full-domain-execution-01.json',
    *['work/restoration-v19/research/official-media-01/'+f for f in
      ('biluoting-gallery-01.jpg','biluoting-gallery-02.jpg','biluoting-gallery-03.jpg','official-2025-pdfpage-16-render-144dpi.png')],
]
FROZEN_PINS = {
    'work/restoration-v19/five_petal_roofs.py':'dc28a947be149a4f8faef91b249024b719769947f8c9a6da5e338e581d867271',
    'work/restoration-v19/northern_court_towers.py':'e71af7ab930eb8b5e209071a8ecbed06a7fc518d7c8e732776b55c736b74a613',
    'work/forbidden_city_geometry.py':'23f815fc93057a0f69b66adc25536485fc05a33935f67fb1613073963e276efc',
    'work/restoration_buildings.py':'aac18ca8c219b8de544dd78d8a7b99000a4d0fe83d40553614065e0c998aaf60',
    'work/restoration-v19-preparation/facts-and-candidates.json':'1cd2f810ab3f910fa282abd46702eafc10e8c4d052311c89155f4e3954812f58',
    'work/restoration-v19/registration/source-registration-evidence-01.json':'4df276dff1531b5faf09e989bba79a983e6add739a64a2880fb59241ad9a0b23',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(relative):
    return json.loads((ROOT/relative).read_text())


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n')


def require(value, message):
    if not value:
        raise AssertionError(message)


def functions(path, names, scope):
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
    require({n.name for n in nodes} == set(names),'CPU AST inventory differs')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope)
    return SimpleNamespace(**{n:scope[n] for n in names})


def validator():
    import re
    petal = functions(ROOT/'work/restoration-v19/five_petal_roofs.py',('_number','_fact','_validate','_point'),{'math':math,'json':json,'re':re})
    f = SimpleNamespace(_ring_area=lambda r:sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(r,r[1:]+r[:1]))/2)
    return functions(HERE/'biluo_pavilion.py',('_require','_number','_circle','_axes','_inradius','_validate'),{'math':math,'json':json,'F':f,'P':petal})


def make():
    for rel,pin in FROZEN_PINS.items():
        require(sha(ROOT/rel) == pin,'Frozen input drift: '+rel)
    actual=read('work/restoration-v19/five-petal-qa/run-02/actual-execution-02.json')
    domain=read('work/restoration-v19/five-petal-qa/run-02/actual-full-domain-execution-01.json')
    require(actual['summary']==[15,0] and actual['actual_terminal_exit_code']==0,'Prior roof factory not green')
    require(domain['summary']==[3,0] and domain['actual_terminal_exit_code']==0,'Prior roof full domain not green')
    facts=read('work/restoration-v19-preparation/facts-and-candidates.json')['entities']['biluoting']['fields']
    r=next(e for e in read('work/restoration-v19/registration/source-registration-evidence-01.json')['candidate_buildings'] if e['candidate_building_id']=='biluoting')
    p={k:copy.deepcopy(r[k]) for k in ('source_part_id','source_polygon_local','source_holes_local','source_polygon_world','source_holes_world','anchor','rotation_z_rad','original_source_record','source_record_sha256','source_actual_actor_names')}
    p.update(building_id='biluoting',primitive_id='biluo_sourcefit_pavilion',column_count=5,occupied_storeys=None,
             reference_floor_count=1,dimension_status='unmeasured_study',third_party_cost=0,paid_service_calls=0,
             human_approval='pending',historical_identity_confirmed=False,allowed_hidden_source_actor_names=[],
             source6m_proxy_height_is_real_building_height=False,mountain_is_reconstructed=False,
             source_support_bottom_z_m=0,known_facts=copy.deepcopy(facts))
    # These are newly chosen sourcefit controls, not promoted private facts.
    roof=copy.deepcopy(read('work/restoration-v19/five-petal-qa/private-profile-v1.json'))
    roof.update(primitive_id='biluo_sourcefit_real_roofs',known_facts=copy.deepcopy(facts),scope='Sourcefit exterior study roof controls; all metres/RGB/phase unmeasured')
    roof['roof_tiers'][0].update(outer_radius_m=1.9,lobe_amplitude_m=.28,inner_radius_m=1.0,inner_lobe_amplitude_m=.05)
    for tier in roof['roof_tiers']:
        tier['eave_z_m']+=2.4; tier['top_z_m']+=2.4
    roof['roof_tiers'][1].update(eave_z_m=6.90,top_z_m=7.60)
    p['roof_profile']=roof
    p['study']={'source_support_top_z_m':2.4,'reference_floor_top_z_m':2.6,
                'column_axis_radius_m':.8,'column_radius_m':.12,
                'lower_bearing_axis_radius_m':1.45,'lower_bearing_radius_m':.1,
                'beam_width_m':.26,'beam_height_m':.22,
                'lower_beam_top_z_m':5.1,'upper_beam_top_z_m':6.65}
    p['material_scheme']={'column':'neutral','beam':'neutral','source_support':'neutral','reference_floor':'other_neutral'}
    p['parameter_evidence']={
        'all_numeric_controls':'unmeasured_study; metres, source-frame azimuth, phase, five column angles, all support/platform heights and RGB are not historical measurements',
        'roof_revisions_from_private_fixture':{'lower_outer_radius_m':[2.0,1.9],'lower_lobe_amplitude_m':[.3,.28],
                                              'lower_inner_radius_m':[.8,1.0],'lower_inner_lobe_amplitude_m':[.08,.05],
                                              'initial_roof_Z_shift_m':2.4,'reason':'complete source fit and five continuous columns wholly inside true lower hole'},
        'upper_visual_proportions':{'status':'unmeasured_study','visual_sources':['official gallery01','official2025 PDF page16/published39','private upper-oblique inspected'],
                                    'upper_rise_m':.70,'upper_outer_radius_m':1.35,'rise_over_outer_radius':.70/1.35,
                                    'lower_inner_top_to_upper_eave_gap_m':.50,'upper_beam_top_z_m':6.65,
                                    'reason':'private rise1.4/outer1.35 visually over-pointed versus official images; reduced rise is explicit visual study, not pixel measurement'},
        'source_support_reference':'full seven-point neutral volume from 0 to study 2.4m; not fabricated mountain/rock silhouette or surveyed peak',
        'reference_floor':'one full seven-point study slab from2.4 to2.6m; not an interior/upper occupied-storey plate',
        'continuous_columns':'five axes at study phase+2pi*i/5, radius.8m; entire shaft lies in actual lower skin hole; upper tops clipped to real upper underside',
        'lower_support':'five .26m wide/.22m high radial beams overlap continuous columns and wholly cover .1m bearing feet; five caps clip real lower underside',
        'rotation':'roof phase baked into private mesh copies before T._contact_surface; source root transform applies once',
        'no_occupied_floor_inference':True,'no_third_court_7m_height_inference':True,
        'actual_fixture_pending':True,
    }
    p['unbuilt']=['Real mountain/rock geometry, measured peak/floor/bridge/column angles and complete source-to-current survey',
                  'South stone bridge to Cuishanglou second storey, east/west lower-mountain steps and support contacts',
                  'Ice-plum finial, curved white-stone plum balustrade, branch-plum hanging spandrels and carved ceiling',
                  'Suzhou painted-beam motif, exact roof/column proportions, concealed historical carpentry and physical tile cavity']
    palette=read('work/restoration-v19/five-petal-qa/private-palette-v1.json')
    palette['scope']='Official documentary roof-color categories only; all RGBA/finish numerical controls unmeasured_study; unqualified support/columns neutral'
    v=validator(); mats={k:SimpleNamespace(name='CPU_'+k) for k in palette['materials']}; v._validate(p,mats)
    full=Polygon(p['source_polygon_local']); radius=max(t['outer_radius_m']+t['lobe_amplitude_m']+t['ridge_radius_m'] for t in roof['roof_tiers'])
    require(full.covers(Point(0,0).buffer(radius,resolution=256)),'Full roof envelope outside exact source')
    require(p['known_facts']==r['original_typed_factual_source_fields'],'Full documentary fields changed')
    pins={rel:sha(ROOT/rel) for rel in INPUTS}
    pins.update({str(path.relative_to(ROOT)):sha(path) for path in (Path(__file__),HERE/'biluo_pavilion.py')})
    return p,palette,{'schema':'v19-biluo-pavilion-preparation/1','input_files_sha256':pins,
                      'prior_roof_only_actual':[15,0],'prior_roof_only_full_domain':[3,0],
                      'new_assembly_actual_verified':False,'new_module_changed_roof_controls_require_new_actual':True,
                      'source_vertices':len(p['source_polygon_local']),'source_holes':0,
                      'source_inradius_m':v._inradius(p['source_polygon_local']),'conservative_complete_roof_envelope_radius_m':radius,
                      'roof_envelope_full_source_covers':True,'Blender_started':False,'native_saved':False,
                      'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False}


def main():
    profile_path,palette_path,report_path=[HERE/f for f in ('profile-v2.json','palette-v1.json','preparation-03.json')]
    require(not profile_path.exists() and not report_path.exists(),'Preserve earlier profile/preparation outputs')
    profile,palette,report=make()
    if palette_path.exists():require(json.loads(palette_path.read_text())==palette,'Preserve prior palette; values differ')
    else:write(palette_path,palette)
    write(profile_path,profile)
    report['profile_sha256']=sha(profile_path);report['palette_sha256']=sha(palette_path)
    report['supersedes_preparation_02']='Root visual correction: upper rise0.70/outer1.35, band gap0.50; all controls unmeasured_study, no private/frozen module change'
    write(report_path,report)
    print(json.dumps({'profile_sha256':report['profile_sha256'],'source_vertices':7,'Blender_started':False}))


if __name__=='__main__':main()
