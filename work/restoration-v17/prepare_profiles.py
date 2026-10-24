"""Four explicit source-qualified study profiles, never surveyed dimensions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(doc, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


registry_path = HERE/'registration/registered-buildings.json'
assert sha(registry_path) == '0ff859b0e1434e9ee1c0501aa2f301fd6b8416e85e32a5c2b525f9e3c18479bc'
registry = json.loads(registry_path.read_text())
assert all(sha(ROOT/path) == digest for path, digest in registry['source_files_sha256'].items())
profiles = []
for original in registry['buildings']:
    p = deepcopy(original)
    ident = p['building_id']
    w, depth = p['study_body_width_m'], p['study_body_depth_m']
    stage = ident == 'shufang_large_stage'
    front = ident == 'shufang_front_hall'
    rear = ident == 'shufang_rear_hall'
    p.update(builder='stage' if stage else 'hall', bays_x=3 if stage or not (front or rear) else 5,
             bays_y=3 if stage or front else 1, occupied_storeys=1 if stage else None,
             reference_floor_count=1, eaves_tiers=2 if stage else 1 if ident=='baohuadian_main' else None,
             paid_service_calls=0, third_party_cost=0, human_approval='pending')
    p['parameter_evidence'] = {
        'all_metric_controls': 'Unmeasured caller study: source polygon is retained; body reserve, heights, thickness, openings and supports are not Palace Museum measurements.',
        'published_90m2': 'Not used to derive any stage width/depth or source scaling.',
        'source_height_6m': 'An inherited assumed proxy height, never used as measured building height.',
        'unknown_eaves': 'Front/rear factual eaves remain null. One modeled shell is provisional, not a newly established historical tier count.'}
    p['unbuilt'] = ['Current metric survey/world datum, precise joinery, dougong, individual roof tiles, lattice and paintwork',
                    'All unverified enclosures/opening leaf counts and complete interiors',
                    'Front hall separate veranda roof topology remains unknown; current body reference is not exact joined roof proof']
    roof_type = 'sijiao_zanjian' if stage else 'yingshan' if rear else 'xieshan'
    p['known_facts'] = {'roof_type': roof_type, 'typed_original_fields': deepcopy(p['original_typed_factual_source_fields']),
                        'qualified_factual_supplements': deepcopy(p['factual_supplements'])}
    if stage:
        band_w, band_d = w*.52, depth*.52
        p['dimensions'] = {'body_width_m': w, 'body_depth_m': depth,
            'slab_bottom_z_m': 0, 'floor_z_m': .85, 'column_top_z_m': 4.6,
            'column_radius_m': .16, 'column_base_radius_m': .25, 'column_base_height_m': .14,
            'beam_width_m': .42, 'beam_height_m': .28,
            'upper_band': {'width_m': band_w, 'depth_m': band_d, 'bottom_z_m': 6.08,
                           'wall_thickness_m': .12, 'occupied_floor': False}}
        p['roof_tiers'] = [
            {'tier_index': 0, 'outer_width_m': w+1.4, 'outer_depth_m': depth+1.4,
             'inner_width_m': band_w, 'inner_depth_m': band_d, 'eave_z_m': 5.1, 'top_z_m': 6.2,
             'skin_thickness_m': .14, 'curve_power': 1.65, 'corner_lift_m': .12},
            {'tier_index': 1, 'outer_width_m': band_w+1.4, 'outer_depth_m': band_d+1.4,
             'inner_width_m': 0, 'inner_depth_m': 0, 'eave_z_m': 6.85, 'top_z_m': 9.15,
             'skin_thickness_m': .20, 'curve_power': 1.65, 'corner_lift_m': .10}]
        p['material_scheme'] = {'column': 'green_paint', 'beam': 'painted_beam', 'wall': 'green_paint',
            'stone': 'white_stone', 'railing': 'red_lacquer', 'roof_main': 'yellow',
            'roof_edge': 'yellow', 'roof_under': 'dark_wood'}
        p['unbuilt'] += ['Side/rear stage enclosure and exact backstage connection/roof not reconstructed',
                         'Only front railing category visible in official photo; repeated bars are illustrative, not a historical count',
                         'Precise upper band fenestration, plaques, decorative inscriptions and finial']
    else:
        floor, height, veranda = .35, 4.6, .85 if front else .7 if rear else .8
        p['dimensions'] = {'body_width_m': w, 'body_depth_m': depth, 'floor_z_m': floor,
            'source_reference_slab_bottom_z_m': 0, 'source_reference_slab_top_z_m': floor,
            'slab_thickness_m': floor, 'wall_thickness_m': .20,
            'column_radius_m': .17, 'column_base_radius_m': .27, 'column_base_height_m': .15,
            'column_top_z_m': height, 'beam_width_m': .36, 'beam_height_m': .28, 'wall_top_z_m': height+.28,
            'enclosure_x_min_m': -w/2, 'enclosure_x_max_m': w/2,
            'enclosure_y_min_m': -depth/2+veranda, 'enclosure_y_max_m': depth/2,
            'veranda_front_depth_m': veranda, 'veranda_rear_depth_m': 0,
            'veranda_west_depth_m': 0, 'veranda_east_depth_m': 0,
            'door_height_m': 3.15, 'window_height_m': 1.95, 'window_sill_height_above_floor_m': .9,
            'door_width_fraction_of_bay': .68, 'window_width_fraction_of_bay': .70,
            'opening_frame_width_m': .075, 'opening_frame_depth_m': .12, 'leaf_panel_depth_m': .05}
        p['roof_tiers'] = [{'tier_index': 0, 'roof_type': roof_type,
            'outer_width_m': w if rear else w+1.25, 'outer_depth_m': depth+1.25,
            'eave_z_m': 5.5, 'top_z_m': 8.1, 'corner_lift_m': 0 if rear else .12,
            'additional_overhang_m': 0, 'annular': False, 'inner_width_m': None, 'inner_depth_m': None}]
        p['material_scheme'] = {'base': 'white_stone', 'column': 'green_paint', 'beam': 'painted_beam',
            'wall': 'red', 'frame': 'red_lacquer', 'infill': 'dark_wood',
            'roof_main': 'grey' if rear else 'yellow', 'roof_edge': 'grey' if rear else 'yellow', 'roof_under': 'dark_wood'}
        p['material_scope'] = 'Rear neutral gray explicitly means unknown tile color; RGB values and unverified rear paint are study references, not pigment measurement.'
        unknown = {'kind': 'unresolved_wall', 'leaf_count': None, 'pattern_category': None,
                   'category_scope': 'unknown_not_inferred'}
        p['facades'] = {side: ({'schedule': [{'bay_index': i, **deepcopy(unknown)} for i in range(p['bays_x'])]}
                               if side in ('south', 'north') else deepcopy(unknown)) for side in ('south', 'north', 'east', 'west')}
        if front or rear:
            for i, row in enumerate(p['facades']['south']['schedule']):
                row.update(kind=('door' if front else 'passage') if i==2 else 'window',
                           pattern_category='风门' if front and i==2 else '穿堂通口' if i==2 else '槛窗',
                           category_scope='official_current_category_or_qualified_H_connection; all metric controls unmeasured')
        if front:
            p['facades']['north']['schedule'][2].update(kind='passage', pattern_category='穿堂通口',
                category_scope='qualified official H connection; aperture dimensions unmeasured')
        if rear:
            p['unbuilt'] += ['Roof tile color and factual eave/storey counts remain null; gray roof is neutral category reference',
                             'Indoor Fengyacun stage/partitions and west ear-room doorway not modeled']
        if ident == 'baohuadian_main':
            p['unbuilt'] += ['All door/window schedule unverified; no invented leaf counts or guessed apertures',
                             'North baoxia roof/join remains complete explicit gray source proxy']
    profiles.append(p)
source_names = [registry_path, HERE/'registration/actual-registration-freeze.json',
                HERE/'research/shufang/facts.json', HERE/'research/shufang/supplemental-01/supplemental-evidence.json',
                HERE/'research/baohuadian/facts.json', ROOT/'work/theatre_stage_buildings.py',
                ROOT/'work/courtyard_hall_buildings.py', Path(__file__)]
doc = {'schema': 'four-source-qualified-building-profiles/v17', 'buildings': profiles,
       'source_files': {str(path.relative_to(ROOT)): sha(path) for path in source_names},
       'facts_are_not_metric_survey': True, 'whole_city_objective_complete': False, 'human_approval': 'pending',
       'third_party_cost': 0, 'paid_service_calls': 0}
write(HERE/'profiles/building-profiles.json', doc)
write(HERE/'profiles/palette.json', {'schema': 'v17-explicit-caller-palette/1',
    'base': 'R.restoration_materials(F.create_materials("R17_"))',
    'custom': {'green_paint': {'color': [.035, .23, .14], 'metallic': 0, 'roughness': .48}},
    'colors_are_unmeasured': True, 'rear_grey_is_unknown_material_reference': True})
print('Prepared four profiles; no Blender/source geometry modified', flush=True)
