"""Independent CPU complete domains/contact planes from exported actual WORLD.

No ideal roof reconstruction. Every support cap's entire upward triangle domain
must lie on real downward roof triangles; whole bases must meet actual supports.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EPS=2e-4
AREA_EPS=1e-7


def require(value,message):
    if not value:raise AssertionError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_rows(doc,geometry):
    p=doc['profile'];c,s=math.cos(p['rotation_z_rad']),math.sin(p['rotation_z_rad']);a=p['anchor'];out={}
    for name,row in geometry.items():
        out[name]={**row,'vertices':[(c*(v[0]-a[0])+s*(v[1]-a[1]),-s*(v[0]-a[0])+c*(v[1]-a[1]),v[2]-a[2]) for v in row['vertices']]}
    return out


def triangles(row,direction=None,materials=None):
    out=[]
    for tri,mi in zip(row['triangles'],row['triangle_materials']):
        if materials is not None and mi not in materials:continue
        a,b,c=[row['vertices'][i] for i in tri];u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        if direction=='up' and n[2]<=1e-12 or direction=='down' and n[2]>=-1e-12:continue
        poly=Polygon([a[:2],b[:2],c[:2]])
        if poly.area<=1e-13:continue
        out.append((poly,a,n))
    return out


def domain(row,direction=None,materials=None):
    items=triangles(row,direction,materials);require(items,'Empty complete projected domain')
    return unary_union([i[0] for i in items])


def compare_domain(a,b,label):
    require(a.geom_type=='Polygon' and b.geom_type=='Polygon','Disconnected '+label)
    require(a.difference(b.buffer(EPS)).area<=AREA_EPS and b.difference(a.buffer(EPS)).area<=AREA_EPS,'Complete domain differs: '+label)
    require(a.boundary.hausdorff_distance(b.boundary)<EPS,'Complete boundary differs: '+label)


def contacts(geometry,records):
    cache={};evidence=[]
    for row in records:
        support,roof=geometry[row['object']],geometry[row['roof']]
        if row['roof'] not in cache:
            down=triangles(roof,'down');cache[row['roof']]=(down,STRtree([t[0] for t in down]))
        down,tree=cache[row['roof']];tops=triangles(support,'up');max_error=0;area=0
        for poly,a,n in tops:
            good=[]
            for index in tree.query(poly):
                other,b,m=down[int(index)];cut=poly.intersection(other)
                if cut.area<=1e-13:continue
                pieces=[cut] if cut.geom_type=='Polygon' else [g for g in getattr(cut,'geoms',[]) if g.geom_type=='Polygon']
                err=0
                for piece in pieces:
                    for x,y in piece.exterior.coords:
                        za=a[2]-(n[0]*(x-a[0])+n[1]*(y-a[1]))/n[2]
                        zb=b[2]-(m[0]*(x-b[0])+m[1]*(y-b[1]))/m[2]
                        err=max(err,abs(za-zb))
                if err<=EPS:good.append(cut)
                max_error=max(max_error,err)
            matched=unary_union(good)
            require(poly.difference(matched).area<=AREA_EPS,'Complete contact cap leaves actual roof underside')
            area+=poly.area
        require(abs(min(v[2] for v in support['vertices'])-row['bottom_z_m'])<EPS,'Actual continuous support bottom differs')
        compare_domain(domain(support,'up'),domain(support,'down'),'support whole top and bottom domain')
        evidence.append({'object':row['object'],'actual_complete_top_area_m2':area,'max_coplanar_error_m':max_error})
    return evidence


def reference_chain(geometry,profile,components):
    support=geometry[components['source_support_reference'][0]]
    floor=geometry[components['source_reference_floor'][0]]
    sz=(min(v[2] for v in support['vertices']),max(v[2] for v in support['vertices']))
    fz=(min(v[2] for v in floor['vertices']),max(v[2] for v in floor['vertices']))
    require(abs(sz[0]-profile['source_support_bottom_z_m'])<EPS and abs(sz[1]-profile['study']['source_support_top_z_m'])<EPS,'Actual source support Z differs')
    require(abs(fz[0]-profile['study']['source_support_top_z_m'])<EPS and abs(fz[1]-profile['study']['reference_floor_top_z_m'])<EPS,'Actual reference floor Z differs')
    require(abs(sz[1]-fz[0])<EPS,'Actual source support does not meet whole reference floor')
    for mesh,zrange in ((support,sz),(floor,fz)):
        for direction,z in (('down',zrange[0]),('up',zrange[1])):
            faces=triangles(mesh,direction);require(faces,'Missing complete reference contact plane')
            for poly,a,n in faces:
                require(abs(a[2]-z)<EPS and math.hypot(n[0],n[1])/abs(n[2])<EPS,'Actual reference end surface is not the complete horizontal contact plane')
        compare_domain(domain(mesh,'up'),domain(mesh,'down'),'complete reference top/bottom contact plane')
    return {'source_support_actual_Z_m':sz,'reference_floor_actual_Z_m':fz,'actual_vertical_gap_m':abs(sz[1]-fz[0])}


def check(doc,geometry,extras=None):
    g=local_rows(doc,geometry);extra=local_rows(doc,extras or {});p=doc['profile'];cp=doc['components'];source=Polygon(p['source_polygon_local'],p['source_holes_local'])
    require(len(g)==43 and len(cp['column'])==5 and len(cp['roof_bearing_cap'])==5,'Actual five-column/support inventory differs')
    for role in ('source_reference_floor','source_support_reference'):
        require(len(cp[role])==1,'One full-source reference required')
        actual_reference_domain=domain(g[cp[role][0]])
        compare_domain(actual_reference_domain,source,role)
        require(len(actual_reference_domain.exterior.coords)-1==7,'Actual reference outer is not all seven source vertices')
    ground_chain=reference_chain(g,p,cp)
    for row in g.values():require(domain(row).difference(source.buffer(EPS)).area<=AREA_EPS,'Actual new mesh leaves complete seven-source domain')
    roofs=sorted(cp['roof'],key=lambda name:g[name]['roof_tier_index']);topdomains=[]
    for index,name in enumerate(roofs):
        row=g[name];top=domain(row,materials={0,1});full=domain(row)
        require(top.geom_type=='Polygon' and len(top.interiors)==(1 if index==0 else 0),'Actual skin true annular/full domain differs')
        require(top.symmetric_difference(full).area<=AREA_EPS,'Actual skin filled its hole or leaves top domain')
        scheme=p['roof_profile']['roof_tiers'][index]['material_scheme'];keys=[scheme[k] for k in ('main','edge','under')]
        require(row['material_keys']==keys,'Actual roof material allocation differs')
        for key,rgba,shader in zip(keys,row['material_rgba'],row['shader_rgba']):
            require(max(abs(a-b) for a,b in zip(rgba,doc['palette'][key]))<1e-6,'Actual diffuse roof palette differs')
            require(max(abs(a-b) for a,b in zip(shader,doc['palette'][key]))<1e-6,'Actual shader roof palette differs')
        topdomains.append(top)
    hole=Polygon(topdomains[0].interiors[0]);floor=g[cp['source_reference_floor'][0]];floor_top=max(v[2] for v in floor['vertices'])
    for name in cp['column']:
        column=g[name];projected=domain(column)
        require(hole.buffer(EPS).covers(projected),'Actual continuous column pierces lower roof skin')
        require(abs(min(v[2] for v in column['vertices'])-floor_top)<EPS,'Actual continuous column is lifted from reference floor')
        require(domain(floor).buffer(EPS).covers(domain(column,'down')),'Whole column foot leaves reference floor')
    for name in cp['roof_bearing_cap']:
        require(topdomains[0].buffer(EPS).covers(domain(g[name])),'Lower cap crosses actual annular hole or eave')
    contact_result=contacts(g,doc['contacts'])
    for link in doc['beam_links']:
        cap,beam,column=[g[link[k]] for k in ('bearing','beam','column')]
        require(domain(beam).buffer(EPS).covers(domain(cap,'down')),'Whole cap base leaves its actual radial beam')
        require(abs(min(v[2] for v in cap['vertices'])-max(v[2] for v in beam['vertices']))<EPS,'Actual cap floats above radial beam')
        require(domain(beam).intersection(domain(column)).area>1e-3,'Actual radial beam disconnected from continuous column')
    lo=p['roof_profile']['roof_tiers'][0]['eave_z_m'];hi=p['roof_profile']['roof_tiers'][0]['top_z_m']
    roof_names={name for role in ('roof','ridge','tile_ribs') for name in cp[role]}
    for name,row in {**g,**extra}.items():
        if name in roof_names:continue
        for poly,a,n in triangles(row):
            length=math.sqrt(sum(x*x for x in n))
            require(not(abs(n[2])/length>.99999 and lo+EPS<a[2]<hi-EPS),'Actual fake interior horizontal plate')
    return {'actual_columns':5,'actual_closed_source_floor_vertices':7,'actual_contact_domains':contact_result,
            'actual_lower_hole_area_m2':hole.area,'actual_floor_and_support_complete_seven_source_domain':True,
            'all_actual_new_meshes_source_contained':True,'no_intermediate_floor_plate':True,'ground_reference_chain':ground_chain}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--readout',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    readout=args.readout.resolve();output=args.output.resolve();require(readout.is_relative_to(HERE) and output.parent==readout.parent and not output.exists(),'New local actual CPU output required')
    doc=json.loads(readout.read_text());require(doc['schema']=='v19-biluo-pavilion-actual-WORLD/1','Actual readout schema differs')
    for rel,pin in doc['input_files_sha256'].items():require(sha(ROOT/rel)==pin,'Frozen actual fixture input drift: '+rel)
    baseline=check(doc,doc['geometry']);negatives=[]
    reasons={'NEG-LIFT-COLUMN':'lifted','NEG-WRONG-MATERIAL':'material allocation','NEG-WRONG-PHASE':'roof underside','NEG-FLAT-CAP':'roof underside','NEG-FAKE-FLOOR':'horizontal plate'}
    for mutant in doc['real_geometry_negative_controls']:
        geometry={**doc['geometry'],**mutant['changed_geometry']}
        try:check(doc,geometry,mutant['additional_geometry'])
        except AssertionError as exc:
            require(reasons[mutant['id']] in str(exc),'Actual mutant rejected for unrelated reason: '+str(exc))
            negatives.append({'id':mutant['id'],'actual_exported_geometry_rejected':True,'reason':str(exc)})
        else:raise AssertionError('Actual exported mutant accepted')
    require(set(reasons)=={r['id'] for r in negatives},'All five actual negatives required')
    require(check(doc,doc['geometry'])==baseline,'Baseline mutated by checker')
    report={'schema':'v19-biluo-actual-full-domains-and-contacts/1','summary':{'passed':1+len(negatives),'failed':0},'baseline':baseline,'negative_controls':negatives,
            'actual_readout_sha256':sha(readout),'checker_sha256':sha(__file__),'EPS_m':EPS,'AREA_EPS_m2':AREA_EPS,
            'source_support_is_not_measured_mountain':True,'ideal_roof_reconstruction_used':False,'Blender_started':False,'native_saved':False,'third_party_cost':0,'human_approval':'pending','whole_city_complete':False}
    with output.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'summary':report['summary'],'sha256':sha(output)}))


if __name__=='__main__':main()
