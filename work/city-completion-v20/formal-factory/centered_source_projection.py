"""Reversible common XY translation for full actual-WORLD source projection.

No snap, repair, rounding, buffer normalization, mesh edits or triangle removal.
Projection/containment functions and their100um tolerance remain frozen.
"""
import math

from shapely.affinity import translate
from shapely.geometry import Polygon


def require(ok,message):
    if not ok:raise AssertionError(message)


def cross(v,t):
    a,b,c=[v[i]for i in t]
    return(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def centered_domains(geometry,source,anchor,full_triangle_manifest,projection,contained):
    require(len(anchor)>=2 and all(type(x)in(int,float)and math.isfinite(x)for x in anchor[:2]),'finite nonbool common anchor required')
    require(source.is_valid and not source.is_empty,'complete original source domain invalid')
    require(geometry and set(geometry)==set(full_triangle_manifest),'complete actual object/triangle manifest differs')
    ox,oy=anchor[:2];centered={};count=positive=degenerate=0
    for name,row in geometry.items():
        require(row['hidden']is False,'actual exterior geometry hidden: '+name)
        require(row['triangles']==full_triangle_manifest[name],'missing/reordered actual triangle indices: '+name)
        original=row['vertices'];near=[]
        for p in original:
            require(len(p)==3 and all(type(x)in(int,float)and math.isfinite(x)for x in p),'invalid actual WORLD vertex')
            q=[p[0]-ox,p[1]-oy,p[2]]
            require(q[0]+ox==p[0]and q[1]+oy==p[1],'WORLD translation not exactly reversible')
            near.append(q)
        for t in row['triangles']:
            require(len(t)==3 and all(type(i)is int and 0<=i<len(original)for i in t),'invalid actual triangle')
            before=cross(original,t);after=cross(near,t)
            require(before==after,'actual triangle XY cross changed under common translation')
            a=Polygon([(original[i][0],original[i][1])for i in t]).area
            b=Polygon([(near[i][0],near[i][1])for i in t]).area
            require((a>1e-12)==(b>1e-12),'positive projected triangle selection changed')
            count+=1;positive+=a>1e-12;degenerate+=a<=1e-12
        centered[name]={**row,'vertices':near}
    # Translate the complete Polygon, including every hole. Never translate a
    # GEOS union back to WORLD: that can recreate invalid tiny components.
    rings=[list(source.exterior.coords)]+[list(r.coords)for r in source.interiors]
    for ring in rings:
        for x,y in ring:require((x-ox)+ox==x and(y-oy)+oy==y,'source translation not exactly reversible')
    near_source=translate(source,xoff=-ox,yoff=-oy)
    actual=projection(centered,list(centered))
    result=contained(actual,near_source,'all complete actual WORLD triangles in common reversible source frame')
    return {**result,'projection_computation_frame':'actual WORLD and complete source both translated by minus original anchorXY',
        'origin_WORLD':[ox,oy],'objects':len(geometry),'all_input_triangle_count':count,
        'positive_area_triangle_count_same':positive,'zero_or_below_original_1e_12_projected_area_count_same':degenerate,
        'all_original_triangle_indices_retained':True,'every_actual_WORLD_and_source_point_exactly_reversible':True,
        'every_triangle_XY_cross_exactly_unchanged':True,'positive_area_selection_unchanged':True,
        'source_holes_preserved':len(source.interiors),'round_snap_repair_or_mesh_change':False,
        '2D_union_translated_back_to_WORLD':False,'support_roof_contact_void_coordinates':'original actual WORLD, untouched',
        'line_point_projection_scope':'All input triangles retained; original frozen positive-area selection is unchanged. Separate display qualification must also preserve/guard projected lines and points.'}
