"""Source-qualified single-storey theatre; pure geometry, caller-owned I/O."""
import json
import math

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import courtyard_hall_buildings as G
import forbidden_city_geometry as F
import restoration_buildings as R


def _validate(p):
    for key in ('building_id', 'name_zh', 'source_part_id', 'anchor', 'rotation_z_rad',
                'source_polygon_local', 'source_polygon_world', 'source_holes_local',
                'dimensions', 'roof_tiers', 'material_scheme', 'known_facts', 'unbuilt'):
        if key not in p:
            raise ValueError('missing explicit theatre field ' + key)
    if p['building_id'] != 'shufang_large_stage':
        raise ValueError('unsupported qualified theatre identity')
    if any(type(p.get(k)) is not int for k in ('bays_x', 'bays_y', 'eaves_tiers', 'occupied_storeys', 'reference_floor_count')):
        raise ValueError('theatre factual counts must be strict integers')
    if (p.get('bays_x'), p.get('bays_y'), p.get('eaves_tiers'),
            p.get('occupied_storeys'), p.get('reference_floor_count')) != (3, 3, 2, 1, 1):
        raise ValueError('three-by-three, two-eave, single-storey theatre required')
    for key in ('third_party_cost', 'paid_service_calls'):
        if type(p.get(key)) is not int or p[key] != 0:
            raise ValueError('theatre budget must be integer zero')
    if p.get('human_approval') != 'pending':
        raise ValueError('geometry cannot grant human approval')
    F._point('anchor', p['anchor'])
    F._number('rotation', p['rotation_z_rad'])
    rings = [F._clean_ring(p['source_polygon_local'])] + [F._clean_ring(h) for h in p['source_holes_local']]
    F._triangulate_rings(rings)
    if len(rings[0]) != len(p['source_polygon_world']):
        raise ValueError('source ring registration differs')
    c, s = math.cos(p['rotation_z_rad']), math.sin(p['rotation_z_rad'])
    for a, b in zip(rings[0], p['source_polygon_world']):
        if math.dist((p['anchor'][0] + c*a[0] - s*a[1], p['anchor'][1] + s*a[0] + c*a[1]), b) > 1e-4:
            raise ValueError('source local/world coordinate mismatch')
    d = p['dimensions']
    for key in ('body_width_m', 'body_depth_m', 'column_radius_m', 'column_base_radius_m',
                'column_base_height_m', 'beam_width_m', 'beam_height_m'):
        F._number(key, d[key], strictly_positive=True)
    if not d['slab_bottom_z_m'] < d['floor_z_m'] < d['column_top_z_m']:
        raise ValueError('theatre support height order invalid')
    if d['beam_width_m'] <= 2*d['column_radius_m'] or d['column_base_radius_m'] <= d['column_radius_m']:
        raise ValueError('complete column cap or base support too narrow')
    w, depth = d['body_width_m'], d['body_depth_m']
    margin = max(d['column_base_radius_m'], d['beam_width_m']/2)
    if G._rectangle_outside_area(rings, -w/2-margin, w/2+margin, -depth/2-margin, depth/2+margin) > 1e-5:
        raise ValueError('complete theatre support envelope leaves source or fills hole')
    band = d['upper_band']
    if band['occupied_floor'] is not False:
        raise ValueError('upper roof band is not an occupied storey')
    for key in ('width_m', 'depth_m', 'wall_thickness_m', 'bottom_z_m'):
        F._number('upper_band ' + key, band[key], strictly_positive=True)
    if not w/3 < band['width_m'] < w or not depth/3 < band['depth_m'] < depth:
        raise ValueError('upper band must enclose the four inner structural axes')
    if band['bottom_z_m']-d['beam_height_m'] <= d['floor_z_m']+d['column_base_height_m']:
        raise ValueError('inner column has no positive height')
    if len(p['roof_tiers']) != 2:
        raise ValueError('two explicitly supplied roof tiers required')
    for i, t in enumerate(p['roof_tiers']):
        if t['tier_index'] != i or not t['eave_z_m'] < t['top_z_m']:
            raise ValueError('roof order invalid')
        for key in ('outer_width_m', 'outer_depth_m', 'skin_thickness_m', 'curve_power'):
            F._number(key, t[key], strictly_positive=True)
        F._number('corner_lift', t['corner_lift_m'], minimum=0)
        if (t['corner_lift_m'] >= t['top_z_m']-t['eave_z_m']
                or t['skin_thickness_m'] >= min(t['outer_width_m'], t['outer_depth_m'], t['top_z_m']-t['eave_z_m'])/3):
            raise ValueError('roof lift or thickness consumes its shell')
        for axis in ('width', 'depth'):
            inner, outer = t['inner_'+axis+'_m'], t['outer_'+axis+'_m']
            if not 0 <= inner < outer or bool(inner) != (i == 0):
                raise ValueError('only the lower roof has a real inner opening')
            if i == 0 and abs(inner-band[axis+'_m']) > 1e-8:
                raise ValueError('lower annular rim must meet the actual band')
    lo, hi = p['roof_tiers']
    if not (lo['outer_width_m'] > w and lo['outer_depth_m'] > depth
            and lo['top_z_m']-lo['skin_thickness_m'] <= band['bottom_z_m'] < lo['top_z_m']
            and hi['eave_z_m'] > lo['top_z_m']+.3
            and hi['outer_width_m'] > band['width_m']+band['wall_thickness_m']
            and hi['outer_depth_m'] > band['depth_m']+band['wall_thickness_m']):
        raise ValueError('roof and band interfaces invalid')
    json.dumps(p, allow_nan=False)
    return rings


def _point(t, x, y, f):
    sx = 1-t['inner_width_m']/t['outer_width_m']
    sy = 1-t['inner_depth_m']/t['outer_depth_m']
    return (t['outer_width_m']*.5*x*(1-sx*f), t['outer_depth_m']*.5*y*(1-sy*f),
            t['eave_z_m']+(t['top_z_m']-t['eave_z_m'])*f**t['curve_power']
            + t['corner_lift_m']*min(abs(x), abs(y))**8*(1-f)**3)


def _roof(p, t, col, mats):
    surface = F._Surface()
    perimeter = []
    for side in range(4):
        for i in range(12):
            u = -1+2*i/12
            perimeter.append((u, -1) if side == 0 else (1, u) if side == 1 else (-u, 1) if side == 2 else (-1, -u))
    indices = []
    for j in range(14):
        for i, (x, y) in enumerate(perimeter):
            xx, yy = perimeter[(i+1) % len(perimeter)]
            f0, f1 = j/14, (j+1)/14
            if not t['inner_width_m'] and j == 13:
                surface.face([_point(t, x, y, f0), _point(t, xx, yy, f0), (0, 0, t['top_z_m'])])
            else:
                surface.face([_point(t, x, y, f0), _point(t, xx, yy, f0), _point(t, xx, yy, f1), _point(t, x, y, f1)])
            indices.append(1 if j == 0 else 0)
    R._closed_skin(surface, t['skin_thickness_m'])
    indices.extend([2]*(len(surface.faces)-len(indices)))
    scheme = p['material_scheme']
    o = R._mesh('V17_'+p['building_id']+'_roof_'+str(t['tier_index']), surface, col,
                [mats[scheme[k]] for k in ('roof_main', 'roof_edge', 'roof_under')], indices)
    o['roof_type'] = 'sijiao_zanjian'
    o['roof_tier_index'], o['annular'] = t['tier_index'], bool(t['inner_width_m'])
    o['roof_topology'] = 'rectangular_four_face_annular' if o['annular'] else 'four_faces_single_central_apex'
    return o


def _tree(obj):
    return BVHTree.FromPolygons([v.co for v in obj.data.vertices], [tuple(p.vertices) for p in obj.data.polygons])


def build_stage(profile, collection, materials=None, mesh_cache=None):
    p = profile
    rings = _validate(p)
    d, ident, scheme = p['dimensions'], p['building_id'], p['material_scheme']
    mats = R.restoration_materials() if materials is None else dict(materials)
    if any(scheme[k] not in mats for k in ('column', 'beam', 'wall', 'stone', 'railing', 'roof_main', 'roof_edge', 'roof_under')):
        raise ValueError('caller theatre palette missing material')
    cache = {} if mesh_cache is None else mesh_cache
    col = F.ensure_collection('V17_'+ident, collection)
    root = bpy.data.objects.new('V17_'+ident+'_root', None)
    col.objects.link(root)
    root.location, root.rotation_euler.z = p['anchor'], p['rotation_z_rad']
    objects, components, contacts = [], {}, []

    def add(o, role):
        o['semantic_role'] = role
        objects.append(o)
        components.setdefault(role, []).append(o)
        return o

    def box(label, center, size, material, role):
        return add(F.box('V17_'+ident+'_'+label, center, size, mats[scheme[material]], col, cache, role), role)

    surface = F._Surface()
    for tri in F._triangulate_rings(rings):
        surface.face([(x, y, d['floor_z_m']) for x, y in tri])
    F._volume_from_top(surface, d['slab_bottom_z_m'])
    slab = add(F._object('V17_'+ident+'_source_reference_slab',
                        F._new_mesh('V17_stage_source_slab', surface.vertices, surface.faces, mats[scheme['stone']]),
                        col, 'source_reference_slab'), 'source_reference_slab')
    slab['reference_floor_only'], slab['not_measured_platform'] = True, True
    roofs = []
    for t in p['roof_tiers']:
        o = add(_roof(p, t, col, mats), 'roof')
        roofs.append({'object': o.name, 'roof_type': 'sijiao_zanjian', **t})
        for category, start, stop in [('roof_main', .078, .96 if t['inner_width_m'] else .86), ('roof_edge', .012, .067)]:
            ribs = F._Surface()
            for side in range(4):
                for i in range(12):
                    u = -1+2*(i+.5)/12
                    x, y = (u, -1) if side == 0 else (1, u) if side == 1 else (-u, 1) if side == 2 else (-1, -u)
                    path = []
                    for j in range(19):
                        a, b, z = _point(t, x, y, start+(stop-start)*j/18)
                        path.append((a, b, z+.003))
                    F._tube(ribs, path, .022, 8)
            o = add(F._object('V17_'+ident+'_tile_lines_'+str(t['tier_index'])+'_'+category,
                             F._new_mesh('V17_stage_tile_lines', ribs.vertices, ribs.faces, mats[scheme[category]]),
                             col, 'roof_tile_ribs'), 'roof_tile_ribs')
            o['intentionally_intersecting_detail'] = True
            o['tile_count_status'] = 'Grouped unmeasured line study, not individual historic tile count'
    w, depth, bw, bh = d['body_width_m'], d['body_depth_m'], d['beam_width_m'], d['beam_height_m']
    band = d['upper_band']
    xs, ys = [-w/2+w*i/3 for i in range(4)], [-depth/2+depth*i/3 for i in range(4)]
    outer = []
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            inner = i in (1, 2) and j in (1, 2)
            top = band['bottom_z_m']-bh if inner else d['column_top_z_m']
            z0 = d['floor_z_m']+d['column_base_height_m']
            base = add(F.column('V17_'+ident+'_base_'+str(i)+'_'+str(j),
                               (x, y, d['floor_z_m']+d['column_base_height_m']/2), d['column_base_radius_m'],
                               d['column_base_height_m'], mats[scheme['stone']], col, cache, 20), 'column_base')
            base['support_object'] = slab.name
            shaft = add(F.column('V17_'+ident+'_column_'+str(i)+'_'+str(j), (x, y, (z0+top)/2),
                                d['column_radius_m'], top-z0, mats[scheme['column']], col, cache, 24),
                        'upper_support_column' if inner else 'column')
            shaft['support_object'], shaft['study_column_axis'] = base.name, [x, y]
            shaft['grid_i'], shaft['grid_j'] = i, j
            if not inner:
                outer.append((x, y))
    beamtop = d['column_top_z_m']+bh
    for sign in (-1, 1):
        box('outer_beam_x', (0, sign*depth/2, beamtop-bh/2), (w+bw, bw, bh), 'beam', 'beam')
        box('outer_beam_y', (sign*w/2, 0, beamtop-bh/2), (bw, depth+bw, bh), 'beam', 'beam')
        box('inner_cross_x', (0, sign*depth/6, band['bottom_z_m']-bh/2), (band['width_m']+bw, bw, bh), 'beam', 'beam')
        box('inner_cross_y', (sign*w/6, 0, band['bottom_z_m']-bh/2), (bw, band['depth_m']+bw, bh), 'beam', 'beam')
        box('band_rim_x', (0, sign*band['depth_m']/2, band['bottom_z_m']-bh/2), (band['width_m']+bw, bw, bh), 'beam', 'beam')
        box('band_rim_y', (sign*band['width_m']/2, 0, band['bottom_z_m']-bh/2), (bw, band['depth_m']+bw, bh), 'beam', 'beam')
    lower, upper = components['roof']
    lower_tree, upper_tree = _tree(lower), _tree(upper)
    for i, (x, y) in enumerate(outer):
        hit = lower_tree.ray_cast(Vector((x, y, beamtop-.01)), Vector((0, 0, 1)), 20)[0]
        if hit is None or hit.z <= beamtop:
            raise ValueError('lower actual roof misses perimeter support')
        o = box('roof_riser_'+str(i), (x, y, (beamtop+hit.z)/2), (bw-.001, bw-.001, hit.z-beamtop+.0002), 'beam', 'roof_support_riser')
        contacts.append({'object': o.name, 'roof': lower.name, 'point_local': list(hit), 'construction': 'Unmeasured plain support; detailed dougong unbuilt'})
    t = band['wall_thickness_m']
    for side, x, y, width, length in [('south', 0, -band['depth_m']/2, band['width_m']+t, t),
                                     ('north', 0, band['depth_m']/2, band['width_m']+t, t),
                                     ('east', band['width_m']/2, 0, t, band['depth_m']+t),
                                     ('west', -band['width_m']/2, 0, t, band['depth_m']+t)]:
        hits = []
        for i in range(25):
            for sign in (-.5, .5):
                xx, yy = ((x+width*(-.5+i/24), y+t*sign) if side in ('south', 'north')
                          else (x+t*sign, y+length*(-.5+i/24)))
                hit = upper_tree.ray_cast(Vector((xx, yy, band['bottom_z_m'])), Vector((0, 0, 1)), 20)[0]
                if hit is None:
                    raise ValueError('upper band outside actual roof')
                hits.append(hit.z)
        top = max(hits)+.001
        if max(hits)-min(hits)+.002 >= p['roof_tiers'][1]['skin_thickness_m']:
            raise ValueError('band would penetrate upper roof exterior')
        o = box('upper_band_'+side, (x, y, (band['bottom_z_m']+top)/2),
                (width, length, top-band['bottom_z_m']), 'wall', 'upper_band_wall')
        o['occupied_floor'], o['wall_side'] = False, side
    # Only the front railing is directly visible in the qualified official photo.
    # Repeated bars express its category; their dimensions/count are not measured.
    for i in range(3):
        a, b = xs[i]+d['column_radius_m']+.025, xs[i+1]-d['column_radius_m']-.025
        y, low, high = -depth/2, d['floor_z_m']+.08, d['floor_z_m']+.76
        for x in (a, b):
            box('front_rail_post', (x, y, (d['floor_z_m']+high)/2), (.075, .075, high-d['floor_z_m']), 'railing', 'front_rail_post')
        for z in (low, high):
            box('front_rail_horizontal', ((a+b)/2, y, z), (b-a+.075, .07, .065), 'railing', 'front_rail')
        for j in range(1, 7):
            box('illustrative_front_lattice', (a+(b-a)*j/7, y, (low+high)/2), (.035, .05, high-low), 'railing', 'front_rail')
    serialized = json.dumps(p, ensure_ascii=False, allow_nan=False)
    for o in [root]+objects:
        if o is not root:
            o.parent = root
        o['restoration_v17_building_id'], o['source_reference_part_id'] = ident, p['source_part_id']
        o['human_approval'], o['third_party_cost'], o['absolute_accuracy_claim'] = 'pending', 0, False
        o['profile_json'] = serialized
    root['occupied_storeys'], root['modeled_upper_occupied_floors'] = 1, 0
    root['structural_bays_x'], root['structural_bays_y'] = 3, 3
    root['unbuilt_features'] = json.dumps(p['unbuilt'], ensure_ascii=False)
    bpy.context.view_layer.update()
    return {'root': root, 'objects': objects, 'components': components, 'openings': [], 'roofs': roofs,
            'reference_floor': slab.name, 'roof_contacts': contacts, 'profile': p, 'unbuilt_features': p['unbuilt']}
