"""Root-only smallest native correction: retain original wall, cut its clone.

This explicitly overwrites only the rejected private V16 candidate after small
historical evidence is archived. It never modifies any of the existing meshes.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
import bpy
import bmesh
from mathutils import Vector

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PROFILE=HERE/'context-wall-profile.json'
PROFILE_SHA='f4704cd7b3158f0c49545bf091e5e496f3c7d64d083dd43ea7d8e0f833b9af99'
NATIVE_INPUT_SHA='0887a39941eb444b99b77fe2f8ae31ae07e51d25a8f1e14ad83ca0e93635bdce'
MANIFEST_INPUT_SHA='af1ba4804ac871be45d89d7a71f3a4757d4bde60bc1982c258945b12221cd27f'
CORE=ROOT/'work/restoration-v16/saved-audit/saved_audit_core.py'
CORE_SHA='72d1fc4253231380ae8db9784a3b6a81a3f66307170e4003e85837d5a68e6ae0'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(4194304),b''):h.update(b)
    return h.hexdigest()
def require(ok,message):
    if not ok:raise AssertionError(message)
def write(path,value):
    with path.open('x')as f:f.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',type=Path,required=True);parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--evidence-dir',type=Path,required=True);a=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    model=a.model.resolve();manifestpath=a.manifest.resolve();out=a.evidence_dir.resolve()
    require(model.parent==ROOT/'outputs/紫禁城现存格局-慈宁花园惠风第十六阶段'and manifestpath==model.parent/'restoration-manifest.json','Only rejected private V16 candidate may be overwritten')
    require(out.is_relative_to(ROOT/'work/restoration-v16/integration')and not out.exists(),'Fresh small correction evidence folder required')
    require(sha(model)==NATIVE_INPUT_SHA and sha(manifestpath)==MANIFEST_INPUT_SHA and sha(PROFILE)==PROFILE_SHA and sha(CORE)==CORE_SHA,'Exact rejected candidate/profile/core binding')
    old_manifest_bytes=manifestpath.read_bytes();manifest=json.loads(old_manifest_bytes);profile=json.loads(PROFILE.read_text())
    require(manifest['base_mesh_count']==13115 and manifest['new_mesh_count']==567 and manifest['scene_mesh_count']==13682 and len(manifest['restorations'])==6 and not manifest.get('context_wall_replacements'),'Only original six-building candidate accepted')
    for p,h in manifest['protected_inputs'].items():require(sha(p)==h,'Original protected input drift '+p)
    probe=ROOT/profile['source_probe_file'];require(sha(probe)==profile['source_probe_sha256'],'Exact actual wall readout binding')
    spec=importlib.util.spec_from_file_location('v16_patch_readonly_core',CORE);C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
    out.mkdir(parents=True);(out/'input-restoration-manifest.json').write_bytes(old_manifest_bytes)
    # Preserve the actual executed producer as small provenance, not another native.
    executed=ROOT/'work/build_forbidden_city_restoration_v16.py';(out/'executed-producer.py').write_bytes(executed.read_bytes())
    beforefiles={Path(p):h for p,h in manifest['protected_inputs'].items()};beforefiles.update({PROFILE:PROFILE_SHA,probe:profile['source_probe_sha256'],CORE:CORE_SHA,Path(__file__).resolve():sha(__file__)})
    bpy.ops.wm.open_mainfile(filepath=str(model),load_ui=False,use_scripts=False);bpy.context.view_layer.update();f=C.frozen_helpers(ROOT)
    meshes={o.name for o in bpy.context.scene.objects if o.type=='MESH'};require(len(meshes)==13682,'Original actual mesh count')
    original_name=profile['original_source_actor'];original=bpy.data.objects[original_name];require(original.type=='MESH'and not original.modifiers and original.data.shape_keys is None and not original.hide_render and original.visible_get(),'Original wall must be intact and visible')
    replacement_name=profile['replacement_object'];require(replacement_name not in bpy.data.objects,'Replacement already exists')
    before={n:{'fingerprint':f['mesh_fingerprint'](bpy.data.objects[n]),'visibility':f['visibility'](bpy.data.objects[n]),'relations':C.mesh_relations(bpy.data.objects[n])}for n in meshes}
    materials={m.name:f['material_state'](m)for m in bpy.data.materials};other={o.name:C.nonmesh_state(o,f['visibility'])for o in bpy.data.objects if o.type!='MESH'};cameras={o.name:C.camera_state(o.data)for o in bpy.data.objects if o.type=='CAMERA'}
    print('CONTEXT_PATCH_ALL_13682_BEFORE_SNAPSHOT',flush=True)
    original_mesh_data={m.as_pointer()for m in bpy.data.meshes}
    clone=original.copy();clone.data=original.data.copy();clone.name=replacement_name
    for col in original.users_collection:col.objects.link(clone)
    # Actual captured source wall has four closed inward-facing components.
    # Correct only the new single-user copy before solid Boolean Difference;
    # original raw winding is immutable and remains protected by fingerprints.
    bm=bmesh.new();bm.from_mesh(clone.data)
    try:bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(clone.data)
    finally:bm.free()
    clone.data.update();bpy.context.view_layer.update()
    C.closed_positive_topology(C.MeshReader(bpy).mesh(clone.name))
    clone['semantic_role']='source_context_wall_replacement';clone['restoration_v16_context_id']=profile['id'];clone['source_context_profile']=json.dumps(profile,ensure_ascii=False,allow_nan=False)
    clone['original_source_actor']=original_name;clone['source_part_id']=profile['source_wall_part_id'];clone['third_party_cost']=0;clone['human_approval']='pending';clone['absolute_accuracy_claim']=False
    clone['opening_method']='Actual Exact Boolean Difference on independent single-user original-wall clone';clone['opening_id']=profile['passage_opening_id'];clone['all_metric_dimensions']='unmeasured source-context study, not surveyed gate'
    clone['source_copy_face_orientation_correction']='New clone only: four captured source components have inward winding; reverse faces before Difference. Original raw winding unchanged.'
    cut=profile['cutter'];w,depth,h=cut['width_m'],cut['depth_m'],cut['cutter_top_z_m']-cut['cutter_bottom_z_m'];x,y,z=cut['center_local'];c,s=math.cos(cut['rotation_z_rad']),math.sin(cut['rotation_z_rad']);anchor=cut['anchor']
    verts=[(sx*w/2,sy*depth/2,sz*h/2)for sx,sy,sz in[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    mesh=bpy.data.meshes.new('V16_TEMP_CONTEXT_CUTTER');mesh.from_pydata(verts,[],[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]);mesh.update();cutter=bpy.data.objects.new(mesh.name,mesh);bpy.context.scene.collection.objects.link(cutter)
    cutter.location=(anchor[0]+c*x-s*y,anchor[1]+s*x+c*y,anchor[2]+z);cutter.rotation_euler.z=cut['rotation_z_rad'];bpy.context.view_layer.update()
    modifier=clone.modifiers.new('V16_documented_Ciyin_north_passage','BOOLEAN');modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter;bpy.context.view_layer.objects.active=clone
    try:bpy.ops.object.modifier_apply(modifier=modifier.name)
    finally:bpy.data.objects.remove(cutter,do_unlink=True);bpy.data.meshes.remove(mesh)
    for datablock in list(bpy.data.meshes):
        if datablock.as_pointer()not in original_mesh_data and datablock.users==0:bpy.data.meshes.remove(datablock)
    require(not clone.modifiers and clone.data.as_pointer()!=original.data.as_pointer(),'Single-user applied clone required')
    original.hide_render=True;original.hide_set(True);bpy.context.view_layer.update()
    require({o.name for o in bpy.context.scene.objects if o.type=='MESH'}==meshes|{clone.name},'Exactly one new context mesh')
    for n,row in before.items():
        obj=bpy.data.objects[n];require(f['mesh_fingerprint'](obj)==row['fingerprint']and C.mesh_relations(obj)==row['relations'],'Existing raw/material/matrix/meta/relations changed '+n)
        require(f['visibility'](obj)==(f['visibility'](original)if n==original_name else row['visibility']),'Existing visibility changed '+n)
    require(all(f['material_state'](bpy.data.materials[n])==v for n,v in materials.items()),'Existing materials changed')
    require(all(C.nonmesh_state(bpy.data.objects[n],f['visibility'])==v for n,v in other.items()),'Existing nonmesh state changed')
    require(all(C.camera_state(bpy.data.objects[n].data)==v for n,v in cameras.items()),'Existing camera data changed')
    require(len(bpy.data.materials)==len(materials),'No new material required')
    reader=C.MeshReader(bpy);topology=C.closed_positive_topology(reader.mesh(clone.name));opening=profile['passage_opening_record'];points=0
    for u in[-.46,-.23,0,.23,.46]:
        for v in[-.46,-.23,0,.23,.46]:
            for sign in[-1,1]:
                xx=opening['center_local'][0]+u*opening['clear_width_m'];zz=opening['center_local'][2]+v*opening['clear_height_m'];aa=C.world_point({'anchor':anchor,'rotation_z_rad':cut['rotation_z_rad']},(xx,cut['center_local'][1]-sign*(depth/2+.1),zz));bb=C.world_point({'anchor':anchor,'rotation_z_rad':cut['rotation_z_rad']},(xx,cut['center_local'][1]+sign*(depth/2+.1),zz))
                require(reader.ray([clone.name],aa,bb)is None,'Actual cloned source wall still blocks documented north passage');points+=1
    require(all(sha(p)==h for p,h in beforefiles.items()),'Protected input changed during correction')
    write(out/'before-existing-mesh-state.json',before)
    write(out/'correction-pre-save-checks.json',{'old13115_and_existing567_meshes_raw_material_matrix_meta_relations_unchanged':True,'only_additional_visibility_exception':original_name,'all_old_material_nonmesh_camera_unchanged':True,'new_context_meshes':1,'actual_clone_closed_topology':topology,'actual_context_passage_bidirectional_rays':points,'input_native_provenance_sha256':NATIVE_INPUT_SHA,'input_manifest_provenance_sha256':MANIFEST_INPUT_SHA,'third_party_cost':0,'human_approval':'pending'})
    updated=copy.deepcopy(manifest);updated['context_wall_replacements']=[{'profile':profile,'original_object':original_name,'object':clone.name,'replacement_object':clone.name,'opening_id':profile['passage_opening_id'],'source_profile_sha256':PROFILE_SHA,'original_wall_hidden_not_modified':True,'all_other_source_wall_geometry_retained':True,'complete_reconstruction_proven':False}]
    updated['visibility_changes'].append({'object':original_name,'before':before[original_name]['visibility'],'after':f['visibility'](original),'context_wall_replacement_id':profile['id']})
    updated['new_mesh_count']=568;updated['scene_mesh_count']=13683;updated['vertex_count']=sum(len(o.data.vertices)for o in bpy.context.scene.objects if o.type=='MESH')
    for row in updated['renders']:row['target_objects']=sorted((set(row['target_objects'])-{original_name})|{clone.name})
    updated['protected_inputs'].update({str(p):h for p,h in beforefiles.items()if p not in updated['protected_inputs']})
    # Input candidate SHA is historical provenance only: output intentionally
    # replaces this same private native path, never an immutable direct input pin.
    updated['context_correction_execution']={'input_native_provenance_sha256':NATIVE_INPUT_SHA,'input_manifest_provenance_sha256':MANIFEST_INPUT_SHA,'archived_input_manifest':str((out/'input-restoration-manifest.json').relative_to(ROOT)),'patch_script':str(Path(__file__).resolve().relative_to(ROOT)),'existing567_new_meshes_and13115_old_raw_unchanged':True,'only_new_visibility_exception':original_name,'only_new_copy_face_orientation_corrected':True,'original_four_source_component_winding_unchanged':True}
    updated['limitations'].append('Source-context north wall clone cut only at documented Ciyin passage; exact historic wall doorway dimensions/style remain unmeasured and unbuilt.')
    bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(model));updated['model_sha256']=sha(model)
    manifestpath.write_text(json.dumps(updated,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    write(out/'correction-execution-receipt.json',{'schema':'v16-Ciyin-context-correction-execution/1','native_sha256':sha(model),'manifest_sha256':sha(manifestpath),'profile_sha256':PROFILE_SHA,'patch_sha256':sha(__file__),'new_mesh_count':568,'scene_mesh_count':13683,'original_candidate_replaced_without_large_backup':True,'old_candidate_is_rejected_not_delivered':True,'saved_full_audit_and_CPU_required':True,'third_party_cost':0,'human_approval':'pending'})
    print('V16_CONTEXT_CORRECTION_SAVED',sha(model),sha(manifestpath),'MESHES',13683,flush=True)


if __name__=='__main__':main()
