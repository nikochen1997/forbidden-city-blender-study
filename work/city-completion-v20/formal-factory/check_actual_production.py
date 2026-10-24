"""Independent source-bound entry; frozen aperture/support/contact math reused.

No private-profile coercion, generator import, Blender, native opening or repair.
"""
import argparse
import copy
import importlib.util
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(ROOT/'work/city-completion-v20/shouan-recess-adapter')]
import formal_contract as K

FROZEN_CHECKER='work/city-completion-v20/shouan-recess-adapter/check_actual_fixture.py'
FROZEN_CHECKER_SHA='8c0be7c4e0ac0850fa23d0ffb3466aa4bdeebb41c69f302f21cc10e5d0f2c4cd'
K.require(K.sha(K.path(FROZEN_CHECKER))==FROZEN_CHECKER_SHA,'frozen full geometry checker changed')
spec=importlib.util.spec_from_file_location('frozen_shouan_geometry_checks',K.path(FROZEN_CHECKER))
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
K.require(M.EPS==1e-4 and M.CONTACT.Z_TOL==2e-4,'frozen complete-domain tolerances changed')


def preserve(doc,binding,profile):
    K.validate_world_header(doc,binding,profile)
    K.require(K.equal(doc['protected_old_materials_before'],doc['protected_old_materials_after']),'pre-existing full material changed')
    actual=M.rows(doc);base={r['name']:r for r in doc['generated_before_adapter']['objects']};a=doc['adapter']
    deleted=a['removed_new_south_wall'];moved=set(a['moved_central_frame_leaf_names'])
    added=set(a['new_wall_names'].values())|set(a['new_roof_closure_names'])
    K.require(set(actual)==set(base)-{deleted}|added and len(actual)==len(base)+7,'only new G14 south wall replacement plus7 allowed')
    K.require(a['retained_objects_before_sha256']==a['retained_objects_after_sha256'],'retained actual signature mismatch')
    K.require(a['old_source_operations']==[]and a['only_original_new_south_wall_deleted']is True,'adapter source/new ownership scope drift')
    for name in set(base)-{deleted}-moved:K.require(K.equal(actual[name],base[name]),'retained actual new geometry/state changed: '+name)
    offset=a['plan']['setback_m_private_study']
    for name in moved:
        v0,v1=base[name]['vertices_local'],actual[name]['vertices_local']
        K.require(base[name]['triangles']==actual[name]['triangles']and base[name]['raw_vertices']==actual[name]['raw_vertices']and base[name]['raw_faces']==actual[name]['raw_faces']and len(v0)==len(v1),'moved central original mesh shape changed')
        K.require(all(abs(b[0]-x[0])<=M.EPS and abs(b[1]-x[1]-offset)<=M.EPS and abs(b[2]-x[2])<=M.EPS for x,b in zip(v0,v1)),'actual central frame/leaf translation differs')
    K.require([r for r in doc['generated_before_adapter']['openings']if r['wall_side']=='north']==[r for r in doc['openings']if r['wall_side']=='north'],'original north openings changed')
    return {'retained_meshes_exactly_unchanged':len(base)-1-len(moved),'central_frames_leaves_translated':len(moved),'new_mesh_delta':7,'all_default_objects_unchanged':3,'source_hide_authorized':False}


def canonical_agreement(doc,factory,contract):
    contract.validate_factory(factory);K.require(K.equal(factory['profile'],doc['profile']),'canonical profile differs')
    by=M.rows(doc);K.require(set(by)==set(factory['mesh_names']),'all actual canonical mesh names required')
    for name,row in by.items():
        actual={key:row[key]for key in contract.MESH_KEYS}
        K.require(K.equal(actual,factory['meshes'][name]),'full raw/evaluated/material/relations canonical mismatch: '+name)
        K.require(row['hidden']is False and row['visibility']=={'hide_render':False,'global_hide_viewport':False,'hide_get':False},'actual new geometry hidden')
    p=doc['profile'];matrix=doc['root_matrix_world'];c,s=math.cos(p['rotation_z_rad']),math.sin(p['rotation_z_rad'])
    expected=[[c,-s,0,p['anchor'][0]],[s,c,0,p['anchor'][1]],[0,0,1,p['anchor'][2]],[0,0,0,1]]
    K.require(all(abs(matrix[i][j]-expected[i][j])<=M.EPS for i in range(4)for j in range(4)),'source WORLD root transform not restored')
    return {'actual_full_meshes':len(by),'full_raw_evaluated_material_profile_capture':True,'exact_factory_coverage_names':sorted(by),'near_origin_work_copy_not_registration_replacement':True}


def all_opening_prisms(doc):
    by=M.rows(doc);evidence=[]
    records=doc['openings'];K.require(len(records)==10 and {r['wall_side']for r in records}=={'south','north'},'all5 north and5 south actual openings required')
    for side in('north','south'):K.require(sorted(r['bay_index']for r in records if r['wall_side']==side)==list(range(5)),'complete per-bay inventory required')
    for record in records:
        K.require(len(record['wall_segment_names'])==1,'one actual opening target required')
        mesh=M.geometry(by[record['wall_segment_names'][0]],True);ys=[v[1]for v in mesh['vertices']]
        x,y,z=record['center_local'];w,h=record['clear_width_m'],record['clear_height_m']
        result=M.void_prism([mesh],[x-w/2+M.EPS,min(ys)-M.EPS,z-h/2+M.EPS,x+w/2-M.EPS,max(ys)+M.EPS,z+h/2-M.EPS],record['wall_side']+' bay '+str(record['bay_index']))
        evidence.append({'opening_id':record['id'],'side':record['wall_side'],'bay_index':record['bay_index'],**result})
    return {'all10_real_structural_through_prisms':evidence,'full_actual_opening_geometry_checked':True,'no_tolerance_relaxation':True}


def source_floor(doc):
    from shapely.geometry import Polygon
    by=M.rows(doc);row=by[doc['reference_floor']];geom=M.geometry(row);z=M.G.zrange(geom)[1]
    actual=M.G.horizontal(geom,z,True);source=Polygon(doc['profile']['source_polygon_world'],doc['profile']['source_holes_world'])
    return {'all11_original_points_retained':len(doc['profile']['source_polygon_world'])==11,
        'actual_entire_triangle_floor_top_in_full_source':M.S.contained(actual,source,'complete source floor actual cap'),
        'full_original_source_in_actual_triangle_floor_top':M.S.contained(source,actual,'complete source floor reverse containment'),
        'raw_symmetric_difference_m2':actual.symmetric_difference(source).area,
        'scope':'complete unions and all components/holes; fixed100um original tolerance, not bbox/hull/selected points'}


def boolean_copy_experiment(doc):
    d=doc['boolean_copy_experiment'];K.require(d['shared_mesh_before']is True and d['unique_mesh_after']is True and d['temporary_objects_removed_before_canonical']is True,'actual copied Boolean contract missing')
    K.require(K.equal(d['partner_before'],d['partner_after']),'shared-mesh partner raw/eval/properties/material changed')
    K.require(d['wall_before']['relations']['data_name']==d['partner_before']['relations']['data_name']and d['wall_after']['relations']['data_name']!=d['partner_after']['relations']['data_name'],'actual data alias independence not observed')
    K.require(not K.equal(d['wall_before']['raw_faces'],d['wall_after']['raw_faces']),'cut wall had no actual topology change')
    bounds=[-.6+M.EPS,-.2-M.EPS,.8+M.EPS,.6-M.EPS,.2+M.EPS,2.2-M.EPS]
    caught=False
    try:M.void_prism([M.geometry(d['wall_before'],True)],bounds,'uncut sentinel')
    except AssertionError:caught=True
    K.require(caught,'uncut actual sentinel did not block expected prism')
    empty=M.void_prism([M.geometry(d['wall_after'],True)],bounds,'cut sentinel')
    return {'actual_boolean_copy_contract_checked':True,'original_operands_preserved':True,
        'untouched_shared_partner_complete_raw_and_evaluated_unchanged':True,'actual_through_prism_after_cut':empty,
        'operand_scope':d['original_operands_preserved_scope'],'historical_source79_opened_or_mutated':False}


def run(doc,binding,profile,factory,contract):
    checks=[]
    def case(id,fn):
        try:checks.append({'id':id,'passed':True,'evidence':fn()})
        except Exception as exc:checks.append({'id':id,'passed':False,'error':type(exc).__name__+': '+str(exc)})
    for ident,fn in[
        ('CPU-01-SOURCE-BOUND-PRESERVATION',lambda:preserve(doc,binding,profile)),
        ('CPU-02-FIVE-WALL-LAYOUT',lambda:M.wall_layout(doc)),
        ('CPU-03-FIVE-FRONT-PRISMS-FOUR-LEAVES',lambda:M.aperture_voids(doc)),
        ('CPU-04-FULL-SUPPORT-AND-SOURCE',lambda:M.supports_and_domain(doc)),
        ('CPU-05-ALL-STRUCTURAL-ROOF-CONTACTS',lambda:M.roof_contacts(doc)),
        ('CPU-06-FULL-CANONICAL-CAPTURE',lambda:canonical_agreement(doc,factory,contract)),
        ('CPU-07-NORTH-AND-SOUTH-ALL10-PRISMS',lambda:all_opening_prisms(doc)),
        ('CPU-08-COMPLETE-11POINT-SOURCE-FLOOR',lambda:source_floor(doc)),
        ('CPU-09-ACTUAL-FROZEN-BOOLEAN-COPY-TEST',lambda:boolean_copy_experiment(doc))]:case(ident,fn)
    controls=[]
    plug=M.added_block(doc);controls.append(('EXTRA-01-ACTUAL-DERIVED-DOOR-PLUG',lambda:M.aperture_voids(plug),'blocks complete'))
    missing=copy.deepcopy(doc);next(r for r in missing['openings']if r['wall_side']=='south'and r['bay_index']==2)['leaf_reference_names'].pop()
    controls.append(('EXTRA-02-ACTUAL-DERIVED-MISSING-LEAF',lambda:M.aperture_voids(missing),'four actual'))
    lifted=copy.deepcopy(doc);name=lifted['adapter']['new_roof_closure_names'][0]
    for v in M.rows(lifted)[name]['vertices_world']:v[2]+=.01
    controls.append(('EXTRA-03-ACTUAL-DERIVED-LIFTED-CLOSURE',lambda:M.roof_contacts(lifted),'height gap'))
    globalhide=copy.deepcopy(doc);first=next(iter(globalhide['protected_global_after'].values()));first['unexpected_global_hide']=True
    controls.append(('EXTRA-04-ACTUAL-DERIVED-GLOBAL-VISIBILITY',lambda:preserve(globalhide,binding,profile),'default3 global objects'))
    for ident,fn,reason in controls:
        try:fn();checks.append({'id':ident,'passed':False,'error':'negative accepted'})
        except AssertionError as exc:checks.append({'id':ident,'passed':reason in str(exc),'rejected_reason':str(exc),'scope':'in-memory actual-export-derived CPU control, not a new Blender/native execution'})
    return checks


def main():
    parser=argparse.ArgumentParser()
    for name in('readout','factory-state','binding','report'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--binding-sha256',required=True);a=parser.parse_args()
    K.require(not a.report.exists()and a.report.resolve().is_relative_to(HERE),'new formal-factory report required')
    K.require(K.sha(a.binding)==a.binding_sha256,'reviewed binding SHA changed');binding=K.read(a.binding);profile,_=K.check_bound_files(binding)
    pins={str(p.resolve()):K.sha(p)for p in(a.readout,a.factory_state,a.binding)}
    doc=K.read(a.readout);factory=K.read(a.factory_state)
    K.require(doc['factory_state_sha256']==K.sha(a.factory_state)and doc['binding_sha256']==a.binding_sha256,'actual factory/readout/binding SHA chain differs')
    spec=importlib.util.spec_from_file_location('v20_formal_pure_capture_contract',K.path(binding['native_contract']));contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
    checks=run(doc,binding,profile,factory,contract)
    K.require(all(K.sha(p)==h for p,h in pins.items()),'actual input changed during CPU audit');K.check_bound_files(binding)
    names=factory['mesh_names'];roles=factory['roles']
    report={'schema':'v20-source-bound-shouan-actual-complete-CPU/1','checks':checks,
        'summary':{'passed':sum(c['passed']for c in checks),'failed':sum(not c['passed']for c in checks)},
        'actual_readout_sha256':K.sha(a.readout),'factory_state_sha256':K.sha(a.factory_state),'binding_sha256':a.binding_sha256,
        'checker_sha256':K.sha(__file__),'inputs_sha256':binding['inputs_sha256'],'actual_coverage_names':sorted(names),
        'coverage_by_role':{'source_domains':sorted(names),'roof_contacts':sorted(set(roles['roofs'])|set(roles['supports'])),'support':sorted(roles['supports']),'boolean_openings':sorted(roles['openings'])},
        'semantic_proofs':{'source_domains':{'complete_triangle_domains_checked':True,'all_components_and_holes_checked':True,'bbox_or_point_only':False,'all_new_outside_source_rejected':True},
            'roof_contacts':{'complete_bottom_and_roof_surfaces_checked':True,'bbox_or_point_only':False,'gap_and_penetration_limits_explicit':True},
            'support':{'complete_named_support_graph_checked':True,'complete_support_contact_domains_checked':True,'engineering_load_capacity_claimed':False},
            'boolean_openings':{'actual_boolean_copy_contract_checked':True,'full_actual_opening_geometry_checked':True,'original_operands_preserved':True}},
        'semantic_proofs_only_valid_when_all_checks_pass':True,
        'roof_contact_scope':'Only named structural roof skins/contact solids/support graph; decorative ridge/tile ribs covered by full source-domain/canonical check, no engineering attachment claimed',
        'EPS_m':M.EPS,'roof_Z_TOL_m':M.CONTACT.Z_TOL,'roof_AREA_TOL_m2':M.CONTACT.AREA_TOL,
        'native_opened':False,'native_saved':False,'generator_imported':False,'source_hide_authorized':False,
        'occupied_storeys':None,'human_approval':'pending','whole_city_complete':False,'third_party_cost':0,'paid_service_calls':0}
    if report['summary']['failed']:
        # A red report must never advertise semantic green booleans by itself.
        report['semantic_proofs']={}
    with a.report.open('x')as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(report['summary']))
    if report['summary']['failed']:raise SystemExit(1)


if __name__=='__main__':main()
