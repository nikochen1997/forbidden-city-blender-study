"""Local Blender geometry helpers; this module does not choose a palace layout.

The roof shapes are parameterized architectural types, not surveyed replicas.
Dimensions, locations, colors and opening schedules must come from caller records.
Importing this module neither mutates the scene nor performs I/O or service calls.
"""
import json
import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon


ROOF_TYPES = {"yingshan", "xuanshan", "xieshan", "wudian"}
DETAIL_LEVELS = {"overview", "near"}
PALETTE = {
    "yellow": ((0.60, 0.285, 0.025), 0.12, 0.32),
    "green": ((0.028, 0.20, 0.10), 0.08, 0.38),
    "grey": ((0.085, 0.10, 0.11), 0.02, 0.72),
    "red": ((0.36, 0.028, 0.018), 0.0, 0.68),
    "red_lacquer": ((0.39, 0.018, 0.012), 0.0, 0.32),
    "white_stone": ((0.66, 0.64, 0.58), 0.0, 0.82),
    "painted_beam": ((0.025, 0.13, 0.11), 0.0, 0.68),
    "dark_wood": ((0.055, 0.027, 0.012), 0.0, 0.71),
}


def _number(name, value, minimum=None, strictly_positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(name + " must be finite")
    if strictly_positive and value <= 0:
        raise ValueError(name + " must be positive")
    if minimum is not None and value < minimum:
        raise ValueError(name + " is below its minimum")
    return value


def _point(name, values):
    if len(values) != 3:
        raise ValueError(name + " requires three coordinates")
    return tuple(_number(name, value) for value in values)


def ensure_collection(name, parent=None):
    """Get a direct child collection or create it, without changing other trees."""
    parent = bpy.context.scene.collection if parent is None else parent
    for collection in parent.children:
        if collection.name == name:
            return collection
    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def create_materials(prefix="FC_"):
    result = {}
    for key, (color, metallic, roughness) in PALETTE.items():
        material = bpy.data.materials.get(prefix + key)
        if material is None:
            material = bpy.data.materials.new(prefix + key)
            material.diffuse_color = (*color, 1)
            material.use_nodes = True
            shader = material.node_tree.nodes.get("Principled BSDF")
            shader.inputs["Base Color"].default_value = (*color, 1)
            shader.inputs["Metallic"].default_value = metallic
            shader.inputs["Roughness"].default_value = roughness
        result[key] = material
    return result


def _new_mesh(name, vertices, faces, material, cache=None, key=None):
    cache_key = (key, material.name if material else None)
    if cache is not None and key is not None and cache_key in cache:
        return cache[cache_key]
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    data.update()
    if material:
        data.materials.append(material)
    if cache is not None and key is not None:
        cache[cache_key] = data
    return data


def _object(name, data, collection, role):
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj["semantic_role"] = role
    obj["representation"] = "typological_approximation"
    obj["third_party_cost"] = 0
    return obj


def box(name, center, dimensions, material, collection, mesh_cache=None, role="wall"):
    center = _point("box center", center)
    dimensions = tuple(_number("box dimension", value, strictly_positive=True) for value in dimensions)
    if len(dimensions) != 3:
        raise ValueError("box dimensions require three values")
    vertices = [(-.5, -.5, -.5), (.5, -.5, -.5), (.5, .5, -.5), (-.5, .5, -.5),
                (-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)]
    data = _new_mesh("FC_unit_box", vertices, faces, material, mesh_cache, "unit_box")
    obj = _object(name, data, collection, role)
    obj.location = center
    obj.scale = dimensions
    return obj


def column(name, center, radius, height, material, collection, mesh_cache=None, segments=16):
    center = _point("column center", center)
    radius = _number("column radius", radius, strictly_positive=True)
    height = _number("column height", height, strictly_positive=True)
    if not isinstance(segments, int) or not 6 <= segments <= 128:
        raise ValueError("column segments must be an integer from 6 to 128")
    vertices = [(math.cos(2 * math.pi * i / segments), math.sin(2 * math.pi * i / segments), z)
                for z in (-.5, .5) for i in range(segments)]
    faces = [tuple(reversed(range(segments))), tuple(range(segments, 2 * segments))]
    faces.extend((i, (i + 1) % segments, (i + 1) % segments + segments, i + segments)
                 for i in range(segments))
    data = _new_mesh("FC_unit_column", vertices, faces, material, mesh_cache, ("column", segments))
    obj = _object(name, data, collection, "column")
    obj.location = center
    obj.scale = (radius, radius, height)
    return obj


class _Surface:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.lookup = {}

    def vertex(self, point):
        key = tuple(round(value, 9) for value in point)
        if key not in self.lookup:
            self.lookup[key] = len(self.vertices)
            self.vertices.append(tuple(point))
        return self.lookup[key]

    def face(self, points):
        indices = [self.vertex(point) for point in points]
        cleaned = []
        for index in indices:
            if not cleaned or index != cleaned[-1]:
                cleaned.append(index)
        if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
            cleaned.pop()
        if len(set(cleaned)) >= 3:
            normal = Vector((0, 0, 0))
            for first, second in zip(cleaned, cleaned[1:] + cleaned[:1]):
                normal += Vector(self.vertices[first]).cross(Vector(self.vertices[second]))
            if normal.length > 1e-12:
                self.faces.append(tuple(cleaned))

    def patch(self, point_fn, across=16, vertical=10, tmax=1):
        for j in range(vertical):
            t0, t1 = tmax * j / vertical, tmax * (j + 1) / vertical
            for i in range(across):
                u0, u1 = -1 + 2 * i / across, -1 + 2 * (i + 1) / across
                self.face([point_fn(u0, t0), point_fn(u1, t0), point_fn(u1, t1), point_fn(u0, t1)])

    def close_underneath(self, bottom_z):
        counts = {}
        for face in self.faces:
            for a, b in zip(face, face[1:] + face[:1]):
                key = tuple(sorted((a, b)))
                counts[key] = counts.get(key, 0) + 1
        boundary = [edge for edge, count in counts.items() if count == 1]
        for a, b in boundary:
            p, q = self.vertices[a], self.vertices[b]
            pb, qb = (p[0], p[1], bottom_z), (q[0], q[1], bottom_z)
            self.face([p, q, qb, pb])
            self.face([pb, qb, (0, 0, bottom_z)])


def _roof_spec(width, depth, rise, roof_type, overhang, end_overhang, ridge_length, upturn):
    if roof_type not in ROOF_TYPES:
        raise ValueError("unknown roof_type: " + str(roof_type))
    width = _number("width", width, strictly_positive=True)
    depth = _number("depth", depth, strictly_positive=True)
    rise = _number("rise", rise, strictly_positive=True)
    overhang = _number("overhang", overhang, minimum=0)
    upturn = _number("upturn", upturn, minimum=0)
    if upturn >= rise:
        raise ValueError("upturn must be smaller than rise")
    if end_overhang is None:
        end_overhang = 0 if roof_type == "yingshan" else overhang
    end_overhang = _number("end_overhang", end_overhang, minimum=0)
    if roof_type == "yingshan" and end_overhang != 0:
        raise ValueError("yingshan has no roof projection beyond its gable ends")
    a, b = width / 2 + end_overhang, depth / 2 + overhang
    if roof_type in {"yingshan", "xuanshan"}:
        ridge = a
    elif ridge_length is None:
        ridge = max(0, a - b * .85) if roof_type == "wudian" else a * .73
    else:
        ridge = _number("ridge_length", ridge_length, minimum=0) / 2
        if ridge >= a:
            raise ValueError("hipped ridge must be shorter than full roof width")
        if roof_type == "xieshan" and ridge == 0:
            raise ValueError("xieshan ridge must be positive")
    return a, b, rise, ridge, upturn


def _roof_points(a, b, rise, ridge, upturn, roof_type, eave_z):
    transition = .42

    def side_point(side, u, t):
        if roof_type in {"yingshan", "xuanshan"}:
            aa = a
        elif roof_type == "xieshan":
            aa = a + (ridge - a) * min(1, t / transition)
        else:
            aa = a + (ridge - a) * t
        bb = b * (1 - t)
        z = eave_z + rise * t ** 1.62 + upturn * abs(u) ** 8 * (1 - t) ** 3
        if side == "south":
            return (aa * u, -bb, z)
        if side == "north":
            return (-aa * u, bb, z)
        if side == "east":
            return (aa, bb * u, z)
        return (-aa, -bb * u, z)
    return side_point, transition


def _roof_surface(a, b, rise, ridge, upturn, roof_type, eave_z, detail):
    surface = _Surface()
    point, transition = _roof_points(a, b, rise, ridge, upturn, roof_type, eave_z)
    across, vertical = (24, 16) if detail == "near" else (12, 10)
    # Include exactly the hip/gable transition so a hard crease is not interpolated away.
    t_values = sorted(set([i / vertical for i in range(vertical + 1)] +
                         ([transition] if roof_type == "xieshan" else [])))
    for side in ("south", "north"):
        for t0, t1 in zip(t_values, t_values[1:]):
            for i in range(across):
                u0, u1 = -1 + 2 * i / across, -1 + 2 * (i + 1) / across
                surface.face([point(side, u0, t0), point(side, u1, t0),
                              point(side, u1, t1), point(side, u0, t1)])
    if roof_type == "wudian":
        for side in ("east", "west"):
            surface.patch(lambda u, t, side=side: point(side, u, t), across, vertical)
    elif roof_type == "xieshan":
        for side in ("east", "west"):
            # The lower hip shares the same t subdivisions with the long slopes.
            lower_t = [value for value in t_values if value <= transition]
            for t0, t1 in zip(lower_t, lower_t[1:]):
                for i in range(across):
                    u0, u1 = -1 + 2 * i / across, -1 + 2 * (i + 1) / across
                    surface.face([point(side, u0, t0), point(side, u1, t0),
                                  point(side, u1, t1), point(side, u0, t1)])
            sign = 1 if side == "east" else -1
            edge_s = [point("south", sign, t) for t in t_values if t >= transition]
            edge_n = [point("north", -sign, t) for t in reversed(t_values) if t >= transition]
            surface.face(edge_s + edge_n[1:])
    else:
        for sign in (-1, 1):
            edge_s = [point("south", sign, t) for t in t_values]
            edge_n = [point("north", -sign, t) for t in reversed(t_values)]
            surface.face(edge_s + edge_n[1:])
    surface.close_underneath(eave_z - .12)
    return surface, point, transition


def _tube(destination, points, radius, segments=6):
    if len(points) < 2:
        return
    # Keep intersecting ornamental tubes as separate closed components. Welding
    # their coincident caps would create nonmanifold edges at the shared ridge.
    surface = _Surface()
    rings = []
    for i, point in enumerate(points):
        p = Vector(point)
        tangent = Vector(points[min(i + 1, len(points) - 1)]) - Vector(points[max(i - 1, 0)])
        if tangent.length < 1e-9:
            continue
        tangent.normalize()
        reference = Vector((0, 0, 1)) if abs(tangent.z) < .9 else Vector((1, 0, 0))
        first = tangent.cross(reference).normalized()
        second = tangent.cross(first).normalized()
        rings.append([tuple(p + radius * (first * math.cos(2 * math.pi * j / segments) +
                                         second * math.sin(2 * math.pi * j / segments)))
                      for j in range(segments)])
    for first, second in zip(rings, rings[1:]):
        for j in range(segments):
            surface.face([first[j], first[(j + 1) % segments], second[(j + 1) % segments], second[j]])
    if rings:
        surface.face(list(reversed(rings[0])))
        surface.face(rings[-1])
    offset = len(destination.vertices)
    destination.vertices.extend(surface.vertices)
    destination.faces.extend(tuple(index + offset for index in face) for face in surface.faces)


def _roof_ridges(a, b, rise, ridge, upturn, roof_type, eave_z, point, transition):
    surface = _Surface()
    offset = .09
    radius = .11
    _tube(surface, [(-ridge, 0, eave_z + rise + offset), (ridge, 0, eave_z + rise + offset)], radius)
    if ridge == 0:
        # A pyramidal hip has a point, not a spurious zero-length main ridge.
        surface = _Surface()
    for sign_x in (-1, 1):
        for sign_y in (-1, 1):
            side = "south" if sign_y == -1 else "north"
            u = sign_x if side == "south" else -sign_x
            values = [i / 16 for i in range(17)]
            if roof_type == "xieshan":
                values = sorted(set(values + [transition]))
            ridge_points = [point(side, u, t) for t in values]
            _tube(surface, [(x, y, z + offset) for x, y, z in ridge_points], radius * .75)
    for side in ("south", "north", "east", "west"):
        if roof_type in {"yingshan", "xuanshan"} and side in {"east", "west"}:
            continue
        _tube(surface, [point(side, -1 + 2 * i / 24, 0) for i in range(25)], .055)
    return surface


def build_roof(name, width, depth, eave_z, rise, collection, materials=None, roof_type="wudian",
               tile_color="yellow", overhang=.7, end_overhang=None, ridge_length=None,
               upturn=.20, detail="overview", mesh_cache=None, double_eave=False,
               upper_scale=.72):
    """Return mesh objects in local coordinates; ridge runs along local X.

    Double eaves use a separate lower annular roof and a complete upper roof.
    Tile-rib detail is a single optional mesh, not one object per tile.
    Unspecified proportions are typological assumptions, never measured claims.
    """
    if detail not in DETAIL_LEVELS:
        raise ValueError("unknown detail level")
    if tile_color not in {"yellow", "green", "grey"}:
        raise ValueError("tile_color must be yellow, green or grey")
    eave_z = _number("eave_z", eave_z)
    a, b, rise, ridge, upturn = _roof_spec(width, depth, rise, roof_type, overhang, end_overhang, ridge_length, upturn)
    upper_scale = _number("upper_scale", upper_scale, strictly_positive=True)
    if not .3 <= upper_scale < .95:
        raise ValueError("upper_scale must be at least .3 and below .95")
    materials = create_materials() if materials is None else materials
    material = materials[tile_color]
    key = ("roof", width, depth, eave_z, rise, roof_type, tile_color, overhang,
           end_overhang, ridge_length, upturn, detail, bool(double_eave), upper_scale)
    result = []
    upper_eave_z = eave_z
    if double_eave:
        lower = _Surface()
        across, vertical = (24, 8) if detail == "near" else (12, 6)
        inner_a, inner_b = a * upper_scale * .94, b * upper_scale * .94
        inner_height = rise * .35

        def skirt(side, u, t):
            aa, bb = a + (inner_a - a) * t, b + (inner_b - b) * t
            z = eave_z + inner_height * t ** 1.62 + upturn * abs(u) ** 8 * (1 - t) ** 3
            if side == "south": return (aa * u, -bb, z)
            if side == "north": return (-aa * u, bb, z)
            if side == "east": return (aa, bb * u, z)
            return (-aa, -bb * u, z)

        for side in ("south", "north", "east", "west"):
            lower.patch(lambda u, t, side=side: skirt(side, u, t), across, vertical)
        # Close the roof skin with thickness; preserve the central aperture.
        original_faces, original_vertices = list(lower.faces), list(lower.vertices)
        counts = {}
        for face in original_faces:
            for first, second in zip(face, face[1:] + face[:1]):
                edge = tuple(sorted((first, second)))
                counts[edge] = counts.get(edge, 0) + 1
        for face in original_faces:
            lower.face([(original_vertices[index][0], original_vertices[index][1], original_vertices[index][2] - .12)
                        for index in reversed(face)])
        for (first, second), count in counts.items():
            if count == 1:
                p, q = original_vertices[first], original_vertices[second]
                lower.face([p, q, (q[0], q[1], q[2] - .12), (p[0], p[1], p[2] - .12)])
        data = _new_mesh(name + "_lower_eave", lower.vertices, lower.faces, material, mesh_cache, key + ("lower",))
        obj = _object(name + "_下檐裙", data, collection, "roof_lower_eave")
        obj["inner_aperture_half_dimensions"] = [inner_a, inner_b]
        result.append(obj)
        drum_height = rise * .05 + .12
        result.append(box(name + "_重檐承托体", (0, 0, eave_z + rise * .35 + drum_height / 2 - .06),
                          (inner_a * 2 + .15, inner_b * 2 + .15, drum_height),
                          materials["red"], collection, mesh_cache, "roof_drum"))
        a, b, ridge = a * upper_scale, b * upper_scale, ridge * upper_scale
        upper_eave_z = eave_z + rise * .40
        rise *= .60
        upturn *= .65
    surface, point, transition = _roof_surface(a, b, rise, ridge, upturn, roof_type, upper_eave_z, detail)
    data = _new_mesh(name + "_surface", surface.vertices, surface.faces, material, mesh_cache, key + ("surface",))
    obj = _object(name + "_屋面", data, collection, "roof")
    result.append(obj)
    ridges = _roof_ridges(a, b, rise, ridge, upturn, roof_type, upper_eave_z, point, transition)
    if ridges.faces:
        data = _new_mesh(name + "_ridges", ridges.vertices, ridges.faces, material, mesh_cache, key + ("ridges",))
        result.append(_object(name + "_正脊垂脊檐口", data, collection, "roof_ridges"))
    if detail == "near":
        ribs = _Surface()
        for side in ("south", "north", "east", "west"):
            if side in {"east", "west"} and roof_type in {"yingshan", "xuanshan"}:
                continue
            count = max(4, min(200, math.ceil((2 * a if side in {"south", "north"} else 2 * b) / .30)))
            tmax = transition if roof_type == "xieshan" and side in {"east", "west"} else 1
            for i in range(count + 1):
                u = -1 + 2 * i / count
                points = [point(side, u, tmax * j / 12) for j in range(13)]
                _tube(ribs, [(x, y, z + .032) for x, y, z in points], .026, 5)
        data = _new_mesh(name + "_tile_ribs", ribs.vertices, ribs.faces, material, mesh_cache, key + ("tiles",))
        result.append(_object(name + "_近景瓦垄", data, collection, "tile_ribs"))
    for obj in result:
        obj["roof_type"] = roof_type
        obj["double_eave"] = bool(double_eave)
        obj["tile_color"] = tile_color
        obj["detail_level"] = detail
        obj["nominal_footprint"] = [float(width), float(depth)]
    return result


def cut_opening(wall, schedule, collection=None, mesh_cache=None):
    """Apply an Exact Boolean to a wall, with the cutter in wall-local units.

    Required: id, type, destination, center, width, height, depth, normal_axis.
    Centers and dimensions refer to unscaled building-local metre coordinates.
    This function supplies geometry only and does not invent destination spaces.
    """
    for key in ("id", "type", "destination", "center", "width", "height", "depth", "normal_axis"):
        if key not in schedule:
            raise ValueError("opening schedule missing " + key)
    if schedule["type"] not in {"door", "window", "deep_alcove"}:
        raise ValueError("unsupported opening type")
    if not schedule["id"] or not schedule["destination"]:
        raise ValueError("opening needs an id and destination")
    axis = str(schedule["normal_axis"]).upper()
    if axis not in {"X", "Y"}:
        raise ValueError("opening normal_axis must be X or Y")
    width, height, depth = [_number(key, schedule[key], strictly_positive=True) for key in ("width", "height", "depth")]
    center = _point("opening center", schedule["center"])
    if schedule["type"] == "deep_alcove" and depth < max(.35, height * .15):
        raise ValueError("deep alcove is too shallow")
    collection = wall.users_collection[0] if collection is None else collection
    bpy.context.view_layer.update()
    axis_index = 0 if axis == "X" else 1
    if schedule["type"] != "deep_alcove":
        wall_depth = wall.dimensions[axis_index]
        if depth / 2 <= wall_depth / 2 + abs(center[axis_index] - wall.location[axis_index]):
            raise ValueError("through-opening cutter must extend beyond both wall faces")
    # Boolean geometry must be single-user, so repeated walls elsewhere stay solid.
    if wall.data.users > 1:
        wall.data = wall.data.copy()
    dims = (width, depth, height) if axis == "Y" else (depth, width, height)
    cutter = box("TEMP_OPENING_" + str(schedule["id"]), center, dims, None, collection, mesh_cache)
    cutter.parent = wall.parent
    bpy.context.view_layer.update()
    previous_active = bpy.context.view_layer.objects.active
    try:
        bpy.context.view_layer.objects.active = wall
        modifier = wall.modifiers.new("Exact_" + str(schedule["id"]), "BOOLEAN")
        modifier.operation = "DIFFERENCE"
        modifier.solver = "EXACT"
        modifier.object = cutter
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    finally:
        bpy.data.objects.remove(cutter, do_unlink=True)
        bpy.context.view_layer.objects.active = previous_active
    openings = json.loads(wall.get("applied_openings", "[]"))
    openings.append(dict(schedule))
    wall["applied_openings"] = json.dumps(openings, ensure_ascii=False)
    return dict(schedule, wall=wall.name)


def build_building(record, collection, detail="overview", materials=None, mesh_cache=None):
    """Build exactly one supplied rectangular footprint; never infer a site plan.

    Required record fields: id, center[3], width, depth, body_height, roof_height,
    roof_type, tile_color. Optional: rotation (radians), wall_color, wall_thickness,
    platform_height, platform_margin, overhang, end_overhang, ridge_length, upturn,
    double_eave, upper_scale, openings, columns, source_refs and representation.
    Openings have wall='south'|'north'|'east'|'west' plus cut_opening fields.
    Explicit columns have center[3], radius and height; no bay counts are invented.
    """
    for key in ("id", "center", "width", "depth", "body_height", "roof_height", "roof_type", "tile_color"):
        if key not in record:
            raise ValueError("building record missing " + key)
    if not isinstance(record["id"], str) or not record["id"]:
        raise ValueError("building id must be a nonempty string")
    center = _point("building center", record["center"])
    width, depth, height = [_number(key, record[key], strictly_positive=True) for key in ("width", "depth", "body_height")]
    thickness = _number("wall_thickness", record.get("wall_thickness", .35), strictly_positive=True)
    if thickness * 2 >= min(width, depth):
        raise ValueError("wall thickness leaves no interior")
    platform_height = _number("platform_height", record.get("platform_height", .15), minimum=0)
    platform_margin = _number("platform_margin", record.get("platform_margin", .40), minimum=0)
    rotation = _number("rotation", record.get("rotation", 0))
    if detail not in DETAIL_LEVELS:
        raise ValueError("unknown detail level")
    # Validate roof settings before creating scene data.
    _roof_spec(width, depth, record["roof_height"], record["roof_type"], record.get("overhang", .7),
               record.get("end_overhang"), record.get("ridge_length"), record.get("upturn", .20))
    materials = create_materials() if materials is None else materials
    wall_color = record.get("wall_color", "red")
    if wall_color not in materials:
        raise ValueError("unknown wall material")
    building = ensure_collection(record["id"], collection)
    structure = ensure_collection(record["id"] + "_主体", building)
    roofs = ensure_collection(record["id"] + "_屋顶", building)
    close_detail = ensure_collection(record["id"] + "_近景细节", building)
    root = bpy.data.objects.new(record["id"], None)
    building.objects.link(root)
    root.location = center
    root.rotation_euler.z = rotation
    root["record"] = json.dumps(record, ensure_ascii=False)
    root["representation"] = record.get("representation", "typological_approximation")
    root["third_party_cost"] = 0
    objects = []
    if platform_height:
        objects.append(box(record["id"] + "_台基", (0, 0, platform_height / 2),
                           (width + 2 * platform_margin, depth + 2 * platform_margin, platform_height),
                           materials["white_stone"], structure, mesh_cache, "podium"))
    floor_depth = min(.12, height * .05)
    objects.append(box(record["id"] + "_地板", (0, 0, platform_height + floor_depth / 2),
                       (width, depth, floor_depth), materials["white_stone"], structure, mesh_cache, "floor"))
    objects.append(box(record["id"] + "_天花", (0, 0, platform_height + height - floor_depth / 2),
                       (width, depth, floor_depth), materials["dark_wood"], structure, mesh_cache, "ceiling"))
    z = platform_height + height / 2
    walls = {
        "south": box(record["id"] + "_南墙", (0, -depth / 2 + thickness / 2, z), (width, thickness, height), materials[wall_color], structure, mesh_cache),
        "north": box(record["id"] + "_北墙", (0, depth / 2 - thickness / 2, z), (width, thickness, height), materials[wall_color], structure, mesh_cache),
        "east": box(record["id"] + "_东墙", (width / 2 - thickness / 2, 0, z), (thickness, depth, height), materials[wall_color], structure, mesh_cache),
        "west": box(record["id"] + "_西墙", (-width / 2 + thickness / 2, 0, z), (thickness, depth, height), materials[wall_color], structure, mesh_cache),
    }
    objects.extend(walls.values())
    openings = []
    for schedule in record.get("openings", []):
        if schedule.get("wall") not in walls:
            raise ValueError("opening has no declared building wall")
        openings.append(cut_opening(walls[schedule["wall"]], schedule, structure, mesh_cache))
    roof_objects = build_roof(record["id"], width, depth, platform_height + height,
                              record["roof_height"], roofs, materials,
                              record["roof_type"], record["tile_color"], record.get("overhang", .7),
                              record.get("end_overhang"), record.get("ridge_length"), record.get("upturn", .20),
                              detail, mesh_cache, record.get("double_eave", False), record.get("upper_scale", .72))
    for obj in roof_objects:
        if obj.get("semantic_role") == "tile_ribs":
            roofs.objects.unlink(obj)
            close_detail.objects.link(obj)
    objects.extend(roof_objects)
    for index, item in enumerate(record.get("columns", [])):
        objects.append(column(record["id"] + "_朱柱_" + str(index), item["center"], item["radius"], item["height"],
                              materials["red_lacquer"], close_detail, mesh_cache))
    for obj in objects:
        obj.parent = root
        obj["building_id"] = record["id"]
    return {"root": root, "collection": building, "structure_collection": structure,
            "roof_collection": roofs, "detail_collection": close_detail, "objects": objects,
            "walls": walls, "openings": openings}


def set_near_detail(building, visible):
    collection = building["detail_collection"]
    collection.hide_render = not bool(visible)
    collection.hide_viewport = not bool(visible)


def evaluated_bounds(objects):
    """Return actual evaluated mesh bounds, after world transforms."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        if evaluated.type != "MESH":
            continue
        mesh = evaluated.to_mesh()
        try:
            points.extend(evaluated.matrix_world @ vertex.co for vertex in mesh.vertices)
        finally:
            evaluated.to_mesh_clear()
    if not points:
        raise ValueError("cannot measure empty mesh objects")
    return [[min(point[i] for point in points) for i in range(3)],
            [max(point[i] for point in points) for i in range(3)]]


def _clean_ring(values):
    ring = []
    for point in values:
        if len(point) != 2:
            raise ValueError("footprint polygon points require two metre coordinates")
        point = tuple(_number("polygon coordinate", value) for value in point)
        if not ring or point != ring[-1]:
            ring.append(point)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    if len(set(ring)) < 3:
        raise ValueError("footprint needs at least three distinct points")
    if abs(_ring_area(ring)) < 1e-7:
        raise ValueError("footprint area is zero or too small")
    return ring


def _ring_area(ring):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1])) / 2


def _triangulate_rings(rings):
    normalized = []
    flat = []
    for index, ring in enumerate(rings):
        is_ccw = _ring_area(ring) > 0
        if is_ccw != (index == 0):
            ring = list(reversed(ring))
        flat.extend(ring)
        normalized.append([Vector((x, y, 0)) for x, y in ring])
    # Tessellation returns indices. Reuse original double precision coordinates;
    # round-tripping through mathutils float32 creates micron slivers at eaves.
    triangles = [[flat[index] for index in triangle]
                 for triangle in tessellate_polygon(normalized)]
    expected = abs(_ring_area(rings[0])) - sum(abs(_ring_area(ring)) for ring in rings[1:])
    actual = sum(abs(_ring_area(triangle)) for triangle in triangles)
    if expected <= 0 or abs(actual - expected) > max(1e-4, expected * 1e-5):
        raise ValueError("footprint triangulation did not preserve exterior and holes")
    return triangles


def _roof_frame(ring, record):
    direction = record.get("roof_direction")
    if direction is not None:
        compass = {name: i * 22.5 for i, name in enumerate(
            ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"])}
        if isinstance(direction, str):
            if direction.upper() in compass:
                direction = compass[direction.upper()]
            else:
                try:
                    direction = float(direction)
                except ValueError as error:
                    raise ValueError("unsupported roof_direction") from error
        azimuth = math.radians(_number("roof_direction", direction))
        downslope = (math.sin(azimuth), math.cos(azimuth))
        ridge_axis = (math.cos(azimuth), -math.sin(azimuth))
        method = "OSM roof:direction: downslope compass azimuth"
    else:
        edge = max([(b[0] - a[0], b[1] - a[1]) for a, b in zip(ring, ring[1:] + ring[:1])],
                   key=lambda pair: pair[0] ** 2 + pair[1] ** 2)
        length = math.hypot(*edge)
        ridge_axis = (edge[0] / length, edge[1] / length)
        if record.get("roof_orientation", "along") == "across":
            ridge_axis = (-ridge_axis[1], ridge_axis[0])
        downslope = (-ridge_axis[1], ridge_axis[0])
        method = "assumption: roof ridge follows longest footprint edge and roof_orientation"
    return ridge_axis, downslope, method


def _clip_halfplane(polygon, plane, tolerance=1e-8):
    if not polygon:
        return []
    result = []
    first = polygon[-1]
    first_value = plane[0] * first[0] + plane[1] * first[1] + plane[2]
    for second in polygon:
        second_value = plane[0] * second[0] + plane[1] * second[1] + plane[2]
        first_inside, second_inside = first_value >= -tolerance, second_value >= -tolerance
        if first_inside != second_inside:
            factor = first_value / (first_value - second_value)
            result.append((first[0] + factor * (second[0] - first[0]),
                           first[1] + factor * (second[1] - first[1])))
        if second_inside:
            result.append(second)
        first, first_value = second, second_value
    return result


def _volume_from_top(top, bottom_z):
    vertices, faces = list(top.vertices), list(top.faces)
    counts = {}
    for face in faces:
        for first, second in zip(face, face[1:] + face[:1]):
            key = tuple(sorted((first, second)))
            counts[key] = counts.get(key, 0) + 1
        top.face([(vertices[index][0], vertices[index][1], bottom_z) for index in reversed(face)])
    for (first, second), count in counts.items():
        if count == 1:
            p, q = vertices[first], vertices[second]
            top.face([p, q, (q[0], q[1], bottom_z), (p[0], p[1], bottom_z)])
    return top


def build_osm_part(record, collection, materials=None, mesh_cache=None):
    """Extrude the supplied actual polygon; retain concavities and inner holes.

    Required: id, polygon (XY metres), min_height, height, roof_height, roof_shape.
    height includes the roof and is measured from ground, as in OSM S3DB.
    roof_direction is the downslope azimuth in compass degrees, north=0/east=90.
    Optional: holes, roof_orientation, tile_color, wall_color and source metadata.
    Hipped/pyramidal roofs are piecewise planar approximations clipped to the
    actual footprint, using its oriented bounds. No minimum rectangle replaces
    the footprint. Complex Chinese roof joinery is not supplied by OSM tags.
    """
    for key in ("id", "polygon", "min_height", "height", "roof_height", "roof_shape"):
        if key not in record:
            raise ValueError("OSM part missing " + key)
    minimum = _number("min_height", record["min_height"], minimum=0)
    height = _number("height", record["height"], strictly_positive=True)
    rise = _number("roof_height", record["roof_height"], minimum=0)
    if height <= minimum or rise > height - minimum + 1e-7:
        raise ValueError("OSM height must exceed min_height, and contain roof_height")
    shape = record["roof_shape"]
    if shape not in {"flat", "skillion", "gabled", "hipped", "pyramidal"}:
        raise ValueError("unsupported OSM roof_shape: " + str(shape))
    if shape != "flat" and rise <= 0:
        raise ValueError("a sloped roof requires an explicit positive roof_height")
    if shape == "flat" and rise > 0:
        raise ValueError("a flat roof uses roof_height=0")
    outer = _clean_ring(record["polygon"])
    rings = [outer] + [_clean_ring(ring) for ring in record.get("holes", [])]
    center = (sum(x for x, y in outer) / len(outer), sum(y for x, y in outer) / len(outer))
    local_rings = [[(x - center[0], y - center[1]) for x, y in ring] for ring in rings]
    triangles = _triangulate_rings(local_rings)
    ridge_axis, downslope, direction_method = _roof_frame(local_rings[0], record)
    u_values = [x * ridge_axis[0] + y * ridge_axis[1] for x, y in local_rings[0]]
    v_values = [x * downslope[0] + y * downslope[1] for x, y in local_rings[0]]
    umin, umax, vmin, vmax = min(u_values), max(u_values), min(v_values), max(v_values)
    uhalf, vhalf = (umax - umin) / 2, (vmax - vmin) / 2
    if min(uhalf, vhalf) < 1e-6:
        raise ValueError("footprint has no usable roof span")

    def plane(vector, scale, constant):
        return (vector[0] * scale, vector[1] * scale, constant)

    if shape == "skillion":
        planes = [plane(downslope, -1 / (2 * vhalf), vmax / (2 * vhalf))]
    elif shape in {"gabled", "hipped", "pyramidal"}:
        planes = [plane(downslope, 1 / vhalf, -vmin / vhalf),
                  plane(downslope, -1 / vhalf, vmax / vhalf)]
        if shape in {"hipped", "pyramidal"}:
            end_span = min(uhalf, vhalf) if shape == "hipped" else uhalf
            planes.extend([plane(ridge_axis, 1 / end_span, -umin / end_span),
                           plane(ridge_axis, -1 / end_span, umax / end_span)])
            if shape == "hipped":
                planes.append((0, 0, 1))
    else:
        planes = [(0, 0, 0)]
    eave = height - rise
    materials = create_materials() if materials is None else materials
    tile_color, wall_color = record.get("tile_color", "yellow"), record.get("wall_color", "red")
    if tile_color not in materials or wall_color not in materials:
        raise ValueError("unknown OSM part material")
    part = ensure_collection(str(record["id"]), collection)
    objects = []
    if eave - minimum > 1e-7:
        top = _Surface()
        for triangle in triangles:
            top.face([(x, y, eave) for x, y in triangle])
        body = _volume_from_top(top, minimum)
        key = ("osm_body", tuple(tuple(vertex) for vertex in body.vertices), tuple(body.faces))
        data = _new_mesh(str(record["id"]) + "_body", body.vertices, body.faces, materials[wall_color], mesh_cache, key)
        objects.append(_object(str(record["id"]) + "_原轮廓主体", data, part, "osm_part_body"))
    if rise > 0:
        top = _Surface()
        for triangle in triangles:
            for index, current in enumerate(planes):
                polygon = list(triangle)
                for other_index, other in enumerate(planes):
                    if index != other_index:
                        polygon = _clip_halfplane(polygon, tuple(other[i] - current[i] for i in range(3)))
                        if len(polygon) < 3:
                            break
                if len(polygon) >= 3:
                    for i in range(1, len(polygon) - 1):
                        points = [polygon[0], polygon[i], polygon[i + 1]]
                        if abs(_ring_area(points)) > 1e-9:
                            top.face([(x, y, eave + rise * max(0, min(1, current[0] * x + current[1] * y + current[2])))
                                      for x, y in points])
        roof = _volume_from_top(top, eave)
        key = ("osm_roof", tuple(tuple(vertex) for vertex in roof.vertices), tuple(roof.faces))
        data = _new_mesh(str(record["id"]) + "_roof", roof.vertices, roof.faces, materials[tile_color], mesh_cache, key)
        objects.append(_object(str(record["id"]) + "_原轮廓坡屋顶", data, part, "osm_part_roof"))
    elif objects:
        # A flat cap is geometry coincident with the body's upper face and uses
        # an editable second material slot, without a duplicate coplanar object.
        body = objects[-1]
        if body.data.users > 1:
            body.data = body.data.copy()
        body.data.materials.append(materials[tile_color])
        for polygon in body.data.polygons:
            if polygon.normal.z > .99 and abs(polygon.center.z - height) < 1e-5:
                polygon.material_index = 1
    for obj in objects:
        obj.location = (center[0], center[1], 0)
        obj["osm_part_id"] = str(record["id"])
        obj["roof_shape"] = shape
        obj["roof_direction_method"] = direction_method
        obj["representation"] = "OSM crowd-sourced footprint and height; roof type approximation, not a measured restoration"
        obj["source_record"] = json.dumps(record, ensure_ascii=False)
        obj["source_refs"] = json.dumps(record.get("source_refs", []), ensure_ascii=False)
        obj["footprint_outer_area"] = abs(_ring_area(outer))
        obj["footprint_holes_area"] = sum(abs(_ring_area(ring)) for ring in rings[1:])
        obj["height_source"] = record.get("height_source", "provided_by_caller_unverified")
        if shape in {"hipped", "pyramidal"}:
            obj["roof_approximation"] = "piecewise planes over oriented bounds, clipped to original polygon; irregular eave heights are approximate"
    return {"collection": part, "objects": objects, "center": [center[0], center[1], 0],
            "roof_direction_method": direction_method, "source_polygon": outer}
