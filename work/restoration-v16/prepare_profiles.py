"""Explicit unmeasured pavilion and Xianruo caller controls; no Blender."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
def read(p):return json.loads((ROOT/p).read_text())
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def main():
    registered=read('work/restoration-v16/registration/registered-buildings.json')
    rows={p['building_id']:p for p in registered['buildings']}
    cg=read('work/restoration-v16/research/cininggarden/facts.json')['entities']
    hf=read('work/restoration-v16/research/huifeng/facts.json')['entities']
    out=[]
    for ident in ('huifengting','linxiting'):
        p=deepcopy(rows[ident]);s=p['study_body_width_m'];huifeng=ident=='huifengting'
        p.update({'builder':'pavilion','bays_x':3,'bays_y':3,'occupied_storeys':None,'reference_floor_count':1,
            'known_facts':deepcopy((hf if huifeng else cg)[ident]['fields']),
            'material_scheme':{'roof_main':'purple_glazed' if huifeng else 'yellow','roof_edge':'peacock_blue' if huifeng else 'green'},
            'unbuilt_features':['Current metric survey/world control','Exact lattice, paintwork, roof tiles and dougong',
                                'Full interior and hidden roof structure','Complete official floor-use evidence'],
            'parameter_evidence':{'all_dimensions':'Unmeasured caller study, including heights, platforms, supports and openings; sourceflat6m not a measured building height.'},
            'paid_service_calls':0})
        if huifeng:
            p['unbuilt_features']+=['Complete rear/side enclosure schedule unknown; open structural reference is not four-face certification',
                'Exact Sumeru profile/cloud carving/finial material','Exact upper roof support arrangement']
            p['dimensions']={'body_side_m':s,'slab_bottom_z_m':0,'floor_z_m':.9,'column_top_z_m':4.15,
                'column_radius_m':.15,'column_base_radius_m':.25,'column_base_height_m':.15,'beam_height_m':.25,'beam_width_m':.30,
                'upper_band':{'side_m':s*.58,'bottom_z_m':6.68,'wall_thickness_m':.12,'occupied_floor':False}}
            p['roof_tiers']=[{'tier_index':0,'outer_side_m':s+2.15,'inner_side_m':s*.58,'eave_z_m':4.6,'top_z_m':6.8,
                'skin_thickness_m':.14,'corner_lift_m':.12,'curve_power':1.65},
                {'tier_index':1,'outer_side_m':s*.58+1.4,'inner_side_m':0,'eave_z_m':7.35,'top_z_m':9.8,
                'skin_thickness_m':.20,'corner_lift_m':.10,'curve_power':1.65}]
        else:
            p['unbuilt_features']+=['Pool boundary absent from geospatial data; no invented water polygon',
                                    'Exact bridge masonry and north/south stair survey']
            p['dimensions']={'body_side_m':s,'slab_bottom_z_m':0,'floor_z_m':1.8,'column_top_z_m':5.25,
                'column_radius_m':.13,'column_base_radius_m':.23,'column_base_height_m':.14,'beam_height_m':.24,'beam_width_m':.28,
                'wall_thickness_m':.16,'window_sill_m':.85,'window_height_m':1.6,'door_height_m':2.6,
                'bridge':{'span_m':3.0,'spring_z_m':.65,'crown_z_m':1.4,'tunnel_depth_m':15.0,'center_y_m':0}}
            p['roof_tiers']=[{'tier_index':0,'outer_side_m':s+1.9,'inner_side_m':0,'eave_z_m':5.85,'top_z_m':8.75,
                'skin_thickness_m':.14,'corner_lift_m':.12,'curve_power':1.65}]
            p['roof_trim_conflict']={'chosen':'green','primary_source':'CG-SITE236537 current dedicated page',
                'other_source':'CG-PAPER2016 says blue; conflict retained, colors not treated synonymous'}
        out.append(p)
    p=deepcopy(rows['xianruoguan']);w,depth=p['study_body_width_m'],p['study_body_depth_m']
    p.update({'builder':'hall','bays_x':5,'bays_y':3,'study_bays_y':3,'eaves_tiers':1,'occupied_storeys':None,'reference_floor_count':1,
        'known_facts':deepcopy(cg['xianruoguan']['fields']),'paid_service_calls':0,
        'material_scheme':{'base':'white_stone','column':'red_lacquer','beam':'painted_beam','wall':'red','frame':'red_lacquer',
                           'infill':'dark_wood','roof_main':'yellow','roof_edge':'yellow','roof_under':'dark_wood'},
        'parameter_evidence':{'all_dimensions':'Unmeasured source-contained caller controls; published4chi historical veranda is not converted to current metric.',
                              'full_source_ring':'Complete8point source reference slab; no ring simplification or baoxia swallowing'},
        'unbuilt':['Precise six-wing joined main/baoxia roof junction; baoxia remains explicit source-volume reference',
                   'Measured elevations, courtyard world control, exact facades/lattice, fine paintwork/interior'],
        'assumptions':['Exterior study with open surrounding verandas; unresolved wall planes are not a historical facade schedule.']})
    p['dimensions']={'body_width_m':w,'body_depth_m':depth,'floor_z_m':.32,'source_reference_slab_bottom_z_m':0,
        'source_reference_slab_top_z_m':.32,'slab_thickness_m':.32,'wall_thickness_m':.22,'column_radius_m':.20,
        'column_base_radius_m':.30,'column_base_height_m':.18,'column_top_z_m':5.7,'beam_width_m':.40,'beam_height_m':.32,
        'wall_top_z_m':6.02,'enclosure_x_min_m':-w/2+1.15,'enclosure_x_max_m':w/2-1.15,
        'enclosure_y_min_m':-depth/2+1.15,'enclosure_y_max_m':depth/2-1.15,
        'veranda_front_depth_m':1.15,'veranda_rear_depth_m':1.15,'veranda_west_depth_m':1.15,'veranda_east_depth_m':1.15,
        'door_height_m':3.5,'window_height_m':2.2,'window_sill_height_above_floor_m':1,
        'door_width_fraction_of_bay':.7,'window_width_fraction_of_bay':.7,'opening_frame_width_m':.08,
        'opening_frame_depth_m':.12,'leaf_panel_depth_m':.05}
    p['roof_tiers']=[{'tier_index':0,'roof_type':'xieshan','outer_width_m':w+1.25,'outer_depth_m':depth+1.25,
        'eave_z_m':6.65,'top_z_m':10.6,'corner_lift_m':.12,'additional_overhang_m':0,'annular':False,
        'inner_width_m':None,'inner_depth_m':None}]
    unknown={'kind':'unresolved_wall','leaf_count':None,'pattern_category':None,'category_scope':'unknown_not_inferred'}
    p['facades']={side:({'schedule':[{'bay_index':i,**unknown} for i in range(5)]} if side in ('south','north') else deepcopy(unknown))
                    for side in ('south','north','east','west')}
    out.append(p)
    paths=['work/restoration-v16/registration/registered-buildings.json','work/restoration-v16/registration/actual-source-actors.json',
           'work/restoration-v16/research/cininggarden/facts.json','work/restoration-v16/research/huifeng/facts.json',
           'work/forbidden-city-research/geospatial/model-data.json','work/restoration-v16/prepare_profiles.py']
    doc={'schema':'garden-source-qualified-profile-controls/v16','buildings':out,'source_files':{n:sha(n) for n in paths},
         'policy':['0 paid calls','Human approvals pending','Whole city incomplete','No stage ZIP','All metrics explicit unmeasured study controls']}
    target=HERE/'profiles/pavilion-hall-profiles.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print('Prepared',len(out),'source-qualified profiles')
if __name__=='__main__':main()
