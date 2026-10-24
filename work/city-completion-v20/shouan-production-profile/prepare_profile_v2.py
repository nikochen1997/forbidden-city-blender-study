"""Only the source79 unmeasured beam width changes after real12/1 evidence."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OLD_PACKAGE='work/city-completion-v20/shouan-production-profile/production-profiles.json'
OLD_SHA='44fd1d4f5b0383494c44db3b8883b560e0230565635fbefe891ea9c20a0d4504'
OLD_REMAINDER='work/city-completion-v20/shouan-production-profile/retained-source-remainder-plan.json'
OLD_REMAINDER_SHA='cd4bed6c0b72342005cc2908f63621df17eab5ac9fe5e986131c0e28e7961008'
RED='work/city-completion-v20/formal-factory/actual-run-01/actual-complete-CPU-02.json'
RED_SHA='ceb125cce669752f523b021c66b66944616bd7ba52f9122f537244762a33983e'
OLD_FACTORY='work/city-completion-v20/formal-factory/actual-run-01/factory-state.json'
OLD_FACTORY_SHA='133bf79f76accb13b09017fc65248eb9bd4e9b9811958b0c8132cc0edc013189'


def require(ok,message):
    if not ok:raise AssertionError(message)


def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())


def corrected_width(old_width,radius,clearance):
    for key,v in(('old beam width',old_width),('column radius',radius),('numerical clearance',clearance)):
        require(type(v)in(int,float)and math.isfinite(v)and v>0,key+' must be finite positive')
    return max(old_width,2*radius+2*clearance)


def complete_column_squares_in_beams(profile):
    """Exact stronger-than-circle test: full circumscribing square per column.

    Frozen G14 beam XY dimensions are W+bw by bw and bw by D+bw.
    A complete circle of radius r is within its complete axis-aligned square.
    Four linear rectangle inequalities prove the WHOLE square is contained in
    at least one supporting beam, including every corner; no sampled rim test.
    """
    d=profile['dimensions'];w,depth,bw,r=[d[k]for k in('body_width_m','body_depth_m','beam_width_m','column_radius_m')]
    for v in(w,depth,bw,r):require(type(v)in(int,float)and math.isfinite(v)and v>0,'invalid positive beam/column dimensions')
    xs=[-w/2];ys=[-depth/2]
    for a in profile['column_bay_widths_x_m']:xs.append(xs[-1]+a)
    for a in profile['column_bay_widths_y_m']:ys.append(ys[-1]+a)
    # The positive end reference is the declared extent. Frozen _axis_grid's
    # cumulative last coordinate can differ only at binary rounding scale.
    require(abs(xs[-1]-w/2)<1e-12 and abs(ys[-1]-depth/2)<1e-12,'axis extent differs')
    xs[-1]=w/2;ys[-1]=depth/2
    grid=sorted({(x,y)for x in xs for y in(ys[0],ys[-1])}|{(x,y)for x in(xs[0],xs[-1])for y in ys[1:-1]})
    beams={'south':(-w/2-bw/2,-depth/2-bw/2,w/2+bw/2,-depth/2+bw/2),
        'north':(-w/2-bw/2,depth/2-bw/2,w/2+bw/2,depth/2+bw/2),
        'west':(-w/2-bw/2,-depth/2-bw/2,-w/2+bw/2,depth/2+bw/2),
        'east':(w/2-bw/2,-depth/2-bw/2,w/2+bw/2,depth/2+bw/2)}
    rows=[]
    for x,y in grid:
        full=(x-r,y-r,x+r,y+r);support=[]
        for name,b in beams.items():
            if b[0]<=full[0]and b[1]<=full[1]and full[2]<=b[2]and full[3]<=b[3]:support.append(name)
        require(support,'complete column-top circumscribing square leaves all beam domains')
        rows.append({'axis':[x,y],'entire_circle_circumscribing_square':full,'whole_square_covering_beams':support})
    return {'all16_perimeter_column_tops':rows,'beam_domains_local':beams,'analytic_circle_normal_clearance_m':bw/2-r,'sampled_points_used':False}


def make_package():
    for rel,h in{OLD_PACKAGE:OLD_SHA,OLD_REMAINDER:OLD_REMAINDER_SHA,RED:RED_SHA,OLD_FACTORY:OLD_FACTORY_SHA}.items():require(sha(ROOT/rel)==h,'old evidence changed: '+rel)
    old=read(ROOT/OLD_PACKAGE);red=read(ROOT/RED)
    require(red['summary']=={'passed':12,'failed':1}and red['factory_state_sha256']==OLD_FACTORY_SHA,'real first formal12/1 evidence required')
    bad=[r for r in red['checks']if r['passed']is False]
    require(len(bad)==1 and bad[0]['id']=='CPU-04-FULL-SUPPORT-AND-SOURCE'and 'column top'in bad[0]['error'],'beam revision must address observed complete column-top support failure only')
    package=copy.deepcopy(old);p=package['buildings'][0];d=p['dimensions'];old_bw=d['beam_width_m']
    clearance=p['source_envelope_derivation']['numerical_clearance_m'];r=d['column_radius_m']
    new_bw=corrected_width(old_bw,r,clearance);d['beam_width_m']=new_bw
    p['source_envelope_derivation']['body_margin_budget_m']['beam']=new_bw/2
    base_margin=d['column_base_radius_m']
    require(new_bw/2<base_margin,'new complete beam projection exceeds unchanged old base-envelope margin')
    revision={'revision':2,'scope':'one unmeasured beam-width correction after real first-formal12/1; no historical metric claim',
        'old_profile_package_sha256':OLD_SHA,'old_factory_state_sha256':OLD_FACTORY_SHA,'old_actual_CPU_red_sha256':RED_SHA,
        'old_beam_width_m':old_bw,'new_beam_width_m':new_bw,'rule':'max(old_width,2*original_column_radius+2*original16ULP_numerical_clearance)',
        'unchanged_original_clearance_m':clearance,'unchanged_source_body_roof_height_column_openings_facts_spans':True,
        'old_max_base_margin_m':base_margin,'new_beam_halfwidth_inside_old_base_margin':True,
        'frozen_G14_derived_bearing_radius':{'rule':'min(unchanged column_radius,.45*beam_width)',
            'old_m':min(r,.45*old_bw),'new_m':min(r,.45*new_bw),'status':'necessary frozen-helper coupling of this one parameter; not a changed column or roof input'},
        'actual_new_geometry_and13_checks':'pending'}
    p['beam_width_revision']=revision
    package['schema']='v20-source-bounded-shouan79-production-study/2';package['profile_revision']=revision
    inputs={**old['inputs_sha256'],OLD_PACKAGE:OLD_SHA,OLD_REMAINDER:OLD_REMAINDER_SHA,RED:RED_SHA,OLD_FACTORY:OLD_FACTORY_SHA,
        str(Path(__file__).resolve().relative_to(ROOT)):sha(__file__)}
    package['inputs_sha256']=inputs
    remainder=read(ROOT/OLD_REMAINDER);remainder['inputs_sha256']=inputs;remainder['profile_revision']=revision
    validate_profile(p,old['buildings'][0]);complete_column_squares_in_beams(p)
    return package,remainder


def validate_profile(profile,old):
    old=copy.deepcopy(old);require('beam_width_revision'in profile,'explicit revised profile required')
    candidate=copy.deepcopy(profile);revision=candidate.pop('beam_width_revision')
    new=corrected_width(old['dimensions']['beam_width_m'],old['dimensions']['column_radius_m'],old['source_envelope_derivation']['numerical_clearance_m'])
    require(type(candidate['dimensions']['beam_width_m'])is float and candidate['dimensions']['beam_width_m']==new,'minimal corrected width rule differs')
    candidate['dimensions']['beam_width_m']=old['dimensions']['beam_width_m']
    require(profile['source_envelope_derivation']['body_margin_budget_m']['beam']==new/2,'beam envelope declaration not updated')
    candidate['source_envelope_derivation']['body_margin_budget_m']['beam']=old['source_envelope_derivation']['body_margin_budget_m']['beam']
    require(canonical(candidate)==canonical(old),'non-beam production profile parameter changed')
    require(revision['new_beam_width_m']==new and revision['old_profile_package_sha256']==OLD_SHA and revision['actual_new_geometry_and13_checks']=='pending','revision scope drift')
    for k in('third_party_cost','paid_service_calls'):require(type(profile[k])is int and profile[k]==0,'cost/calls must remain integer0')
    return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');a=parser.parse_args();docs=make_package()
    if a.write:
        for name,d in zip(('production-profiles-v2.json','retained-source-remainder-plan-v2.json'),docs):
            with(HERE/name).open('x')as f:json.dump(d,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'beam_width_m':docs[0]['buildings'][0]['dimensions']['beam_width_m'],'only_one_dimension_changed':True,'actual_new_geometry_pending':True}))


if __name__=='__main__':main()
