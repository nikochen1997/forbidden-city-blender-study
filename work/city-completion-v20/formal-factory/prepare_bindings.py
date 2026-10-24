"""Freeze fresh actual-factory inputs only after explicit adapter_v2 SHA review."""
import argparse
import json
from pathlib import Path

import formal_contract as K

ADAPTER='work/city-completion-v20/shouan-recess-adapter/shouan_recess_adapter_v2.py'
ADAPTER_SHA='029f7c93f7f62d51cbd2dde859e0a3496fe64c9b0ee94422f3dd9bfc526a437a'


def make_binding():
    profile,palette,*_=K.load_evidence()
    K.require(K.sha(K.path(ADAPTER))==ADAPTER_SHA,'reviewed adapter_v2 source changed')
    package=K.read(K.path(K.PROFILE_PACKAGE));pins=dict(package['inputs_sha256'])
    direct=[K.PROFILE_PACKAGE,K.PALETTE,K.QUALIFICATION,K.PROBE,K.SOURCE_CPU,
        'work/city-completion-v20/native-prep/stage20_contract.py',
        'work/city-completion-v20/native-prep/produce_city_progress_v20.py',
        'work/city-completion-v20/native-prep/read_saved_city_v20.py',
        'work/city-completion-v20/shouan-recess-adapter/recess_contract.py',
        'work/city-completion-v20/shouan-recess-adapter/check_actual_fixture.py',ADAPTER,
        'work/restoration-v16/saved-audit/saved_audit_core.py',
        'work/restoration-v19/saved-audit/evaluated_geometry_fingerprint.py',
        'work/restoration-v19/northern_court_towers.py','work/square_garden_pavilions.py',
        'work/build_forbidden_city_restoration_v11.py','work/build_forbidden_city_restoration_v15.py',
        'work/restoration-v18/module-qa/check_actual_exterior_supports.py',
        'work/restoration-v18/module-qa/fixture_profile_contract_v2.py',
        'work/restoration-v17/hall-qa/check_actual_supports_v3.py',
        'work/restoration-v14/saved-audit/saved-projection/check_saved_projection.py',
        'work/restoration-v19/tower-qa/check_actual_contact_domains.py',
        'work/restoration-v19/formal-support-review/review_formal_supports.py']
    direct+=[str(p.relative_to(K.ROOT))for p in sorted(K.HERE.glob('*.py'))]
    single=K.HERE/'single-profile.json';K.require(single.exists()and K.equal(K.read(single),profile),'single profile extraction absent or altered')
    direct.append(str(single.relative_to(K.ROOT)))
    for rel in direct:
        actual=K.sha(K.path(rel))
        if rel in pins:K.require(pins[rel]==actual,'upstream pinned input drift: '+rel)
        pins[rel]=actual
    binding={'schema':'v20-shouan79-formal-factory-binding/1',
        'profile_package':K.PROFILE_PACKAGE,'single_profile':str(single.relative_to(K.ROOT)),'palette':K.PALETTE,
        'adapter_module':ADAPTER,'scene_builder':str((K.HERE/'stage20_scene.py').relative_to(K.ROOT)),
        'native_contract':'work/city-completion-v20/native-prep/stage20_contract.py',
        'geometry_module':'work/forbidden_city_geometry.py','readonly_core':'work/restoration-v16/saved-audit/saved_audit_core.py',
        'collection_name':'restoration_v20_shouan79','inputs_sha256':pins,
        'actual_run_pending':True,'actual_Boolean_support_roof_CPU_pending':True,
        'production_build_allowed':True,'native_open_allowed':False,'source_hide_allowed':[],
        'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False}
    K.check_bound_files(binding);return binding


def main():
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');a=p.parse_args()
    profile,*_=K.load_evidence();single=K.HERE/'single-profile.json'
    if not single.exists():
        K.require(a.write,'single-profile missing; use explicit --write once')
        with single.open('x')as f:f.write(K.canonical(profile)+'\n')
    b=make_binding()
    if a.write:
        dest=K.HERE/'factory-bindings-01.json'
        with dest.open('x')as f:json.dump(b,f,ensure_ascii=False,indent=2);f.write('\n')
        print('binding_sha256',K.sha(dest))
    else:print(json.dumps({'inputs':len(b['inputs_sha256']),'actual_run_pending':True,'adapter_v2_sha256':ADAPTER_SHA}))


if __name__=='__main__':main()
