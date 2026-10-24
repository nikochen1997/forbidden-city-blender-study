"""Entry-only guard tests. Does not verify actual factory geometry."""
import argparse
import copy
import json
from pathlib import Path

import formal_contract as K


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);a=parser.parse_args();assert not a.report.exists()
    p,*_=K.load_evidence();old={n:{'object':{'visibility':{'hide_render':False,'global_hide_viewport':False,'hide_get':False}}}for n in('Cube','Camera','Light')}
    b={'inputs_sha256':{'entry_only':'synthetic'}}
    d={'schema':'v20-source-bounded-shouan-recess-actual-world/1','coordinate_space':'WORLD','profile':p,'native_opened':False,'native_saved':False,'rendered':False,'production_build':True,
        'occupied_storeys':None,'source_visibility_changes':[],'inputs_sha256':b['inputs_sha256'],
        'construction_frame_transform':{'method':'G14 near-origin full-source working copy, restore original p and unique newroot WORLD before observer/adapter','original_anchor':p['anchor'],'original_rotation_z_rad':p['rotation_z_rad'],'working_anchor':[0.,0.,0.],'working_rotation_z_rad':0.,'full_source_rings_retained':True,'original_profile_unchanged':True},
        'protected_global_before':copy.deepcopy(old),'protected_global_after':copy.deepcopy(old),'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False}
    rows=[]
    assert K.validate_world_header(d,b,p)
    rows.append({'id':'VIS-ENTRY-01','input':'synthetic default3 header with real pinned production profile','operation':'validate_world_header','expected':'accept header only','passed':True,'actual':'accepted; no actual geometry assertion'})
    for name,key in(('Cube','global_hide_viewport'),('Camera','hide_render'),('Light','hide_get')):
        bad=copy.deepcopy(d);bad['protected_global_after'][name]['object']['visibility'][key]=True;caught=False
        try:K.validate_world_header(bad,b,p)
        except AssertionError as e:caught='default3 global objects'in str(e)
        rows.append({'id':'EXTRA-VIS-'+key,'input':name+'.visibility.'+key+'=True in private CPU copy','operation':'validate_world_header','expected':'reject actual captured flag change','passed':caught,'actual':'rejected'if caught else'wrongly accepted'})
    s=(K.HERE/'check_actual_production_v2.py').read_text();expected="globalhide['protected_global_after']['Cube']['object']['visibility']['global_hide_viewport']=True"
    ok=expected in s and "first['unexpected_global_hide']"not in s
    rows.append({'id':'VIS-ENTRY-02','input':'v2 actual-derived control source','operation':'exact mutation field read','expected':'flip actual global viewport flag, not invented metadata','passed':ok,'actual':'actual flag mutation confirmed'if ok else'wrong source'})
    report={'schema':'v20-formal-global-visibility-entry-CPU/1','checks':rows,'summary':{'passed':sum(r['passed']for r in rows),'failed':sum(not r['passed']for r in rows)},'inputs_sha256':{str(f.relative_to(K.ROOT)):K.sha(f)for f in(K.HERE/'formal_contract.py',K.HERE/'check_actual_production.py',K.HERE/'check_actual_production_v2.py',Path(__file__).resolve())},'entry_only':True,'actual_factory_or_native_verified':False,'Blender_started':False,'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False}
    with a.report.open('x')as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(report['summary']));assert report['summary']['failed']==0


if __name__=='__main__':main()
