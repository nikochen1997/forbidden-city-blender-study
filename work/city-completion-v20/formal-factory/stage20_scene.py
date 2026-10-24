"""Qualified source79 new-object builder; no scene mutation on import.

Construction uses the frozen G14 once near the origin, then restores original
source registration before observation and the separate caller recess adapter.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(ROOT/'work'),str(ROOT/'work/restoration-v19'),str(ROOT/'work/city-completion-v20/shouan-recess-adapter')]
import formal_contract as K


def load_binding():
    b=K.read(HERE/'factory-bindings-01.json');K.check_bound_files(b);return b


def load_adapter(binding):
    spec=importlib.util.spec_from_file_location('qualified_shouan_recess_adapter_v2',K.path(binding['adapter_module']))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def stamp(obj,profile):
    for key,value in{'restoration_v20_subject':'shouan79','source_reference_part_id':K.SUBJECT,
        'dimension_status':'unmeasured_study','absolute_accuracy_claim':False,
        'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False,
        'profile_sha256':None}.items():
        # profile_sha256 uses the G14 canonical profile digest, not file bytes.
        obj[key]=value if key!='profile_sha256'else __import__('hashlib').sha256(K.canonical(profile).encode()).hexdigest()


def rename_owned_mesh_data(objects,old_data_pointers,exclude_names=()):
    import bpy
    groups={}
    for obj in objects:
        K.require(obj.type=='MESH'and obj.data.as_pointer()not in old_data_pointers,'cannot rename pre-existing datablock')
        groups.setdefault(obj.data.as_pointer(),[]).append(obj)
    for owners in groups.values():
        selected=[o.name for o in owners if o.name not in exclude_names]or[o.name for o in owners]
        target=K.stable_mesh_name(min(selected));data=owners[0].data
        K.require(target not in bpy.data.meshes or bpy.data.meshes[target]==data,'deterministic new mesh name collides')
        data.name=target;K.require(data.name==target,'Blender changed deterministic mesh name')


def build_geometry(profile,palette,collection_name,observe_generated=None):
    import bpy
    from mathutils import Vector
    import courtyard_hall_buildings as G
    import forbidden_city_geometry as F
    b=load_binding();expected,expected_palette=K.check_bound_files(b)
    K.validate_profile(profile,expected);K.require(K.equal(palette,expected_palette),'palette differs from pinned source-bound study')
    K.require(collection_name==b['collection_name']and collection_name not in bpy.data.collections,'new bound collection required')
    K.require('V14_shouangong'not in bpy.data.collections,'G14 child collection collides')
    A=load_adapter(b);original=K.canonical(profile);G._validate(profile)
    old_ptrs={o.as_pointer()for o in bpy.data.objects};old_data={m.as_pointer()for m in bpy.data.meshes}
    mats={}
    for key,row in palette['materials'].items():
        name='V20_SHOUAN79_MAT_'+key;K.require(name not in bpy.data.materials,'new material collides')
        mat=bpy.data.materials.new(name);mat.use_nodes=True;mat.diffuse_color=row['rgba']
        shader=mat.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value=row['rgba'];shader.inputs['Metallic'].default_value=row['metallic'];shader.inputs['Roughness'].default_value=row['roughness']
        mats[key]=mat
    collection=F.ensure_collection(collection_name)
    q=K.construction_profile(profile)
    result=G.build_hall(q,collection,mats,{})
    K.require(K.canonical(profile)==original,'original production profile mutated')
    root=result['root'];root.location=profile['anchor'];root.rotation_euler.z=profile['rotation_z_rad']
    result['profile']=copy.deepcopy(profile);result['manifest']['profile_sha256']=__import__('hashlib').sha256(K.canonical(profile).encode()).hexdigest()
    root['hall_study_profile']=json.dumps(profile,ensure_ascii=False,allow_nan=False)
    construction={'method':'G14 near-origin full-source working copy, restore original p and unique newroot WORLD before observer/adapter',
        'original_anchor':profile['anchor'],'original_rotation_z_rad':profile['rotation_z_rad'],
        'working_anchor':[0.,0.,0.],'working_rotation_z_rad':0.,'full_source_rings_retained':True,'original_profile_unchanged':True}
    root['construction_frame_transform']=json.dumps(construction,ensure_ascii=False)
    for obj in result['objects']+[root]:stamp(obj,profile)
    # Excluding the intentionally replaced south wall makes shared data names
    # stable before/after adapter even if it shares data with another wall.
    rename_owned_mesh_data(result['objects'],old_data,[result['walls']['south'].name])
    bpy.context.view_layer.update()
    for opening in result['openings']:
        opening['center_world']=list(root.matrix_world@Vector(opening['center_local']))
        opening['normal_world']=list(root.matrix_world.to_3x3()@Vector(opening['normal_local']))
    root['openings']=json.dumps(result['openings'],ensure_ascii=False)
    if observe_generated:observe_generated(result)
    result=A.recess_geometry(result,old_ptrs,mats)
    for obj in result['objects']+[root]:stamp(obj,profile)
    rename_owned_mesh_data(result['objects'],old_data)
    bpy.context.view_layer.update()
    for opening in result['openings']:
        opening['center_world']=list(root.matrix_world@Vector(opening['center_local']))
        opening['normal_world']=list(root.matrix_world.to_3x3()@Vector(opening['normal_local']))
    root['openings']=json.dumps(result['openings'],ensure_ascii=False)
    K.require(K.canonical(profile)==original and K.equal(result['profile'],profile),'real source profile changed during construction')
    result['construction_frame_transform']=construction
    result['declared_material_names']=[m.name for m in mats.values()]
    result['outer_collection']=collection
    return result


def build_stage20(request):
    """The root producer calls this exact API after independent actual checks."""
    b=load_binding();profile,palette=K.check_bound_files(b)
    K.validate_profile(request['profile'],profile)
    result=build_geometry(profile,palette,request['collection_name'])
    return {'mesh_objects':result['objects'],'root_objects':[result['root']]}
