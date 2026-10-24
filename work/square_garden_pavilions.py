"""Source-qualified square pavilion studies. Pure geometry; caller owns I/O."""
import json
import math

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import forbidden_city_geometry as F
import restoration_buildings as R
import imperial_monuments as M


def _validate(p):
    for k in ('building_id','name_zh','source_part_id','source_polygon_local','source_holes_local',
              'anchor','rotation_z_rad','dimensions','roof_tiers','material_scheme','known_facts','unbuilt_features'):
        if k not in p: raise ValueError('pavilion profile missing '+k)
    if p['building_id'] not in ('huifengting','linxiting'): raise ValueError('unsupported registered pavilion')
    if p['occupied_storeys'] is not None or p['reference_floor_count'] != 1:
        raise ValueError('roof tiers cannot certify occupied floors')
    if p['bays_x'] != 3 or p['bays_y'] != 3: raise ValueError('published square3x3 reference required')
    F._point('anchor',p['anchor']);F._number('rotation',p['rotation_z_rad'])
    rings=[F._clean_ring(p['source_polygon_local'])]+[F._clean_ring(r) for r in p['source_holes_local']]
    F._triangulate_rings(rings)
    d=p['dimensions']
    for k in ('body_side_m','column_radius_m','column_base_radius_m','column_base_height_m','beam_height_m','beam_width_m'):
        F._number(k,d[k],strictly_positive=True)
    if not d['slab_bottom_z_m'] < d['floor_z_m'] < d['column_top_z_m']: raise ValueError('invalid support levels')
    if d['column_base_radius_m'] <= d['column_radius_m']: raise ValueError('column base too narrow')
    expected=2 if p['building_id']=='huifengting' else 1
    if len(p['roof_tiers']) != expected: raise ValueError('wrong explicit roof tier count')
    for i,t in enumerate(p['roof_tiers']):
        for k in ('outer_side_m','skin_thickness_m','curve_power'): F._number(k,t[k],strictly_positive=True)
        if t['tier_index']!=i or not t['eave_z_m'] < t['top_z_m']: raise ValueError('invalid roof levels')
        if not 0 <= t['inner_side_m'] < t['outer_side_m']: raise ValueError('invalid annular opening')
        if bool(t['inner_side_m']) != (expected==2 and i==0): raise ValueError('only lower double eave is annular')
        if t['skin_thickness_m'] >= min(t['outer_side_m'],t['top_z_m']-t['eave_z_m'])/3: raise ValueError('skin too thick')
    if p['roof_tiers'][0]['outer_side_m'] <= d['body_side_m']: raise ValueError('roof misses outer columns')
    if expected==2:
        b=d['upper_band'];lower,upper=p['roof_tiers']
        if b['occupied_floor'] is not False or b['side_m'] != lower['inner_side_m']:
            raise ValueError('upper support band must meet annular inner rim without occupied floor')
        if not lower['top_z_m']-lower['skin_thickness_m'] <= b['bottom_z_m'] < lower['top_z_m'] < upper['eave_z_m']:
            raise ValueError('band/lower roof contact levels invalid')
        if upper['outer_side_m'] <= b['side_m']+b['wall_thickness_m']: raise ValueError('upper roof misses band')
    elif d.get('upper_band') is not None: raise ValueError('single roof cannot imply upper band')
    json.dumps(p,allow_nan=False)
    return rings


def _roof(p,t,col,mats):
    surf=F._Surface();mi=[];perimeter=[];around=12;levels=14
    for side in range(4):
        for i in range(around):
            u=-1+2*i/around
            perimeter.append((u,-1) if side==0 else (1,u) if side==1 else (-u,1) if side==2 else (-1,-u))
    a=t['outer_side_m']/2;inner=t['inner_side_m'];stop=1-inner/t['outer_side_m']
    def point(x,y,f):
        s=stop*f
        return (a*x*(1-s),a*y*(1-s),t['eave_z_m']+(t['top_z_m']-t['eave_z_m'])*f**t['curve_power']+
                t['corner_lift_m']*min(abs(x),abs(y))**8*(1-f)**3)
    for j in range(levels):
        for i,(x,y) in enumerate(perimeter):
            xx,yy=perimeter[(i+1)%len(perimeter)];f0,f1=j/levels,(j+1)/levels
            if not inner and j==levels-1: surf.face([point(x,y,f0),point(xx,yy,f0),(0,0,t['top_z_m'])])
            else: surf.face([point(x,y,f0),point(xx,yy,f0),point(xx,yy,f1),point(x,y,f1)])
            mi.append(1 if j==0 else 0)
    n=len(surf.faces);R._closed_skin(surf,t['skin_thickness_m']);mi.extend([2]*(len(surf.faces)-n))
    obj=R._mesh('V16_'+p['building_id']+'_square_roof_'+str(t['tier_index']),surf,col,
                [mats[p['material_scheme']['roof_main']],mats[p['material_scheme']['roof_edge']],mats['dark_wood']],mi)
    obj['roof_type']='sijiao_zanjian';obj['roof_tier_index']=t['tier_index'];obj['annular']=bool(inner)
    obj['roof_topology']='square_annular_open_inner_rim' if inner else 'four_curved_faces_single_central_apex'
    return obj


def _tree(obj):
    return BVHTree.FromPolygons([v.co for v in obj.data.vertices],[tuple(f.vertices) for f in obj.data.polygons])


def _tile_ribs(p,t,col,mats):
    surfaces=[F._Surface(),F._Surface()];a=t['outer_side_m']/2;stop=1-t['inner_side_m']/t['outer_side_m']
    def point(side,u,f):
        x,y=(u,-1) if side==0 else (1,u) if side==1 else (-u,1) if side==2 else (-1,-u)
        return (a*x*(1-stop*f),a*y*(1-stop*f),t['eave_z_m']+(t['top_z_m']-t['eave_z_m'])*f**t['curve_power']+
                t['corner_lift_m']*abs(u)**8*(1-f)**3+.003)
    for side in range(4):
        for i in range(12):
            u=-1+2*(i+.5)/12
            for index,lo,hi in [(0,.078,.96 if t['inner_side_m'] else .86),(1,.012,.067)]:
                F._tube(surfaces[index],[point(side,u,lo+(hi-lo)*j/18) for j in range(19)],.022,8)
    out=[]
    for index,s in enumerate(surfaces):
        material=mats[p['material_scheme']['roof_main' if index==0 else 'roof_edge']]
        obj=F._object('V16_'+p['building_id']+'_tile_ribs_'+str(t['tier_index'])+'_'+str(index),
            F._new_mesh('V16_pyramid_tile_ribs',s.vertices,s.faces,material),col,'roof_tile_ribs')
        obj['roof_tier_index']=t['tier_index'];obj['intentionally_intersecting_detail']=True
        obj['tile_count_status']='Unmeasured grouped tile-line study, not individual historical tile count';out.append(obj)
    return out


def build_pavilion(profile,collection,materials=None,mesh_cache=None):
    p=profile;rings=_validate(p);d=p['dimensions'];ident=p['building_id']
    mats=R.restoration_materials() if materials is None else dict(materials)
    cache={} if mesh_cache is None else mesh_cache
    col=F.ensure_collection('V16_'+ident,collection);root=bpy.data.objects.new('V16_'+ident+'_root',None);col.objects.link(root)
    root.location=p['anchor'];root.rotation_euler.z=p['rotation_z_rad']
    objects=[];components={};openings=[];contact=[]
    def add(o,role):
        objects.append(o);components.setdefault(role,[]).append(o);o['semantic_role']=role;return o
    def box(name,c,sz,mat,role):return add(F.box('V16_'+ident+'_'+name,c,sz,mats[mat],col,cache,role),role)
    s=F._Surface()
    for tri in F._triangulate_rings(rings):s.face([(x,y,d['floor_z_m']) for x,y in tri])
    F._volume_from_top(s,d['slab_bottom_z_m'])
    slab=add(F._object('V16_'+ident+'_source_reference_slab',F._new_mesh('V16_'+ident+'_slab',s.vertices,s.faces,mats['white_stone']),col,'source_reference_slab'),'source_reference_slab')
    slab['reference_floor_only']=True;slab['not_measured_platform']=True
    if ident=='linxiting':
        b=d['bridge'];cutter=M.make_vault_cutter('TEMP_V16_Linxi_single_arch',b['span_m'],b['spring_z_m'],b['crown_z_m'],
            b['tunnel_depth_m'],b['center_y_m'],col,bottom_z=d['slab_bottom_z_m']-.2,center_y=0)
        cutter.rotation_euler.z=math.pi/2;M._apply_cutter(slab,cutter,'V16_Linxi_true_arch')
        openings.append({'id':'linxiting_single_bridge_arch','type':'arched_water_tunnel','wall':slab.name,'normal_axis':'X',
                         'span_axis':'Y','center_local':[0,b['center_y_m'],(d['slab_bottom_z_m']+b['spring_z_m'])/2],
                         'span_m':b['span_m'],'spring_z_m':b['spring_z_m'],'crown_z_m':b['crown_z_m'],
                         'dimension_status':'unmeasured_study','method':'Exact Boolean; cutter removed','pool_geometry':'unbuilt_unknown_boundary'})
        slab['actual_bridge_arch_count']=1
    roofs=[]
    for tier in p['roof_tiers']:
        roof=add(_roof(p,tier,col,mats),'roof');roofs.append({'object':roof.name,**tier,'roof_type':'sijiao_zanjian','annular':bool(tier['inner_side_m'])})
        for obj in _tile_ribs(p,tier,col,mats):add(obj,'roof_tile_ribs')
    lowtree=_tree(components['roof'][0]);side=d['body_side_m'];floor=d['floor_z_m'];base_h=d['column_base_height_m']
    xs=[-side/2+side*i/3 for i in range(4)]
    grid=sorted(set([(x,y) for x in xs for y in (-side/2,side/2)]+[(x,y) for y in xs for x in (-side/2,side/2)]))
    def column(x,y,top,label,role='column'):
        base=add(F.column('V16_'+ident+'_'+label+'_base',(x,y,floor+base_h/2),d['column_base_radius_m'],base_h,mats['white_stone'],col,cache,20),'column_base')
        z0=floor+base_h;o=add(F.column('V16_'+ident+'_'+label,(x,y,(z0+top)/2),d['column_radius_m'],top-z0,mats['red'],col,cache,24),role)
        base['support_object']=slab.name;o['support_object']=base.name;o['study_column_axis']=[x,y];return o
    for i,(x,y) in enumerate(grid):column(x,y,d['column_top_z_m'],'perimeter_'+str(i),'column' if ident=='huifengting' else 'pilaster')
    def beams(span,top,label):
        bw=d['beam_width_m'];h=d['beam_height_m']
        for sign in (-1,1):
            box(label+'_x',(0,sign*span/2,top-h/2),(span+bw,bw,h),'painted_beam','beam')
            box(label+'_y',(sign*span/2,0,top-h/2),(bw,span+bw,h),'painted_beam','beam')
    beamtop=d['column_top_z_m']+d['beam_height_m'];beams(side,beamtop,'perimeter_beam')
    for i,(x,y) in enumerate(grid):
        hit=lowtree.ray_cast(Vector((x,y,beamtop-.01)),Vector((0,0,1)),20)[0]
        if hit is None or hit.z<=beamtop:raise ValueError('actual lower roof does not meet support riser')
        riser=box('roof_riser_'+str(i),(x,y,(beamtop+hit.z)/2),(d['beam_width_m']-.001,d['beam_width_m']-.001,hit.z-beamtop+.0002),'painted_beam','roof_support_riser')
        contact.append({'object':riser.name,'roof':components['roof'][0].name,'point_local':list(hit),'construction':'unmeasured plain riser, not measured dougong'})
    if ident=='huifengting':
        b=d['upper_band'];span=b['side_m'];h=d['beam_height_m']
        for i,(x,y) in enumerate(((-span/2,-span/2),(span/2,-span/2),(span/2,span/2),(-span/2,span/2))):
            column(x,y,b['bottom_z_m']-h,'inner_support_'+str(i),'upper_support_column')
        beams(span,b['bottom_z_m'],'upper_band_support')
        tree=_tree(components['roof'][1]);t=b['wall_thickness_m']
        for wall,x,y,ww,dd in [('south',0,-span/2,span+t,t),('north',0,span/2,span+t,t),('east',span/2,0,t,span+t),('west',-span/2,0,t,span+t)]:
            hits=[]
            for i in range(25):
                q=-.5+i/24
                for sign in (-.5,.5):
                    xx,yy=(x+ww*q,y+t*sign) if wall in ('south','north') else (x+t*sign,y+dd*q)
                    hit=tree.ray_cast(Vector((xx,yy,b['bottom_z_m'])),Vector((0,0,1)),20)[0]
                    if hit is None:raise ValueError('upper band exceeds roof')
                    hits.append(hit.z)
            top=max(hits)+.001
            if max(hits)-min(hits)+.002>=p['roof_tiers'][1]['skin_thickness_m']:raise ValueError('band would pierce upper tile surface')
            o=box('upper_band_'+wall,(x,y,(b['bottom_z_m']+top)/2),(ww,dd,top-b['bottom_z_m']),'dark_wood','upper_band_wall')
            o['occupied_floor']=False;o['wall_side']=wall;o['not_measured_hidden_construction']=True
    else:
        t=d['wall_thickness_m'];top=d['column_top_z_m']+d['beam_height_m'];walls={}
        for wall,x,y,ww,dd in [('south',0,-side/2,side+t,t),('north',0,side/2,side+t,t),('east',side/2,0,t,side+t),('west',-side/2,0,t,side+t)]:
            o=box('wall_'+wall,(x,y,(floor+top)/2),(ww,dd,top-floor),'red','wall');walls[wall]=o;o['wall_side']=wall
            for bay in range(3):
                kind='door' if bay==1 else 'window';across=-side/2+side*(bay+.5)/3
                bottom=floor if kind=='door' else floor+d['window_sill_m'];height=d[kind+'_height_m'];width=side/3*.78
                center=[across,y,bottom+height/2] if wall in ('south','north') else [x,across,bottom+height/2]
                axis='Y' if wall in ('south','north') else 'X';oid=ident+'_'+wall+'_'+str(bay)
                row={'id':oid,'type':kind,'destination':'unmeasured_study_interior','center':center,'width':width,'height':height,'depth':t+.5,'normal_axis':axis}
                record=F.cut_opening(o,row,col,None);leaves=[];frames=[]
                count=4 if kind=='door' else 1
                for n in range(count):
                    c=list(center);c[0 if axis=='Y' else 1]+=-width/2+width/count*(n+.5)
                    sz=(width/count*.98,.055,height*.98) if axis=='Y' else (.055,width/count*.98,height*.98)
                    leaf=box(oid+'_leaf_'+str(n),c,sz,'dark_wood',kind+'_leaf' if kind=='door' else 'window_infill_proxy')
                    leaf['opening_id']=oid;leaf['lattice_geometry']='category reference only; exact lattice unbuilt';leaves.append(leaf.name)
                for sign in (-1,1):
                    c=list(center);c[0 if axis=='Y' else 1]+=sign*(width+.07)/2
                    sz=(.07,.11,height) if axis=='Y' else (.11,.07,height)
                    frames.append(box(oid+'_jamb',c,sz,'red','opening_frame').name)
                record.update({'wall':o.name,'wall_side':wall,'bay_index':bay,'kind':kind,'center_local':center,'clear_width_m':width,
                    'clear_height_m':height,'bottom_z_m':bottom,'leaf_count':4 if kind=='door' else None,'leaf_reference_names':leaves,
                    'frame_names':frames,'normal_axis':axis,'dimension_status':'unmeasured_study','door_pose':'closed independent leaves'})
                openings.append(record)
        for sign in (-1,1):
            x=sign*(side/2+.06);span=side/3*.78
            for y in (-span/2,span/2):box('waterdoor_guard_post',(x,y,floor+.43),(.07,.07,.86),'dark_wood','wood_guardrail')
            box('waterdoor_guard_rail',(x,0,floor+.81),(.07,span+.07,.09),'dark_wood','wood_guardrail')
    if ident=='huifengting':
        radius=side/2+.34;stations=[-radius+2*radius*i/3 for i in range(4)];post=.12
        positions=set([(x,y) for x in stations for y in (-radius,radius)]+[(x,y) for y in stations for x in (-radius,radius)])
        for x,y in sorted(positions):box('stone_balustrade_post',(x,y,floor+.46),(post,post,.92),'white_stone','stone_railing_post')
        for axis in ('X','Y'):
            for sign in (-1,1):
                for i,(a,b) in enumerate(zip(stations,stations[1:])):
                    if axis=='X' and sign==-1 and i==1:continue
                    c=((a+b)/2,sign*radius,floor+.43) if axis=='X' else (sign*radius,(a+b)/2,floor+.43)
                    dims=(b-a-post,.10,.54) if axis=='X' else (.10,b-a-post,.54)
                    o=box('unmeasured_stone_panel',c,dims,'white_stone','stone_railing_panel')
                    o['carving_geometry']='Cloud carving unbuilt; plain documented material/category reference'
        stair_sides=(-1,)
    else:stair_sides=(-1,1)
    # Additive ground-supported step studies. Sizes and locations are not surveyed.
    for sign in stair_sides:
        edge=max(sign*y for x,y in rings[0]);n=5 if ident=='huifengting' else 6
        for i in range(n):
            height=floor*(n-i)/n
            o=box('unmeasured_steps',(0,sign*(edge-.06+.32*(i+.5)),height/2),(1.75,.34,height),'white_stone','exterior_step')
            o['support_plane_z_m']=0;o['placement_status']='unmeasured apron reference outside original source outline where necessary'
    # The visible crown is a simple continuous unmeasured silhouette proxy.
    apex=p['roof_tiers'][-1]['top_z_m'];fs=F._Surface();n=24;r=.14;hh=.42
    ring=[(r*math.cos(2*math.pi*i/n),r*math.sin(2*math.pi*i/n),apex+.06) for i in range(n)]
    fs.face(list(reversed([(x,y,apex-.002) for x,y,z in ring])))
    for i,a in enumerate(ring):
        b=ring[(i+1)%n];fs.face([(a[0],a[1],apex-.002),(b[0],b[1],apex-.002),b,a]);fs.face([a,b,(0,0,apex+hh)])
    add(F._object('V16_'+ident+'_unmeasured_finial',F._new_mesh('V16_'+ident+'_finial',fs.vertices,fs.faces,mats[p['material_scheme']['roof_edge']]),col,'finial'),'finial')
    serialized=json.dumps(p,ensure_ascii=False,allow_nan=False)
    for o in [root]+objects:
        if o!=root:o.parent=root
        o['restoration_v16_building_id']=ident;o['source_reference_part_id']=p['source_part_id'];o['absolute_accuracy_claim']=False
        o['human_approval']='pending';o['third_party_cost']=0;o['profile_json']=serialized
    root['occupied_storeys']='unknown';root['modeled_upper_occupied_floors']=0
    root['unbuilt_features']=json.dumps(p['unbuilt_features'],ensure_ascii=False)
    bpy.context.view_layer.update()
    return {'root':root,'objects':objects,'components':components,'openings':openings,'roofs':roofs,
            'reference_floor':slab.name,'roof_contacts':contact,'profile':p,'unbuilt_features':p['unbuilt_features']}
