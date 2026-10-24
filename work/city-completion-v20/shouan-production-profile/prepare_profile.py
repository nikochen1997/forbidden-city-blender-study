"""Read real pinned source evidence and emit one conditional production study.

CPU only. Never imports Blender, a scene producer or a private fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path

from source_bounded_profile import profile_from_evidence, require

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
PINS={
 'work/city-completion-v20/plan-registration/shouan79-source-bounded-qualification-proposal-02.json':'af9cd952bd51fa5eb7f512a7b2544ebb3ab25c88d2943cc047e152b400d78872',
 'work/city-completion-v20/shouan-registration/run-01/actual-source-actors.json':'7f22e6c002a86d856ebdcc10af1784b94444d9d433b4ac2d55f7eade7f31c54b',
 'work/city-completion-v20/shouan-registration/run-01/actual-source-domain-CPU-01.json':'69f6002e258e48ed86e20902db84497643f7bfd137ec36e81c4ba3043999665e',
 'work/city-completion-v20/shouan-registration/source-local-frame-draft-01.json':'33c09627e9da6af437a9b212dc6c9a71bb2a421eadcb8c8a20220b2ef32255c5',
 'work/city-completion-v20/shouan-research/typed-facts-and-candidates.json':'6daeb1468755ebebb670fb77540c9814160a4bfed94c86deaa7a510f3a9ef6ab',
 'work/city-completion-v20/plan-registration/plan-source-diagnostic-01.json':'60c4263c7c486df0c7ce09272fd6be2c9a960c1a8710f538027bd79f331fc25f',
 'work/city-completion-v20/plan-registration/official-plan10-embedded.png':'a7a3c47e48c1864fe3dd5a53244e25a9da108f08ef22f467f3b55ec3f62f2a83',
 'work/city-completion-v20/shouan-research/shouan-official-236505.html':'1dde848ad38f1cf092378c9cd365ce47b9f45e066d26f27df6f4a5e733551f30',
 'work/city-completion-v20/shouan-research/official-2025-stone-paving.pdf':'398799d8941b230c6ef2aaf1cb9c13e882b9cb2c0cc411c4d6ede75828f263b1',
 'work/forbidden-city-research/geospatial/model-data.json':'06dfa30cbd6401d2b555b842c03dd47fa055a4de6024b4904b39cc2652a2248e',
 'work/courtyard_hall_buildings.py':'5123db7be8948e9bdb4dc6d8edb712d01ad98075e5e6a40251be5aa8f666a86d',
 'work/restoration_buildings.py':'aac18ca8c219b8de544dd78d8a7b99000a4d0fe83d40553614065e0c998aaf60',
 'work/forbidden_city_geometry.py':'23f815fc93057a0f69b66adc25536485fc05a33935f67fb1613073963e276efc',
 'work/four_hall_buildings.py':'1d3267d25946ecf468da3a9d60103ef522c202452f60d0e500643d14ce9dcc1a',
}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_inputs():
    for name,expected in PINS.items():require(sha(ROOT/name)==expected,'pinned input changed: '+name)
    def read(s):return json.loads((ROOT/s).read_text())
    q=read('work/city-completion-v20/plan-registration/shouan79-source-bounded-qualification-proposal-02.json')
    actor_doc=read('work/city-completion-v20/shouan-registration/run-01/actual-source-actors.json')
    cpu=read('work/city-completion-v20/shouan-registration/run-01/actual-source-domain-CPU-01.json')
    require(cpu['summary']=={'passed':7,'failed':0},'real full-cap source CPU proof missing')
    require(cpu['native_sha256']==actor_doc['native_sha256']=='c2e981596258654e9f15ff9ab60f065d5b068a7f72b4a1cd39cf343203f1f125','working native provenance changed')
    require(actor_doc['native_mesh_count']==14976 and actor_doc['original_source_mesh_count']==2845 and actor_doc['camera_count']==136,'native header differs')
    require(actor_doc['all_mesh_raw_evaluated_material_relations_camera_guards_equal']is True
        and actor_doc['native_saved']is False and actor_doc['renderer_called']is False
        and actor_doc['geometry_created']is False,'actual source guard or read-only evidence missing')
    frame=read('work/city-completion-v20/shouan-registration/source-local-frame-draft-01.json')['sources'][0]
    actual=actor_doc['actor_evidence']['way-40624979-p0_原轮廓主体']
    official=read('work/city-completion-v20/shouan-research/typed-facts-and-candidates.json')['buildings']['shouan_main']
    model=read('work/forbidden-city-research/geospatial/model-data.json')
    records={x['id']:x for x in model['parts']}
    require(records['way-40624979-p0']==actual['source_record']==frame['original_source_record'],'model/frame/actual source records differ')
    neighbours=[records[k]for k in('way-40624995-p0','way-40624997-p0')]
    return q,frame,actual,official,neighbours


def make_package():
    q,frame,actual,official,neighbours=load_inputs()
    profile,remainder=profile_from_evidence(q,frame,actual,official,neighbours)
    profile['source_record_sha256']=frame['source_record_sha256']
    pins={**PINS,**{str(p.relative_to(ROOT)):sha(p)for p in(HERE/'prepare_profile.py',HERE/'source_bounded_profile.py')}}
    package={'schema':'v20-source-bounded-shouan79-production-study/1','buildings':[profile],
        'inputs_sha256':pins,'native_source_sha256':'c2e981596258654e9f15ff9ab60f065d5b068a7f72b4a1cd39cf343203f1f125',
        'scope':'Only source79 main hall conditional source-bounded study; not historical precision or source-hide permission',
        'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False,
        'production_factory_run':False,'native_opened_or_saved':False,'source_actor_visibility_changes':[],
        'reference_floor_expected_in_new_factory_meshes':True,'planned_remainder_is_mesh':False,
        'future_remainder_mesh_and_sourcehide_qualification':'Actual factory full projected triangle union then exact original-source difference must be separately audited; no gray remainder geometry or hide permission from this package'}
    remainder['inputs_sha256']=pins
    colors={'base':([.66,.64,.58,1],0,.82),'column':([.39,.018,.012,1],0,.32),
        'beam':([.025,.13,.11,1],0,.68),'wall':([.36,.028,.018,1],0,.68),
        'frame':([.39,.018,.012,1],0,.32),'infill':([.055,.027,.012,1],0,.71),
        'roof_main':([.60,.285,.025,1],.12,.32),'roof_edge':([.60,.285,.025,1],.12,.32),
        'roof_under':([.085,.10,.11,1],.02,.72)}
    palette={'schema':'v20-source-bounded-shouan79-study-palette/1','materials':{k:{'rgba':rgba,'metallic':metal,'roughness':rough}for k,(rgba,metal,rough)in colors.items()},
        'category_scope':'Only yellow-glazed-tile roof category is official fact. All RGB/finishes and nonroof material colors are visual study controls, not measured current materials.',
        'numeric_status':'unmeasured_study','third_party_cost':0,'paid_service_calls':0,'human_approval':'pending',
        'inputs_sha256':pins}
    return package,palette,remainder


def validate_package(package,palette,remainder):
    expected=make_package()
    for actual,want,label in zip((package,palette,remainder),expected,('profile','palette','remainder')):
        require(type(actual)is dict and json.dumps(actual,ensure_ascii=False,sort_keys=True,allow_nan=False)==json.dumps(want,ensure_ascii=False,sort_keys=True,allow_nan=False),label+' differs from deterministic pinned source-bounded package')
    # Python bool compares equal to 0/1; enforce types independently of equality.
    for doc in(package,palette,package['buildings'][0]):
        for k in('third_party_cost','paid_service_calls'):require(type(doc[k])is int and doc[k]==0,k+' must be integer zero')
    for k in('bays_x','bays_y','study_eaves_tiers','reference_floor_count'):
        require(type(package['buildings'][0][k])is int,k+' must be integer')
    require(package['buildings'][0]['facing']is None and package['buildings'][0]['eaves_tiers']is None,'factual unknown promoted')
    return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
    docs=make_package();validate_package(*docs)
    if args.write:
        for name,doc in zip(('production-profiles.json','production-palette.json','retained-source-remainder-plan.json'),docs):
            path=HERE/name;require(not path.exists(),'refusing to overwrite prepared evidence: '+name)
            path.write_text(json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    p=docs[0]['buildings'][0]
    print(json.dumps({'passed':True,'body_width_m':p['dimensions']['body_width_m'],'body_depth_m':p['dimensions']['body_depth_m'],
        'factual_height_m':None,'source_hide_allowed':[],'factory_run':False},ensure_ascii=False))


if __name__=='__main__':main()
