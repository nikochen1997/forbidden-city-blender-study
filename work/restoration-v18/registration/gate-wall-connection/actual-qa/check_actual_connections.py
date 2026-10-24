"""Independent CPU domain checks. Never import Blender or the connection builder."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import traceback

from shapely.geometry import MultiPoint, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[5]
PROPOSAL = 'work/restoration-v18/registration/gate-wall-connection/planned-gap-and-source-contained-proposal-01.json'
PROPOSAL_SHA = '07a3cbc19fe055bd5e472bc1736faa26067d79ba8b29fbfcdc0f27d83b37488a'
CAPTURE = 'work/restoration-v18/registration/actual-source-actors.json'
CAPTURE_SHA = '335f196ff733321c36b38fc17942254f5580772b998cff478e7e329e6f4a799f'
PROFILE_FILE = 'work/restoration-v18/profiles/building-profiles-v1.json'
PROFILE_SHA = '043ab05ca41bcb2dafc39b7eaf85a18506822eefe85cc461a09fd817b72275d0'
PALETTE_FILE = 'work/restoration-v18/profiles/palette-v1.json'
PALETTE_SHA = '7b1033aeb5bf197b811ebb5676e551cae34b890445319f4b47a86350e19404ca'
EPS = 1e-4
AREA = 1e-7
MAX_OVERLAP = .005


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned(path, digest):
    path = ROOT / path
    require(sha(path) == digest, 'immutable input SHA differs: ' + str(path))
    return json.loads(path.read_text())


def domain(actual, expected, label):
    """Complete domain and complete boundary, including holes; no sample points."""
    require(actual.is_valid and expected.is_valid, label + ': invalid domain')
    require(actual.geom_type == expected.geom_type == 'Polygon', label + ': disconnected domain')
    require(len(actual.interiors) == len(expected.interiors), label + ': hole count differs')
    missing = expected.difference(actual.buffer(EPS)).area
    extra = actual.difference(expected.buffer(EPS)).area
    boundary = actual.boundary.hausdorff_distance(expected.boundary)
    require(missing <= AREA and extra <= AREA and boundary <= EPS,
            label + ': complete area/boundary exceeds 100um')
    return {'missing_outside_100um_area_m2': missing, 'extra_outside_100um_area_m2': extra,
            'complete_boundary_Hausdorff_m': boundary, 'actual_area_m2': actual.area,
            'expected_area_m2': expected.area, 'actual_holes': len(actual.interiors)}


def mesh_arrays(mesh):
    vertices, triangles = mesh['vertices'], mesh['triangles']
    require(bool(vertices) and bool(triangles), 'actual geometry absent')
    require(all(len(v) == 3 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in v)
                for v in vertices), 'nonfinite actual vertex')
    require(all(len(t) == 3 and len(set(t)) == 3 and all(type(i) is int and 0 <= i < len(vertices) for i in t)
                for t in triangles), 'invalid actual triangle index')
    return vertices, triangles


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def normal(points):
    a, b, c = points
    return cross([b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)])


def cap(mesh, z, normal_sign=None):
    vertices, triangles = mesh_arrays(mesh)
    polys = []
    for tri in triangles:
        points = [vertices[i] for i in tri]
        if all(abs(p[2]-z) <= EPS for p in points):
            n = normal(points)
            if abs(n[2]) <= 1e-12:
                continue
            if normal_sign is not None:
                require(n[2]*normal_sign > 0, 'actual cap winding reversed')
            polys.append(Polygon([p[:2] for p in points]))
    require(bool(polys), 'actual complete horizontal cap absent')
    return unary_union(polys)


def prism(mesh, expected, low, high, label):
    vertices, triangles = mesh_arrays(mesh)
    require(abs(min(v[2] for v in vertices)-low) <= EPS
            and abs(max(v[2] for v in vertices)-high) <= EPS, label + ': wrong Z extent')
    require(all(min(abs(v[2]-low), abs(v[2]-high)) <= EPS for v in vertices),
            label + ': non-prism Z layer')
    edges, directed, graph, volume6 = Counter(), Counter(), {}, 0.0
    origin = vertices[0]
    for tri in triangles:
        points = [vertices[i] for i in tri]
        n = normal(points)
        require(sum(x*x for x in n) > 1e-24, label + ': zero-area actual triangle')
        for a, b in zip(tri, tri[1:] + tri[:1]):
            edges[tuple(sorted((a, b)))] += 1
            directed[(a, b)] += 1
            graph.setdefault(a, set()).add(b)
            graph.setdefault(b, set()).add(a)
        a, b, c = [[p[j]-origin[j] for j in range(3)] for p in points]
        volume6 += sum(a[j]*cross(b, c)[j] for j in range(3))
        flat = max(p[2] for p in points)-min(p[2] for p in points) <= EPS
        if not flat:
            # Every point of the finite side triangle is bounded, not its extrapolated plane.
            xy = MultiPoint([p[:2] for p in points]).convex_hull
            require(expected.boundary.buffer(EPS).covers(xy),
                    label + ': complete finite side projection outside boundary tube')
    require(all(count == 2 for count in edges.values()), label + ': open/nonmanifold actual mesh')
    require(all(directed[(a, b)] == directed[(b, a)] for a, b in edges),
            label + ': inconsistent edge winding')
    reached, pending = set(), [next(iter(graph))]
    while pending:
        v = pending.pop()
        if v not in reached:
            reached.add(v)
            pending.extend(graph[v]-reached)
    require(len(reached) == len(vertices), label + ': disconnected/unused mesh vertices')
    require(volume6 > 0, label + ': inward or nonpositive volume')
    bottom, top = cap(mesh, low, -1), cap(mesh, high, +1)
    bproof = domain(bottom, expected, label + ' bottom')
    tproof = domain(top, expected, label + ' top')
    require(abs(volume6/6-expected.area*(high-low)) <= max(AREA, EPS*expected.length*(high-low)),
            label + ': volume differs from full prism')
    return bottom, {'bottom_cap': bproof, 'top_cap': tproof, 'positive_volume_m3': volume6/6,
                    'vertices': len(vertices), 'triangles': len(triangles), 'all_closed_oriented': True}


def depth(poly, vector):
    """Extremum of every vertex of every full intersection component."""
    if poly.is_empty:
        return None
    geometries = list(poly.geoms) if hasattr(poly, 'geoms') else [poly]
    coords = []
    for g in geometries:
        if g.geom_type == 'Polygon':
            coords.extend(g.exterior.coords)
            for ring in g.interiors:
                coords.extend(ring.coords)
        elif hasattr(g, 'coords'):
            coords.extend(g.coords)
    values = [x*vector[0]+y*vector[1] for x, y in coords]
    return max(values)-min(values)


def check_geometries(connectors, gate_walls, old_walls, proposal, capture):
    require(set(connectors) == set(gate_walls) == set(old_walls) == {'west', 'east'},
            'exact two distinct sides required')
    source = Polygon(proposal['gate_source_polygon_world'], proposal['gate_source_holes_world'])
    # The exact gate sidewall frame is in the immutable proposal's local/world polygons.
    rows, all_new_names = [], set()
    for row in proposal['rows']:
        side = row['side']
        expected = Polygon(row['proposal']['polygon_world'], row['proposal']['holes_world'])
        conn, proof = prism(connectors[side], expected, 0, 3, side + ' connector')
        require(not connectors[side].get('hidden', False), 'connector hidden')
        name = connectors[side]['object']
        require(name not in all_new_names, 'duplicate connector object')
        all_new_names.add(name)
        gate_expected = shape(row['planned_gate_sidewall_XY'])
        gate, gateproof = prism(gate_walls[side], gate_expected, .35, 4.88, side + ' gate wall')
        old = old_walls[side]
        original = capture['actor_evidence'][row['original_wall_actor']]
        expected_old = cap({'vertices': original['evaluated_world_vertices'],
                            'triangles': original['evaluated_world_triangles']}, 0)
        actual_old = cap(old, 0)
        require(actual_old.equals_exact(expected_old, 0) or actual_old.symmetric_difference(expected_old).area == 0,
                side + ': old full domain changed')
        require(old['vertices'] == original['evaluated_world_vertices']
                and old['triangles'] == original['evaluated_world_triangles'], side + ': old evaluated geometry differs')
        require(source.buffer(EPS).covers(conn) and conn.difference(source.buffer(EPS)).area <= AREA,
                side + ': connector outside complete source domain')
        # Proposal holes are a separate source limit, never filled by a bbox approximation.
        for hole in source.interiors:
            require(conn.intersection(Polygon(hole).buffer(-EPS)).area <= AREA,
                    side + ': connector fills a source hole')
        oldover, gateover = conn.intersection(actual_old), conn.intersection(gate)
        require(oldover.area > AREA and gateover.area > AREA, side + ': no positive full end overlap')
        olddepth = depth(oldover, row['proposal']['normal_along_actual_terminal'])
        # gate normal from the long edge of its immutable side polygon, also avoiding angle reconstruction.
        worldp = list(gate_expected.exterior.coords)
        # The first box edge may be short; use the longest boundary edge (gate local Y).
        a,b = max(zip(worldp,worldp[1:]), key=lambda ab: math.dist(*ab))
        length = math.dist(a,b)
        gatenormal = [-(b[1]-a[1])/length, (b[0]-a[0])/length]
        gatedepth = depth(gateover, gatenormal)
        require(olddepth <= MAX_OVERLAP and gatedepth <= MAX_OVERLAP,
                side + ': actual overlap depth exceeds 5mm')
        desired_gap = expected.difference(actual_old.union(gate))
        uncovered = desired_gap.difference(conn.buffer(EPS)).area
        require(uncovered <= AREA, side + ': full inside gap has uncovered domain')
        joined = unary_union([actual_old, conn, gate])
        require(joined.geom_type == 'Polygon', side + ': end joins disconnected')
        props = connectors[side].get('custom_properties', {})
        require(not any(k in props for k in ('source_building_id', 'source_part_id', 'osm_part_id',
                                             'source_wall_id', 'source_reference_part_id')),
                side + ': connector inherited original-source identity')
        require(type(props.get('third_party_cost')) is int and props['third_party_cost'] == 0
                and props.get('human_approval') == 'pending'
                and props.get('not_historical_attachment') is True
                and props.get('unmeasured_source_context') is True
                and props.get('complete_old_endcap_continuation_claimed') is False,
                side + ': reference scope or zero budget metadata differs')
        rows.append({'side': side, 'connector': name, 'prism': proof, 'gate_wall': gateproof,
                     'old_wall_full_raw_evaluated_geometry_unchanged': True,
                     'actual_old_wall_overlap_area_m2': oldover.area,
                     'actual_gate_wall_overlap_area_m2': gateover.area,
                     'actual_old_overlap_depth_m': olddepth, 'actual_gate_overlap_depth_m': gatedepth,
                     'complete_inside_gap_uncovered_outside_100um_area_m2': uncovered,
                     'connector_outside_source_area_m2': conn.difference(source).area,
                     'single_connected_full_union': True})
    return {'rows': rows, 'EPS_m': EPS, 'AREA_m2': AREA, 'MAX_OVERLAP_m': MAX_OVERLAP,
            'actual_connector_count': 2, 'original_wall_visibility_exceptions_added': 0,
            'complete_full_width_old_endcap_continuation_claimed': False}


def check(doc):
    """Exact factory schema, also usable by a saved reader exporting that schema."""
    require(doc['schema'] == 'v18-gate-wall-connections-actual-factory-world/1', 'wrong readout schema')
    require(doc['coordinate_space'] == 'WORLD', 'WORLD actual readout required')
    require(all(Path(path).suffix.lower() != '.blend' for path in doc['inputs_sha256']),
            'isolated context CPU must not require a native file')
    require(all(sha(ROOT/path) == value for path,value in doc['inputs_sha256'].items()),
            'actual factory immutable input bytes drifted')
    proposal, capture = pinned(PROPOSAL, PROPOSAL_SHA), pinned(CAPTURE, CAPTURE_SHA)
    require(doc['proposal_sha256'] == PROPOSAL_SHA, 'wrong proposal binding')
    require(doc['source_capture_sha256'] == CAPTURE_SHA, 'wrong old-source capture binding')
    profiles = pinned(PROFILE_FILE, PROFILE_SHA)
    profile = next(p for p in profiles['buildings'] if p['building_id'] == 'nansansuo_common_gate')
    require(doc['profile'] == profile, 'actual gate uses wrong frozen profile')
    grey = pinned(PALETTE_FILE, PALETTE_SHA)['materials']['grey']['rgba']
    require(len(doc['connectors']) == 2 and {r['side'] for r in doc['connectors']} == {'west', 'east'},
            'exact connector side inventory differs')
    geometry = doc['geometry']
    connectors = {r['side']: geometry[r['object']] for r in doc['connectors']}
    gate_walls = {side: geometry[name] for side, name in doc['actual_gate_sidewalls'].items()}
    old_walls = {side: row['after'] for side, row in doc['old_walls'].items()}
    result = check_geometries(connectors, gate_walls, old_walls, proposal, capture)
    _, result['complete_reference_floor'] = prism(geometry[doc['reference_floor']],
        Polygon(proposal['gate_source_polygon_world'], proposal['gate_source_holes_world']),
        0, .35, 'whole eight-point reference slab')
    for side, connector in connectors.items():
        mats = connector['materials']
        require(len(mats) == 1 and all(abs(a-b) < 1e-6 for key in ('diffuse', 'shader')
                                     for a,b in zip(mats[0][key], grey)), side + ': neutral grey palette differs')
        require(all(i == 0 for i in connector['raw_face_material_indices'])
                and all(i == 0 for i in connector['triangle_materials']), side + ': unaccounted connector material index')
    for side in ('west', 'east'):
        row = doc['old_walls'][side]
        original = capture['actor_evidence'][next(r['original_wall_actor'] for r in proposal['rows'] if r['side'] == side)]
        require(row['before'] == row['after'] == geometry[row['object']],
                side + ': original wall changed during factory operations')
        for key in ('raw_vertices', 'raw_faces', 'raw_face_material_indices', 'matrix_world',
                    'custom_properties', 'parent', 'actual_material_slots', 'visibility'):
            require(row['after'][key] == original[key], side + ': original raw/state guard differs: ' + key)
        expected_collections = [c['name'] for c in original['collections']]
        actual_collections = row['after']['collections']
        if actual_collections and isinstance(actual_collections[0], dict):
            require(actual_collections == original['collections'], side + ': old collection flags differ')
        else:
            require(actual_collections == expected_collections, side + ': old collection membership differs')
        require(len(row['after']['materials']) == len(original['actual_material_slots']),
                side + ': old material slot count differs')
        for mat, (_, name) in zip(row['after']['materials'], original['actual_material_slots']):
            captured = capture['material_evidence'][name]
            colour = next(v['default_value'] for v in captured['node_colour_inputs'] if v['socket'] == 'Base Color')
            require(mat['name'] == name and mat['diffuse'] == captured['diffuse_rgba'] and mat['shader'] == colour,
                    side + ': old diffuse/shader material state differs')
    require(type(doc['original_source_population_before']) is int
            and type(doc['original_source_population_after']) is int
            and doc['original_source_population_before'] >= 0
            and doc['original_source_population_before'] == doc['original_source_population_after'],
            'original source population changed')
    require(doc['new_original_source_identifier_count'] == 0, 'new context counted as original source')
    require(doc['old_source_visibility_changes'] == [], 'old wall visibility changed')
    require(type(doc['third_party_cost']) is int and doc['third_party_cost'] == 0,
            'integer-zero budget differs')
    # Actual private Blender mutations must be rejected by the same complete-domain path.
    negatives = doc['real_geometry_negative_controls']
    require(len(negatives) == 2 and {n['id'] for n in negatives} == {'EXTRA-01', 'EXTRA-02'},
            'two actual geometry negative controls absent')
    result['actual_geometry_negative_controls'] = []
    for mutation in negatives:
        require(mutation['actual_geometry_exported_before_restore'] is True, 'actual mutant geometry absent')
        try:
            check_geometries(mutation['connectors'], gate_walls, old_walls, proposal, capture)
        except AssertionError as exc:
            reason = str(exc)
            wanted = 'boundary tube' if mutation['id'] == 'EXTRA-01' else 'open/nonmanifold'
            require(wanted in reason, 'actual mutant rejected for unrelated reason: ' + reason)
            result['actual_geometry_negative_controls'].append({'id': mutation['id'], 'rejected': True, 'reason': reason})
        else:
            raise AssertionError('actual geometry negative unexpectedly passed: ' + mutation['id'])
        check_geometries(connectors, gate_walls, old_walls, proposal, capture)
    require(all(sha(ROOT/path) == value for path,value in doc['inputs_sha256'].items()),
            'actual factory inputs changed during full-domain CPU')
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--readout', type=Path, required=True)
    ap.add_argument('--readout-sha256', required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    require(not args.output.exists(), 'fresh CPU report path required')
    require(sha(args.readout) == args.readout_sha256, 'actual readout SHA mismatch')
    report = {'schema': 'v18-actual-gate-connection-full-domain-CPU/1',
              'readout_file': str(args.readout.resolve()), 'readout_sha256': args.readout_sha256,
              'checker_file': str(Path(__file__).resolve()), 'checker_sha256': sha(__file__),
              'proposal_sha256': PROPOSAL_SHA, 'capture_sha256': CAPTURE_SHA}
    try:
        report['evidence'] = check(json.loads(args.readout.read_text()))
        require(sha(args.readout) == args.readout_sha256, 'actual readout changed during CPU')
        report['summary'] = {'passed': 1, 'failed': 0}
        code = 0
    except Exception as exc:
        report['summary'] = {'passed': 0, 'failed': 1}
        report.update(error=str(exc), traceback=traceback.format_exc())
        code = 1
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(report['summary']))
    raise SystemExit(code)


if __name__ == '__main__':
    main()
