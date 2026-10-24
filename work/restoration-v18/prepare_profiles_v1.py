"""Resolve V18 caller controls from frozen actual registration; no Blender/native I/O."""
import ast
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

from shapely.geometry import Polygon, box

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "registration/registered-buildings.json"
REGISTRY_SHA = "b236c32053d58453daf4c1c9fa656b3ceb26328c4e1c1760469cbbd95f32141e"
EXPECTATIONS = HERE / "module-qa/fixture-expectations-v1.json"
PHOTO_ID = "nansansuo_middle_middle_hall"
GATE_ID = "nansansuo_common_gate"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise AssertionError(message)


def write(path, value):
    require(not path.exists(), "Preserve previous file " + str(path))
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    require(sha(REGISTRY) == REGISTRY_SHA, "Actual registry drift")
    registered = json.loads(REGISTRY.read_text())
    expected_doc = json.loads(EXPECTATIONS.read_text())
    expected = {r["building_id"]: r for r in expected_doc["buildings"]}
    module_path = HERE / "module-qa/fixture_profile_contract_v2.py"
    spec = importlib.util.spec_from_file_location("v18_profile_contract", module_path)
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    inputs = {str(REGISTRY.relative_to(ROOT)): REGISTRY_SHA, **registered["source_files_sha256"], **expected_doc["source_files_sha256"]}
    for path in [Path(__file__), EXPECTATIONS, module_path, HERE / "caller_material_overrides.py", ROOT / "work/courtyard_hall_buildings.py", ROOT / "work/four_hall_buildings.py", ROOT / "work/restoration_buildings.py"]:
        inputs[str(path.relative_to(ROOT))] = sha(path)
    for name, pin in inputs.items():
        require(sha(ROOT / name) == pin, "Pinned preparation input drift " + name)
    require(len(registered["buildings"]) == 10 and set(expected) == {r["building_id"] for r in registered["buildings"]}, "Exact ten actual source rows required")
    palette_ast = ast.parse((ROOT / "work/forbidden_city_geometry.py").read_text())
    colors = next(ast.literal_eval(n.value) for n in palette_ast.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PALETTE" for t in n.targets))
    states = {key: {"rgba": [*colors[key][0], 1], "metallic": colors[key][1], "roughness": colors[key][2]} for key in ("green", "grey", "red", "red_lacquer")}
    palette = {"schema":"v18-explicit-caller-palette/1", "custom":{key:{"color":state["rgba"][:3],"metallic":state["metallic"],"roughness":state["roughness"]} for key,state in states.items()}, "materials":states,
               "source_files_sha256":{"work/forbidden_city_geometry.py":sha(ROOT/'work/forbidden_city_geometry.py'),str(Path(__file__).relative_to(ROOT)):sha(__file__)},
               "scope":"Exact caller RGB controls read from frozen F.PALETTE; green-glazed category official, pigment/finish numeric unmeasured. Neutral unknown walls/beams/columns except photo-qualified front columns/frames only.","third_party_cost":0}
    buildings, checks = [], []
    for row in registered["buildings"]:
        ident = row["building_id"]; expectation = expected[ident]
        require(row["source_actor_geometry_verified"] is True and row["source_part_id"] == expectation["source_part_id"], "Native geometry/qualified entity binding absent")
        width, depth = row["study_body_width_m"], row["study_body_depth_m"]
        gate, photo = ident == GATE_ID, ident == PHOTO_ID
        p = {key:copy.deepcopy(row[key]) for key in ("building_id","name_zh","source_part_id","source_component_id","source_polygon_world","source_holes_world","source_polygon_local","source_holes_local","anchor","rotation_z_rad","source_actual_actor_names","allowed_hidden_source_actor_names","original_source_record","original_source_polygon_world","original_source_holes_world","source_record_sha256","source_component_geometry","source_containment_proof","qualified_factual_source_fields","source6m_proxy_height_is_real_building_height")}
        p.update({"builder":"hall","registration_file":str(REGISTRY.relative_to(ROOT)),"registration_sha256":REGISTRY_SHA,"bays_x":expectation['width_bays'],"bays_y":1 if gate else None,"study_bays_x":expectation['width_bays'],"study_bays_y":1,"eaves_tiers":1,"occupied_storeys":None,"reference_floor_count":1,"third_party_cost":0,"paid_service_calls":0,"human_approval":"pending","factual_roof_type":expectation['roof_type'],"caller_front_columns_material_key":"red" if photo else None,"measured_world_azimuth":None,"current_metric_registration":None})
        p['original_typed_factual_source_fields']=copy.deepcopy(row['qualified_factual_source_fields'])
        p['typed_factual_source_fields']=copy.deepcopy(row['qualified_factual_source_fields'])
        p['known_facts']={"roof_type":expectation['roof_type'],"qualified_original_fields":copy.deepcopy(row['qualified_factual_source_fields']),"roof_color_material_class":"green_glazed","occupied_storeys":None,"current_width_m":None,"current_depth_m":None,"current_height_m":None,"current_datum_m":None,"door_leaf_count":None,"window_leaf_count":None,"door_open_state":None,"precise_window_pattern":None,"exact_original_aperture_count":None,"front_bay_categories":"WWDWW" if photo else None,"front_bay_categories_basis":"photo-caption-qualified bay category only, not exact aperture count" if photo else None}
        t=.20
        p['dimensions']={"body_width_m":width,"body_depth_m":depth,"floor_z_m":.35,"source_reference_slab_bottom_z_m":0,"source_reference_slab_top_z_m":.35,"slab_thickness_m":.35,"wall_thickness_m":t,"column_radius_m":.17,"column_base_radius_m":.27,"column_base_height_m":.15,"column_top_z_m":4.6,"beam_width_m":.36,"beam_height_m":.28,"wall_top_z_m":4.88,"enclosure_x_min_m":-width/2+.11,"enclosure_x_max_m":width/2-.11,"enclosure_y_min_m":-depth/2+t/2,"enclosure_y_max_m":depth/2-t/2,"veranda_front_depth_m":t/2,"veranda_rear_depth_m":t/2,"veranda_west_depth_m":.11,"veranda_east_depth_m":.11,"door_height_m":3.15,"window_height_m":1.95,"window_sill_height_above_floor_m":.9,"door_width_fraction_of_bay":.68,"window_width_fraction_of_bay":.70,"opening_frame_width_m":.075,"opening_frame_depth_m":.12,"leaf_panel_depth_m":.05}
        p['roof_tiers']=[{"tier_index":0,"roof_type":expectation['roof_type'],"outer_width_m":width+.8 if gate else width,"outer_depth_m":depth+.8,"eave_z_m":5.5,"top_z_m":8.1,"corner_lift_m":.10 if gate else 0,"additional_overhang_m":0,"annular":False,"inner_width_m":None,"inner_depth_m":None}]
        p['material_scheme']={"base":"grey","column":"grey","beam":"grey","wall":"grey","frame":"red_lacquer" if photo else "grey","infill":"grey","roof_main":"green","roof_edge":"green","roof_under":"grey"}
        p['material_scope']='Green glazed roof category is official. Other colors default neutral. Only photographed middle establishment middle hall front reference columns use caller red override and its front opening frames red; no rear/side or other hall paint inference. Numeric RGB/finish unmeasured.'
        p['facades']={side:({"schedule":[{"bay_index":i,"kind":"unresolved_wall","leaf_count":None,"pattern_category":None,"category_scope":"unknown_enclosure_reference_not_historic_solid_wall_fact"} for i in range(p['bays_x'])]} if side in ('south','north') else {"kind":"unresolved_wall","leaf_count":None,"pattern_category":None,"category_scope":"unknown_not_inferred"}) for side in ('south','north','east','west')}
        for side,index,kind in expectation['apertures']:
            item=p['facades'][side]['schedule'][index]
            item.update(kind=kind,pattern_category='door-containing bay' if kind=='door' else 'windowed bay',category_scope=expectation['aperture_scope'])
        p['parameter_evidence']={"all_metric_parameters":{"status":"unmeasured_engineering_study_controls","source_fit_dimensions":"complete registered source-contained body with .5m all-side reserve; not architectural survey","source_proxy_height_used_as_real_hall_height":False,"equal_bay_spans_are_study_only":True,"numeric_values":copy.deepcopy(p['dimensions']),"roof_numeric_values":copy.deepcopy(p['roof_tiers'])},"inert_opening_dimensions_on_unresolved_facades":{"status":"required API controls; never generate apertures when category unresolved"},"engineering_wall_insets":{"x_m":.11,"y_m":.10,"historical_veranda_assertion":False},"roof_xy_budget":{"outer_expansion_m":.8,"additional_nominal_decorative_half_extent_budget_m":.09,"within_registered_reserve_m":.5,"scope":"conservative parameter preflight only; actual all-triangle roof/ridge/tile projection must pass separately"},"conditional_facade":{"photo_only_middle_middle":photo,"actual_original_opening_total":None,"model_representative_aperture_records":len(expectation['apertures']),"exact_leaf_count_and_open_pose":None}}
        p['unbuilt']=["Current measured dimensions/datum/precise azimuth; source 6m proxy not building height","Unknown main-hall depth bays, equal-span reality and occupied storeys","All exact leaf counts, opening subdivisions, poses, lattice/joinery and complete interiors","All unqualified enclosure categories and rear/side paintwork","All retained ancillary source proxies, side halls, well pavilions and neighbours remain separate pending source-qualified evidence"]
        if gate:p['unbuilt']+=['Official inside/outside jiaocuo ramp category retained; ramp width/depth/rise/slope/tread dimensions and physical through-route unresolved']
        if photo:p['unbuilt']+=['Photo doorway/platform steps visible category only; step count/dimensions and exact original aperture subdivisions unresolved']
        contract.check_profile_intent(p,expectation)
        local=Polygon(p['source_polygon_local'],p['source_holes_local']);require(local.is_valid,'source local polygon invalid')
        require(local.covers(box(-width/2-.5,-depth/2-.5,width/2+.5,depth/2+.5)), 'body plus full reserve outside source')
        rw,rd=p['roof_tiers'][0]['outer_width_m'],p['roof_tiers'][0]['outer_depth_m']
        require(local.covers(box(-rw/2-.09,-rd/2-.09,rw/2+.09,rd/2+.09)), 'nominal roof plus decorative budget outside source')
        c,s=math.cos(p['rotation_z_rad']),math.sin(p['rotation_z_rad'])
        require(all(math.dist((p['anchor'][0]+c*x-s*y,p['anchor'][1]+s*x+c*y),world)<=1e-4 for (x,y),world in zip(p['source_polygon_local'],p['source_polygon_world'])),'source frame differs')
        checks.append({"id":ident,"passed":True,"input":"actual registration and official fact/photo expectation","operation":"null-preserving profile contract; complete source area contains body reserve and nominal roof/decor budget; full source frame exact","expected":"caller controls only, no measurement promotion","actual_source_vertices":len(p['source_polygon_world']),"factual_depth_bays":p['bays_y'],"occupied_storeys":None,"nominal_full_footprint_control_area_outside_source_m2":0.,"actual_generated_geometry_checked":False})
        buildings.append(p)
    outdir=HERE/'profiles';outdir.mkdir(exist_ok=True)
    palettepath=outdir/'palette-v1.json';write(palettepath,palette);inputs[str(palettepath.relative_to(ROOT))]=sha(palettepath)
    doc={"schema":"v18-source-qualified-ten-exterior-caller-profiles/1","buildings":buildings,"source_files":inputs,"registry_file":str(REGISTRY.relative_to(ROOT)),"registry_sha256":REGISTRY_SHA,"fixture_expectations_file":str(EXPECTATIONS.relative_to(ROOT)),"fixture_expectations_sha256":sha(EXPECTATIONS),"facts_are_not_metric_survey":True,"whole_city_objective_complete":False,"human_approval":"pending","third_party_cost":0,"paid_service_calls":0,"source_reference_floors_complete_original_shapes":True,"physical_through_route_certified":False}
    profilepath=outdir/'building-profiles-v1.json';write(profilepath,doc)
    write(outdir/'preparation-math-report-01.json',{"schema":"v18.formal-caller-preparation-math/1","summary":{"passed":len(checks),"failed":0},"checks":checks,"profile_sha256":sha(profilepath),"palette_sha256":sha(palettepath),"registered_actual_source_bound":True,"Blender_started":False,"generated_V18_geometry_verified":False,"third_party_cost":0})
    print('PROFILES',sha(profilepath));print('PALETTE',sha(palettepath))


if __name__=='__main__':main()
