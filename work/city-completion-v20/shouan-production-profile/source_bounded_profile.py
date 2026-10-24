"""Pure deterministic source-bound profile math; no Blender or file I/O."""
import math

from shapely.affinity import affine_transform
from shapely.geometry import Point, Polygon, box, mapping


def require(ok,message):
    if not ok:raise AssertionError(message)


def _horizontal_edges(polygon,y):
    coords=list(polygon.exterior.coords)
    hits=[]
    for (x0,y0),(x1,y1)in zip(coords,coords[1:]):
        if y0==y1:continue
        if min(y0,y1)<=y<max(y0,y1):
            a=(x1-x0)/(y1-y0);b=x0-a*y0
            hits.append((a*y+b,a,b))
    hits.sort()
    require(len(hits)==2,'source must be y-monotone in its fixed study frame')
    return hits[0][1:],hits[1][1:]


def maximum_centered_rectangle(polygon,clearance):
    """Exact piecewise search, not sampled bbox/hull fitting.

    For a y-monotone polygon, the x interval is affine between every vertex y.
    The limiting half-width over [-h,h] is the running minimum of four affine
    boundaries and previous extrema. Its area is piecewise quadratic: interval
    ends, pair crossings, and each quadratic stationary point cover all maxima.
    """
    require(polygon.is_valid and polygon.area>0 and not polygon.interiors,'valid hole-free source required')
    require(math.isfinite(clearance)and clearance>0,'positive numerical source clearance required')
    core=polygon.buffer(-clearance,join_style=2)
    require(core.geom_type=='Polygon'and not core.interiors and core.contains(Point(0,0)),'centered inner source domain unavailable')
    hmax=min(-core.bounds[1],core.bounds[3])
    knots=sorted({0.,hmax,*[abs(y)for x,y in core.exterior.coords if 0<abs(y)<hmax]})
    left,right=_horizontal_edges(core,0.)
    prefix=min(-left[1],right[1]);candidates=[];intervals=[]
    for lo,hi in zip(knots,knots[1:]):
        mid=(lo+hi)/2
        lp,rp=_horizontal_edges(core,mid);ln,rn=_horizontal_edges(core,-mid)
        lines=[(-lp[0],-lp[1]),(rp[0],rp[1]),(ln[0],-ln[1]),(-rn[0],rn[1]),(0.,prefix)]
        hs={lo,hi}
        for i,(a,b)in enumerate(lines):
            if a<0:
                stationary=-b/(2*a)
                if lo<=stationary<=hi:hs.add(stationary)
            for c,d in lines[i+1:]:
                if a!=c:
                    cross=(d-b)/(a-c)
                    if lo<=cross<=hi:hs.add(cross)
        accepted=[]
        for h in sorted(hs):
            width=min(a*h+b for a,b in lines)
            if h>0 and width>0:
                item=(4*width*h,width,h)
                candidates.append(item);accepted.append(list(item))
        prefix=min(prefix,*[a*hi+b for a,b in lines])
        intervals.append({'h_interval':[lo,hi],'limiting_halfwidth_affine_lines':lines,'area_candidates':[a for a in accepted]})
    require(candidates,'no centered conservative source rectangle')
    optimum=max(candidates,key=lambda v:(v[0],v[1],-v[2]))
    width,height=optimum[1:]
    # Nudge toward the interior only at binary rounding scale, never architectural
    # metres. Preserve both the mathematical optimum and conservative result.
    nudges=0
    while not core.covers(box(-width,-height,width,height)):
        width=math.nextafter(width,0.);height=math.nextafter(height,0.);nudges+=1
        require(nudges<=4096,'numeric maximum could not be made conservative')
    rectangle=box(-width,-height,width,height)
    require(polygon.covers(rectangle),'complete source does not cover fitted rectangle')
    return rectangle,{'fixed_center':[0.,0.],'fixed_axis':'source-derived study frame, not surveyed azimuth',
        'method':'All piecewise affine width boundaries, all crossings and quadratic stationary points',
        'complete_polygon_used_not_MRR_or_hull':True,'mathematical_optimum_area_m2':optimum[0],
        'mathematical_optimum_halfwidth_m':optimum[1],'mathematical_optimum_halfdepth_m':optimum[2],
        'conservative_area_m2':rectangle.area,'binary_inward_nudges':nudges,'numerical_clearance_m':clearance,
        'piecewise_intervals':intervals,'candidate_count':len(candidates),'inner_source_polygon':mapping(core)}


def profile_from_evidence(qualification,source_frame,actual_actor,official_building,neighbours):
    permitted=qualification['permitted_next_work']
    require(qualification['qualified_for_conditional_source_bounded_study']is True
        and qualification['subject_source_id']=='way-40624979-p0','79 bounded study qualification required')
    source=actual_actor['source_record'];frame=source_frame['local_frame_draft']
    require(source['polygon']==permitted['source79_full_polygon_world']==frame['source_polygon_world']
        and source['holes']==permitted['source79_full_holes_world']==frame['source_holes_world'],'full actual source ring differs')
    P=Polygon(frame['source_polygon_local'],frame['source_holes_local'])
    maxworld=max(abs(v)for p in source['polygon']for v in p)
    clearance=16*2.**(math.floor(math.log2(maxworld))-23)
    envelope,proof=maximum_centered_rectangle(P,clearance)
    hx,hy=envelope.bounds[2:]
    tube=.085 # exact largest fixed R._roof_geometry tube radius; no beasts added
    rw,rd=2*(hx-tube),2*(hy-tube)
    overhang=min(rw,rd)*.045
    w,d=rw-2*overhang,rd-2*overhang
    u=d
    dims={'body_width_m':w,'body_depth_m':d,'slab_thickness_m':u*.018,
        'source_reference_slab_bottom_z_m':0.,'source_reference_slab_top_z_m':u*.018,'floor_z_m':u*.018,
        'wall_thickness_m':u*.025,'column_radius_m':u*.014,'column_base_radius_m':u*.020,'column_base_height_m':u*.032,
        'column_top_z_m':u*(.018+.36),'beam_width_m':u*.025,'beam_height_m':u*.036,
        'wall_top_z_m':u*(.018+.36+.036),'enclosure_x_min_m':-w/2,'enclosure_x_max_m':w/2,
        'enclosure_y_min_m':-d/2,'enclosure_y_max_m':d/2,'veranda_front_depth_m':0.,'veranda_rear_depth_m':0.,
        'veranda_west_depth_m':0.,'veranda_east_depth_m':0.,'door_height_m':u*.22,'window_height_m':u*.15,
        'window_sill_height_above_floor_m':u*.065,'opening_frame_width_m':u*.008,
        'opening_frame_depth_m':u*.033,'leaf_panel_depth_m':u*.004,
        'door_width_fraction_of_bay':.66,'window_width_fraction_of_bay':.62}
    xs=permitted['relative_post_axes_x']
    north_to_south=permitted['relative_post_axes_y_north_to_south']
    ys=[1-v for v in reversed(north_to_south)]
    xspans=[w*(b-a)for a,b in zip(xs,xs[1:])]
    yspans=[d*(b-a)for a,b in zip(ys,ys[1:])]
    def schedule(front):
        return [{'bay_index':i,'kind':'door'if i==2 else'window',
            'leaf_count':4 if front and i==2 else None,
            'pattern_category':'步步锦'if front and i==2 else None,
            'category_scope':'DPM236505 named bay category; opening metric sizes unmeasured'}for i in range(5)]
    facts={r['key']:r['value']for r in official_building['facts']}
    require(facts['front_bays']==5 and facts['depth_bays']==3 and facts['roof_type']=='xieshan'
        and facts['roof_covering']=='yellow_glazed_tile'and facts['facing_direction_official_text']is None
        and facts['roof_eave_tier_count']is None,'factual/inference layer drift')
    theta=frame['rotation_z_rad'];c,s=math.cos(theta),math.sin(theta);anchor=frame['anchor']
    transform=[c,-s,s,c,anchor[0],anchor[1]]
    body=box(-w/2,-d/2,w/2,d/2)
    margins={'column_base':dims['column_base_radius_m'],'beam':dims['beam_width_m']/2,
        'wall_and_closure':dims['wall_thickness_m']/2,'opening_frame_normal':dims['opening_frame_depth_m']/2,
        'leaf_normal':dims['leaf_panel_depth_m']/2}
    m=max(margins.values())
    support=box(-w/2-m,-d/2-m,w/2+m,d/2+m)
    require(envelope.covers(support),'body/base/frame conservative envelope exceeds roof envelope')
    eave=dims['wall_top_z_m']+u*.055
    roof={'tier_index':0,'roof_type':'xieshan','outer_width_m':rw,'outer_depth_m':rd,
        'eave_z_m':eave,'top_z_m':eave+u*.28,'corner_lift_m':u*.018,
        'annular':False,'inner_width_m':None,'inner_depth_m':None,'additional_overhang_m':0.}
    unbuilt=['Measured actual height, datum, floor/storey count, eave-tier count and surveyed body/roof footprints',
        'Interior8 post-grid intersections and their beams: frozen G14 builds only16 perimeter posts, not24 full intersections',
        'Precise column/bay dimensions, dougong, concealed carpentry, physical roof tile cavities and ridge beasts',
        'Exact joinery/lattice motifs, opening dimensions, unknown noncentral/rear leaf counts and leaf poses',
        '95/97 turning-gallery names, roofs, levels and all source bodies outside79; all remain intact',
        'Chunxi80 main/rear juandian partition and all other compound buildings remain pending']
    profile={**{k:frame[k]for k in ('anchor','rotation_z_rad','source_polygon_local','source_polygon_world','source_holes_local','source_holes_world')},
        'building_id':'shouangong','name_zh':'寿安宫正殿','source_part_id':source['id'],'builder':'hall',
        'preparation_scope':'qualified_source_bounded_unmeasured_study','production_use_allowed':True,
        'source_actor_geometry_verified':True,'generated_geometry_verified':False,'historical_identity_confirmed':False,
        'source_actual_actor_names':[actual_actor['name']],'allowed_hidden_source_actor_names':[],
        'original_source_record':source,'dimension_status':'unmeasured_study','facing':None,'study_front_facing':'south',
        'study_front_qualification':'official_plan_inference_only','bays_x':5,'bays_y':3,
        'column_bay_widths_x_m':xspans,'column_bay_widths_y_m':yspans,
        'enclosure_column_indices_x':list(range(6)),'enclosure_column_indices_y':list(range(4)),
        'eaves_tiers':None,'study_eaves_tiers':1,'occupied_storeys':None,'reference_floor_count':1,
        'dimensions':dims,'roof_tiers':[roof],
        'facades':{'south':{'schedule':schedule(True)},'north':{'schedule':schedule(False)},
            'east':{'kind':'unresolved_wall','leaf_count':None},'west':{'kind':'unresolved_wall','leaf_count':None}},
        'material_scheme':{k:k for k in ('base','column','beam','wall','frame','infill','roof_main','roof_edge','roof_under')},
        'known_facts':facts,'official_facts_raw':official_building,
        'factual_unknowns':qualification['known_unknowns'],
        'parameter_evidence':{'all_metric_values':{'status':'unmeasured_study','scope':'Deterministic source-inscribed safe envelope plus explicitly proportional visual controls; not historic dimensions'},
            'nonuniform_column_spans':{'status':'official_plan_relative_inference','relative_x':xs,'relative_y_north_to_south':north_to_south,
                'local_y_ascending_relative':ys,'metric_scale':'source-safe control scale, no pixel-to-metre fit',
                'source_pixel_axis_to_local':{'pixel_x_increasing':'local +X west to east','pixel_y_increasing':'local -Y north to south',
                    'G14_y_axis_order':'south to north: reverse pixel intervals [49,86,54]/189',
                    'column_x_pixels':[296,347,398,471,522,575],'column_y_pixels_north_to_south':[240,294,380,429],
                    'manual_pick_uncertainty_pixels':3,'pixel_error_is_not_metric_accuracy':True}},
            'enclosure_grid':'explicit original column indices so openings share nonuniform x axes',
            'height':'all floor/base/column/eave/roof Z are proportional illustration; 6m source draft never adopted'},
        'central_front_recess':{'required_caller_adapter':True,'bay_index':2,'depth_m':yspans[0],
            'depth_rule':'first actual nonuniform localY column interval; unmeasured relative plan control','implemented_by_G14':False},
        'source_envelope_derivation':{**proof,'all_source_WORLD_clearance_factor_float32_ULPs':16,
            'roof_fixed_tube_XY_radius_upper_bound_m':tube,'roof_beasts_included':False,'beasts_status':'unbuilt, no fabricated bounds',
            'roof_overhang_each_side_m':overhang,'roof_overhang_formula':'0.045*min(source-safe outer roof W,D)',
            'body_margin_budget_m':margins,'body_and_all_base_frame_projections_bounded':True,
            'conservative_architecture_envelope_local':mapping(envelope),
            'body_reference_domain_local':mapping(body),'support_frame_envelope_local':mapping(support)},
        'unbuilt':unbuilt,'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False,
        'preserved_neighbour_source_records':neighbours,'source6m_is_actual_height':False,
        'full_reference_floor_is_unmeasured_source_support':True,'factual_floor_z_m':None,'factual_height_m':None,
        'source_remainder_policy':'Original79 stays visible now. Preserve both full exact source-minus-body and source-minus-envelope plans. Future display replacement needs actual full generated projection difference and separate approval.'}
    remainder={'schema':'shouan79-exact-source-remainder-plan/1','source_polygon_world':source['polygon'],'source_holes_world':source['holes'],
        'full_source_domain_world':mapping(Polygon(source['polygon'],source['holes'])),
        'unresolved_outside_body_world':mapping(affine_transform(P.difference(body),transform)),
        'unresolved_outside_conservative_envelope_world':mapping(affine_transform(P.difference(envelope),transform)),
        'body_reference_domain_world':mapping(affine_transform(body,transform)),
        'conservative_envelope_world':mapping(affine_transform(envelope,transform)),
        'actual_generated_projection_difference_still_pending':True,'source79_hidden_now':False,
        'source95_97_modified_or_hidden':False,'gray_remainder_mesh_created':False,'historical_partition_approved':False}
    return profile,remainder
