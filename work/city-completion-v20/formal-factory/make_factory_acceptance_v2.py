"""Pure report aggregation after real factory plus all13 actual CPU checks.

Does not execute Blender or invent a terminal receipt. Readiness must separately
bind the root-observed actual factory terminal receipt, not this aggregation.
"""
import argparse
import importlib.util
import json
from pathlib import Path

import formal_contract_v2 as K


def aggregate(factory,tests,cpu,binding,factory_sha,runner_sha):
    for doc,n in((tests,1),(cpu,13)):
        K.require(type(doc['summary']['passed'])is int and doc['summary']['passed']==n and type(doc['summary']['failed'])is int and doc['summary']['failed']==0,'actual pass/fail counts require strict integers')
    K.require(tests['summary']=={'passed':1,'failed':0}and len(tests['checks'])==1 and tests['checks'][0]['passed']is True,'actual factory execution report must pass1/0')
    K.require(tests['actual_factory_build_completed']is True and tests['full_raw_evaluated_material_profile_capture']is True and tests['native_opened']is False and tests['native_saved']is False,'actual isolated factory proof missing')
    K.require(tests['factory_sha256']==runner_sha and tests['checks'][0]['factory_state_sha256']==factory_sha,'actual runner/canonical SHA differs')
    K.require(cpu['summary']=={'passed':13,'failed':0}and len(cpu['checks'])==13 and all(x['passed']is True for x in cpu['checks']),'full actual CPU13/0 required')
    K.require(cpu['factory_state_sha256']==factory_sha and cpu['binding_sha256']==tests['binding_sha256'],'CPU/factory binding SHA differs')
    K.require(cpu['actual_coverage_names']==sorted(factory['mesh_names'])and cpu['inputs_sha256']==binding['inputs_sha256'],'full current canonical coverage/input map differs')
    for doc in(factory,tests,cpu):K.zero_scope(doc)
    return {'schema':'v20-actual-factory-canonical-acceptance/1','summary':{'passed':1,'failed':0},
        'factory_state_sha256':factory_sha,'actual_coverage_names':sorted(factory['mesh_names']),
        'actual_factory_build_completed':True,'full_raw_evaluated_material_profile_capture':True,
        'native_opened':False,'native_saved':False,'third_party_cost':0,'paid_service_calls':0,
        'human_approval':'pending','whole_city_complete':False,
        'scope':'Pure aggregation of passed real factory report, full canonical actual capture and full13/0 CPU; not a new Blender execution and not a terminal receipt',
        'root_observed_actual_factory_terminal_receipt_still_required':True}


def main():
    parser=argparse.ArgumentParser()
    for n in('factory-state','factory-tests','cpu-report','binding','report'):parser.add_argument('--'+n,type=Path,required=True)
    a=parser.parse_args();K.require(not a.report.exists()and a.report.resolve().is_relative_to(K.HERE),'new acceptance report required')
    paths=[a.factory_state,a.factory_tests,a.cpu_report,a.binding];before={str(p.resolve()):K.sha(p)for p in paths}
    factory,tests,cpu,binding=[K.read(p)for p in paths];K.check_bound_files(binding)
    spec=importlib.util.spec_from_file_location('v20_factory_pure_contract_acceptance',K.path(binding['native_contract']));contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract);contract.validate_factory(factory)
    result=aggregate(factory,tests,cpu,binding,K.sha(a.factory_state),K.sha(K.path(binding['factory_runner'])))
    result['evidence_inputs_sha256']={**before,str(Path(__file__).resolve()):K.sha(__file__)}
    K.require(all(K.sha(p)==h for p,h in before.items()),'actual evidence bytes changed')
    with a.report.open('x')as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(result['summary']))


if __name__=='__main__':main()
