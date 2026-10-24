"""Source-bound Biluo exterior/support study; caller owns I/O, hiding and saving.

Five continuous study columns support the upper real skin; five short beams and
actual-underside caps support the lower annular skin. No interior floor is made.
"""
import hashlib
import json
import math

import bpy
from mathutils import Matrix

import forbidden_city_geometry as F
import northern_court_towers as T
import five_petal_roofs as P


def _require(value, message):
    if not value:
        raise ValueError(message)


def _number(name, value, positive=False):
    _require(type(value) in (int, float) and math.isfinite(value) and (not positive or value > 0), 'Invalid finite study ' + name)
    return value


def _circle(x, y, radius, count=24):
    return [(x+radius*math.cos(i*2*math.pi/count), y+radius*math.sin(i*2*math.pi/count)) for i in range(count)]


def _axes(p):
    radius, phase = p['study']['column_axis_radius_m'], p['roof_profile']['phase_rad']
    return [(radius*math.cos(phase+i*2*math.pi/5), radius*math.sin(phase+i*2*math.pi/5)) for i in range(5)]


def _inradius(ring):
    _require(len(ring) == 7 and F._ring_area(ring) > 0, 'Complete seven-point CCW source required')
    distances = []
    for a, b, c in zip(ring, ring[1:]+ring[:1], ring[2:]+ring[:2]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        _require(dx*(c[1]-b[1])-dy*(c[0]-b[0]) > 0, 'Source must retain its complete convex domain')
        distances.append((dx*(-a[1])-dy*(-a[0]))/math.hypot(dx, dy))
    _require(min(distances) > 0, 'Reference center leaves source')
    return min(distances)


def _validate(p, materials):
    _require(p['building_id'] == 'biluoting' and p['source_part_id'] == 'way-43525093-p0', 'Exact Biluo/source binding required')
    _require(p['dimension_status'] == 'unmeasured_study' and p['human_approval'] == 'pending' and p['occupied_storeys'] is None, 'Study/null scope differs')
    for key, expected in (('third_party_cost', 0), ('paid_service_calls', 0), ('reference_floor_count', 1), ('column_count', 5)):
        _require(type(p[key]) is int and p[key] == expected, 'Strict integer ' + key + ' differs')
    _require(p['source_holes_local'] == p['source_holes_world'] == [], 'This exact source has no holes')
    _require(not p['allowed_hidden_source_actor_names'] and not p['historical_identity_confirmed'], 'No hide or historical release allowed')
    _require(p['source6m_proxy_height_is_real_building_height'] is False and p['mountain_is_reconstructed'] is False, 'Proxy/mountain promoted')
    _require(p['known_facts'] == p['roof_profile']['known_facts'], 'Roof/body documentary facts differ')
    _require(p['known_facts']['column_count']['value'] == 5 and p['known_facts']['mountain_support_apex_z_m']['value'] is None, 'Unknown mountain or five columns changed')
    _require(p['known_facts']['occupied_storeys']['value'] is None and p['known_facts']['floor_z_m']['value'] is None, 'Unknown storey/datum promoted')
    P._validate(p['roof_profile'], materials)
    d, lower, upper = p['study'], *p['roof_profile']['roof_tiers']
    for key, value in d.items():
        _number(key, value, positive=True)
    _require(0 <= p['source_support_bottom_z_m'] < d['source_support_top_z_m'] < d['reference_floor_top_z_m'] < d['lower_beam_top_z_m']-d['beam_height_m'], 'Ground/reference/beam order invalid')
    _require(d['lower_beam_top_z_m'] < lower['eave_z_m']-lower['skin_thickness_m']-.05, 'Lower beams reach the skin range')
    _require(lower['top_z_m']+.05 < d['upper_beam_top_z_m'] < upper['eave_z_m']-upper['skin_thickness_m']-.05, 'Upper beam between-tier clearance invalid')
    _require(d['column_axis_radius_m']+d['column_radius_m'] < lower['inner_radius_m']-.03, 'Continuous columns pierce lower annular skin')
    _require(d['column_axis_radius_m']+d['column_radius_m'] < upper['outer_radius_m']-.03, 'Upper skin does not cover full column footprint')
    _require(d['lower_bearing_axis_radius_m']-d['lower_bearing_radius_m'] > lower['inner_radius_m']+lower['inner_lobe_amplitude_m']+.03, 'Lower bearing crosses true roof hole')
    _require(d['lower_bearing_axis_radius_m']+d['lower_bearing_radius_m'] < lower['outer_radius_m']-.03, 'Lower bearing leaves roof outer domain')
    _require(d['beam_width_m'] > 2*d['lower_bearing_radius_m']+.02, 'Whole lower bearing base is not covered by radial beam')
    _require(d['column_radius_m'] < d['beam_width_m']/2, 'Beam-to-column overlap absent')
    radius = _inradius(p['source_polygon_local'])
    envelope = max(t['outer_radius_m']+t['lobe_amplitude_m']+max(t['ridge_radius_m'],t['tile_radius_m']) for t in (lower,upper))
    _require(envelope < radius-.03, 'Entire roof/decorative disk leaves complete source halfplanes')
    c, s = math.cos(p['rotation_z_rad']), math.sin(p['rotation_z_rad'])
    _require(len(p['source_polygon_world']) == 7, 'Source outer vertices removed')
    for local, world in zip(p['source_polygon_local'], p['source_polygon_world']):
        actual = (p['anchor'][0]+c*local[0]-s*local[1], p['anchor'][1]+s*local[0]+c*local[1])
        _require(math.dist(actual,world) < 1e-8, 'Full source frame differs')
    for key in ('column','beam','source_support','reference_floor'):
        _require(p['material_scheme'][key] in materials, 'Missing explicit caller material')
    json.dumps(p, allow_nan=False)


def build_biluo_pavilion(profile, collection, materials, mesh_cache=None):
    """Build one local load-path study, preserving all seven source vertices.

    Object phase is baked into private roof-data copies before T's raw-local
    downward-face clipping. Root then applies the source world frame once.
    """
    _validate(profile, materials)
    p, d = profile, profile['study']
    cache = {} if mesh_cache is None else mesh_cache
    prefix = 'V19_' + p['primitive_id']
    col = F.ensure_collection(prefix, collection)
    root = bpy.data.objects.new(prefix+'_root', None); col.objects.link(root)
    root.location, root.rotation_euler.z = p['anchor'], p['rotation_z_rad']
    objects, components, contacts, beam_links = [], {}, [], []
    digest = hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

    def add(obj, role):
        obj.parent = root; obj['semantic_role'] = role; obj['building_id'] = 'biluoting'
        obj['source_reference_part_id'] = p['source_part_id']; obj['profile_sha256'] = digest
        obj['dimension_status'] = 'unmeasured_study'; obj['human_approval'] = 'pending'
        obj['third_party_cost'] = 0; obj['paid_service_calls'] = 0; obj['occupied_storeys'] = 'unknown'
        objects.append(obj); components.setdefault(role,[]).append(obj)
        return obj

    def source_prism(label, bottom, top, role, material):
        surf = F._Surface()
        for triangle in F._triangulate_rings([p['source_polygon_local']]):
            surf.face([(x,y,top) for x,y in triangle])
        F._volume_from_top(surf,bottom)
        obj = add(F._object(prefix+'_'+label,F._new_mesh(prefix+'_'+label,surf.vertices,surf.faces,materials[material]),col,role),role)
        T._fixed(obj)
        obj['reference_only'] = True; obj['not_reconstructed_mountain_or_historic_platform'] = True
        return obj

    support = source_prism('source_support_reference',p['source_support_bottom_z_m'],d['source_support_top_z_m'],'source_support_reference',p['material_scheme']['source_support'])
    floor = source_prism('complete_source_reference_floor',d['source_support_top_z_m'],d['reference_floor_top_z_m'],'source_reference_floor',p['material_scheme']['reference_floor'])
    roof_result = P.build_five_petal_roofs(p['roof_profile'],col,materials,cache)
    for obj in roof_result['objects']:
        transform = obj.matrix_basis.copy()
        obj.data = obj.data.copy(); obj.data.transform(transform)
        obj.matrix_basis = Matrix.Identity(4)
        T._fixed(obj)
        obj['phase_baked_into_private_mesh'] = p['roof_profile']['phase_rad']
        add(obj,obj['semantic_role'])
    roofs = sorted(components['roof'],key=lambda obj:obj['roof_tier_index'])

    def contact(label, roof, footprint, bottom, role, material, tier):
        # T clips the full convex domain to the real downward triangles. It
        # fails rather than interpolating unsupported sparse rim samples.
        surf = T._contact_surface(roof,footprint,bottom)
        obj = add(F._object(prefix+'_'+label,F._new_mesh(prefix+'_'+label,surf.vertices,surf.faces,materials[material]),col,role),role)
        T._fixed(obj)
        obj['roof_contact_object'] = roof.name; obj['bottom_z_m'] = bottom
        obj['support_footprint_local'] = json.dumps(footprint); obj['roof_tier_index'] = tier
        contacts.append({'object':obj.name,'roof':roof.name,'footprint_local':footprint,'bottom_z_m':bottom,'role':role,'tier_index':tier})
        return obj

    axes = _axes(p)
    columns = [contact('continuous_column_'+str(i),roofs[1],_circle(x,y,d['column_radius_m']),d['reference_floor_top_z_m'],'column',p['material_scheme']['column'],1) for i,(x,y) in enumerate(axes)]

    def beam(label, a, b, top, role):
        length = math.dist(a,b)+d['beam_width_m']
        obj = F.box(prefix+'_'+label,((a[0]+b[0])/2,(a[1]+b[1])/2,top-d['beam_height_m']/2),(length,d['beam_width_m'],d['beam_height_m']),materials[p['material_scheme']['beam']],col,None,role)
        obj.rotation_euler.z = math.atan2(b[1]-a[1],b[0]-a[0])
        T._fixed(obj); add(obj,role)
        return obj

    for level,top in ((0,d['lower_beam_top_z_m']),(1,d['upper_beam_top_z_m'])):
        for i,(a,b) in enumerate(zip(axes,axes[1:]+axes[:1])):
            beam('ring_beam_'+str(level)+'_'+str(i),a,b,top,'study_ring_beam')
    phase = p['roof_profile']['phase_rad']
    for i,a in enumerate(axes):
        angle = phase+i*2*math.pi/5
        b = (d['lower_bearing_axis_radius_m']*math.cos(angle),d['lower_bearing_axis_radius_m']*math.sin(angle))
        link = beam('lower_radial_beam_'+str(i),a,b,d['lower_beam_top_z_m'],'study_radial_beam')
        cap = contact('lower_bearing_'+str(i),roofs[0],_circle(*b,d['lower_bearing_radius_m']),d['lower_beam_top_z_m'],'roof_bearing_cap',p['material_scheme']['beam'],0)
        cap['support_object'] = link.name
        beam_links.append({'beam':link.name,'bearing':cap.name,'column':columns[i].name})
    for column in columns:
        column['support_object'] = floor.name
    root['profile_sha256'] = digest; root['biluoting_pavilion_profile'] = json.dumps(p,ensure_ascii=False)
    root['mountain_reconstructed'] = False; root['whole_city_complete'] = False
    bpy.context.view_layer.update()
    return {'root':root,'objects':objects,'components':components,'roofs':roofs,
            'contacts':contacts,'beam_links':beam_links,'reference_floor':floor,
            'source_support_reference':support,'profile':p,'third_party_cost':0,
            'occupied_storeys':None,'reference_floor_count':1,'human_approval':'pending',
            'complete_reconstruction_proven':False,'unbuilt_features':p['unbuilt']}
