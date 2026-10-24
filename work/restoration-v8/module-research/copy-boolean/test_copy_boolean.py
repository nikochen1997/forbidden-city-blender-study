"""Read a frozen native; test Exact subtraction on disposable source deep copies.

This is a technical experiment, not a building reconstruction or portal schedule.
It never hides source actors or saves a native, and imports no preparation script.
"""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

WORK = Path(__file__).resolve().parents[3]
sys.dont_write_bytecode = True
sys.path.insert(0, str(WORK))
import forbidden_city_geometry as F
import imperial_monuments as M


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(4194304), b''):
            h.update(chunk)
    return h.hexdigest()


def safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, bpy.types.ID):
        return {'id_type': value.bl_rna.identifier, 'name': value.name_full}
    if hasattr(value, 'to_dict'):
        return safe(value.to_dict())
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if hasattr(value, 'to_list'):
        return safe(value.to_list())
    try:
        return [safe(v) for v in value]
    except TypeError:
        return str(value)


def digest(value):
    return hashlib.sha256(json.dumps(safe(value), sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def mesh_digest(mesh):
    h = hashlib.sha256()
    for seq, field, dtype, count in [(mesh.vertices, 'co', 'f', 3),
                                    (mesh.edges, 'vertices', 'i', 2),
                                    (mesh.loops, 'vertex_index', 'i', 1),
                                    (mesh.polygons, 'loop_start', 'i', 1),
                                    (mesh.polygons, 'loop_total', 'i', 1),
                                    (mesh.polygons, 'material_index', 'i', 1),
                                    (mesh.polygons, 'use_smooth', 'b', 1)]:
        values = array(dtype, [0]) * (len(seq) * count)
        seq.foreach_get(field, values)
        h.update(field.encode()); h.update(values.tobytes())
    for attr in sorted(mesh.attributes, key=lambda item: item.name):
        h.update(digest([attr.name, attr.data_type, attr.domain, len(attr.data)]).encode())
        spec = {'FLOAT': ('value', 'f', 1), 'INT': ('value', 'i', 1),
                'INT8': ('value', 'i', 1), 'BOOLEAN': ('value', 'b', 1),
                'FLOAT_VECTOR': ('vector', 'f', 3), 'FLOAT2': ('vector', 'f', 2),
                'FLOAT_COLOR': ('color', 'f', 4), 'BYTE_COLOR': ('color', 'f', 4)}.get(attr.data_type)
        if spec:
            field, dtype, count = spec
            values = array(dtype, [0]) * (len(attr.data) * count)
            attr.data.foreach_get(field, values)
            h.update(values.tobytes())
        else:
            h.update(digest([[safe(getattr(item, k)) for k in ('value', 'vector', 'color') if hasattr(item, k)]
                             for item in attr.data]).encode())
    h.update(digest([m.name_full if m else None for m in mesh.materials]).encode())
    return h.hexdigest()


def material_digest(material):
    tree = material.node_tree
    nodes, links = [], []
    if tree:
        for node in sorted(tree.nodes, key=lambda item: item.name):
            props = {}
            for prop in node.bl_rna.properties:
                if prop.identifier == 'rna_type' or prop.type == 'COLLECTION':
                    continue
                try:
                    props[prop.identifier] = safe(getattr(node, prop.identifier))
                except (AttributeError, TypeError, RuntimeError):
                    pass
            sockets = []
            for direction, seq in [('input', node.inputs), ('output', node.outputs)]:
                for socket in seq:
                    sockets.append([direction, socket.identifier, socket.name,
                                    safe(socket.default_value) if hasattr(socket, 'default_value') else None])
            nodes.append([node.name, node.bl_idname, props, sockets])
        links = sorted([link.from_node.name, link.from_socket.identifier,
                        link.to_node.name, link.to_socket.identifier] for link in tree.links)
    return digest({'name': material.name_full, 'diffuse': list(material.diffuse_color),
                   'metallic': material.metallic, 'roughness': material.roughness,
                   'use_nodes': material.use_nodes, 'backface': material.use_backface_culling,
                   'nodes': nodes, 'links': links, 'custom': dict(material.items())})


def slots(obj):
    return [[slot.link, slot.material.name_full if slot.material else None] for slot in obj.material_slots]


def source_fingerprints(objects, label):
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    material_hashes = {m.name_full: material_digest(m) for m in bpy.data.materials}
    rows = []
    for index, obj in enumerate(objects):
        evaluated = obj.evaluated_get(deps)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=deps)
        try:
            parts = {'raw': mesh_digest(obj.data), 'evaluated': mesh_digest(mesh),
                     'transform': digest([obj.matrix_world, obj.matrix_basis, obj.matrix_parent_inverse,
                                          obj.parent.name if obj.parent else None]),
                     'actual_slots': digest([slots(obj), slots(evaluated)]),
                     'shader': digest([[name, material_hashes[name]] for name in sorted(
                         {slot.material.name_full for slot in obj.material_slots if slot.material})]),
                     'colour': digest(list(obj.color)), 'source_records': digest(dict(obj.items())),
                     'visibility': digest([obj.hide_render, obj.hide_viewport, obj.hide_get(), obj.visible_get(),
                                            [[c.name, c.hide_render, c.hide_viewport] for c in obj.users_collection]])}
            rows.append({'name': obj.name, 'data_name': obj.data.name, 'parts': parts,
                         'sha256': digest(parts)})
        finally:
            evaluated.to_mesh_clear()
        if (index + 1) % 1000 == 0:
            print('FINGERPRINT_PROGRESS', label, index + 1, len(objects), flush=True)
    return rows


def world_bvh(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(deps)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=deps)
    try:
        mesh.calc_loop_triangles()
        points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
        triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
        categories = [mesh.polygons[t.polygon_index].material_index for t in mesh.loop_triangles]
        actual_slots = slots(evaluated)
        return BVHTree.FromPolygons(points, triangles, all_triangles=True), categories, actual_slots
    finally:
        evaluated.to_mesh_clear()


def ray(tree, origin, direction, distance):
    bvh, categories, effective_slots = tree
    p, n, face, length = bvh.ray_cast(Vector(origin), Vector(direction), distance)
    if p is None:
        return None
    slot_index = categories[face]
    return {'point': list(p), 'normal': list(n), 'distance': length, 'material_index': slot_index,
            'actual_slot': effective_slots[slot_index] if slot_index < len(effective_slots) else None}


def topology(obj, evaluated=False, require_solid=True):
    eval_obj=None;mesh=obj.data;matrix=obj.matrix_world
    if evaluated:
        deps=bpy.context.evaluated_depsgraph_get();eval_obj=obj.evaluated_get(deps)
        mesh=eval_obj.to_mesh(preserve_all_data_layers=True,depsgraph=deps);matrix=eval_obj.matrix_world
    bm = bmesh.new(); bm.from_mesh(mesh)
    try:
        finite = all(math.isfinite(v) for vert in bm.verts for v in vert.co)
        bad=[edge for edge in bm.edges if len(edge.link_faces)!=2]
        bad_edges=len(bad);orientation_conflicts=0
        for edge in bm.edges:
            if len(edge.link_faces)==2:
                directions=[next(loop.vert==edge.verts[0] for loop in face.loops if loop.edge==edge)
                            for face in edge.link_faces]
                orientation_conflicts+=directions[0]==directions[1]
        seen, components = set(), []
        for start in bm.verts:
            if start in seen:
                continue
            stack, verts = [start], set()
            while stack:
                current = stack.pop()
                if current in verts:
                    continue
                verts.add(current); seen.add(current)
                stack.extend(edge.other_vert(current) for edge in current.link_edges)
            faces = {face for v in verts for face in v.link_faces}
            anchor = [sum(v.co[k] for v in verts) / len(verts) for k in range(3)]
            volume = 0.0
            for face in faces:
                pts = [[float(v.co[k]) - anchor[k] for k in range(3)] for v in face.verts]
                for i in range(1, len(pts) - 1):
                    a, b, c = pts[0], pts[i], pts[i + 1]
                    volume += (a[0]*(b[1]*c[2]-b[2]*c[1]) + a[1]*(b[2]*c[0]-b[0]*c[2]) + a[2]*(b[0]*c[1]-b[1]*c[0]))/6
            components.append({'vertices': len(verts), 'faces': len(faces), 'signed_volume_local': volume,
                               'centre_world': list(matrix @ Vector(anchor))})
        result = {'finite': finite, 'nonmanifold_edges': bad_edges, 'orientation_conflict_edges':orientation_conflicts,
                  'edges':len(bm.edges),'vertices': len(bm.verts),
                  'faces': len(bm.faces), 'components': components,
                  'signed_volume_local': sum(x['signed_volume_local'] for x in components),
                  'nonmanifold_edge_world_endpoints':[[list(matrix@v.co) for v in edge.verts] for edge in bad[:16]]}
        if require_solid and (not finite or bad_edges or orientation_conflicts or not components or any(c['signed_volume_local'] <= 1e-7 for c in components)):
            raise AssertionError('copy is not finite/closed/positive: ' + json.dumps(result))
        return result
    finally:
        bm.free()
        if eval_obj is not None:eval_obj.to_mesh_clear()


def inside(point, ring):
    x, y = point; value = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            value = not value
    return value


def centroid(ring):
    area2 = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]+ring[:1]))
    return [sum((a[k]+b[k])*(a[0]*b[1]-b[0]*a[1]) for a,b in zip(ring,ring[1:]+ring[:1]))/(3*area2)
            for k in range(2)]


def clone_source(original, name, collection):
    obj = original.copy(); obj.data = original.data.copy(); obj.name = name; collection.objects.link(obj)
    bpy.context.view_layer.update()
    assert obj.matrix_world == original.matrix_world, 'deep copy world matrix changed'
    assert slots(obj) == slots(original), 'deep copy effective slots changed'
    assert mesh_digest(obj.data) == mesh_digest(original.data), 'deep copy raw face/material data changed'
    return obj


def rebase_working_copy(obj, matrix):
    old_matrix=obj.matrix_world.copy();old_world=[old_matrix@v.co for v in obj.data.vertices]
    old_slots=slots(obj);old_faces=[(tuple(p.vertices),p.material_index,p.use_smooth) for p in obj.data.polygons]
    obj.data=obj.data.copy()
    a,b,c,d=map(float,(matrix[0][0],matrix[0][1],matrix[1][0],matrix[1][1]));det=a*d-b*c
    tx,ty,tz=map(float,(matrix[0][3],matrix[1][3],matrix[2][3]))
    for vertex,world in zip(obj.data.vertices,old_world):
        dx,dy=float(world.x)-tx,float(world.y)-ty
        vertex.co=((d*dx-b*dy)/det,(-c*dx+a*dy)/det,float(world.z)-tz)
    obj.matrix_world=matrix;obj.data.update();bpy.context.view_layer.update()
    error=max((matrix@v.co-old).length for v,old in zip(obj.data.vertices,old_world))
    assert error<=1e-4,'working-copy rebase exceeded fixed 0.0001m world limit'
    assert slots(obj)==old_slots and [(tuple(p.vertices),p.material_index,p.use_smooth) for p in obj.data.polygons]==old_faces
    return {'operation':'new working-copy coordinate re-expression only','source_world_matrix_preserved_before_reexpression':safe(old_matrix),
            'working_copy_world_matrix':safe(matrix),'maximum_actual_world_vertex_difference_m':error,
            'fixed_world_error_limit_m':1e-4,'face_order_and_material_slots_unchanged':True,
            'source_actor_matrix_not_changed':True}


def apply_exact(obj, cutter):
    obj.data = obj.data.copy()  # Includes users=1 cached/source-copy ownership boundary.
    previous = bpy.context.view_layer.objects.active
    try:
        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new('COPY_TECH_EXACT', 'BOOLEAN')
        modifier.operation = 'DIFFERENCE'; modifier.solver = 'EXACT'; modifier.use_self = True; modifier.object = cutter
        assert bpy.ops.object.modifier_apply(modifier=modifier.name) == {'FINISHED'}
        raw = {'vertices': len(obj.data.vertices), 'faces': len(obj.data.polygons)}
        try:
            raw['topology_before_cleanup'] = topology(obj)
        except AssertionError as error:
            raw['topology_before_cleanup_error'] = str(error)
        cleanup = M.clean_boolean_mesh(obj, threshold=1e-6)
        bpy.context.view_layer.update()
        return {'solver': 'EXACT', 'use_self': True, 'raw_after_boolean': raw, 'cleanup': cleanup,
                'data_detached_before_boolean': True}
    finally:
        bpy.context.view_layer.objects.active = previous


def prism(name, ring, low, high, collection):
    surf = F._Surface()
    for triangle in F._triangulate_rings([ring]):
        surf.face([(x, y, high) for x, y in triangle])
    F._volume_from_top(surf, low)
    return F._object(name, F._new_mesh(name, surf.vertices, surf.faces, None), collection, 'technical_cutter')


def projected_mask_volume(obj, ring):
    """Independent closed-surface integral over the convex vertical mask.

    Integrate z*n_z dA on clipped source triangles. This measures the actual
    source volume inside the mask without running another mesh Boolean.
    """
    orientation=1 if F._ring_area(ring)>0 else -1
    deps=bpy.context.evaluated_depsgraph_get();evaluated=obj.evaluated_get(deps)
    mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=deps)
    integral=0.0
    try:
        mesh.calc_loop_triangles()
        world=[list(evaluated.matrix_world@v.co) for v in mesh.vertices]
        for triangle in mesh.loop_triangles:
            polygon=[world[i] for i in triangle.vertices]
            for a,b in zip(ring,ring[1:]+ring[:1]):
                if not polygon:break
                def value(p):return orientation*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))
                clipped=[];first=polygon[-1];v0=value(first)
                for second in polygon:
                    v1=value(second);i0=v0>=0;i1=v1>=0
                    if i0!=i1:
                        t=v0/(v0-v1);clipped.append([first[k]+t*(second[k]-first[k]) for k in range(3)])
                    if i1:clipped.append(second)
                    first,v0=second,v1
                polygon=clipped
            for i in range(1,len(polygon)-1):
                a,b,c=polygon[0],polygon[i],polygon[i+1]
                area=((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
                integral+=area*(a[2]+b[2]+c[2])/3
        return integral
    finally:evaluated.to_mesh_clear()


def trial_mask(original, record, ring, centre, angle, collection):
    obj = clone_source(original, 'COPY_TECH_' + record['id'], collection)
    old_bvh = world_bvh(original); before_slots = slots(original)
    cutter = prism('COPY_TECH_994_RAW_FOOTPRINT_Z_MINUS100_TO150', ring, -100, 150, collection)
    actual_ring=[]
    for x,y in ring:
        point=min((cutter.matrix_world@v.co for v in cutter.data.vertices),key=lambda p:(p.x-x)**2+(p.y-y)**2)
        actual_ring.append([point.x,point.y])
    original_topology=topology(original)
    expected_removed_volume=projected_mask_volume(original,actual_ring)
    operation = apply_exact(obj, cutter)
    topo = topology(obj)
    original_volume=original_topology['signed_volume_local']*abs(original.matrix_world.determinant())
    retained_volume=topo['signed_volume_local']*abs(obj.matrix_world.determinant())
    removed_volume=original_volume-retained_volume
    volume_tolerance=max(.01,original_volume*1e-5)
    assert 0<removed_volume<original_volume,'mask removed none or all of the source'
    assert abs(removed_volume-expected_removed_volume)<=volume_tolerance,'difference volume disagrees with independent source integral'
    assert slots(obj) == before_slots, 'effective material slots changed'
    new_bvh = world_bvh(obj); inner, outer, errors = [], [], []
    project=lambda p:math.cos(angle)*(p[0]-centre[0])+math.sin(angle)*(p[1]-centre[1])
    mask_low=min(project(p) for p in ring);mask_high=max(project(p) for p in ring)
    end_rays={'negative_x':0,'positive_x':0};middle_retained=[]
    poly = record['polygon']; xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    for i in range(1, 64):
        for j in range(1, 16):
            x=min(xs)+(max(xs)-min(xs))*i/64; y=min(ys)+(max(ys)-min(ys))*j/16
            if not inside((x,y),poly):continue
            old=ray(old_bvh,(x,y,200),(0,0,-1),400)
            if old is None:continue
            new=ray(new_bvh,(x,y,200),(0,0,-1),400)
            if inside((x,y),ring):
                inner.append([x,y])
                if new is not None:errors.append({'kind':'mask_not_empty','xy':[x,y],'new':new})
            else:
                outer.append([x,y])
                u=project([x,y])
                if u<mask_low:end_rays['negative_x']+=1
                elif u>mask_high:end_rays['positive_x']+=1
                else:middle_retained.append([x,y])
                if new is None or (Vector(new['point'])-Vector(old['point'])).length>5e-4 or new['actual_slot']!=old['actual_slot'] or new['material_index']!=old['material_index'] or (Vector(new['normal'])-Vector(old['normal'])).length>.005:
                    errors.append({'kind':'outside_changed','xy':[x,y],'old':old,'new':new})
    assert len(inner)>20 and len(outer)>20, 'insufficient real source-positive rays'
    assert min(end_rays.values())>10,'actual source ends were not both preserved'
    assert not errors, 'actual mask/outside mismatch '+json.dumps(errors[:6])
    return {'source_actor':original.name,'copy':obj.name,'operation':operation,'topology':topo,
            'inside_source_positive_then_copy_empty_vertical_rays':len(inner),
            'outside_equal_hit_position_normal_material_rays':len(outer),
            'outside_hit_tolerance_metres':5e-4,'source_and_copy_slots':before_slots,
            'retained_end_outside_rays':end_rays,'component_count_observed_not_assumed':len(topo['components']),
            'middle_outside_mask_source_rays_preserved':len(middle_retained),'middle_outside_examples':middle_retained[:8],
            'original_volume_m3':original_volume,'retained_volume_m3':retained_volume,'removed_volume_m3':removed_volume,
            'independent_projected_source_volume_inside_mask_m3':expected_removed_volume,
            'volume_comparison_tolerance_m3':volume_tolerance,
            'preservation_rule':'Both source ends remain and every sampled outside surface is unchanged; an original outside-mask connecting strip is retained, not forced into two components.',
            'mask_z':[-100,150],'mask_is_actual_994_raw_polygon':True}


def trial_prototype(platform, wall, centre, angle, collection):
    clones=[clone_source(obj,'COPY_TECH_PROTOTYPE_'+obj.name,collection) for obj in (platform,wall)]
    matrix=Matrix.Translation(Vector((centre[0],centre[1],0))) @ Matrix.Rotation(angle,4,'Z')
    inverse=matrix.inverted()
    points=[inverse @ (obj.matrix_world @ v.co) for obj in (platform,wall) for v in obj.data.vertices]
    low=min(p.y for p in points)-2;high=max(p.y for p in points)+2
    record={'width':4.0,'spring_z':4.0,'crown_z':6.0,'bottom_z':0.0,'cutter_bottom_z':-.2,
            'local_x':0.0,'center_x':0.0,'y_min':low,'y_max':high}
    cutter=M.make_vault_cutter('COPY_TECH_NOT_A_HISTORICAL_GATE_ROUTE',record,collection,y_min=low,y_max=high)
    cutter.matrix_world=matrix
    bpy.context.view_layer.update(); cutter_world_before=digest([cutter.matrix_world,mesh_digest(cutter.data)])
    results=[]
    for original,obj in zip((platform,wall),clones):
        rebase=rebase_working_copy(obj,matrix)
        old=world_bvh(original);operation=apply_exact(obj,cutter);new=world_bvh(obj);topo=topology(obj)
        voids,controls=[],[]
        direction=matrix.to_3x3() @ Vector((0,1,0));distance=high-low+10
        for x in (-.8,0,.8):
            for z in (.5,3.5,5.0):
                origin=matrix @ Vector((x,low-4,z))
                a=ray(old,origin,direction,distance);b=ray(new,origin,direction,distance)
                assert a is not None, 'prototype did not first cross original actual actor '+original.name
                assert b is None, 'prototype copy passage still blocked '+original.name
                voids.append({'local_x_z':[x,z],'original_hit':a['point'],'copy_hit':None})
        candidate_probes=[];control_errors=[];control_sides=set()
        for x in (-25,-20,-15,-10,-7.5,-5,-3,3,5,7.5,10,15,20,25):
            for z in (2.0,5.0):
                origin=matrix @ Vector((x,low-4,z));a=ray(old,origin,direction,distance);b=ray(new,origin,direction,distance)
                candidate_probes.append({'local_x_z':[x,z],'original_hit':a,'copy_hit':b})
                if a is not None:
                    if b is None or (Vector(a['point'])-Vector(b['point'])).length>=5e-4 or a['actual_slot']!=b['actual_slot']:
                        control_errors.append(candidate_probes[-1])
                    else:
                        controls.append({'local_x_z':[x,z],'original_hit':a['point'],'copy_solid_hit':b['point']});control_sides.add(-1 if x<0 else 1)
                elif b is not None:control_errors.append(candidate_probes[-1])
        assert not control_errors,'actual original-positive outside control changed '+original.name+' '+json.dumps(control_errors[:6])
        assert len(controls)>=4 and control_sides=={-1,1},'insufficient actual original-positive control sites '+original.name
        assert slots(obj)==slots(original),'prototype effective slots changed'
        results.append({'source_actor':original.name,'copy':obj.name,'coordinate_reexpression':rebase,'operation':operation,'topology':topo,
                        'void_rays':voids,'solid_controls':controls,'all_fixed_control_candidates':candidate_probes})
    assert cutter_world_before==digest([cutter.matrix_world,mesh_digest(cutter.data)]),'same world cutter changed between operations'
    return {'test_only_not_portal_location':True,'caller_width_spring_crown_metres':[4,4,6],
            'centre_is_994_raw_area_centroid':centre,'rotation_radians':angle,'local_record':record,
            'same_world_space_cutter_for_both_copies':True,'targets':results}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--native',type=Path,required=True);parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'results.json').exists():raise ValueError('refuse to overwrite actual prior report')
    inputs={str(p.resolve()):sha(p) for p in [args.native,args.data,Path(__file__),Path(F.__file__),Path(M.__file__),Path(M.R.__file__)]}
    assert sha(args.native)=='a19537c9ddcd37e4576c55410ca89bcad2203f6f6458711fc9d437b89f5f02bb'
    assert sha(args.data)=='06dfa30cbd6401d2b555b842c03dd47fa055a4de6024b4904b39cc2652a2248e'
    sources=sorted([obj for obj in bpy.context.scene.objects if obj.type=='MESH'],key=lambda obj:obj.name)
    assert len(sources)==6901,'this experiment requires frozen 6901-mesh V7 native'
    baseline={kind:{x.name for x in getattr(bpy.data,kind)} for kind in ['objects','meshes','collections','materials','cameras','curves','images','node_groups']}
    previous_active=bpy.context.view_layer.objects.active
    print('ACTUAL_NATIVE_DISCOVERY_BEGIN',flush=True)
    data=json.loads(args.data.read_text());records={x['id']:x for x in data['parts']}
    originals={}
    for sid in ['way-638156517-p0','way-638156505-p0','way-638157005-p0']:
        candidates=[obj for obj in bpy.data.collections['source_parts'].all_objects if obj.type=='MESH' and obj.get('source_building_id')==sid]
        assert len(candidates)==1,(sid,[x.name for x in candidates]);originals[sid]=candidates[0]
    def actual_refs(obj):
        value=obj.get('source_refs',[])
        return json.loads(value) if isinstance(value,str) else safe(value)
    walls=[obj for obj in sources if 'https://www.openstreetmap.org/way/638176319' in actual_refs(obj)]
    assert len(walls)==1,'must actually discover one wall by source_refs, not guess its actor name'
    wall=walls[0];print('ACTUAL_WALL_DISCOVERED',wall.name,flush=True)
    source_wall_topology={'actual_actor':wall.name,'raw':topology(wall,require_solid=False),
                          'evaluated':topology(wall,evaluated=True,require_solid=False),
                          'self_intersection_not_certified_by_edge_topology':True}
    (out/'source-wall-topology.json').write_text(json.dumps(source_wall_topology,ensure_ascii=False,indent=2)+'\n')
    print('SOURCE_WALL_TOPOLOGY',json.dumps(source_wall_topology),flush=True)
    ring=records['way-638156994-p0']['polygon'];centre=centroid(ring)
    edge=Vector((ring[1][0]-ring[0][0],ring[1][1]-ring[0][1]));angle=math.atan2(edge.y,edge.x)
    (out/'source-inputs.json').write_text(json.dumps({'input_sha256':inputs,'records':{sid:records[sid] for sid in ['way-638156517-p0','way-638156505-p0','way-638157005-p0','way-638156994-p0']},'actual_wall_discovery':{'source_url':'https://www.openstreetmap.org/way/638176319','actual_actor':wall.name,'original_custom_properties':safe(dict(wall.items()))},'prototype_test_only':{'width':4,'spring':4,'crown':6,'centre':centre,'no_historical_portal_location_claim':True}},ensure_ascii=False,indent=2)+'\n')
    before=source_fingerprints(sources,'before');(out/'source-fingerprints-before.json').write_text(json.dumps(before,ensure_ascii=False)+'\n')
    results=[]
    try:
        collection=bpy.data.collections.new('COPY_TECH_DISPOSABLE_ONLY');bpy.context.scene.collection.children.link(collection)
        for sid in ['way-638156517-p0','way-638156505-p0']:
            try:
                print('TRIAL_MASK_START',sid,flush=True)
                evidence=trial_mask(originals[sid],records[sid],ring,centre,angle,collection)
                results.append({'id':'COPY-01-'+sid,'status':'pass','evidence':evidence});print('TRIAL_MASK_PASS',sid,flush=True)
            except Exception:
                results.append({'id':'COPY-01-'+sid,'status':'fail','error':traceback.format_exc()});print(results[-1]['error'],flush=True)
        try:
            print('TRIAL_PROTOTYPE_START',flush=True)
            evidence=trial_prototype(originals['way-638157005-p0'],wall,centre,angle,collection)
            results.append({'id':'COPY-02','status':'pass','evidence':evidence});print('TRIAL_PROTOTYPE_PASS',flush=True)
        except Exception:
            results.append({'id':'COPY-02','status':'fail','error':traceback.format_exc()});print(results[-1]['error'],flush=True)
    finally:
        for kind in ['objects','meshes','collections','materials','cameras','curves','images','node_groups']:
            blocks=getattr(bpy.data,kind)
            for block in list(blocks):
                if block.name not in baseline[kind]:blocks.remove(block,do_unlink=True)
        bpy.context.view_layer.objects.active=previous_active;bpy.context.view_layer.update()
    after=source_fingerprints(sources,'after');(out/'source-fingerprints-after.json').write_text(json.dumps(after,ensure_ascii=False)+'\n')
    mismatches=[a['name'] for a,b in zip(before,after) if a!=b]
    same_inputs=all(sha(Path(p))==h for p,h in inputs.items())
    restored=all({x.name for x in getattr(bpy.data,kind)}==names for kind,names in baseline.items())
    guard={'id':'COPY-03-SOURCE-GUARD','status':'pass' if not mismatches and restored and same_inputs else 'fail',
           'evidence':{'original_mesh_count':len(sources),'per_actor_raw_eval_world_shader_slots_colour_source_visibility_unchanged':not mismatches,'mismatch_names':mismatches,'all_original_fingerprints_before_sha256':sha(out/'source-fingerprints-before.json'),'all_original_fingerprints_after_sha256':sha(out/'source-fingerprints-after.json'),'all_temporary_datablocks_removed':restored,'input_bytes_unchanged':same_inputs}}
    results.append(guard)
    report={'schema':'v8-source-copy-boolean-technical-experiment/1','summary':{'total':len(results),'passed':sum(x['status']=='pass' for x in results),'failed':sum(x['status']=='fail' for x in results)},'inputs_sha256':inputs,'actual_discovery':{'wall':wall.name,'parts':{sid:obj.name for sid,obj in originals.items()}},'results':results,'native_saved':False,'source_hidden_or_modified':bool(mismatches),'third_party_cost':0,'historical_gate_dimensions_or_route_certified':False,'human_approval':'pending','limitations':['Prototype W4/spring4/crown6 and centre994 are test-only, not an architectural gate schedule.','Mask subtraction is a technical source-copy option, not approval to delete or hide a whole wing.','Each Boolean uses a new data copy; frozen F/M remain unchanged.','Controlled cleanup threshold1e-6 is in object-local mesh coordinates; report includes actual world displacement.']}
    (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('COPY_BOOLEAN_SUMMARY',json.dumps(report['summary']),flush=True)
    if report['summary']['failed']:raise SystemExit(1)


if __name__=='__main__':main()
