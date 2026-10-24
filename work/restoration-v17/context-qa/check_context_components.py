"""Independent CPU checks of captured WORLD triangles; no builder import."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
KERNEL_PATH = HERE.parent / 'stage-qa/check_stage_world_source.py'
KERNEL_SHA = 'd89db1dae5f3d910ca6ab862ce92ac761455a8bf7b96f313246b4e702d92c741'
REGISTRY_SHA = '0ff859b0e1434e9ee1c0501aa2f301fd6b8416e85e32a5c2b525f9e3c18479bc'
PRODUCER_SHA = 'c4e74d847dbcef9723728c7d7404fbaad5039341281302c340da5704d082611f'


def need(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


need(sha(KERNEL_PATH) == KERNEL_SHA, 'independent source CPU kernel drift')
spec = importlib.util.spec_from_file_location('context_independent_source_CPU_kernel', KERNEL_PATH)
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


def resolve(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def projected(mesh):
    vertices, triangles = mesh['vertices'], mesh['triangles']
    need(vertices and triangles, 'actual context mesh empty')
    need(all(len(v) == 3 and all(type(x) in (int, float) and math.isfinite(x) for x in v)
             for v in vertices), 'finite actual WORLD vertices')
    need(all(len(t) == 3 and all(type(i) is int and 0 <= i < len(vertices) for i in t)
             for t in triangles), 'strict actual triangle indices')
    polys = [Polygon([vertices[i][:2] for i in t]) for t in triangles]
    return unary_union([p for p in polys if p.area > 1e-14])


def horizontal_slice(meshes, z):
    """Intersect actual triangle edges, using consistent index order per edge."""
    lines = []
    for mesh in meshes:
        vertices = mesh['vertices']
        for tri in mesh['triangles']:
            points = []
            for i, j in zip(tri, tri[1:] + tri[:1]):
                i, j = sorted((i, j))
                a, b = vertices[i], vertices[j]
                da, db = a[2] - z, b[2] - z
                if abs(da) < 1e-12:
                    points.append(tuple(a[:2]))
                if abs(db) < 1e-12:
                    points.append(tuple(b[:2]))
                if da * db < 0:
                    f = (z - a[2]) / (b[2] - a[2])
                    points.append((a[0] + (b[0] - a[0])*f, a[1] + (b[1] - a[1])*f))
            points = list(dict.fromkeys(points))
            if len(points) == 2 and math.dist(*points) > 1e-12:
                lines.append(LineString(points))
            elif len(points) > 2:
                raise AssertionError('slice coincides with a complete face; use declared interior Z samples')
    need(lines, 'actual horizontal section absent')
    result = unary_union(list(polygonize(unary_union(lines))))
    need(not result.is_empty, 'actual horizontal slice did not close')
    return result


def side_reference_domains(component, full_source):
    # Explicit unmeasured caller reference thickness; independent Shapely clipping.
    return [LineString(edge).buffer(.18, cap_style=2).intersection(full_source)
            for edge in component['source_side_edges_world']]


def check(doc):
    need(doc['coordinate_space'] == 'WORLD', 'actual direct WORLD coordinates required')
    regpath = resolve(doc['registry_file'])
    producer = resolve(doc['producer_module_file'])
    need(doc['registry_sha256'] == REGISTRY_SHA == sha(regpath), 'registry source freeze mismatch')
    need(doc['producer_module_sha256'] == PRODUCER_SHA == sha(producer), 'producer pin mismatch; CPU never imports producer')
    registry = json.loads(regpath.read_text())
    expected_components = {r['component_id']: r for r in registry['context_components']}
    rows = doc['context_components']
    need(len(rows) == 3 and {r['component']['component_id'] for r in rows} == set(expected_components),
         'complete three context components required exactly once')
    evidence = []
    for row in rows:
        comp = row['component']
        ident = comp['component_id']
        need(comp == expected_components[ident], 'component full source/holes/frame differs from frozen registry ' + ident)
        need(len(row['objects']) == len(set(row['objects'])) and set(row['objects']) == set(row['geometry']),
             'actual context object/geometry inventory mismatch ' + ident)
        need(row['reference_floor'] in row['geometry'], 'reference floor is not owned by component')
        meshes = list(row['geometry'].values())
        for name, mesh in row['geometry'].items():
            need(mesh['object'] == name, 'actual mesh object locator mismatch')
            vis = mesh['visibility']
            need(not vis['hide_render'] and not vis['hide_viewport'] and not vis['hide_get'], 'actual context hidden ' + name)
            projected(mesh)
        source = C.polygon(comp['source_polygon_world'], comp['source_holes_world'])
        all_projection = unary_union([projected(m) for m in meshes])
        result = {'component_id': ident, 'objects': row['objects'],
                  'complete_all_triangle_projection': C.compare_domains(source, all_projection, ident + ' complete projection')}
        floor = dict(row['geometry'][row['reference_floor']], hidden=False)
        if ident != 'source_middle_neck':
            need(len(meshes) == 1 and floor['role'] == 'retained_source_proxy_remainder', 'proxy remainder inventory')
            result['caps'] = {k: C.compare_domains(source, p, ident + ' ' + k)
                              for k, p in C.mesh_domains(floor, 6, 0).items()}
        else:
            need(floor['role'] == 'reference_passage_floor', 'neck complete reference floor role')
            result['floor_caps'] = {k: C.compare_domains(source, p, 'neck floor ' + k)
                                   for k, p in C.mesh_domains(floor, .35, 0).items()}
            caps = [dict(m, hidden=False) for m in meshes if m['role'] == 'unknown_roof_thin_reference_cap']
            sides = [m for m in meshes if m['role'] == 'unmeasured_reference_passage_side']
            need(len(caps) == 1 and len(sides) == 2 and len(meshes) == 4, 'neck floor/two sides/thin cap inventory')
            result['overhead_caps'] = {k: C.compare_domains(source, p, 'neck overhead ' + k)
                                      for k, p in C.mesh_domains(caps[0], 5.10, 4.88).items()}
            wanted_sides = side_reference_domains(comp, source)
            for side in sides:
                need(abs(min(v[2] for v in side['vertices']) - .35) <= .0001
                     and abs(max(v[2] for v in side['vertices']) - 4.88) <= .0001, 'neck side full declared Z extent')
            C.compare_domains(unary_union(wanted_sides), unary_union([projected(s) for s in sides]), 'full two neck sides')
            a, b = comp['passage_axis_world']
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            route = LineString([(a[0] - dx/length*.1, a[1] - dy/length*.1),
                                (b[0] + dx/length*.1, b[1] + dy/length*.1)])
            section_rows = []
            for z in (.55, 1.5, 3.9, 4.7):
                occupied = horizontal_slice(meshes, z)
                geometry = C.compare_domains(unary_union(wanted_sides), occupied, 'neck occupied section z=' + str(z))
                need(occupied.intersection(route).is_empty, 'actual opaque neck blocks N/S central route')
                section_rows.append({'z_m': z, 'actual_side_positive_components': len(C.parts(occupied)),
                                     'actual_N_S_axis_blocked': False, 'full_occupied_domain': geometry})
            result['neck_actual_triangle_sections'] = section_rows
        evidence.append(result)
    return {'schema': 'v17-context-complete-source-independent-CPU/1', 'passed': True,
            'component_count': 3, 'fixed_tolerance_m': .0001, 'components': evidence,
            'checker_sha256': sha(__file__), 'CPU_kernel_sha256': KERNEL_SHA,
            'builder_imported': False, 'Blender_launched': False,
            'roof_category_or_metric_survey_proven': False,
            'complete_original_H_T_Bao_assemblies_verified': False,
            'saved_seven_component_adapter_required': True,
            'whole_city_or_east_route_completed': False}
