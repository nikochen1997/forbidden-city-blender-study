"""Build a source-grounded, explicitly provisional whole-city exterior study.

Run with Blender --background --python this_file -- --data model-data.json
--output-dir PATH. This script never fetches data or calls paid services.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import forbidden_city_geometry as F


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--width', type=int, default=4800)
    parser.add_argument('--samples', type=int, default=48)
    parser.add_argument('--only', default='')
    parser.add_argument('--skip-renders', action='store_true')
    return parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])


ARGS = arguments()
DATA_BYTES = ARGS.data.read_bytes()
DATA = json.loads(DATA_BYTES)
OUT = ARGS.output_dir.resolve()
(OUT / 'renders').mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for collection in list(bpy.data.collections):
    if collection.name != 'Collection':
        bpy.data.collections.remove(collection)
SCENE = bpy.context.scene
SCENE.unit_settings.system = 'METRIC'
SCENE.unit_settings.scale_length = 1.0
PARTS = F.ensure_collection('source_parts')
GROUND = F.ensure_collection('source_ground_and_water')
WALLS = F.ensure_collection('source_city_walls')
INNER_WALLS = F.ensure_collection('source_inner_walls')
LAND = F.ensure_collection('source_vegetation')
STUDIO = F.ensure_collection('cameras_and_lights')
MATS = F.create_materials()
CACHE = {}
PART_RECORDS = []
RENDERS = []
ISSUES = []
SITE_BOUNDS = DATA['stats']['site_bounds_enu_m']
CX = (SITE_BOUNDS[0] + SITE_BOUNDS[2]) / 2
CY = (SITE_BOUNDS[1] + SITE_BOUNDS[3]) / 2


def material(name, color, roughness=.7, metallic=0):
    result = bpy.data.materials.new('FC_' + name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    shader = result.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Metallic'].default_value = metallic
    return result


MATS['black'] = material('black_glazed_tiles', (.035, .043, .042), .30, .12)
MATS['stone'] = MATS['white_stone']
MATS['wood'] = MATS['dark_wood']
MATS['ground'] = material('courtyard_paving', (.43, .42, .385), .92)
MATS['path'] = material('mapped_path', (.56, .54, .48), .9)
MATS['earth'] = material('outside_ground', (.35, .38, .34), 1)
MATS['water'] = material('moat_water', (.035, .135, .15), .18, .28)
MATS['foliage'] = material('trees', (.034, .12, .06), .95)
MATS['grass'] = material('garden_ground', (.14, .22, .12), 1)
MATS['trunk'] = material('tree_trunk', (.11, .055, .025), .94)


def flat_polygon(name, record, z, mat, collection):
    outer = [tuple(point) for point in record['polygon']]
    holes = [[tuple(point) for point in ring] for ring in record.get('holes', [])]
    triangles = F._triangulate_rings([outer] + holes)
    mesh = bpy.data.meshes.new(name)
    vertices, faces = [], []
    for triangle in triangles:
        index = len(vertices)
        vertices.extend((x, y, z) for x, y in triangle)
        faces.append((index, index + 1, index + 2))
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj['source_refs'] = json.dumps(record.get('source_refs', []))
    obj['representation'] = 'mapped_polygon_with_provisional_surface_material'
    return obj


def strip(name, points, width, z, height, mat, collection, taper_top=None):
    vertices, faces = [], []
    half_top = (width if taper_top is None else taper_top) / 2
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < .001:
            continue
        nx, ny = -dy / length, dx / length
        base = len(vertices)
        for zz, half in ((z, width / 2), (z + height, half_top)):
            vertices.extend([(a[0] + nx * half, a[1] + ny * half, zz),
                             (b[0] + nx * half, b[1] + ny * half, zz),
                             (b[0] - nx * half, b[1] - ny * half, zz),
                             (a[0] - nx * half, a[1] - ny * half, zz)])
        faces.extend(tuple(base + i for i in f) for f in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)))
    if not vertices:
        return None
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def build_ground():
    F.box('未测绘外围基底', (CX, CY, -2.0), (6000, 6000, 1), MATS['earth'], GROUND, CACHE)
    for item in DATA['site_polygons']:
        flat_polygon('城域地面_' + item['id'], item, 0, MATS['ground'], GROUND)
    for item in DATA.get('water_polygons', []):
        flat_polygon('水域_' + (item.get('name') or '') + item['id'], item, .025, MATS['water'], GROUND)
    for item in DATA.get('landcover_polygons', []):
        flat_polygon('绿地_' + item['id'], item, .035, MATS['grass'], LAND)
    for item in DATA.get('path_polygons', []):
        flat_polygon('铺地面_' + item['id'], item, .045, MATS['path'], GROUND)
    for item in DATA.get('paths', []):
        obj = strip('路_' + item['id'], item['points'], max(.1, item.get('width') or 2), .015, .012, MATS['path'], GROUND)
        if obj:
            obj['source_refs'] = json.dumps(item.get('source_refs', []))
            obj['assumptions'] = json.dumps(item.get('assumptions', []), ensure_ascii=False)


def build_walls():
    for item in DATA.get('city_wall_lines', []):
        if item.get('original_tags', {}).get('historic') != 'citywalls':
            obj = strip('低矮边界_' + item['id'], item['points'], max(.1,item.get('width') or .4),
                        max(0,item.get('min_height') or 0), max(.1,item.get('height') or .5), MATS['stone'], INNER_WALLS)
            if obj:
                obj['source_refs'] = json.dumps(item.get('source_refs', []))
                obj['assumptions'] = json.dumps(item.get('assumptions', []),ensure_ascii=False)
            continue
        obj = strip('城垣_' + item['id'], item['points'], 8.62, 0, 9.90, MATS['red'], WALLS, taper_top=6.66)
        if obj:
            obj['height_source'] = 'https://www.dpm.org.cn/explore/building/236441.html'
            obj['source_refs'] = json.dumps(item.get('source_refs', []) + [obj['height_source']])
            obj['original_osm_height'] = str(item.get('height'))
            obj['uncertainty'] = '9.90m height scope and parapet inclusion need section survey; no guessed merlon pattern added'
    for item in DATA.get('inner_walls', []):
        obj = strip('院墙_' + item['id'], item['points'], max(.15, item.get('width') or .6),
                    max(0, item.get('min_height') or 0), max(.2, item.get('height') or 3.5), MATS['red'], INNER_WALLS)
        if obj:
            obj['source_refs'] = json.dumps(item.get('source_refs', []))
            obj['assumptions'] = json.dumps(item.get('assumptions', []), ensure_ascii=False)


def build_parts():
    groups = {}
    for index, item in enumerate(DATA['parts']):
        parent = item.get('parent_name') or item.get('name') or '尚未核实名称的建筑'
        if parent not in groups:
            groups[parent] = F.ensure_collection(parent, PARTS)
        result = F.build_osm_part(item, groups[parent], MATS, CACHE)
        for obj in result['objects']:
            obj['display_name'] = item.get('name') or parent
            obj['source_building_id'] = item['id']
        PART_RECORDS.append({'id': item['id'], 'name': item.get('name'), 'parent_name': parent,
                             'objects': [obj.name for obj in result['objects']],
                             'source_refs': item.get('source_refs', []),
                             'height_source': item.get('height_source'), 'assumptions': item.get('assumptions', [])})
        if index % 100 == 0:
            print('PARTS', index, '/', len(DATA['parts']), flush=True)


def build_trees():
    crown_mesh = None
    for index, item in enumerate(DATA.get('trees', [])):
        h = max(1, item.get('height') or 5)
        diameter = max(.5, item.get('diameter_crown') or h * .65)
        x, y = item['x'], item['y']
        trunk = F.column('树干_' + item['id'], (x,y,h*.20), .16, h*.4, MATS['trunk'], LAND, CACHE, 8)
        if crown_mesh is None:
            verts = [(0,0,1)] + [(math.cos(i*math.pi/4),math.sin(i*math.pi/4),.0) for i in range(8)]
            faces = [(0, i+1, (i+1)%8+1) for i in range(8)] + [tuple(range(8,0,-1))]
            crown_mesh = bpy.data.meshes.new('共享示意树冠')
            crown_mesh.from_pydata(verts, [], faces)
            crown_mesh.materials.append(MATS['foliage'])
        crown = bpy.data.objects.new('树冠_' + item['id'], crown_mesh)
        LAND.objects.link(crown)
        crown.location = (x,y,h*.25)
        crown.scale = (diameter/2,diameter/2,h*.75)
        for obj in (trunk,crown):
            obj['source_refs'] = json.dumps(item.get('source_refs', []))
            obj['assumptions'] = json.dumps(item.get('assumptions', []), ensure_ascii=False)


def camera(name, location, target, lens=48, ortho=None):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    STUDIO.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
    data.lens = lens
    data.clip_end = 10000
    if ortho:
        data.type = 'ORTHO'
        data.ortho_scale = ortho
    return obj


def setup_lighting():
    world = bpy.data.worlds.new('晴空_程序背景')
    SCENE.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (.52,.63,.76,1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = .65
    data = bpy.data.lights.new('午后日光', 'SUN')
    obj = bpy.data.objects.new('午后日光', data)
    STUDIO.objects.link(obj)
    data.energy = 3.0
    data.angle = .10
    obj.rotation_euler = (math.radians(25),math.radians(-22),math.radians(-25))
    SCENE.render.engine = 'BLENDER_EEVEE_NEXT'
    SCENE.eevee.taa_render_samples = ARGS.samples
    SCENE.render.image_settings.file_format = 'PNG'
    SCENE.render.image_settings.color_mode = 'RGB'
    SCENE.render.resolution_percentage = 100
    SCENE.view_settings.view_transform = 'AgX'
    SCENE.view_settings.look = 'AgX - Medium High Contrast'
    SCENE.view_settings.exposure = .35
    SCENE.render.film_transparent = False


def render(filename, cam, width, height, description, plan=False):
    path = 'renders/' + filename + '.png'
    RENDERS.append({'file': path, 'camera': cam.name, 'width': width, 'height': height, 'description': description})
    chosen = {item.strip() for item in ARGS.only.split(',') if item.strip()}
    if ARGS.skip_renders or (chosen and filename[:2] not in chosen):
        return
    SCENE.camera = cam
    SCENE.render.resolution_x = width
    SCENE.render.resolution_y = height
    SCENE.render.filepath = str(OUT / path)
    original_colors = {}
    if plan:
        SCENE.render.engine = 'BLENDER_WORKBENCH'
        shading = SCENE.display.shading
        shading.light = 'FLAT'
        shading.color_type = 'OBJECT'
        shading.show_shadows = False
        shading.show_cavity = False
        shading.show_object_outline = True
        shading.object_outline_color = (.03,.03,.03)
        shading.background_type = 'WORLD'
        SCENE.world.color = (1,1,1)
        for obj in SCENE.objects:
            if obj.type != 'MESH':
                continue
            original_colors[obj] = tuple(obj.color)
            if 'source_building_id' in obj:
                value = .16 if obj.name.endswith('原轮廓坡屋顶') else .28
            elif obj in WALLS.objects.values() or obj in INNER_WALLS.objects.values():
                value = .38
            elif obj in LAND.objects.values():
                value = .80
            elif obj.name.startswith('水域_'):
                value = .64
            elif obj.name.startswith(('路_', '铺地面_')):
                value = .88
            else:
                value = 1.0
            obj.color = (value,value,value,1)
    print('RENDER_START', path, flush=True)
    try:
        bpy.ops.render.render(write_still=True)
    finally:
        for obj, color in original_colors.items():
            obj.color = color
        SCENE.render.engine = 'BLENDER_EEVEE_NEXT'
    print('RENDER_DONE', path, flush=True)


def authoring_state(overview):
    SCENE.camera = overview
    SCENE.display.shading.color_type = 'MATERIAL'
    SCENE.world.color = (.10,.13,.17)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.shading.type = 'MATERIAL'
                space.shading.use_scene_world = True
                space.shading.use_scene_lights = True
                space.region_3d.view_perspective = 'CAMERA'
                space.region_3d.view_camera_zoom = 0


print('BUILD_SOURCE_GROUND', flush=True)
build_ground()
print('BUILD_SOURCE_WALLS', flush=True)
build_walls()
print('BUILD_SOURCE_PARTS', len(DATA['parts']), flush=True)
build_parts()
print('BUILD_SOURCE_TREES', len(DATA.get('trees', [])), flush=True)
build_trees()
setup_lighting()
overview = camera('Camera_Whole_City', (CX+1000,CY-1450,1250),(CX,CY+5,0),45)
overhead = camera('Camera_Orthographic_North_Up', (CX,CY,1700),(CX,CY,0),ortho=1280)
axis = camera('Camera_Outer_Court', (CX+280,CY-610,300),(CX-15,CY-180,10),50)
inner = camera('Camera_Inner_Court', (CX+260,CY+80,300),(CX-10,CY+245,10),45)
northeast = camera('Camera_Northeast', (CX+520,CY+70,320),(CX+200,CY+275,10),48)
west = camera('Camera_West', (CX-490,CY-25,330),(CX-200,CY+180,10),48)
SCENE['concept_only'] = True
SCENE['reconstruction_claim'] = 'source_grounded_overview; NOT absolute or surveyed reconstruction'
SCENE['third_party_cost'] = 0
SCENE['fc_data_sha256'] = hashlib.sha256(DATA_BYTES).hexdigest()
SCENE['fc_data_parts_count'] = len(DATA['parts'])
SCENE['qa_source_parts_collection'] = PARTS.name
SCENE['attribution'] = '© OpenStreetMap contributors. Data under ODbL. Museum references: dpm.org.cn.'
SCENE['known_limitations'] = json.dumps(['OSM crowd-sourced heights and source-defined assumptions require survey confirmation',
    'Whole-site exterior massing only; no complete interiors, carvings, painted patterns, true roof curvature or tile detail',
    'Known OSM/official height conflicts remain recorded; not silently reconciled'], ensure_ascii=False)
authoring_state(overview)
SCENE.render.resolution_x = ARGS.width
SCENE.render.resolution_y = round(ARGS.width * 3/4)
blend = OUT / '紫禁城现存格局-全域底模.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
render('01-全宫鸟瞰-有来源底模',overview,ARGS.width,round(ARGS.width*3/4),'全宫外观体量，众包轮廓与高度，不是测绘复原')
render('02-全宫正投影-北向上',overhead,5120,6144,'实际模型正投影与真实地理方位')
render('03-外朝中轴区',axis,3840,2880,'外朝区域近景，核对三大殿与午门序列')
render('04-内廷与御花园区',inner,3840,2880,'内廷区域近景，保留现存非全局对称格局')
render('05-东北宁寿宫区',northeast,3840,2880,'东北区域近景，未知细节仍待核对')
render('06-西部宫苑区',west,3840,2880,'西部宫苑区域近景')
render('07-全宫工程投影',overhead,3840,4608,'由实际网格生成的单色模型投影',plan=True)
authoring_state(overview)
SCENE.render.resolution_x = ARGS.width
SCENE.render.resolution_y = round(ARGS.width*3/4)
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
manifest = {'schema':'forbidden-city-source-grounded-overview/v1','stage':'source_grounded_overview',
            'claimed_absolute_accuracy':False,'human_approval':'pending',
            'source_parts_collection':PARTS.name,'overview_camera':overview.name,
            'source_data_sha256':SCENE['fc_data_sha256'],'source_data':'data/model-data.json',
            'generation':{'provider':'local_blender','budget':0,'actualCost':0,'thirdPartyCalls':0},
            'parts':PART_RECORDS,'renders':RENDERS,'issues':ISSUES,'data_stats':DATA.get('stats',{}),
            'attribution':SCENE['attribution'],'limitations':json.loads(SCENE['known_limitations'])}
(OUT/'scene-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('WHOLE_CITY_OVERVIEW_COMPLETE',len(PART_RECORDS),str(blend),flush=True)
