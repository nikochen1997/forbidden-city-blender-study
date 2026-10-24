"""Root-only fresh Blender fixture. Never opens/saves a native or renders."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

import bpy
from mathutils import Vector

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.dont_write_bytecode=True


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
    if not value:raise AssertionError(message)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--binding-sha256',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);out=args.output_dir.resolve()
    require(out.parent==HERE and not out.exists() and not bpy.data.filepath,'Fresh private factory output required')
    binding=HERE/'fixture-bindings-v3.json';require(sha(binding)==args.binding_sha256,'Reviewed fixture binding SHA differs')
    prep=json.loads((HERE/'preparation-03.json').read_text());pins=dict(json.loads(binding.read_text())['input_files_sha256'])
    pins[str(binding.relative_to(ROOT))]=args.binding_sha256
    for name,pin in pins.items():require(sha(ROOT/name)==pin,'Frozen input drift: '+name)
    require(sha(HERE/'profile-v2.json')==prep['profile_sha256'],'Prepared profile changed')
    require(sha(HERE/'palette-v1.json')==prep['palette_sha256'],'Prepared palette changed')
    out.mkdir()
    sys.path.insert(0,str(ROOT/'work'));sys.path.insert(0,str(ROOT/'work/restoration-v19'))
    import forbidden_city_geometry as F
    B=load('biluo_local_support_module',HERE/'biluo_pavilion.py')
    C=load('independent_actual_audit',ROOT/'work/restoration-v16/saved-audit/saved_audit_core.py')
    profile=json.loads((HERE/'profile-v2.json').read_text());palette=json.loads((HERE/'palette-v1.json').read_text())['materials']
    materials={}
    for key,rgba in palette.items():
        m=bpy.data.materials.new('BILUO_'+key);m.use_nodes=True;m.diffuse_color=rgba
        m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=rgba;materials[key]=m
    collection=F.ensure_collection('V19_BILUO_SOURCEFIT_FACTORY')
    result=B.build_biluo_pavilion(profile,collection,materials,{})
    reader=C.MeshReader(bpy);checks=[];mutants=[]

    def export(objects):
        reader.refresh([o.name for o in objects]);rows={}
        for obj in objects:
            require(not obj.hide_viewport and not obj.hide_get() and obj.visible_get(),'Actual fixture object unexpectedly hidden; evaluated transforms cannot be trusted')
            m=reader.mesh(obj.name)
            rows[obj.name]={'vertices':[list(v) for v in m['vertices']],'triangles':[list(t) for t in m['triangles']],
                            'triangle_materials':m['triangle_materials'],'semantic_role':obj.get('semantic_role'),
                            'roof_tier_index':obj.get('roof_tier_index'),
                            'material_keys':[mat.name.removeprefix('BILUO_') for mat in obj.data.materials],
                            'material_rgba':[list(mat.diffuse_color) for mat in obj.data.materials],
                            'shader_rgba':[list(mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value) for mat in obj.data.materials]}
        return rows

    def case(ident,fn):
        try:evidence=fn();checks.append({'id':ident,'passed':True,'evidence':evidence});print('PASS',ident,flush=True)
        except Exception as exc:checks.append({'id':ident,'passed':False,'error':str(exc),'traceback':traceback.format_exc()});print('FAIL',ident,str(exc),flush=True)

    def contact():
        reader.refresh();errors=[]
        require(len(result['components']['column'])==5,'Five actual continuous columns required')
        for row in result['contacts']:
            m=reader.mesh(row['object']);roof=reader.mesh(row['roof'])
            up=set(i for tri in m['triangles'] if (m['vertices'][tri[1]]-m['vertices'][tri[0]]).cross(m['vertices'][tri[2]]-m['vertices'][tri[0]]).z>1e-10 for i in tri)
            error=max(roof['tree'].find_nearest(m['vertices'][i])[3] for i in up)
            require(error<2e-4,'Actual whole-cap vertices leave roof underside')
            require(abs(min(v.z for v in m['vertices'])-row['bottom_z_m'])<2e-4,'Actual support bottom height differs')
            errors.append(error)
        for obj in result['components']['column']:
            require(abs(min(v.z for v in reader.mesh(obj.name)['vertices'])-profile['study']['reference_floor_top_z_m'])<2e-4,'Continuous column leaves full source reference floor')
        return {'actual_columns':5,'actual_roof_contacts':len(errors),'max_top_vertex_distance_m':max(errors),'full_contact_face_domain_CPU_still_required':True}

    def materials_check():
        for obj in result['objects']:
            if obj.get('semantic_role')=='roof':
                tier=profile['roof_profile']['roof_tiers'][obj['roof_tier_index']]
                keys=[tier['material_scheme'][k] for k in ('main','edge','under')]
                require([m.name.removeprefix('BILUO_') for m in obj.data.materials]==keys,'Actual roof material allocation differs')
                for mat,key in zip(obj.data.materials,keys):require(max(abs(a-b) for a,b in zip(mat.diffuse_color,palette[key]))<1e-6,'Actual roof material color differs')
        return {'actual_lower_main':'peacock_blue','actual_upper_main':'jade_green','both_edges':'amethyst_purple'}

    def no_plate(objects=None):
        reader.refresh();lo=profile['roof_profile']['roof_tiers'][0]['eave_z_m'];hi=profile['roof_profile']['roof_tiers'][0]['top_z_m']
        roof_names={o.name for role in ('roof','ridge','tile_ribs') for o in result['components'][role]}
        for obj in result['objects'] if objects is None else objects:
            if obj.name in roof_names:continue
            m=reader.mesh(obj.name)
            for tri in m['triangles']:
                a,b,c=[m['vertices'][i] for i in tri];n=(b-a).cross(c-a)
                if n.length>1e-10 and abs(n.z)/n.length>.99999 and lo<a.z<hi:
                    raise AssertionError('Actual unexpected interior horizontal plate')
        return {'actual_horizontal_occupied_floor_plates_between_eaves':0}

    def topology():
        require(len(result['objects'])==43,'Actual assembly mesh inventory differs')
        return {o.name:C.closed_positive_topology(reader.mesh(o.name)) for o in result['objects']}

    def invalid():
        variants=[]
        for key,value in (('column_axis_radius_m',.95),('beam_width_m',.18),('column_radius_m',0)):
            p=copy.deepcopy(profile);p['study'][key]=value;variants.append(p)
        for key,value in (('reference_floor_count',2),('third_party_cost',True),('occupied_storeys',2)):
            p=copy.deepcopy(profile);p[key]=value;variants.append(p)
        baseline=tuple(tuple(sorted(x.name for x in group)) for group in (bpy.data.objects,bpy.data.meshes,bpy.data.materials,bpy.data.collections))
        for p in variants:
            try:B.build_biluo_pavilion(p,collection,materials,{})
            except (ValueError,KeyError):pass
            else:raise AssertionError('Invalid support profile accepted')
            require(tuple(tuple(sorted(x.name for x in group)) for group in (bpy.data.objects,bpy.data.meshes,bpy.data.materials,bpy.data.collections))==baseline,'Invalid preflight left geometry')
        return {'actual_rejected_invalid_profiles':len(variants),'zero_datablock_mutation':True}

    case('ACTUAL-01-CLOSED-POSITIVE',topology)
    case('ACTUAL-02-CONTINUOUS-COLUMNS-AND-CONTACT',contact)
    case('ACTUAL-03-MATERIAL',materials_check)
    case('ACTUAL-04-NO-PLATE',no_plate)
    case('ACTUAL-05-PREFLIGHT',invalid)
    baseline=export(result['objects'])
    fingerprints=C.frozen_helpers(ROOT)
    guard={o.name:fingerprints['mesh_fingerprint'](o) for o in result['objects']}

    def mutation(ident,obj,change,restore,checker,reason):
        def check():
            try:
                change();reader.refresh()
                changed=export([obj])
                try:checker()
                except AssertionError as exc:require(reason in str(exc),'Mutant rejected for unrelated reason');evidence={'rejected':True,'reason':str(exc)}
                else:raise AssertionError('Actual mutant accepted')
                mutants.append({'id':ident,'changed_geometry':changed,'additional_geometry':{}})
                return evidence
            finally:restore();reader.refresh()
        case(ident,check)

    column=result['components']['column'][0];old=column.location.copy()
    mutation('NEG-LIFT-COLUMN',column,lambda:setattr(column,'location',old+Vector((0,0,.05))),lambda:setattr(column,'location',old),contact,'roof underside')
    roof=result['roofs'][0];oldmat=roof.data.materials[0]
    mutation('NEG-WRONG-MATERIAL',roof,lambda:roof.data.materials.__setitem__(0,materials['jade_green']),lambda:roof.data.materials.__setitem__(0,oldmat),materials_check,'material allocation')
    roof=result['roofs'][1];oldrot=roof.rotation_euler.copy()
    mutation('NEG-WRONG-PHASE',roof,lambda:setattr(roof,'rotation_euler',(0,0,.13)),lambda:setattr(roof,'rotation_euler',oldrot),contact,'roof underside')
    cap=result['components']['roof_bearing_cap'][0];raw=cap.data;mut=raw.copy()
    def flatten():
        cap.data=mut;bottom=cap['bottom_z_m'];z=max(v.co.z for v in mut.vertices)
        for v in mut.vertices:
            if v.co.z>bottom+1e-5:v.co.z=z
        mut.update()
    def restore_cap():cap.data=raw;bpy.data.meshes.remove(mut)
    mutation('NEG-FLAT-CAP',cap,flatten,restore_cap,contact,'roof underside')

    def fake_plate():
        center=profile['anchor'][:2];z=sum(profile['roof_profile']['roof_tiers'][0][k] for k in ('eave_z_m','top_z_m'))/2
        slab=F.box('actual_bad_plate',(center[0],center[1],z),(.8,.8,.1),materials['neutral'],collection)
        try:
            row=export([slab])
            try:no_plate(result['objects']+[slab])
            except AssertionError as exc:require('interior horizontal plate' in str(exc),'Wrong fake plate rejection')
            else:raise AssertionError('Actual fake floor accepted')
            mutants.append({'id':'NEG-FAKE-FLOOR','changed_geometry':{},'additional_geometry':row})
            return {'actual_fake_plate_rejected':True}
        finally:data=slab.data;bpy.data.objects.remove(slab,do_unlink=True);bpy.data.meshes.remove(data);reader.refresh()
    case('NEG-FAKE-FLOOR',fake_plate)
    def final_guard():
        require({o.name:fingerprints['mesh_fingerprint'](o) for o in result['objects']}==guard,'Actual mutation restore differs')
        for name,pin in pins.items():require(sha(ROOT/name)==pin,'Frozen input changed')
        require(export(result['objects'])==baseline,'Restored actual WORLD differs')
        return {'all_actual_baseline_geometry_exactly_restored':True,'native_opened_saved':False,'input_SHA_unchanged':True}
    case('FINAL-GUARD',final_guard)
    readout={'schema':'v19-biluo-pavilion-actual-WORLD/1','profile':profile,'geometry':baseline,
             'components':{k:[o.name for o in v] for k,v in result['components'].items()},
             'contacts':result['contacts'],'beam_links':result['beam_links'],'palette':palette,
             'real_geometry_negative_controls':mutants,'input_files_sha256':pins,
             'source_support_reference_is_not_mountain_reconstruction':True,'native_saved':False,'third_party_cost':0,'human_approval':'pending'}
    write(out/'actual-geometry.json',readout)
    write(out/'actual-tests.json',{'schema':'v19-biluo-pavilion-actual-tests/1','summary':{'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks)},'checks':checks,
        'actual_geometry_sha256':sha(out/'actual-geometry.json'),'third_party_cost':0,'native_saved':False,'human_approval':'pending','whole_city_complete':False})
    require(all(c['passed'] for c in checks),'Actual fixture red; preserve report')


if __name__=='__main__':main()
