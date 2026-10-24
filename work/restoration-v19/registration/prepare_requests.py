"""Prepare one V19 current-V18 probe; never execute Blender or modify old files."""
import hashlib
import json
from pathlib import Path

from probe_contract import record_sha,validate_request

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FACTS='work/restoration-v19-preparation/facts-and-candidates.json'
PREP='work/restoration-v19-preparation/source-candidate-registration-preparation.json'
MODEL='work/forbidden-city-research/geospatial/model-data.json'
NATIVE='outputs/紫禁城现存格局-南三所第十八阶段/紫禁城现存格局-南三所第十八阶段.blend'
MANIFEST='outputs/紫禁城现存格局-南三所第十八阶段/restoration-manifest.json'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4194304),b''):h.update(block)
    return h.hexdigest()


def main():
    out=HERE/'source-probe-requests.json'
    assert not out.exists(),'fresh immutable probe request required'
    expected={FACTS:'1cd2f810ab3f910fa282abd46702eafc10e8c4d052311c89155f4e3954812f58',
              PREP:'41a74b1cec77916ff7cf4b8bc3870a7d94a53eb55ade2aa90e27c062026414d3',
              MODEL:'06dfa30cbd6401d2b555b842c03dd47fa055a4de6024b4904b39cc2652a2248e',
              MANIFEST:'0ec36629f96f40bedc87d0c24ed2360550f5e08ef28ea35d83c32c5fce729b23'}
    assert all(sha(ROOT/p)==v for p,v in expected.items())
    facts,prep,model,manifest=[json.loads((ROOT/p).read_text()) for p in (FACTS,PREP,MODEL,MANIFEST)]
    policy=json.loads((ROOT/'work/render-delivery-policy.json').read_text())
    assert policy['current_native']==NATIVE and policy['current_native_sha256']=='1b3d14372e4756432c1f6513e59217a0410afe85b53ca69849cec338be502122'
    assert manifest['model_sha256']==policy['current_native_sha256']
    targets=[r['source_part_id'] for r in prep['targets']]
    neighbours=[r['source_record']['id'] for r in prep['external_source_context']['parts']]
    parts={r['id']:r for r in model['parts']}
    for row in prep['targets']:
        source=parts[row['source_part_id']]
        assert source==row['source_record'] and source['polygon']==row['source_polygon_world']
        assert source.get('holes',[])==row['source_holes_world']
        fact=next(r for r in facts['source_candidates'] if r['source_part_id']==source['id'])
        assert fact['source_record_sha256']==row['source_record_sha256']==record_sha(source)
    for layer in ('parts','inner_walls','paths','landcover_polygons'):
        table={r['id']:r for r in model[layer]}
        assert all(table[r['source_record']['id']]==r['source_record']
                   and record_sha(r['source_record'])==r['source_record_sha256']
                   for r in prep['external_source_context'][layer])
    surfaces=[]
    for layer,prefix,lines in (('paths','路_',[140,144]),('landcover_polygons','绿地_',[136,137])):
        for row in prep['external_source_context'][layer]:
            sid=row['source_record']['id']
            surfaces.append({'layer':layer,'source_id':sid,'source_record_sha256':row['source_record_sha256'],
                'recipe_actor_name':prefix+sid,'actor_name_is_recipe_expectation':True,
                'recipe_evidence':{'file':'work/assemble_forbidden_city.py','lines':lines,
                                   'identity_fields':['object.name','source_refs','object.type==MESH','no source_building_id']},
                'actual_actor_identity':'pending actual read-only probe','architectural_route_or_measured_garden_boundary_claim':False})
    inputs=dict(expected)
    for mapping in (prep['inputs_sha256'],facts['inputs_sha256']):
        for p,digest in mapping.items():
            assert sha(ROOT/p)==digest
            assert p not in inputs or inputs[p]==digest
            inputs[p]=digest
    inputs[NATIVE]=policy['current_native_sha256']
    for p in ('work/restoration-v19/registration/probe_contract.py','work/restoration-v19/registration/prepare_requests.py'):
        inputs[p]=sha(ROOT/p)
    request={'schema':'v19-readonly-current-V18-source-probe-request/1','native_file':str(ROOT/NATIVE),
        'native_sha256':policy['current_native_sha256'],'accepted_manifest_file':MANIFEST,
        'accepted_manifest_sha256':expected[MANIFEST],
        'expected_mesh_count':14502,'expected_source_mesh_count':2845,'expected_camera_count':136,
        'selected_part_ids':targets,'nearby_source_part_ids':neighbours,'anchor_part_ids':[],
        'source_record_sha256':{sid:record_sha(parts[sid]) for sid in targets+neighbours},
        'source_wall_line_ids':[r['source_record']['id'] for r in prep['external_source_context']['inner_walls']],
        'source_wall_record_sha256':{r['source_record']['id']:r['source_record_sha256'] for r in prep['external_source_context']['inner_walls']},
        'context_surface_requests':surfaces,'inputs_sha256':inputs,'allowed_hidden_source_actor_names':[],
        'context_source_actor_rule':'Exact construction recipe name + type MESH + source_refs identity; not documentary bridge/mountain/gate registration',
        'full_source_records_and_all_rings_must_be_retained':True,
        'native_save_allowed':False,'render_allowed':False,'producer_import_allowed':False,
        'native_readonly_status':'pending root unique serial Blender execution',
        'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False}
    print(json.dumps(validate_request(request,model,manifest),ensure_ascii=False))
    with out.open('x') as stream:json.dump(request,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('REQUEST_SHA256',sha(out))


if __name__=='__main__':main()
