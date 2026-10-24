"""Synthetic aggregation-entry tests only, not an actual factory acceptance."""
import argparse
import copy
import json
from pathlib import Path

import formal_contract as K
from make_factory_acceptance import aggregate


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);a=parser.parse_args()
    assert not a.report.exists()
    scope={'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False}
    f={**scope,'mesh_names':['synthetic-entry-only']}
    t={**scope,'summary':{'passed':1,'failed':0},'checks':[{'passed':True,'factory_state_sha256':'syntheticSHA'}],
        'actual_factory_build_completed':True,'full_raw_evaluated_material_profile_capture':True,'native_opened':False,'native_saved':False,'factory_sha256':'runnerSHA','binding_sha256':'bindingSHA'}
    c={**scope,'summary':{'passed':13,'failed':0},'checks':[{'passed':True}for _ in range(13)],'factory_state_sha256':'syntheticSHA','binding_sha256':'bindingSHA','actual_coverage_names':['synthetic-entry-only'],'inputs_sha256':{'test':'synthetic'}}
    b={'inputs_sha256':{'test':'synthetic'}};rows=[]
    def run(id,fn,rejected):
        try:fn();ok=not rejected;actual='允许聚合'if ok else'错误接受'
        except AssertionError as e:ok=rejected;actual='拒绝: '+str(e)
        rows.append({'id':id,'input':'synthetic-only fixture; no actual Blender evidence','operation':'aggregate() header/count/coverage strict entry test','expected':'拒绝'if rejected else'允许纯聚合','passed':ok,'actual':actual})
    run('ACCEPT-ENTRY-01',lambda:aggregate(f,t,c,b,'syntheticSHA','runnerSHA'),False)
    for id,path,value in[
        ('EXTRA-A01',(1,'summary','passed'),True),('EXTRA-A02',(2,'summary','failed'),False),
        ('EXTRA-A03',(2,'summary','passed'),12),('EXTRA-A04',(1,'checks',0,'passed'),False),
        ('EXTRA-A05',(2,'actual_coverage_names'),[]),('EXTRA-A06',(2,'factory_state_sha256'),'wrong'),
        ('EXTRA-A07',(1,'native_opened'),True),('EXTRA-A08',(2,'third_party_cost'),-1),('EXTRA-A09',(0,'human_approval'),'approved')]:
        docs=copy.deepcopy([f,t,c,b]);target=docs
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
        run(id,lambda docs=docs:aggregate(*docs,'syntheticSHA','runnerSHA'),True)
    report={'schema':'v20-acceptance-aggregation-entry-only-CPU/1','checks':rows,'summary':{'passed':sum(x['passed']for x in rows),'failed':sum(not x['passed']for x in rows)},'inputs_sha256':{str(p.relative_to(K.ROOT)):K.sha(p)for p in(K.HERE/'make_factory_acceptance.py',Path(__file__).resolve())},'synthetic_entry_only':True,'actual_factory_or_native_accepted':False,'Blender_started':False,**scope}
    with a.report.open('x')as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps(report['summary']));assert report['summary']['failed']==0


if __name__=='__main__':main()
