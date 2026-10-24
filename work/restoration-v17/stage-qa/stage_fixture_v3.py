"""Root稍后在factory Blender执行；当前只做prepare-only，不读生成器算法。

实际证明全部来自evaluated vertices/loop triangles、actual materials与BVH。
角色key只定位对象；负控保留原有tags，改变真实mesh/transform/material。
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stage_geometry_kernel as K

EPS = 2e-4
CONTACT_INSET = .005


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_profile(p):
    require(p['building_id'] == 'shufang_large_stage', 'fixture requires one exact stage')
    for key, value in [('bays_x', 3), ('bays_y', 3), ('eaves_tiers', 2),
                       ('occupied_storeys', 1), ('reference_floor_count', 1)]:
        require(type(p[key]) is int and p[key] == value, key + ' exact integer contract')
    d = p['dimensions']
    for key in ('body_width_m', 'body_depth_m', 'column_radius_m', 'column_base_radius_m',
                'column_base_height_m', 'beam_width_m', 'beam_height_m'):
        require(type(d[key]) in (int, float) and math.isfinite(d[key]) and d[key] > 0, key + ' positive reference dimension')
    require(d['slab_bottom_z_m'] < d['floor_z_m'] < d['column_top_z_m'], 'reference vertical order')
    band = d['upper_band']
    require(band['occupied_floor'] is False, 'upper band must not be occupied floor')
    for k in ('width_m', 'depth_m', 'wall_thickness_m'):
        require(type(band[k]) in (int, float) and math.isfinite(band[k]) and band[k] > 0, 'upper band ' + k)
    require(band['wall_thickness_m'] * 2 < min(band['width_m'], band['depth_m']), 'upper band has real void')
    tiers = p['roof_tiers']
    require(len(tiers) == 2 and [r['tier_index'] for r in tiers] == [0, 1], 'two ordered roofs')
    for r in tiers:
        for k in ('outer_width_m', 'outer_depth_m', 'skin_thickness_m', 'curve_power'):
            require(type(r[k]) in (int, float) and math.isfinite(r[k]) and r[k] > 0, 'roof positive ' + k)
        require(all(type(r[k]) in (int,float) and math.isfinite(r[k]) for k in ('top_z_m','eave_z_m','corner_lift_m'))
                and r['top_z_m'] > r['eave_z_m'] and r['corner_lift_m'] >= 0, 'roof reference heights')
    require(0 < tiers[0]['inner_width_m'] < tiers[0]['outer_width_m'] and
            0 < tiers[0]['inner_depth_m'] < tiers[0]['outer_depth_m'], 'lower must be annular')
    require(tiers[1]['inner_width_m'] == tiers[1]['inner_depth_m'] == 0, 'upper must be full central cap')
    return True


def preflight(bindings, allow_pending=False):
    require(bindings['schema'] == 'v17-stage-independent-qa-bindings/1', 'binding schema')
    missing = []
    for stem in ('module', 'profile', 'source_support', 'palette'):
        path, digest = bindings.get(stem + '_path'), bindings.get(stem + '_sha256')
        if path is None or digest is None:
            missing.append(stem + '_path/sha256')
        else:
            require(isinstance(digest, str) and len(digest) == 64 and
                    all(c in '0123456789abcdef' for c in digest), stem + ' must have exact SHA256')
            require(sha(path) == digest, stem + ' immutable input SHA drift')
    if bindings.get('profile_selector') is None:
        missing.append('profile_selector')
    for role in ('columns', 'bases', 'beams', 'band_walls', 'band_rim', 'band_crossbeams', 'rail_panels'):
        value = bindings['component_keys'].get(role)
        if not value:
            missing.append('component_keys.' + role)
    if missing:
        require(allow_pending, 'Final inputs not pinned: ' + ', '.join(missing))
        return {'status': 'PENDING_FINAL_INPUT_SHA_AND_ROLE_KEYS', 'missing': missing,
                'Blender_launched': False, 'geometry_verified': False}
    require(bindings['status'] == 'final_inputs_pinned', 'binding must explicitly be final_inputs_pinned')
    require(bindings.get('transitive_source_sha256'), 'explicit direct/transitive module dependencies must also be pinned')
    for path,digest in bindings['transitive_source_sha256'].items():
        require(sha(path)==digest,'transitive module input SHA drift '+path)
    return {'status': 'READY_FOR_ROOT_FACTORY_BLENDER_EXECUTION', 'geometry_verified': False}


def select_profile(doc, selector):
    require(isinstance(selector, list), 'profile_selector must be an explicit key/index path')
    for key in selector:
        doc = doc[key]
    validate_profile(doc)
    return doc


def execute(bindings, out):
    # 本函数只有root用真正Blender启动且final四输入SHA完整时才可达。
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    preflight(bindings)
    require(not bpy.data.filepath, 'Factory-startup only; opening any city native is forbidden')
    require(not out.exists(), 'Use a fresh stage-qa output directory; never overwrite an original red')
    require(out.is_relative_to(HERE), 'Outputs must stay in independent stage-qa directory')
    out.mkdir(parents=True)
    profile = select_profile(json.loads(Path(bindings['profile_path']).read_text()), bindings['profile_selector'])
    source = json.loads(Path(bindings['source_support_path']).read_text())
    production_source=source['source_status']=='actual_source_capture_not_official_measurement'
    if production_source:
        require(source['source_part_id'] == 'way-40632241-p0' and source['source_component'] == 'source_north_projection', 'source target identity')
    else:
        require(source['source_status']=='independent_synthetic_fixture_not_production_source'
                and source['source_part_id']=='qa-private-rectangle'
                and bindings.get('execution_scope')=='private_fixture_only_not_production_source_proof',
                'synthetic source must be unmistakably private fixture scope')
    require(not source['holes_local_xy'], 'This simple source fixture must not silently ignore holes')
    require(source['provenance_path'] and sha(source['provenance_path']) == source['provenance_sha256'], 'independent source provenance drift')
    require(abs(source['floor_z_m'] - profile['dimensions']['floor_z_m']) < EPS, 'source cap z must share declared reference floor')
    source_triangles = K.triangulate_polygon(source['outer_local_xy'])
    palette_spec = json.loads(Path(bindings['palette_path']).read_text())['materials']
    collection = bpy.data.collections.new('V17_STAGE_INDEPENDENT_FIXTURE_ONLY')
    bpy.context.scene.collection.children.link(collection)
    materials = {}
    for key, state in palette_spec.items():
        m = bpy.data.materials.new('V17QA_' + key)
        m.diffuse_color = state['rgba']; m.use_nodes = True
        node = m.node_tree.nodes.get('Principled BSDF')
        node.inputs['Base Color'].default_value = state['rgba']
        node.inputs['Metallic'].default_value = state.get('metallic', 0)
        node.inputs['Roughness'].default_value = state.get('roughness', .5)
        materials[key] = m
    spec = importlib.util.spec_from_file_location('stage_module_under_test', bindings['module_path'])
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(bindings['module_path']).resolve().parent))
    spec.loader.exec_module(module)
    (out/'execution-input-receipt.json').write_text(json.dumps({'bindings':bindings,
        'fixture_sha256':sha(Path(__file__)),'kernel_sha256':sha(HERE/'stage_geometry_kernel.py'),
        'production_source':production_source,'city_native_opened':False},ensure_ascii=False,indent=2)+'\n')
    try:
        result = module.build_stage(copy.deepcopy(profile), collection, materials=materials, mesh_cache={})
    except Exception as exc:
        (out/'initial-build-red.json').write_text(json.dumps({'passed':False,'error':str(exc),
            'traceback':traceback.format_exc(),'production_source':production_source},ensure_ascii=False,indent=2)+'\n')
        raise
    require(set(('root', 'objects', 'components', 'openings', 'roofs', 'reference_floor', 'roof_contacts', 'profile')) <= set(result), 'public result API')
    require(result['openings'] == [], 'No unverified opening or door leaf schedule may be invented')

    def object_ref(ref):
        return bpy.data.objects[ref] if isinstance(ref, str) else ref

    def unique_objects(seq):
        return list({o.name: o for o in map(object_ref, seq)}.values())

    def roles():
        out = {}
        for role, keys in bindings['component_keys'].items():
            keys = [keys] if isinstance(keys, str) else keys
            require(isinstance(keys, list) and keys, 'explicit component role ' + role)
            out[role] = unique_objects([o for key in keys for o in result['components'][key]])
        return out

    def roof_objects():
        return [object_ref(r[bindings['roof_object_key']]) for r in result['roofs']]

    def snapshot(world=False):
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        inv = result['root'].matrix_world.inverted()
        meshes = {}
        for o in unique_objects(result['objects']):
            if o.type != 'MESH':
                continue
            evaluated = o.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            try:
                mesh.calc_loop_triangles()
                vertices = [list(evaluated.matrix_world @ v.co) if world else
                            list(inv @ (evaluated.matrix_world @ v.co)) for v in mesh.vertices]
                mats = []
                for m in mesh.materials:
                    require(m is not None, 'actual empty material slot ' + o.name)
                    bs = m.node_tree.nodes.get('Principled BSDF') if m.use_nodes and m.node_tree else None
                    mats.append({'name': m.name, 'diffuse': list(m.diffuse_color),
                                 'shader': list(bs.inputs['Base Color'].default_value) if bs else None})
                meshes[o.name] = {'vertices': vertices, 'triangles': [list(t.vertices) for t in mesh.loop_triangles],
                                  'material_indices': [t.material_index for t in mesh.loop_triangles], 'materials': mats,
                                  'hidden': bool(o.hide_render or o.hide_get())}
            finally:
                evaluated.to_mesh_clear()
        return meshes

    def tree(mesh):
        return BVHTree.FromPolygons([Vector(v) for v in mesh['vertices']], mesh['triangles'], all_triangles=True)

    def merged_tree(meshes, names):
        verts, faces = [], []
        for name in names:
            mesh = meshes[name]; offset = len(verts)
            verts.extend(Vector(v) for v in mesh['vertices'])
            faces.extend(tuple(offset + i for i in f) for f in mesh['triangles'])
        require(bool(faces), 'actual query requires nonempty evaluated faces')
        return BVHTree.FromPolygons(verts, faces, all_triangles=True)

    def height(mesh_tree, x, y, high):
        hit = mesh_tree.ray_cast(Vector((x, y, high)), Vector((0, 0, -1)), 100)[0]
        return None if hit is None else hit.z

    def assert_cover(subject, cover, label):
        e = K.triangle_union_uncovered(subject, cover)
        require(e['subject_area_m2'] > 1e-8, label + ' actual cap absent')
        e['allowed_uncovered_area_m2']=max(2e-6,e['subject_area_m2']*2e-6,e['subject_boundary_perimeter_m']*EPS*2)
        require(e['uncovered_area_m2'] <= e['allowed_uncovered_area_m2'], label + ' uncovered full-cap area ' + str(e))
        return e

    def full_cap_contacts(meshes):
        role = roles(); cols, bases = role['columns'], role['bases']
        require(len(cols) == len(bases) == 16, 'exact 16 actual main columns and bases')
        centres = {}
        for obj in cols:
            lo, hi = K.bounds(meshes[obj.name]['vertices'])
            centres[obj.name] = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2)
        xs = K.clustered_axes([v[0] for v in centres.values()]); ys = K.clustered_axes([v[1] for v in centres.values()])
        require(len(xs) == len(ys) == 4 and len(set(centres.values())) == 16, 'actual strict 4 by 4 axes')
        cells=[(min(range(4),key=lambda i:abs(x-xs[i])),min(range(4),key=lambda i:abs(y-ys[i]))) for x,y in centres.values()]
        require(set(cells)=={(i,j) for i in range(4) for j in range(4)} and len(cells)==16, 'all 16 grid combinations required')
        require(abs(xs[-1]-xs[0]-profile['dimensions']['body_width_m'])<8e-4
                and abs(ys[-1]-ys[0]-profile['dimensions']['body_depth_m'])<8e-4,'actual full axis spans must equal declared body width/depth')
        for values in (xs, ys):
            gaps = [b - a for a, b in zip(values, values[1:])]
            require(max(gaps) - min(gaps) < 5e-4 and min(gaps) > 0, 'actual axes must be uniform')
        floor = meshes[object_ref(result['reference_floor']).name]
        floor_z = profile['dimensions']['floor_z_m']
        floor_top = K.horizontal_triangles(floor, floor_z, EPS, direction=1)
        floor_bvh = tree(floor)
        all_beams = unique_objects(role['beams'] + role['band_rim'] + role['band_crossbeams'])
        require(len(all_beams)==12 and len(role['band_walls'])==4,'actual outer4/cross4/rim4 beams and four band walls')
        beam_tree = merged_tree(meshes, [o.name for o in all_beams])
        contact_records, outer, inner = [], 0, 0
        for col in cols:
            c = meshes[col.name]; low, high = K.bounds(c['vertices']); x, y = centres[col.name]
            boundary = min(abs(x - xs[0]), abs(x - xs[-1]), abs(y - ys[0]), abs(y - ys[-1])) < 5e-4
            outer += int(boundary); inner += int(not boundary)
            matches = []
            for base in bases:
                a, b = K.bounds(meshes[base.name]['vertices'])
                if abs((a[0] + b[0]) / 2 - x) < EPS and abs((a[1] + b[1]) / 2 - y) < EPS:
                    matches.append((base, a, b))
            require(len(matches) == 1, 'base matched by actual XY, not support tag')
            base, a, b = matches[0]
            require(abs(a[2] - floor_z) < EPS and abs(low[2] - b[2]) < EPS, 'actual base/column vertical contact')
            foot = K.horizontal_triangles(meshes[base.name], a[2], EPS)
            base_top = K.horizontal_triangles(meshes[base.name], b[2], EPS, direction=1)
            bottom = K.horizontal_triangles(c, low[2], EPS)
            cap = K.horizontal_triangles(c, high[2], EPS)
            e1 = assert_cover(foot, floor_top, 'base bottom ' + base.name)
            for tri in foot:
                for point in tri:
                    hit=floor_bvh.ray_cast(Vector((point[0],point[1],a[2]+.02)),Vector((0,0,-1)),.04)[0]
                    require(hit is not None and abs(hit.z-a[2])<EPS,'actual base rim BVH misses slab '+base.name)
            e2 = assert_cover(bottom, base_top, 'column bottom ' + col.name)
            support = []
            allowed = role['beams'] if boundary else role['band_rim'] + role['band_crossbeams']
            for beam in allowed:
                bm = meshes[beam.name]
                for f in bm['triangles']:
                    tri = [bm['vertices'][i] for i in f]
                    if K.normal(tri)[2] < -.99 and all(high[2] - CONTACT_INSET - EPS <= v[2] <= high[2] + EPS for v in tri):
                        support.append([v[:2] for v in tri])
            e3 = assert_cover(cap, support, 'complete column top ' + col.name)
            for tri in cap:
                for point in tri + [(sum(p[0] for p in tri)/3, sum(p[1] for p in tri)/3)]:
                    hit = beam_tree.ray_cast(Vector((point[0], point[1], high[2] - .02)), Vector((0, 0, 1)), .05)[0]
                    require(hit is not None and -CONTACT_INSET - EPS <= hit.z - high[2] <= EPS, 'actual BVH cap contact ' + col.name)
            if boundary:
                require(abs(high[2] - profile['dimensions']['column_top_z_m']) < EPS, 'outer column top reference z')
            else:
                require(high[2] > profile['dimensions']['column_top_z_m'] + EPS, 'inner four must reach upper rim support')
            contact_records.append({'column': col.name, 'outer': boundary, 'base_bottom': e1,
                                    'column_bottom': e2, 'column_top': e3, 'actual_top_z_m': high[2]})
        require(outer == 12 and inner == 4, 'actual outer12 + inner4')
        band_records=[]
        z=profile['dimensions']['upper_band']['bottom_z_m'];beam_tops=[]
        for beam in all_beams:beam_tops.extend(K.horizontal_triangles(meshes[beam.name],z,EPS,direction=1))
        for wall in role['band_walls']:
            lo,hi=K.bounds(meshes[wall.name]['vertices']);require(abs(lo[2]-z)<EPS,'band wall bottom reference z')
            e=assert_cover(K.horizontal_triangles(meshes[wall.name],lo[2],EPS),beam_tops,'upper band wall bottom '+wall.name)
            band_records.append({'wall':wall.name,'actual_full_bottom_cap':e})
        return {'outer': outer, 'inner': inner, 'actual_axes_x': xs, 'actual_axes_y': ys,
                'contacts': contact_records,'four_band_wall_full_bottom_contacts':band_records}

    def source_coverage(meshes):
        floor = meshes[object_ref(result['reference_floor']).name]
        top = K.horizontal_triangles(floor, source['floor_z_m'], EPS, direction=1)
        return assert_cover(source_triangles, top, 'complete source footprint floor cap')

    def topology(meshes):
        records=[]
        for name,m in meshes.items():
            edges={};volume=0.0
            require(not m['hidden'],'owned geometry hidden from actual view '+name)
            for face in m['triangles']:
                a,b,c=[m['vertices'][i] for i in face]
                require(sum(x*x for x in K.normal([a,b,c]))>.99,'actual degenerate triangle '+name)
                for i,j in zip(face,face[1:]+face[:1]):
                    key=tuple(sorted((i,j)));edges[key]=edges.get(key,0)+1
                volume+=(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6
            require(edges and all(n==2 for n in edges.values()),'actual nonmanifold triangle edges '+name)
            require(volume>1e-9,'actual nonpositive closed volume '+name)
            records.append({'object':name,'actual_triangles':len(m['triangles']),'actual_signed_volume_m3':volume})
        return {'actual_closed_owned_meshes':len(records),'records':records}

    def roofs_geometry(meshes):
        roofs = roof_objects(); require(len(roofs) == 2, 'actual two roof objects')
        lower, upper = [meshes[o.name] for o in roofs]
        records = []
        for mesh, row in zip((lower, upper), profile['roof_tiers']):
            lo, hi = K.bounds(mesh['vertices'])
            require(abs(hi[0] - lo[0] - row['outer_width_m']) < 5e-4 and
                    abs(hi[1] - lo[1] - row['outer_depth_m']) < 5e-4, 'actual rectangular roof footprint')
            records.append({'actual_bounds': [lo, hi], 'declared_tier': row['tier_index']})
        ltree, utree = tree(lower), tree(upper)
        lr, ur = profile['roof_tiers']
        for fx, fy in ((0,0), (.8,0),(-.8,0),(0,.8),(0,-.8),(.75,.75),(-.75,-.75)):
            require(height(ltree, fx*lr['inner_width_m']/2, fy*lr['inner_depth_m']/2, lr['top_z_m']+2) is None, 'lower actual annular hole closed')
        for fx, fy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1)):
            x = fx * (lr['inner_width_m'] + lr['outer_width_m']) / 4
            y = fy * (lr['inner_depth_m'] + lr['outer_depth_m']) / 4
            require(height(ltree,x,y,lr['top_z_m']+2) is not None, 'lower annular roof missing real sector')
        apex = K.apex_from_actual_vertices(upper)
        require(apex['unique_maximum_xy_count'] == 1 and
                max(abs(x) for x in apex['maximum_xy_centre_m']) < 5e-4, 'upper must have one central actual apex, not long ridge')
        require(abs(apex['max_z_m'] - ur['top_z_m']) < 5e-4, 'actual upper apex height')
        radii = (.25,.5,.75)
        samples = []
        for radius in radii:
            zs = [height(utree,x,y,ur['top_z_m']+2) for x,y in
                  ((radius*ur['outer_width_m']/2,0),(-radius*ur['outer_width_m']/2,0),
                   (0,radius*ur['outer_depth_m']/2),(0,-radius*ur['outer_depth_m']/2))]
            require(all(z is not None for z in zs) and max(zs)-min(zs)<.002, 'actual four-way normalized slopes disagree')
            require(max(zs) < apex['max_z_m'] - EPS, 'upper ridge plateau not allowed')
            samples.append(zs)
        require(all(samples[i][0] > samples[i+1][0] for i in range(2)), 'actual roof rises toward one centre')
        return {'lower_hole_actual_BVH_probes':7,'annular_positive_controls':6,'upper_apex':apex,
                'four_way_actual_BVH_samples':samples,'actual_roofs':records}

    def no_upper_floor(meshes):
        band = profile['dimensions']['upper_band']; floor_z = profile['dimensions']['floor_z_m']
        candidates = {}
        roof_names = {o.name for o in roof_objects()}
        floor_name = object_ref(result['reference_floor']).name
        for name, mesh in meshes.items():
            if name in roof_names or name == floor_name:
                continue
            for face in mesh['triangles']:
                tri = [mesh['vertices'][i] for i in face]
                if abs(K.normal(tri)[2]) > .99 and max(v[2] for v in tri)-min(v[2] for v in tri)<EPS:
                    z = sum(v[2] for v in tri)/3
                    if floor_z+1 < z < profile['roof_tiers'][1]['eave_z_m']+.02:
                        candidates.setdefault(round(z,3),[]).append([v[:2] for v in tri])
        w = (band['width_m']/2-band['wall_thickness_m'])*.92
        d = (band['depth_m']/2-band['wall_thickness_m'])*.92
        square = K.triangulate_polygon([[-w,-d],[w,-d],[w,d],[-w,d]])
        levels=[]
        for z, faces in candidates.items():
            e=K.triangle_union_uncovered(square,faces)
            require(e['coverage_fraction'] < .9, 'unapproved broad occupied upper floor at z='+str(z))
            levels.append({'actual_z_m':z,'upper_interior_horizontal_coverage':e['coverage_fraction']})
        return {'actual_reference_floor_count':1,'extra_upper_floor_detected':False,'actual_horizontal_levels':levels}

    def colors_and_no_false_leaf(meshes):
        role=roles(); checked_columns=0; checked_roof_faces=0
        for col in role['columns']:
            m=meshes[col.name]
            for mi in set(m['material_indices']):
                state=m['materials'][mi]
                require(K.green(state['diffuse']) and state['shader'] is not None and K.green(state['shader']), 'actual rendered column not green '+col.name)
            checked_columns+=1
        for obj in roof_objects():
            m=meshes[obj.name]
            for face,mi in zip(m['triangles'],m['material_indices']):
                tri=[m['vertices'][i] for i in face]
                if K.normal(tri)[2]>.1:
                    state=m['materials'][mi]
                    require(K.yellow(state['diffuse']) and state['shader'] is not None and K.yellow(state['shader']), 'actual exposed roof face not yellow '+obj.name)
                    checked_roof_faces+=1
        for obj in role.get('roof_details',[]):
            m=meshes[obj.name]
            for mi in set(m['material_indices']):
                state=m['materials'][mi]
                require(K.yellow(state['diffuse']) and state['shader'] is not None and K.yellow(state['shader']),
                        'actual grouped roof detail not yellow '+obj.name)
        require(checked_roof_faces>0,'no actual yellow top faces checked')
        for obj in result['objects']:
            require(obj.get('leaf_count') is None and obj.get('door_leaf_count') is None
                    and obj.get('window_leaf_count') is None,'invented known leaf count '+obj.name)
        # 栏杆是24根示意构件+6柱，不当作24叶或24块有史料计数的门窗。
        require(len(role.get('rail_posts',[]))==6,'six actual illustration posts for three front groups')
        grouped={0:[],1:[],2:[]}
        dims=profile['dimensions'];pitch=dims['body_width_m']/3
        for obj in role['rail_panels']:
            lo,hi=K.bounds(meshes[obj.name]['vertices']);x=(lo[0]+hi[0])/2
            i=max(0,min(2,int((x+dims['body_width_m']/2)/pitch)))
            require(lo[0]>=-dims['body_width_m']/2+i*pitch-EPS and hi[0]<=-dims['body_width_m']/2+(i+1)*pitch+EPS,'railing leaves its actual bay')
            grouped[i].append([lo,hi])
        require(all(grouped.values()) and all(any(hi[0]-lo[0]>.5*pitch for lo,hi in group) for group in grouped.values()),'actual three front railing groups with horizontal spans')
        all_tree=merged_tree(meshes,list(meshes)); dims=profile['dimensions']
        rail_top=max(K.bounds(meshes[o.name]['vertices'])[1][2] for o in role['rail_panels'])
        zvalues=[rail_top+.12, (rail_top+dims['column_top_z_m'])/2, dims['column_top_z_m']-.2]
        ray_count=0
        for z in zvalues:
            require(z<dims['column_top_z_m'],'railing must leave open pavilion bay above')
            for i in range(3):
                x=(i-1)*dims['body_width_m']/3
                hit=all_tree.ray_cast(Vector((x,-dims['body_depth_m']/2-.5,z)),Vector((0,1,0)),1.0)[0]
                require(hit is None,'actual unverified front leaf/opaque panel blocks open bay')
                ray_count+=1
        return {'actual_green_columns':checked_columns,'actual_yellow_top_triangles':checked_roof_faces,
                'actual_front_void_rays':ray_count,'invented_leaf_count':False}

    checks=[]
    def case(ident,label,fn,negative=False):
        try:
            evidence=fn()
            checks.append({'id':ident,'operation':label,'passed':not negative,'evidence':evidence,
                           'negative_rejected':False} if negative else
                          {'id':ident,'operation':label,'passed':True,'evidence':evidence})
        except Exception as exc:
            checks.append({'id':ident,'operation':label,'passed':negative,'negative_rejected':negative,
                           'error':str(exc),'traceback':traceback.format_exc()})
        print(('PASS' if checks[-1]['passed'] else 'FAIL'),ident,label,flush=True)

    original=snapshot()
    direct_world={'schema':'v17-stage-direct-evaluated-world-baseline/1',
        'coordinate_space':'world',
        'capture_method':'direct_evaluated_matrix_world_times_mesh_vertex_not_local_reprojection',
        'building_id':profile['building_id'],'source_part_id':source['source_part_id'],
        'source_component_id':source.get('source_component'),
        'reference_floor_object':object_ref(result['reference_floor']).name,
        'actual_root_matrix_world':[list(row) for row in result['root'].matrix_world],
        'input_sha256':{k:bindings[k+'_sha256'] for k in ('module','profile','source_support','palette')},
        'fixture_sha256':sha(Path(__file__)),'kernel_sha256':sha(HERE/'stage_geometry_kernel.py'),
        'meshes':snapshot(world=True),'production_source_verified':False}
    world_path=out/'actual-evaluated-world-baseline.json'
    world_path.write_text(json.dumps(direct_world,ensure_ascii=False)+'\n')
    case('ACTUAL-00','actual evaluated owned meshes are visible, manifold, nondegenerate, positive volume',lambda:topology(snapshot()))
    case('ACTUAL-01','16 evaluated columns: full bottom/top cap union and independent BVH contacts',lambda:full_cap_contacts(snapshot()))
    case('ACTUAL-02','full captured source footprint supported by actual floor triangles',lambda:source_coverage(snapshot()))
    case('ACTUAL-03','actual lower annular hole + upper rectangular four-way single apex',lambda:roofs_geometry(snapshot()))
    case('ACTUAL-04','two roofs and one floor with no extra upper slab',lambda:no_upper_floor(snapshot()))
    case('ACTUAL-05','actual face materials and no false leaf/opaque front infill',lambda:colors_and_no_false_leaf(snapshot()))
    # 负控只修改真实对象。保持所有原物体custom properties；恢复后再核逐字节快照。
    tags_before={o.name:{k:str(o[k]) for k in o.keys()} for o in result['objects']}
    original_geometry_sha=hashlib.sha256(json.dumps(original,sort_keys=True).encode()).hexdigest()
    original_tags_sha=hashlib.sha256(json.dumps(tags_before,sort_keys=True).encode()).hexdigest()
    mutation_states=[]
    original_data={o.name:o.data for o in unique_objects(result['objects'])}
    def transform_channels(obj):
        return {'matrix_basis':[list(row) for row in obj.matrix_basis],
                'matrix_local':[list(row) for row in obj.matrix_local],
                'matrix_world':[list(row) for row in obj.matrix_world],
                'location':list(obj.location),'scale':list(obj.scale),
                'rotation_mode':obj.rotation_mode,'rotation_euler':list(obj.rotation_euler),
                'rotation_quaternion':list(obj.rotation_quaternion),
                'rotation_axis_angle':list(obj.rotation_axis_angle)}
    original_transform_channels={o.name:transform_channels(o) for o in unique_objects(result['objects'])}
    restore_diagnostics=[]
    def snapshot_difference(before,after):
        names=sorted(set(before)|set(after));rows=[]
        for name in names:
            if before.get(name)==after.get(name):continue
            if name not in before or name not in after:
                rows.append({'object':name,'added':name not in before,'removed':name not in after});continue
            a,b=before[name],after[name]
            fields=[k for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]
            av,bv=a['vertices'],b['vertices']
            delta=max((abs(x-y) for v,w in zip(av,bv) for x,y in zip(v,w)),default=0) if len(av)==len(bv) else None
            rows.append({'object':name,'changed_fields':fields,'max_abs_vertex_delta_m':delta,
                         'after_changed_record':b})
        return rows
    def post_restore(ident,detail=None):
        actual=snapshot();actual_world=snapshot(world=True)
        objects=unique_objects(result['objects'])
        local_diff=snapshot_difference(original,actual)
        world_diff=snapshot_difference(direct_world['meshes'],actual_world)
        transforms={o.name:transform_channels(o) for o in objects}
        changed_transforms={n:{'before':original_transform_channels.get(n),'after':row}
                            for n,row in transforms.items() if original_transform_channels.get(n)!=row}
        changed_data=[o.name for o in objects if o.name not in original_data or o.data is not original_data[o.name]]
        row={'mutant_id':ident,'exact_local_snapshot_restored':actual==original,
             'exact_world_snapshot_restored':actual_world==direct_world['meshes'],
             'tags_restored':tags_same(),'original_data_pointers_restored':not changed_data,
             'changed_data_objects':changed_data,'changed_transforms':changed_transforms,
             'local_snapshot_differences':local_diff,'world_snapshot_differences':world_diff,
             'after_local_sha256':hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest(),
             'after_world_sha256':hashlib.sha256(json.dumps(actual_world,sort_keys=True).encode()).hexdigest(),
             'restore_detail':detail}
        restore_diagnostics.append(row)
        (out/'restore-diagnostics.json').write_text(json.dumps({'schema':'v17-stage-mutant-exact-restore-diagnostics/1',
            'fixture_sha256':sha(Path(__file__)),'records':restore_diagnostics},ensure_ascii=False,indent=2)+'\n')
        print('RESTORE-DIAGNOSTIC',ident,'local_exact='+str(row['exact_local_snapshot_restored']),
              'world_exact='+str(row['exact_world_snapshot_restored']),flush=True)
    def tags_same():
        return tags_before=={o.name:{k:str(o[k]) for k in o.keys()} for o in result['objects'] if o.name in tags_before}
    def changed():
        mutated=snapshot();require(mutated!=original,'negative did not change actual evaluated state')
        require(tags_same(),'negative changed original tags instead of geometry')
        mutation_states.append({'index':len(mutation_states)+1,'before_actual_geometry_sha256':original_geometry_sha,
            'after_actual_geometry_sha256':hashlib.sha256(json.dumps(mutated,sort_keys=True).encode()).hexdigest(),
            'original_tags_sha256_unchanged':original_tags_sha})

    upper=roof_objects()[1]; old_data=upper.data
    ur=profile['roof_tiers'][1]; w,d=ur['outer_width_m']/2,ur['outer_depth_m']/2
    z,peak=ur['eave_z_m'],ur['top_z_m']
    points=[[-w,-d,z],[w,-d,z],[w,d,z],[-w,d,z],[-w*.55,0,peak],[w*.55,0,peak]]
    faces=[(0,1,5),(0,5,4),(1,2,5),(2,3,4),(2,4,5),(3,0,4),(3,2,1,0)]
    to_object=upper.matrix_world.inverted()@result['root'].matrix_world
    points=[to_object@Vector(p) for p in points]
    bad=bpy.data.meshes.new('QA_MUTANT_LONG_RIDGE');bad.from_pydata(points,[],faces);bad.update()
    for m in old_data.materials:bad.materials.append(m)
    upper.data=bad
    changed();case('EXTRA-GEO-01','keep tags, replace actual upper roof by long-ridge mesh',lambda:roofs_geometry(snapshot()),True)
    upper.data=old_data;bpy.data.meshes.remove(bad)
    post_restore('EXTRA-GEO-01')

    band=profile['dimensions']['upper_band'];z=band['bottom_z_m']+.15
    w,d=band['width_m']*.45,band['depth_m']*.45
    verts=[[-w,-d,z],[w,-d,z],[w,d,z],[-w,d,z]]
    bad=bpy.data.meshes.new('QA_MUTANT_EXTRA_UPPER_FLOOR');bad.from_pydata(verts,[],[(0,1,2,3)]);bad.update()
    obj=bpy.data.objects.new('QA_MUTANT_UNTAGGED_SLAB',bad);collection.objects.link(obj);obj.parent=result['root']
    bad.materials.append(next(iter(materials.values())));result['objects'].append(obj)
    changed();case('EXTRA-GEO-02','keep original tags, add real untagged upper floor plane',lambda:no_upper_floor(snapshot()),True)
    result['objects'].remove(obj);bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(bad)
    post_restore('EXTRA-GEO-02')

    floor=object_ref(result['reference_floor']);old_data=floor.data
    eval_obj=floor.evaluated_get(bpy.context.evaluated_depsgraph_get());eval_mesh=eval_obj.to_mesh();eval_mesh.calc_loop_triangles()
    verts=[tuple(v.co) for v in eval_mesh.vertices];all_faces=[tuple(t.vertices) for t in eval_mesh.loop_triangles]
    inv=result['root'].matrix_world.inverted()
    drop=None
    for i,f in enumerate(all_faces):
        tri=[list(inv@(floor.matrix_world@Vector(verts[k]))) for k in f]
        if K.normal(tri)[2]>.99 and all(abs(v[2]-source['floor_z_m'])<EPS for v in tri):
            overlap=K.triangle_union_uncovered(source_triangles,[[v[:2] for v in tri]])
            if overlap['coverage_fraction']>1e-5:drop=i;break
    eval_obj.to_mesh_clear();require(drop is not None,'no source-support floor triangle found for real negative')
    bad=bpy.data.meshes.new('QA_MUTANT_MISSING_SOURCE_CAP_TRIANGLE');bad.from_pydata(verts,[],[f for i,f in enumerate(all_faces) if i!=drop]);bad.update()
    for m in old_data.materials:bad.materials.append(m)
    floor.data=bad
    changed();case('EXTRA-GEO-03','keep tags, remove actual source-support top triangle',lambda:source_coverage(snapshot()),True)
    floor.data=old_data;bpy.data.meshes.remove(bad)
    post_restore('EXTRA-GEO-03')

    col=roles()['columns'][0];basis=col.matrix_basis.copy();channels=transform_channels(col)
    col.location.x+=.27
    changed();case('EXTRA-GEO-04','keep tags, move actual main column away from 4x4 axes/support',lambda:full_cap_contacts(snapshot()),True)
    col.matrix_basis=basis
    col.location=channels['location'];col.scale=channels['scale'];col.rotation_mode=channels['rotation_mode']
    if col.rotation_mode=='QUATERNION':col.rotation_quaternion=channels['rotation_quaternion']
    elif col.rotation_mode=='AXIS_ANGLE':col.rotation_axis_angle=channels['rotation_axis_angle']
    else:col.rotation_euler=channels['rotation_euler']
    post_restore('EXTRA-GEO-04',{'old_matrix_basis':channels['matrix_basis'],
        'legacy_matrix_local_before':channels['matrix_local'],
        'legacy_local_vs_basis_max_abs':max(abs(a-b) for x,y in zip(channels['matrix_local'],channels['matrix_basis']) for a,b in zip(x,y)),
        'exact_saved_channels_reapplied':True})

    col=roles()['columns'][0];old_data=col.data;new_data=old_data.copy();col.data=new_data
    wrong=bpy.data.materials.new('QA_MUTANT_RED_COLUMN');wrong.diffuse_color=(.65,.015,.02,1);wrong.use_nodes=True
    wrong.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.65,.015,.02,1)
    for i in range(len(new_data.materials)):new_data.materials[i]=wrong
    changed();case('EXTRA-GEO-05','keep tags, change real column material to red',lambda:colors_and_no_false_leaf(snapshot()),True)
    col.data=old_data;bpy.data.meshes.remove(new_data);bpy.data.materials.remove(wrong)
    post_restore('EXTRA-GEO-05')

    # 额外反例：不增加leaf tags、不改空openings，只插入真实不透明门状片。
    dd=profile['dimensions'];w=dd['body_width_m']/3*.4;y=-dd['body_depth_m']/2
    z0,z1=dd['floor_z_m']+.1,dd['floor_z_m']+2.3
    bad=bpy.data.meshes.new('QA_MUTANT_UNTAGGED_LEAF');bad.from_pydata([[-w,y,z0],[w,y,z0],[w,y,z1],[-w,y,z1]],[],[(0,1,2,3)]);bad.update()
    obj=bpy.data.objects.new('QA_MUTANT_UNTAGGED_OPAQUE_PANEL',bad);collection.objects.link(obj);obj.parent=result['root']
    bad.materials.append(next(iter(materials.values())));result['objects'].append(obj)
    changed();case('EXTRA-GEO-06','keep empty openings/tags, add real opaque untagged front leaf',lambda:colors_and_no_false_leaf(snapshot()),True)
    result['objects'].remove(obj);bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(bad)
    post_restore('EXTRA-GEO-06')

    case('RESTORE-GUARD','all six real geometry/material mutants restored actual baseline and tags',
         lambda:require(snapshot()==original and tags_same(),'mutation restore changed actual baseline'))
    input_hashes={k:bindings[k+'_sha256'] for k in ('module','profile','source_support','palette')}
    case('INPUT-GUARD','final module/profile/source/palette SHA unchanged',lambda:preflight(bindings))
    report={'schema':'v17-stage-actual-evaluated-geometry-qa/2','checks':checks,
            'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),
            'input_sha256':input_hashes,'fixture_sha256':sha(Path(__file__)),
            'kernel_sha256':sha(HERE/'stage_geometry_kernel.py'),'city_native_opened':False,
            'scene_saved':False,'rendered':False,'generator_geometry_helpers_imported_for_expected':False,
            'production_source_input':production_source,
            'actual_production_source_verified':False,
            'strict_world_source_check_required':production_source,
            'preliminary_source_area_coverage_passed':production_source and next(x['passed'] for x in checks if x['id']=='ACTUAL-02'),
            'direct_world_baseline_path':str(world_path),'direct_world_baseline_sha256':sha(world_path),
            'module_geometry_verified':all(x['passed'] for x in checks),'source_coverage_scope':source['source_status'],
            'real_mutation_fingerprints':mutation_states}
    (out/'actual-stage-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (out/'actual-evaluated-baseline.json').write_text(json.dumps(original,ensure_ascii=False)+'\n')
    require(report['failed']==0,'Actual stage geometry QA has failures; original red retained')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--bindings',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path)
    ap.add_argument('--prepare-only',action='store_true')
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args=ap.parse_args(argv)
    bindings=json.loads(args.bindings.read_text())
    if args.prepare_only:
        print(json.dumps(preflight(bindings,allow_pending=True),ensure_ascii=False,indent=2))
        return
    preflight(bindings)
    require(args.output_dir is not None,'fresh output-dir required')
    execute(bindings,args.output_dir.resolve())


if __name__=='__main__':
    main()
