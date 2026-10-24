"""Complete WORLD triangle domains in one reversible common-origin frame.

No local readout substitution, coordinate rounding, repair, snapping, or changed
limits. Domain geometries stay in the centered frame; do not translate them back.
"""
import copy,hashlib,importlib.util,math
from pathlib import Path
from shapely.geometry import Polygon,shape
from shapely.validation import explain_validity
HERE=Path(__file__).resolve().parent
CORE_SHA='3f2e4464d1983777b50a96a952c00d36eff9ddb9ecf99b5f506d9293e730c535'
p=HERE/'check_source79_display.py'
if hashlib.sha256(p.read_bytes()).hexdigest()!=CORE_SHA:raise AssertionError('frozen domain core changed')
s=importlib.util.spec_from_file_location('source79_domain_frozen_v1',p);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)

def valid(g,label):
 M.require(g.is_valid,label+' invalid complete geometry: '+explain_validity(g))
 return g

def normalize(rows,source,anchor):
 M.require(len(anchor)==3 and all(type(v)in(int,float)and math.isfinite(v)for v in anchor),'explicit finite common source anchor required')
 ox,oy=anchor[:2];out=[];audit=[];maxerr=0.;cross_changed=0
 def xy(x,y):
  nonlocal maxerr
  a,b=x-ox,y-oy;err=max(abs((a+ox)-x),abs((b+oy)-y));maxerr=max(maxerr,err)
  M.require(err==0,'common-origin translation is not exactly reversible')
  return a,b
 rings=[]
 for ring in [source.exterior,*source.interiors]:rings.append([xy(x,y)for x,y in ring.coords])
 pp=valid(Polygon(rings[0],rings[1:]),'complete centered source')
 for row in rows:
  rr=dict(row);vv=row['vertices_world'];rr['vertices_world']=[[*xy(v[0],v[1]),v[2]]for v in vv]
  M.tri_rows(rr)
  for t,mi in row['triangles_with_material_index']:
   a,b,c=[vv[i]for i in t];aa,bb,cc=[rr['vertices_world'][i]for i in t]
   before=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);after=(bb[0]-aa[0])*(cc[1]-aa[1])-(bb[1]-aa[1])*(cc[0]-aa[0])
   cross_changed+=before!=after
   M.require(before==after,'triangle XY cross changed under common-origin translation')
  g=valid(M.projected(rr),'centered mesh '+row['name'])
  audit.append({'name':row['name'],'vertices':len(vv),'complete_triangles':len(row['triangles_with_material_index']),'complete_projection_type':g.geom_type,'complete_projection_valid':True})
  out.append(rr)
 return out,pp,{'coordinate_frame':'actual_WORLD_minus_common_source_anchor','common_origin_world':list(anchor),'z_unchanged':True,'only_projection_domains_translated':True,'uses_actual_WORLD_vertices':True,'uses_exported_local_vertices':False,'rounding_snapping_geometry_repair':False,'geometry_translated_back_to_WORLD':False,'exact_roundtrip_max_error_m':maxerr,'triangle_XY_cross_changed_count':cross_changed,'complete_source_ring_count':len(rings),'all_actual_mesh_complete_projection_validity':audit,'raw_WORLD_vertices_and_triangle_indices_retained_in_SHA_bound_actual_export':True}

def all_serialized_geometries_valid(value):
 count=0
 def walk(v):
  nonlocal count
  if isinstance(v,dict):
   if 'geometry'in v and isinstance(v['geometry'],dict):valid(shape(v['geometry']),'complete serialized domain');count+=1
   for x in v.values():walk(x)
  elif isinstance(v,(list,tuple)):
   for x in v:walk(x)
 walk(value);return count

def analyze_geometry(rows,source,floors,roofs,remainders,anchor):
 rr,pp,audit=normalize(rows,source,anchor)
 analysis=M.analyze_geometry(rr,pp,floors,roofs,remainders)
 audit['complete_serialized_geometry_count_validated']=all_serialized_geometries_valid(analysis)
 analysis['projection_frame_and_full_validity']=audit
 return analysis

def private_geometry_negatives(rows,source,floors,roofs,anchor):
 rr,pp,audit=normalize(rows,source,anchor)
 return M.private_geometry_negatives(rr,pp,floors,roofs)
