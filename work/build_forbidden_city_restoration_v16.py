"""Compose six registered garden buildings; save only a new local native."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE));sys.dont_write_bytecode=True
import forbidden_city_geometry as F
import restoration_buildings as R
import courtyard_hall_buildings as G
import square_garden_pavilions as P
import cining_tower_buildings as T
from build_forbidden_city_restoration_v11 import mesh_fingerprint,material_state,visibility
from build_forbidden_city_restoration_v15 import nonmesh_state,mesh_relations,camera_state

BASE=ROOT/'outputs/紫禁城现存格局-重华建福第十五阶段/紫禁城现存格局-重华建福第十五阶段.blend'
BASE_SHA='54a09df9df1030494bf354d06b9dfd96c05023e1f289c8c123579a8c1e673b38'
MODEL_NAME='紫禁城现存格局-慈宁花园惠风第十六阶段.blend'
TARGETS={'huifengting','linxiting','xianruoguan','baoxianglou','jiyunlou_cininggarden','ciyinlou'}
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4194304),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,v):
    p.parent.mkdir(exist_ok=True,parents=True)
    with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,required=True)
    args=ap.parse_args(sys.argv[sys.argv.index('--')+1:]);dest=args.output_dir.resolve()
    assert dest.parent==ROOT/'outputs' and not (dest/MODEL_NAME).exists() and not (dest/'restoration-manifest.json').exists()
    profile_paths=[HERE/'restoration-v16/profiles/pavilion-hall-profiles.json',HERE/'restoration-v16/profiles/tower-profiles.json']
    docs=[read(p) for p in profile_paths];profiles=[p for doc in docs for p in doc['buildings']]
    assert len(profiles)==6 and {p['building_id'] for p in profiles}==TARGETS
    previous=read(BASE.parent/'restoration-manifest.json')
    assert sha(BASE)==BASE_SHA and sha(BASE.parent/'restoration-manifest.json')=='3c045304a3cb653b0db496ead776909a8471e427e7698119ecef71a5b7a51059'
    expected={str(BASE):BASE_SHA,str(BASE.parent/'restoration-manifest.json'):sha(BASE.parent/'restoration-manifest.json')}
    for path in profile_paths+[Path(__file__).resolve(),HERE/'square_garden_pavilions.py',HERE/'cining_tower_buildings.py',
          HERE/'forbidden_city_geometry.py',HERE/'restoration_buildings.py',HERE/'courtyard_hall_buildings.py',HERE/'four_hall_buildings.py',
          HERE/'build_forbidden_city_restoration_v11.py',HERE/'build_forbidden_city_restoration_v15.py',HERE/'restoration-v16/profiles/palette.json']:
        expected[str(path)]=sha(path)
    for doc in docs:
        for rel,h in doc.get('source_files',doc.get('source_files_sha256',{})).items():
            assert sha(ROOT/rel)==h,'Frozen source changed: '+rel
            expected[str(ROOT/rel)]=h
    for p in profiles:
        if p.get('builder')=='pavilion':P._validate(p)
        elif p['building_id']=='xianruoguan':G._validate(p)
        else:T._validate(p)
    print('V16_PREFLIGHT_OK',flush=True)
    bpy.ops.wm.open_mainfile(filepath=str(BASE),load_ui=False,use_scripts=False)
    scene=bpy.context.scene;bpy.context.view_layer.update()
    old={o.name:{'visibility':visibility(o),'fingerprint':mesh_fingerprint(o)} for o in scene.objects if o.type=='MESH'}
    old_other={o.name:nonmesh_state(o) for o in bpy.data.objects if o.type!='MESH'}
    old_mat={m.name:material_state(m) for m in bpy.data.materials}
    old_rel={o.name:mesh_relations(o) for o in scene.objects if o.type=='MESH'}
    old_cam={o.name:camera_state(o) for o in bpy.data.objects if o.type=='CAMERA'}
    assert len(old)==previous['scene_mesh_count']==13115
    assert not bpy.data.libraries and not any(i.source=='FILE' and not i.packed_file for i in bpy.data.images)
    mats=R.restoration_materials(F.create_materials('R16_'));palette=read(HERE/'restoration-v16/profiles/palette.json')
    for key,row in palette['custom'].items():
        m=bpy.data.materials.new('R16_'+key);m.use_nodes=True;m.diffuse_color=(*row['color'],1)
        bsdf=m.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=(*row['color'],1)
        bsdf.inputs['Metallic'].default_value=row['metallic'];bsdf.inputs['Roughness'].default_value=row['roughness'];mats[key]=m
    col=F.ensure_collection('restoration_v16_慈宁花园惠风来源限定研究');records=[];names=set();remainders=[]
    for p in profiles:
        ident=p['building_id']
        if p.get('builder')=='pavilion':result=P.build_pavilion(p,col,mats)
        elif ident=='xianruoguan':result=G.build_hall(p,col,mats)
        else:result=T.build_tower(p,col,mats)
        root=result['root']
        for o in [root]+result['objects']:
            if 'restoration_v14_building_id' in o:del o['restoration_v14_building_id']
            o['restoration_v16_building_id']=ident;o['absolute_accuracy_claim']=False;o['human_approval']='pending';o['third_party_cost']=0
        assert not set(o.name for o in result['objects']) & (set(old)|names)
        names.update(o.name for o in result['objects'])
        floor=result.get('reference_floor',result.get('manifest',{}).get('reference_floor'))
        if hasattr(floor,'name'):floor=floor.name
        records.append({'building_id':ident,'name_zh':p['name_zh'],'root':root.name,'profile':p,'objects':[o.name for o in result['objects']],
            'components':{k:[o.name for o in v] for k,v in result['components'].items()},'openings':result['openings'],'roofs':result['roofs'],
            'reference_floor':floor,'roof_contacts':result.get('roof_contacts',[]),'complete_reconstruction_proven':False})
        if ident=='xianruoguan':
            component=next(c for c in p['source_components'] if c['component_id']=='south_baoxia')
            c,s=math.cos(p['rotation_z_rad']),math.sin(p['rotation_z_rad'])
            ring=[]
            for x,y in component['source_polygon_world']:
                xx,yy=x-p['anchor'][0],y-p['anchor'][1];ring.append((c*xx+s*yy,-s*xx+c*yy))
            surf=F._Surface()
            for tri in F._triangulate_rings([F._clean_ring(ring)]):surf.face([(x,y,6) for x,y in tri])
            F._volume_from_top(surf,0)
            obj=F._object('V16_xianruo_baoxia_retained_source_volume',F._new_mesh('V16_xianruo_retained_baoxia',surf.vertices,surf.faces,mats['grey']),col,'retained_source_proxy_remainder')
            obj.parent=root;obj['restoration_v16_remainder_id']='xianruoguan_baoxia';obj['source_part_id']=p['source_part_id']
            obj['third_party_cost']=0;obj['human_approval']='pending';obj['absolute_accuracy_claim']=False
            obj['roof_category_known']='juanpeng_xieshan';obj['why_unbuilt']='Exact six-wing joined roof geometry unresolved; flat6m is inherited source proxy, not measured baoxia height'
            names.add(obj.name);remainders.append({'object':obj.name,'source_component':component,'proxy_height_is_measured':False})
        print('V16_BUILT',ident,len(result['objects']),flush=True)
    allowed=sorted({n for p in profiles for n in p['allowed_hidden_source_actor_names']});assert len(allowed)==6
    changes=[]
    for n in allowed:
        o=bpy.data.objects[n];assert n in old and not o.hide_render and not o.hide_get()
        o.hide_render=True;o.hide_set(True);changes.append({'object':n,'before':old[n]['visibility'],'after':visibility(o)})
    bpy.context.view_layer.update()
    assert {o.name for o in scene.objects if o.type=='MESH'}==set(old)|names
    assert all(mesh_fingerprint(bpy.data.objects[n])==row['fingerprint'] for n,row in old.items())
    assert all(visibility(bpy.data.objects[n])==row['visibility'] for n,row in old.items() if n not in allowed)
    assert all(nonmesh_state(bpy.data.objects[n])==row for n,row in old_other.items())
    assert all(material_state(bpy.data.materials[n])==row for n,row in old_mat.items())
    assert all(mesh_relations(bpy.data.objects[n])==row for n,row in old_rel.items())
    assert all(camera_state(bpy.data.objects[n])==row for n,row in old_cam.items())
    assert sum(bool(o.get('source_building_id')) for o in scene.objects if o.type=='MESH')==2845
    for name,value in [('base-mesh-fingerprints',old),('base-nonmesh-state',old_other),('base-material-state',old_mat),('base-mesh-relations',old_rel),('base-camera-state',old_cam)]:
        write(dest/('evidence/'+name+'.json'),value)
    camera=bpy.data.objects['R11_Whole_City']
    targets=sorted({n for n in previous['renders'][0]['target_objects'] if not bpy.data.objects[n].hide_render}|names)
    points=[world_to_camera_view(scene,camera,bpy.data.objects[n].matrix_world@Vector(v)) for n in targets for v in bpy.data.objects[n].bound_box]
    assert all(0<=p.x<=1 and 0<=p.y<=1 and camera.data.clip_start<=p.z<=camera.data.clip_end for p in points)
    count=sum(len(o.data.vertices) for o in scene.objects if o.type=='MESH');assert count<=10000000
    scene['restoration_v16_stage']='惠风方攒尖重檐、临溪方亭单桥、慈宁三座两层佛楼及咸若主馆；抱厦/池界/未知院落仍未完成。'
    scene['whole_city_objective_complete']=False;scene['absolute_accuracy_claim']=False;scene['third_party_cost']=0
    bpy.context.preferences.filepaths.save_version=0
    native=dest/MODEL_NAME;bpy.ops.wm.save_as_mainfile(filepath=str(native));assert native.stat().st_size<=1500000000
    write(dest/'restoration-manifest.json',{'schema':'forbidden-city-restoration-study/v16','model_file':MODEL_NAME,'model_sha256':sha(native),
        'base_native_sha256':BASE_SHA,'protected_inputs':expected,'base_mesh_count':len(old),'new_mesh_count':len(names),'scene_mesh_count':len(old)+len(names),
        'original_source_mesh_count':2845,'restorations':records,'retained_source_display_remainders':remainders,'visibility_changes':changes,
        'whole_city_camera':camera.name,'vertex_count':count,'new_material_palette':palette,
        'renders':[{'role':'final_whole_city','file':'outputs/紫禁城全宫高清图/01-全宫鸟瞰-第十六阶段.png','camera':camera.name,'width':6144,'height':4608,
                    'only_selected':False,'target_objects':targets}],
        'retained_source_components':read(HERE/'restoration-v16/registration/registered-buildings.json')['deferred_entities'],
        'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','goal_status':'active','whole_city_objective_complete':False,'claimed_absolute_accuracy':False,
        'limitations':['Whole city and many gray volumes incomplete','All metric values unmeasured study controls','Tower upper interior floors/stairs not reconstructed; no full slab covering Bao skylights',
                       'Huifeng rear/side enclosure unknown; frontal open photograph not all-face certification','Linxi blue/green trim source conflict retained; dedicatedcurrentpage green chosen',
                       'No measured Cining pond boundary: water geometry remains unbuilt','Xianruo joined baoxia roof not reconstructed, exact source lobe remains gray'],
        'final_user_deliverable':'High-resolution image; no stage ZIP or duplicated source tree','attribution':'© OpenStreetMap contributors ODbL; architectural descriptions: Palace Museum official sources.'})
    assert all(sha(p)==h for p,h in expected.items());print('V16_NATIVE_SAVED',sha(native),'MESHES',len(old)+len(names),flush=True)
if __name__=='__main__':main()
