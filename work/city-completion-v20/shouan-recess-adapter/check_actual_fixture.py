"""Independent complete-domain CPU audit of the private actual WORLD export.

No bpy, generator, native I/O or geometry repairs. Negatives are explicitly
actual-export-derived CPU controls, not extra Blender executions.
"""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

from shapely.geometry import LineString, Polygon, box
from shapely.ops import polygonize, unary_union

from recess_contract import plan_geometry, validate_private

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EPS = 1e-4
HELPERS = {
    'work/restoration-v18/module-qa/check_actual_exterior_supports.py': '566fc03c4044a87db6a45016219ea023adbf7ea240fd4b6b36c4097b06a194f7',
    'work/restoration-v19/tower-qa/check_actual_contact_domains.py': '35107c3650e86702d2b21a30e1931390aa66a80a2b2d337bd08751bd143c4327',
    'work/restoration-v19/formal-support-review/review_formal_supports.py': '4b732ad9896f93053b32c8dfcbc2f23918165db9bf3354be851b47da7600f790',
}


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, rel):
    require(sha(ROOT/rel) == HELPERS[rel], 'frozen CPU helper drift')
    spec = importlib.util.spec_from_file_location(name, ROOT/rel)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


S = load('v20_actual_complete_supports', next(iter(HELPERS)))
G, P = S.G, S.G.P
CONTACT = load('v20_actual_complete_roof_contacts', list(HELPERS)[1])
require(P.EPS == EPS and CONTACT.Z_TOL == 2e-4, 'frozen model tolerances drift')
section_path = list(HELPERS)[2]
require(sha(ROOT/section_path) == HELPERS[section_path], 'frozen actual section helper drift')
node = next(n for n in ast.parse((ROOT/section_path).read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'horizontal_section')
ns = {'LineString': LineString, 'polygonize': polygonize, 'unary_union': unary_union, 'require': require}
exec(compile(ast.Module(body=[node], type_ignores=[]), str(ROOT/section_path), 'exec'), ns)
horizontal_section = ns['horizontal_section']


def geometry(row, local=False):
    return {'vertices': row['vertices_local' if local else 'vertices_world'], 'triangles': row['triangles'],
            'hidden': row['hidden'], **row['props']}


def rows(doc):
    result = {r['name']: r for r in doc['objects']}
    require(len(result) == len(doc['objects']), 'duplicate actual mesh names')
    return result


def preserve(doc):
    validate_private(doc['profile'], 'private_fixture')
    require(doc['schema'] == 'v20-private-shouan-recess-actual-world/1' and doc['coordinate_space'] == 'WORLD', 'actual WORLD export required')
    require(doc['native_opened'] is False and doc['native_saved'] is False and doc['production_build'] is False, 'private factory is not native or production evidence')
    require(doc['occupied_storeys'] is None, 'occupied storeys remain unknown')
    require(doc['protected_global_before'] == doc['protected_global_after'], 'unrelated global object changed')
    actual = rows(doc); base = {r['name']: r for r in doc['generated_before_adapter']['objects']}; a = doc['adapter']
    deleted = a['removed_new_south_wall']; moved = set(a['moved_central_frame_leaf_names'])
    added = set(a['new_wall_names'].values()) | set(a['new_roof_closure_names'])
    require(set(actual) == set(base)-{deleted} | added and len(actual) == len(base)+7, 'only one new wall replaced by five walls and three closures')
    require(a['retained_objects_before_sha256'] == a['retained_objects_after_sha256'], 'retained object signature mismatch')
    for name in set(base)-{deleted}-moved:
        require(actual[name] == base[name], 'retained roof/north/sides/column/beam/floor or other object changed: '+name)
    offset = a['plan']['setback_m_private_study']
    for name in moved:
        v0, v1 = base[name]['vertices_local'], actual[name]['vertices_local']
        require(base[name]['triangles'] == actual[name]['triangles'] and len(v0) == len(v1), 'moved central frame/leaf shape changed')
        require(all(abs(b[0]-x[0]) <= EPS and abs(b[1]-x[1]-offset) <= EPS and abs(b[2]-x[2]) <= EPS for x, b in zip(v0, v1)),
                'central frame/leaf translation differs from actual setback')
    old_north = [r for r in doc['generated_before_adapter']['openings'] if r['wall_side'] == 'north']
    require(old_north == [r for r in doc['openings'] if r['wall_side'] == 'north'], 'north opening records changed')
    return {'retained_meshes_exactly_unchanged': len(base)-1-len(moved), 'central_frames_and_leaf_meshes_translated': len(moved),
            'unrelated_global_objects_unchanged': len(doc['protected_global_before']), 'new_mesh_delta': 7}


def wall_layout(doc):
    by = rows(doc); p = doc['profile']; spec = plan_geometry(p); names = doc['adapter']['new_wall_names']
    require(set(names) == set(spec['wall_bounds_local']), 'five wall identities required')
    top_sections = {}
    for label, name in names.items():
        mesh = geometry(by[name], True); top = G.horizontal(mesh, G.zrange(mesh)[1], True)
        expected = box(*spec['wall_bounds_local'][label])
        S.contained(top, expected, 'actual complete new wall top')
        S.contained(expected, top, 'expected complete new wall top')
        top_sections[label] = horizontal_section(mesh, p['dimensions']['wall_top_z_m']-.05)
    corners = []
    for first, second in [('south_west_two_bays', 'return_west'), ('return_west', 'recessed_central_bay'),
                          ('south_east_two_bays', 'return_east'), ('return_east', 'recessed_central_bay')]:
        overlap = top_sections[first].intersection(top_sections[second]).area
        require(overlap > P.AREA_EPS, 'actual return/front/recess wall corner has no positive-area overlap')
        corners.append({'pair': [first, second], 'actual_triangle_section_overlap_m2': overlap})
    return {'walls': len(names), 'only_central_plane_recessed': True, 'corners': corners}


def clip3(points, axis, sign, limit):
    if not points:
        return []
    out = []; first = points[-1]; da = sign*(first[axis]-limit)
    for second in points:
        db = sign*(second[axis]-limit)
        if (da >= 0) != (db >= 0):
            f = da/(da-db); out.append([first[i]+f*(second[i]-first[i]) for i in range(3)])
        if db >= 0:
            out.append(second)
        first, da = second, db
    return out


def area3(points):
    if len(points) < 3:
        return 0.
    total = 0.; a = points[0]
    for b, c in zip(points[1:], points[2:]):
        u, v = ([q[i]-a[i] for i in range(3)] for q in (b, c))
        cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        total += math.sqrt(sum(x*x for x in cross))/2
    return total


def void_prism(meshes, bounds, label):
    """Entire actual triangle intersection with the open aperture volume.

    The normal-axis interval extends outside both actual wall faces. Therefore
    any solid wall plugging it must expose a triangle surface inside this prism;
    absence of surfaces cannot hide a prism wholly contained inside that wall.
    """
    xmin, ymin, zmin, xmax, ymax, zmax = bounds
    maximum = 0.
    for mesh in meshes:
        for tri in mesh['triangles']:
            cut = [mesh['vertices'][i] for i in tri]
            for axis, sign, limit in ((0, 1, xmin), (0, -1, xmax), (1, 1, ymin), (1, -1, ymax), (2, 1, zmin), (2, -1, zmax)):
                cut = clip3(cut, axis, sign, limit)
                if not cut:
                    break
            maximum = max(maximum, area3(cut))
    require(maximum < 1e-10, 'actual structural wall surface blocks complete '+label+' aperture prism')
    return {'maximum_structural_triangle_area_inside_clear_prism_m2': maximum,
            'complete_volume_surface_intersection_not_ray_sample': True}


def aperture_voids(doc):
    by = rows(doc); spec = plan_geometry(doc['profile']); names = doc['adapter']['new_wall_names']
    opening_records = sorted((r for r in doc['openings'] if r['wall_side'] == 'south'), key=lambda r: r['bay_index'])
    require(len(opening_records) == 5, 'all five actual apertures required')
    evidence = []
    for i, record in enumerate(opening_records):
        name = names[spec['wall_for_bay'][i]]; mesh = geometry(by[name], True)
        require(record['wall_segment_names'] == [name], 'actual opening target wall differs')
        expected_y = spec['central_y'] if i == 2 else spec['front_y']
        x, y, z = record['center_local']; width, height = record['clear_width_m'], record['clear_height_m']
        require(abs(y-expected_y) < 1e-9, 'only central actual aperture must move back')
        ys = [v[1] for v in mesh['vertices']]
        require(abs(max(ys)-min(ys)-doc['profile']['dimensions']['wall_thickness_m']) <= 2*EPS,
                'actual opening wall depth differs from study thickness')
        result = void_prism([mesh], [x-width/2+EPS, min(ys)-EPS, z-height/2+EPS,
                                   x+width/2-EPS, max(ys)+EPS, z+height/2-EPS], 'bay '+str(i))
        evidence.append({'bay_index': i, 'target': name, 'actual_through_wall_depth_m': max(ys)-min(ys), **result})
    center = opening_records[2]; x, y, z = center['center_local']
    approach = void_prism([geometry(by[n], True) for n in names.values()],
                          [x-center['clear_width_m']/2+EPS, spec['front_y']-.2, z-center['clear_height_m']/2+EPS,
                           x+center['clear_width_m']/2-EPS, y+.2, z+center['clear_height_m']/2-EPS], 'central recessed approach')
    leaves = center['leaf_reference_names']
    require(len(leaves) == len(set(leaves)) == 4 and all(n in by for n in leaves), 'exactly four actual central leaf references required')
    require(all(by[n]['role'] == 'door_leaf' for n in leaves), 'four references must be actual leaf meshes')
    require(center['leaf_pose'] == 'neutral_unmeasured_reference_not_known_open_state', 'leaf open state is unknown')
    return {'five_real_through_voids': evidence, 'central_approach_structural_void': approach,
            'central_actual_leaf_reference_count': 4,
            'leaf_references_excluded_from_structural_wall_void_test': True,
            'documented_open_state_spacing_carving_claimed': False}


def supports_and_domain(doc):
    by = rows(doc); geom = {n: geometry(r) for n, r in by.items()}
    b = {'id': 'shouangong', 'profile': doc['profile'], 'components': doc['components'],
         'geometry': geom, 'reference_floor': doc['reference_floor']}
    result = S.supports(b)
    floor = geom[doc['reference_floor']]; floor_z = G.zrange(floor)[1]
    floor_top = G.horizontal(floor, floor_z, True)
    wall_bottoms = []
    for n in doc['adapter']['new_wall_names'].values():
        lo, hi = G.zrange(geom[n]); cap = G.horizontal(geom[n], lo, False)
        require(abs(lo-floor_z) <= EPS, 'new complete wall bottom leaves floor Z')
        wall_bottoms.append({'name': n, **S.contained(cap, floor_top, 'actual full new wall bottom')})
    closures = []
    front_beam = next(n for n in doc['components']['beam'] if by[n]['props'].get('wall_side') == 'south')
    for n in doc['components']['roof_closure_wall']:
        row = by[n]; cap, z, _ = G.full_cap(geom[n], False); side = row['props']['wall_side']
        if n in doc['adapter']['new_roof_closure_names']:
            target = row['props']['support_object']
        elif side == 'south':
            target = front_beam
        else:
            target = doc['walls'][side]
        closures.append({'name': n, 'actual_support': target, **G.supported(cap, z, [geom[target]], True, 'complete closure bottom')})
    source = Polygon(doc['profile']['source_polygon_world'], doc['profile']['source_holes_world'])
    domain = S.contained(S.projection(geom, list(geom)), source, 'all actual complete triangle projections')
    return {'original_columns_bases_bearings': result, 'five_new_wall_bottoms': wall_bottoms,
            'all_closure_bottoms': closures, 'all_actual_source_domain': domain,
            'retained_south_closure_fully_supported_by_original_front_beam': front_beam}


def roof_contacts(doc):
    by = rows(doc); evidence = []
    for row in doc['objects']:
        target = row['props'].get('roof_contact_object')
        if target:
            evidence.append(CONTACT.check_one(row, by[target]))
    require(len(evidence) == len(doc['components']['roof_closure_wall'])+len(doc['components']['roof_bearing_post']), 'complete contact inventory omitted')
    return {'complete_actual_contact_solids': evidence, 'XY_support_tolerance_m': EPS,
            'roof_affine_Z_tolerance_m': CONTACT.Z_TOL, 'per_triangle_uncovered_area_tolerance_m2': CONTACT.AREA_TOL}


def added_block(doc):
    mutated = copy.deepcopy(doc); by = rows(mutated)
    rec = next(r for r in mutated['openings'] if r['wall_side'] == 'south' and r['bay_index'] == 2)
    row = by[rec['wall_segment_names'][0]]; x, y, z = rec['center_local']; t = mutated['profile']['dimensions']['wall_thickness_m']
    w, h = rec['clear_width_m']/2, rec['clear_height_m']/2
    vertices = [[x+dx, y+dy, z+dz] for dx, dy, dz in [(-w,-t/2,-h),(w,-t/2,-h),(w,t/2,-h),(-w,t/2,-h),(-w,-t/2,h),(w,-t/2,h),(w,t/2,h),(-w,t/2,h)]]
    offset = len(row['vertices_local']); row['vertices_local'].extend(vertices)
    matrix = mutated['root_matrix_world']
    row['vertices_world'].extend([[sum(matrix[i][j]*v[j] for j in range(3))+matrix[i][3] for i in range(3)] for v in vertices])
    faces = [(0,3,2),(0,2,1),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    row['triangles'].extend([[offset+i for i in tri] for tri in faces])
    return mutated


def run(doc):
    checks = []
    for ident, function in [('CPU-01-PRESERVATION', preserve), ('CPU-02-FIVE-WALL-LAYOUT', wall_layout),
                            ('CPU-03-REAL-APERTURE-PRISMS-FOUR-LEAVES', aperture_voids),
                            ('CPU-04-FULL-SUPPORT-AND-SOURCE', supports_and_domain), ('CPU-05-ALL-ROOF-CONTACTS', roof_contacts)]:
        try:
            evidence = function(doc); checks.append({'id': ident, 'passed': True, 'evidence': evidence})
        except Exception as exc:
            checks.append({'id': ident, 'passed': False, 'error': str(exc)})
    controls = []
    plug = added_block(doc)
    controls.append(('EXTRA-01-ACTUAL-DERIVED-DOOR-PLUG', lambda: aperture_voids(plug), 'blocks complete'))
    leaves = copy.deepcopy(doc); next(r for r in leaves['openings'] if r['wall_side'] == 'south' and r['bay_index'] == 2)['leaf_reference_names'].pop()
    controls.append(('EXTRA-02-ACTUAL-DERIVED-MISSING-LEAF', lambda: aperture_voids(leaves), 'four actual'))
    lifted = copy.deepcopy(doc); name = lifted['adapter']['new_roof_closure_names'][0]
    for v in rows(lifted)[name]['vertices_world']:
        v[2] += .01
    controls.append(('EXTRA-03-ACTUAL-DERIVED-LIFTED-CLOSURE', lambda: roof_contacts(lifted), 'height gap'))
    other = copy.deepcopy(doc); next(iter(other['protected_global_after'].values()))['visibility'][2] = True
    controls.append(('EXTRA-04-ACTUAL-DERIVED-GLOBAL-VISIBILITY', lambda: preserve(other), 'global object changed'))
    for ident, function, reason in controls:
        try:
            function(); checks.append({'id': ident, 'passed': False, 'error': 'negative accepted'})
        except AssertionError as exc:
            checks.append({'id': ident, 'passed': reason in str(exc), 'rejected_reason': str(exc),
                           'type': 'in-memory actual-export-derived CPU control; not another Blender run'})
    return checks


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--readout', type=Path, required=True); parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(); require(not args.report.exists(), 'preserve prior actual report')
    pin = sha(args.readout); doc = json.loads(args.readout.read_text()); checks = run(doc)
    require(sha(args.readout) == pin, 'actual readout input changed')
    report = {'schema': 'v20-private-shouan-actual-complete-CPU/1', 'checks': checks,
              'summary': {'passed': sum(c['passed'] for c in checks), 'failed': sum(not c['passed'] for c in checks)},
              'actual_readout_sha256': pin, 'checker_sha256': sha(__file__), 'frozen_helpers_sha256': HELPERS,
              'native_opened': False, 'native_saved': False, 'generator_imported': False,
              'production_registration_verified': False, 'third_party_cost': 0, 'paid_service_calls': 0,
              'human_approval': 'pending', 'whole_city_complete': False}
    with args.report.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps(report['summary']))
    if report['summary']['failed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
