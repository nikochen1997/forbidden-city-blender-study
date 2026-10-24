"""Compose source-qualified Chonghua/Jianfu exterior studies; preserve originals."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import forbidden_city_geometry as F
import courtyard_hall_buildings as G
import courtyard_shared_supports as S
from build_forbidden_city_restoration_v11 import mesh_fingerprint, material_state, visibility

BASE = ROOT / 'outputs/紫禁城现存格局-奉先养心斋宫第十四阶段/紫禁城现存格局-奉先养心斋宫第十四阶段.blend'
BASE_SHA = 'f7df76a8fbd64a1259687dd9d8b48fa3a717e66fc5b67d33d46d8542af2caa66'
BASE_MANIFEST_SHA = 'ac7c0d5bb154025b4a0baef2c1e09765b45c31edf98611ba95669affbd4e101c'
MODEL_NAME = '紫禁城现存格局-重华建福第十五阶段.blend'
TARGET_IDS = {'chongjingdian','chonghuagong','baozhongdian','yudedian_chonghua','cuiyunguan','jianfugong','fuchendian'}
CORE = {
 'forbidden_city_geometry.py':'23f815fc93057a0f69b66adc25536485fc05a33935f67fb1613073963e276efc',
 'restoration_buildings.py':'aac18ca8c219b8de544dd78d8a7b99000a4d0fe83d40553614065e0c998aaf60',
 'four_hall_buildings.py':'1d3267d25946ecf468da3a9d60103ef522c202452f60d0e500643d14ce9dcc1a',
 'build_forbidden_city_restoration_v11.py':'1ccce3fcca040d311f6c48fc52cd38cf053d484e627e20f03ad2f4a1c9eeb130',
}

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for block in iter(lambda:stream.read(4194304),b''):h.update(block)
 return h.hexdigest()

def read(path):return json.loads(Path(path).read_text())
def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x') as stream:
  json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')

def nonmesh_state(obj):
 return {'type':obj.type,'data':obj.data.name if obj.data else None,
  'matrix_world':[list(row) for row in obj.matrix_world],
  'parent':obj.parent.name if obj.parent else None,'visibility':visibility(obj),
  'color':list(obj.color),'custom_properties':{k:str(obj[k]) for k in obj.keys()}}

def mesh_relations(obj):
 return {'parent':obj.parent.name if obj.parent else None,'data_name':obj.data.name,
  'collections':sorted(c.name for c in obj.users_collection),
  'modifiers':[{'name':m.name,'type':m.type,'show_viewport':m.show_viewport,'show_render':m.show_render} for m in obj.modifiers],
  'shape_keys_name':obj.data.shape_keys.name if obj.data.shape_keys else None}

def camera_state(obj):
 keys=('type','lens','lens_unit','ortho_scale','sensor_width','sensor_height','sensor_fit','shift_x','shift_y',
  'clip_start','clip_end','display_size','passepartout_alpha','show_passepartout')
 state={k:getattr(obj.data,k) for k in keys}
 dof=obj.data.dof
 state['dof']={k:getattr(dof,k) for k in ('use_dof','focus_distance','aperture_fstop','aperture_blades','aperture_rotation','aperture_ratio')}
 state['dof']['focus_object']=dof.focus_object.name if dof.focus_object else None
 return state

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--output-dir',type=Path,required=True)
 parser.add_argument('--profiles',type=Path,required=True)
 parser.add_argument('--profiles-sha256',required=True)
 parser.add_argument('--module-sha256',required=True)
 parser.add_argument('--support-module-sha256',required=True)
 args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
 destination=args.output_dir.resolve()
 assert destination.parent==ROOT/'outputs'
 assert not (destination/MODEL_NAME).exists() and not (destination/'restoration-manifest.json').exists()
 spec=read(args.profiles)
 expected={BASE:BASE_SHA,BASE.parent/'restoration-manifest.json':BASE_MANIFEST_SHA,
  args.profiles.resolve():args.profiles_sha256,HERE/'courtyard_hall_buildings.py':args.module_sha256,
  HERE/'courtyard_shared_supports.py':args.support_module_sha256,
  Path(__file__).resolve():sha(__file__)}
 expected.update({HERE/p:h for p,h in CORE.items()})
 expected.update({ROOT/p:h for p,h in spec['source_files'].items()})
 assert all(sha(p)==h for p,h in expected.items()),'Frozen input changed'
 assert {p['building_id'] for p in spec['buildings']}==TARGET_IDS
 assert len(spec['buildings'])==7 and not spec['shared_supports'] and not spec['source_derived_ramps']
 for profile in spec['buildings']:G._validate(profile)
 write(destination/'evidence/profile-module-preflight.json',{'passed':True,'profiles_sha256':args.profiles_sha256,
  'module_sha256':args.module_sha256,'native_not_yet_opened':True,'target_ids':sorted(TARGET_IDS)})
 print('V15_PREFLIGHT_OK',flush=True)
 bpy.ops.wm.open_mainfile(filepath=str(BASE),load_ui=False,use_scripts=False)
 scene=bpy.context.scene;bpy.context.view_layer.update()
 previous=read(BASE.parent/'restoration-manifest.json')
 old={o.name:{'visibility':visibility(o),'fingerprint':mesh_fingerprint(o)} for o in scene.objects if o.type=='MESH'}
 old_other={o.name:nonmesh_state(o) for o in bpy.data.objects if o.type!='MESH'}
 old_materials={m.name:material_state(m) for m in bpy.data.materials}
 old_relations={o.name:mesh_relations(o) for o in scene.objects if o.type=='MESH'}
 old_cameras={o.name:camera_state(o) for o in bpy.data.objects if o.type=='CAMERA'}
 assert len(old)==previous['scene_mesh_count']==12757
 assert sum(bool(o.get('source_building_id')) for o in scene.objects if o.type=='MESH')==2845
 assert not bpy.data.libraries and not any(i.source=='FILE' and not i.packed_file for i in bpy.data.images)
 print('V15_BASE_CAPTURED',len(old),flush=True)
 collection=F.ensure_collection('restoration_v15_重华建福来源限定研究')
 assert not any(m.name.startswith('R15_') for m in bpy.data.materials)
 materials=F.create_materials('R15_')
 # Explicit visualization color for the officially blue-glazed Fuchen roof; no pigment measurement.
 blue=bpy.data.materials.new('R15_blue_glazed');blue.diffuse_color=(.025,.10,.25,1);blue.use_nodes=True
 shader=blue.node_tree.nodes.get('Principled BSDF')
 shader.inputs['Base Color'].default_value=(.025,.10,.25,1)
 shader.inputs['Metallic'].default_value=.08;shader.inputs['Roughness'].default_value=.38
 materials['blue_glazed']=blue
 records=[];new_names=set()
 shared={};support_records=[];ramp_records=[]
 for row in spec['shared_supports']:
  obj=S.build_support(row,collection,materials['white_stone'])
  assert row['support_id'] not in shared
  shared[row['support_id']]=obj;new_names.add(obj.name)
  support_records.append({'support_id':row['support_id'],'object':obj.name,'source':row})
 for row in spec['source_derived_ramps']:
  assert row['shared_support_id'] in shared
  obj=S.build_ramp(row,collection);new_names.add(obj.name)
  ramp_records.append({'object':obj.name,'source':row})
 bpy.context.view_layer.update()
 for profile in spec['buildings']:
  shared_obj=shared[profile['reference_support_id']] if profile.get('reference_support_id') else None
  result=G.build_hall(profile,collection,materials,shared_support_object=shared_obj)
  root=result['root']
  for obj in [root]+result['objects']:
   # The frozen generator namespace is not this caller's stage membership.
   if 'restoration_v14_building_id' in obj:del obj['restoration_v14_building_id']
   obj['absolute_accuracy_claim']=False;obj['human_approval']='pending';obj['third_party_cost']=0
   obj['restoration_v15_building_id']=profile['building_id']
  assert all(o.name not in old and o.name not in new_names for o in result['objects'])
  new_names.update(o.name for o in result['objects'])
  records.append({'building_id':profile['building_id'],'name_zh':profile['name_zh'],'root':root.name,'profile':profile,
   'objects':[o.name for o in result['objects']],
   'components':{k:[o.name for o in v] for k,v in result['components'].items()},
   'openings':result['openings'],'roofs':result['roofs'],'reference_floor':result['manifest']['reference_floor'],
   'reference_support_id':profile.get('reference_support_id'),'support_owned_by_building':shared_obj is None,
   'assumptions':result['assumptions'],'complete_reconstruction_proven':False})
  print('V15_BUILT',profile['building_id'],len(result['objects']),flush=True)
 remainders=[]
 for row in spec['source_display_remainders']:
  obj=S.build_remainder(row,collection)
  bpy.context.view_layer.update()
  main=next(r for r in records if r['profile']['source_part_id']==row['source_part_id'])
  shared_endpoints=sorted(set(map(tuple,row['polygon_world'])) & set(map(tuple,main['profile']['source_polygon_world'])))
  assert len(shared_endpoints)==2,'This source partition must have two shared cutline endpoints'
  slab=bpy.data.objects[main['reference_floor']]
  slab_points=[slab.matrix_world@v.co for v in slab.data.vertices]
  inverse=obj.matrix_world.inverted();aligned=[]
  before=[obj.matrix_world@v.co for v in obj.data.vertices]
  for endpoint in shared_endpoints:
   distance=lambda v:((v.x-endpoint[0])**2+(v.y-endpoint[1])**2)**.5
   target=min(slab_points,key=distance)
   assert distance(target)<1e-4,'Shared source endpoint absent from actual new main slab'
   indices=[i for i,p in enumerate(before) if distance(p)<1e-4]
   assert len(indices)==2,'Expected only bottom/top vertices at each shared endpoint'
   for i in indices:
    old_point=before[i];new=Vector((target.x,target.y,old_point.z))
    assert (new-old_point).length<1e-4
    obj.data.vertices[i].co=inverse@new
    aligned.append({'vertex':i,'before_world':list(old_point),'after_world':list(new),'main_slab':slab.name})
  assert len(aligned)==4
  obj.data.update();bpy.context.view_layer.update()
  changed={r['vertex'] for r in aligned}
  for i,v in enumerate(obj.data.vertices):
   actual=obj.matrix_world@v.co
   assert actual.z==before[i].z
   if i not in changed:assert actual==before[i]
  for r in aligned:
   assert (obj.matrix_world@obj.data.vertices[r['vertex']].co-Vector(r['after_world'])).length<1e-7
  obj['construction_cutline_alignment']=json.dumps(aligned)
  obj['construction_cutline_alignment_scope']='Only new fragment shared endpoints; float32 construction correction, not historical relocation. Original source actors unchanged.'
  assert obj.name not in old and obj.name not in new_names
  new_names.add(obj.name);remainders.append({'object':obj.name,'source':row,'construction_cutline_alignment':aligned})
 hide_rows=spec['buildings']+spec['shared_supports']+spec['source_derived_ramps']+spec['source_display_remainders']
 allowed=sorted({n for p in hide_rows for n in p.get('allowed_hidden_source_actor_names',p.get('original_actor_names',[]))})
 assert len(allowed) and set(allowed)==set(spec['allowed_hidden_source_actor_names'])
 changes=[]
 for name in allowed:
  obj=bpy.data.objects[name]
  assert name in old and not obj.hide_render and not obj.hide_get()
  obj.hide_render=True;obj.hide_set(True)
  changes.append({'object':name,'before':old[name]['visibility'],'after':visibility(obj),
   'reason':'Reversible display replacement; original geometry retained. Compound remainder re-displayed explicitly where applicable.'})
 bpy.context.view_layer.update()
 assert {o.name for o in scene.objects if o.type=='MESH'}==set(old)|new_names
 assert all(mesh_fingerprint(bpy.data.objects[n])==v['fingerprint'] for n,v in old.items())
 assert all(visibility(bpy.data.objects[n])==v['visibility'] for n,v in old.items() if n not in allowed)
 assert all(nonmesh_state(bpy.data.objects[n])==v for n,v in old_other.items())
 assert all(material_state(bpy.data.materials[n])==v for n,v in old_materials.items())
 assert all(mesh_relations(bpy.data.objects[n])==v for n,v in old_relations.items())
 assert all(camera_state(bpy.data.objects[n])==v for n,v in old_cameras.items())
 assert sum(bool(o.get('source_building_id')) for o in scene.objects if o.type=='MESH')==2845
 vertex_total=sum(len(o.data.vertices) for o in scene.objects if o.type=='MESH')
 assert vertex_total<=10000000,'Local authoring vertex budget exceeded'
 write(destination/'evidence/base-mesh-fingerprints.json',old)
 write(destination/'evidence/base-nonmesh-state.json',old_other)
 write(destination/'evidence/base-material-state.json',old_materials)
 write(destination/'evidence/base-mesh-relations.json',old_relations)
 write(destination/'evidence/base-camera-state.json',old_cameras)
 camera=bpy.data.objects['R11_Whole_City']
 targets=sorted({n for n in previous['renders'][0]['target_objects'] if not bpy.data.objects[n].hide_render}|new_names)
 scene.render.resolution_x,scene.render.resolution_y=6144,4608;scene.render.resolution_percentage=100
 points=[world_to_camera_view(scene,camera,bpy.data.objects[n].matrix_world@Vector(c)) for n in targets for c in bpy.data.objects[n].bound_box]
 framing=all(0<=p.x<=1 and 0<=p.y<=1 and camera.data.clip_start<=p.z<=camera.data.clip_end for p in points)
 write(destination/'evidence/camera-preflight.json',{'passed':framing,'camera':camera.name,
  'target_mesh_count':len(targets),'x':[min(p.x for p in points),max(p.x for p in points)],'y':[min(p.y for p in points),max(p.y for p in points)],
  'projection_source':'Actual mesh bounding-box preflight; final rendering must check evaluated vertices including moat.'})
 assert framing
 scene.camera=camera
 scene['restoration_v15_stage']='重华五殿及建福抚辰来源限定研究；保留未核抱厦和惠风亭等源占位，非完整院落复原。'
 scene['restoration_v15_profiles_sha256']=args.profiles_sha256
 scene['restoration_v15_module_sha256']=args.module_sha256
 scene['whole_city_objective_complete']=False;scene['absolute_accuracy_claim']=False;scene['third_party_cost']=0
 bpy.context.preferences.filepaths.save_version=0
 native=destination/MODEL_NAME
 bpy.ops.wm.save_as_mainfile(filepath=str(native))
 assert native.stat().st_size<=1500000000,'Local native storage budget exceeded'
 manifest={'schema':'forbidden-city-restoration-study/v15','model_file':MODEL_NAME,'model_sha256':sha(native),
  'base_native_sha256':BASE_SHA,'profiles_sha256':args.profiles_sha256,'module_sha256':args.module_sha256,
  'new_material_palette':{'blue_glazed':{'color':[.025,.10,.25],'metallic':.08,'roughness':.38,'scope':'Visualization approximation of documented blue tiles; not measured pigment.'}},
  'protected_inputs':{str(p):h for p,h in expected.items()},'base_mesh_count':len(old),'new_mesh_count':len(new_names),
  'scene_mesh_count':len(old)+len(new_names),'original_source_mesh_count':2845,'authoring_budget_evidence':{'actual_vertices':vertex_total,'maximum_vertices':10000000,'native_bytes':native.stat().st_size,'maximum_native_bytes':1500000000},'restorations':records,
  'retained_source_display_remainders':remainders,'visibility_changes':changes,'whole_city_camera':camera.name,
  'shared_supports':support_records,'source_derived_ramps':ramp_records,
  'retained_source_components':spec['retained_source_components'],
  'renders':[{'role':'final_whole_city','file':'outputs/紫禁城全宫高清图/01-全宫鸟瞰-第十五阶段.png','camera':camera.name,
   'width':6144,'height':4608,'only_selected':False,'engineering_display':False,'target_objects':targets,
   'visibility_objects':[o.name for o in scene.objects if o.type=='MESH' and not o.hide_render]}],
  'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','goal_status':'active',
  'whole_city_objective_complete':False,'claimed_absolute_accuracy':False,'limitations':spec['policy'],
  'final_user_deliverable':'High-resolution image; no stage ZIP or duplicated source tree',
  'attribution':'© OpenStreetMap contributors, ODbL; descriptive facts: Palace Museum official website.'}
 write(destination/'restoration-manifest.json',manifest)
 assert all(sha(p)==h for p,h in expected.items())
 print('V15_NATIVE_SAVED',manifest['model_sha256'],'MESHES',len(old)+len(new_names),flush=True)

if __name__=='__main__':main()
