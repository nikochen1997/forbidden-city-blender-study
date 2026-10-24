"""Independent CPU full-domain supports of the three formal run03 bodies.

Reads actual WORLD triangles only. Frozen V18 supports() is reused as a pure
hall-cap primitive, without invoking its Nansansuo schema or identity contract.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import traceback

from shapely.geometry import LineString, Point
from shapely.ops import polygonize, unary_union

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
READOUT=ROOT/'work/restoration-v19/formal-factory-run-03/actual-world-geometry.json'
READOUT_SHA='da5c38ed9f7fc502095726b27a6c58f8a32d09465e02519d4c4ba3bce6bcf466'
HELPER=ROOT/'work/restoration-v18/module-qa/check_actual_exterior_supports.py'
HELPER_SHA='566fc03c4044a87db6a45016219ea023adbf7ea240fd4b6b36c4097b06a194f7'
XY_EPS=1e-4
PLANAR_Z_EPS=1e-4
ROOF_AFFINE_Z_EPS=2e-4


def require(value,message):
    if not value:raise AssertionError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


require(sha(HELPER)==HELPER_SHA,'Frozen hall support helper drift')
H=load('frozen_V18_pure_hall_cap_supports',HELPER)
G=H.G
require(G.P.EPS==XY_EPS and G.EPS==PLANAR_Z_EPS,'Frozen 100um support tolerance differs')


def actual_mesh(row):
    props=json.loads(row['props_json'])
    return {'vertices':row['vertices_world'],'triangles':[t[0] for t in row['triangles_with_material_index']],
            **{k:props[k] for k in ('support_object',) if k in props}}


def hall_input(doc,ident):
    building=next(b for b in doc['buildings'] if b['building_id']==ident)
    require(ident in ('juanqinzhai','yucuixuan'),'Exact V19 hall identity required')
    rows={r['name']:r for r in doc['objects']};names=building['objects']
    require(len(names)==len(set(names)) and all(n in rows for n in names),'Complete actual hall population omitted')
    return {'id':ident,'profile':building['profile'],'components':building['components'],
            'reference_floor':building['reference_floor'],'geometry':{n:actual_mesh(rows[n]) for n in names}}


def check_hall(doc,ident):
    building=hall_input(doc,ident)
    # No H.check(), H.IDS or Nansansuo identity/schema is invoked.
    evidence=H.supports(building)
    return {'building_id':ident,'actual_meshes':len(building['geometry']),
            'full_source_floor_bases_column_bottom_top_and_bearing_bottom':evidence,
            'planar_XY_tolerance_m':XY_EPS,'planar_Z_tolerance_m':PLANAR_Z_EPS,
            'roof_3D_contacts_scope':'root independent actual roof contact report, affine Z200um'}


def closure_bottoms(doc):
    building=hall_input(doc,'juanqinzhai');rows={r['name']:r for r in doc['objects']};cp=building['components'];geometry=building['geometry']
    walls={json.loads(rows[n]['props_json'])['wall_side']:n for n in cp['wall']};out=[]
    require(len(cp['roof_closure_wall'])==4 and len(walls)==4,'Four actual new closures/walls required')
    for name in cp['roof_closure_wall']:
        props=json.loads(rows[name]['props_json']);wall=walls[props['wall_side']]
        require(props.get('caller_junction_adapter') is not None,'Actual V19 replacement marker absent')
        cap,z,full=G.full_cap(geometry[name],False)
        result=G.supported(cap,z,[geometry[wall]],True,'actual new closure full bottom on original wall top')
        wall_z=G.zrange(geometry[wall])[1];wall_top=G.horizontal(geometry[wall],wall_z,True)
        out.append({'closure':name,'wall':wall,'side':props['wall_side'],'actual_full_bottom_cap':full,
                    'actual_support':result,'raw_area_outside_wall_top_m2':cap.difference(wall_top).area,
                    'actual_Z_gap_m':abs(z-wall_z),'maximum_bottom_rim_vertex_outside_wall_diagnostic_m':max(Point(p).distance(wall_top) for p in cap.exterior.coords),'footprint_not_axis_sampled':True})
    return out


def horizontal_section(mesh,z):
    """Actual triangle/plane intersections; 1nm weld is numerical only."""
    segments=[]
    for tri in mesh['triangles']:
        vertices=[mesh['vertices'][i] for i in tri];points=[]
        for a,b in zip(vertices,vertices[1:]+vertices[:1]):
            da,db=a[2]-z,b[2]-z
            if abs(da)<1e-12:points.append(a[:2])
            if da*db<0:
                f=da/(da-db);points.append((a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1])))
        points=list(dict.fromkeys((round(p[0],9),round(p[1],9)) for p in points))
        if len(points)==2 and points[0]!=points[1]:segments.append(LineString(points))
    require(segments,'Actual closure section missing')
    polygons=list(polygonize(unary_union(segments)));require(polygons,'Actual triangle section is open')
    section=unary_union(polygons);require(section.is_valid and section.geom_type=='Polygon' and not section.interiors,'Actual closure section incomplete/holed')
    return section


def closure_corners(doc):
    building=hall_input(doc,'juanqinzhai');rows={r['name']:r for r in doc['objects']};geometry=building['geometry']
    byside={json.loads(rows[n]['props_json'])['wall_side']:n for n in building['components']['roof_closure_wall']}
    bottoms={s:G.full_cap(geometry[n],False) for s,n in byside.items()};z=max(v[1] for v in bottoms.values())+.01
    require(all(z<G.zrange(geometry[n])[1] for n in byside.values()),'Slice not inside all four actual closures')
    sections={s:horizontal_section(geometry[n],z) for s,n in byside.items()}
    for side in sections:G.P.compare_complete(sections[side],bottoms[side][0],'actual complete closure section vs complete bottom')
    evidence=[]
    for a,b in (('south','west'),('south','east'),('north','west'),('north','east')):
        overlap=sections[a].intersection(sections[b]);require(overlap.area>G.P.AREA_EPS,'Actual adjacent closure sections have no positive-area connection '+a+'/'+b)
        evidence.append({'sides':[a,b],'actual_section_Z_m':z,'actual_positive_overlap_area_m2':overlap.area,
                         'intersection_bounds_WORLD':list(overlap.bounds),'buffered_overlap_used':False,
                         'section_from_all_actual_triangle_plane_intersections':True})
    return evidence


def reject(fn,reason):
    try:fn()
    except AssertionError as exc:
        require(reason in str(exc),'Private mutant rejected for unrelated reason: '+str(exc))
        return {'same_checker_rejected':True,'reason':str(exc),'scope':'actual-export-derived private in-memory CPU mutant, not another Blender run'}
    raise AssertionError('Private actual-export-derived mutant accepted')


def shifted(doc,name,delta):
    clone=copy.deepcopy(doc);row=next(r for r in clone['objects'] if r['name']==name)
    for v in row['vertices_world']:
        for i,x in enumerate(delta):v[i]+=x
    return clone


def verify_inputs(doc):
    require(sha(READOUT)==READOUT_SHA,'Actual run03 readout drift')
    require(sha(HELPER)==HELPER_SHA,'Frozen helper drift')
    for relative,pin in doc['inputs_sha256'].items():require(sha(ROOT/relative)==pin,'Protected formal input drift: '+relative)


def main():
    doc=json.loads(READOUT.read_text());verify_inputs(doc);require(len(doc['objects'])==431,'Complete formal431 export required')
    require({b['building_id'] for b in doc['buildings']}=={'juanqinzhai','yucuixuan','fuwangge'},'Exact three formal identities required')
    support_inputs={str(Path(path).relative_to(ROOT)):sha(path) for path in (HELPER,H.SUPPORT,G.LEGACY,Path(H.K.__file__),Path(__file__),HERE/'fuwang_support_review.py')}
    checks=[]
    def case(ident,fn):
        try:
            evidence=fn();passed=not(isinstance(evidence,dict) and evidence.get('passed') is False)
            checks.append({'id':ident,'passed':passed,'evidence':evidence});print('PASS' if passed else 'FAIL',ident,flush=True)
        except Exception as exc:checks.append({'id':ident,'passed':False,'error':str(exc),'traceback':traceback.format_exc()});print('FAIL',ident,str(exc),flush=True)
    for ident in ('juanqinzhai','yucuixuan'):case(ident+'-FULL-SUPPORT',lambda ident=ident:check_hall(doc,ident))
    case('JUANQIN-FOUR-CLOSURE-FULL-BOTTOMS',lambda:closure_bottoms(doc))
    case('JUANQIN-FOUR-CORNER-SECTIONS',lambda:closure_corners(doc))
    fuwang=load('formal_fuwang_complete_supports',HERE/'fuwang_support_review.py')
    case('FUWANG-FORMAL-290-FULL-SUPPORT',lambda:fuwang.check_fuwang(doc))
    name=next(b for b in doc['buildings'] if b['building_id']=='juanqinzhai')['components']['column'][0]
    case('EXTRA-CPU-MOVE-COLUMN',lambda:reject(lambda:check_hall(shifted(doc,name,(.5,0,0)),'juanqinzhai'),'actual complete column bottom'))
    def Z_boundary():
        check_hall(shifted(doc,name,(0,0,.000099)),'juanqinzhai')
        over=reject(lambda:check_hall(shifted(doc,name,(0,0,.000101)),'juanqinzhai'),'actual support Z contact missing')
        return {'private_actual_column_lift99um_same_checker_passed':True,'lift101um_same_checker_rejected':over,'planar_Z_tolerance_m':PLANAR_Z_EPS}
    case('EXTRA-CPU-PLANAR-Z-BOUNDARY',Z_boundary)
    west=next(n for b in doc['buildings'] if b['building_id']=='juanqinzhai' for n in b['components']['roof_closure_wall'] if n.endswith('_west'))
    case('EXTRA-CPU-BREAK-CLOSURE-CORNER',lambda:reject(lambda:closure_corners(shifted(doc,west,(0,.5,0))),'no positive-area connection'))
    case('EXTRA-CPU-BLOCK-FUWANG-WALKWAY-HOLE',lambda:fuwang.negative_hole_control(doc))
    def final_guard():
        verify_inputs(doc)
        for relative,pin in support_inputs.items():require(sha(ROOT/relative)==pin,'Support helper input drift: '+relative)
        return {'all_run03_input_SHA_unchanged':True,'all_support_helper_SHA_unchanged':True,'old_modules_and_profiles_untouched':True}
    case('FINAL-INPUT-GUARD',final_guard)
    report={'schema':'v19-three-formal-body-complete-support-CPU/1','summary':{'passed':sum(r['passed'] for r in checks),'failed':sum(not r['passed'] for r in checks)},'checks':checks,
            'actual_run03_readout_sha256':sha(READOUT),'script_sha256':sha(__file__),'frozen_V18_support_helper_sha256':HELPER_SHA,
            'protected_formal_inputs_sha256':doc['inputs_sha256'],'support_audit_inputs_sha256':support_inputs,
            'XY_full_domain_tolerance_m':XY_EPS,'horizontal_support_Z_tolerance_m':PLANAR_Z_EPS,
            'roof_affine_Z_tolerance_m':ROOF_AFFINE_Z_EPS,'roof_3D_contact_report_is_separate':True,
            'all_shapes_use_full_actual_triangle_domain_unions':True,'new_Blender_run':False,'native_opened_saved':False,'third_party_cost':0,'human_approval':'pending','whole_city_complete':False}
    write(HERE/'formal-support-CPU-01.json',report)
    require(report['summary']['failed']==0,'Support review red; original report preserved')


if __name__=='__main__':main()
