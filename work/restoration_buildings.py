"""Local, source-labelled building-type studies, never surveyed reconstructions.

No scene is created on import. The caller owns registration, source profiles,
review cameras and saving. All undocumented dimensions remain model assumptions.
"""
import json
import math

import bpy
from mathutils import Vector

import forbidden_city_geometry as F


REQUIRED = ("building_id", "name_zh", "source_part_id", "anchor", "rotation_z_radians",
            "body_width_m", "body_depth_m", "total_height_m", "bays_x", "bays_y",
            "roof_type", "eaves_tiers", "floor_stories", "material_scheme",
            "dimension_evidence", "verified_facts", "uncertain_dimensions")


def _material(name, color, roughness=.5):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        material.diffuse_color = (*color, 1)
        shader = material.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (*color, 1)
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Metallic"].default_value = .06
    return material


def restoration_materials(materials=None):
    result = dict(F.create_materials() if materials is None else materials)
    extras = {"black": ((.018, .028, .028), .30), "green": ((.025, .16, .065), .32),
              "paint_blue": ((.015, .09, .16), .48), "paint_green": ((.025, .19, .12), .48),
              "gilt": ((.59, .31, .055), .35), "glass_dark": ((.035, .075, .085), .23)}
    for key, (color, roughness) in extras.items():
        result[key] = _material("REST_" + key, color, roughness)
    return result


def _positive(name, value):
    return F._number(name, value, strictly_positive=True)


def _validate(profile):
    for key in REQUIRED:
        if key not in profile:
            raise ValueError("restoration profile missing " + key)
    if profile.get("full_geometry_eligible") is False or profile["total_height_m"] is None:
        raise ValueError("full geometry disabled: no documented height; retain material-only source instead")
    for key in ("body_width_m", "body_depth_m", "total_height_m"):
        _positive(key, profile[key])
    F._point("anchor", profile["anchor"])
    F._number("rotation_z_radians", profile["rotation_z_radians"])
    for key in ("bays_x", "bays_y"):
        value = profile[key]
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 30:
            raise ValueError(key + " must be an explicit positive bay count; unknown counts cannot be invented")
    if profile["roof_type"] not in {"xieshan", "juanpeng_xieshan", "wudian"}:
        raise ValueError("unsupported restoration roof type")
    if profile["eaves_tiers"] not in {1, 2, 3}:
        raise ValueError("eaves_tiers must be 1, 2 or 3")
    if profile.get("semantic_front", "negative-y") not in {"positive-y", "negative-y"}:
        raise ValueError("semantic_front must be positive-y or negative-y")
    scheme = profile["material_scheme"]
    for key in ("main_roof", "roof_edge", "lower_eaves", "wall", "column"):
        if not scheme.get(key):
            raise ValueError("full geometry needs an explicit material scheme: " + key)
    if min(profile["body_width_m"], profile["body_depth_m"], profile["total_height_m"]) < 3:
        raise ValueError("building is too small for the declared architectural study parameters")


def _face(surface, indices, material_index, points):
    before = len(surface.faces)
    surface.face(points)
    indices.extend([material_index] * (len(surface.faces) - before))


def _closed_skin(surface, thickness=.12):
    vertices, faces = list(surface.vertices), list(surface.faces)
    counts = {}
    for face in faces:
        surface.face([(vertices[index][0], vertices[index][1], vertices[index][2] - thickness)
                      for index in reversed(face)])
        for a, b in zip(face, face[1:] + face[:1]):
            edge = tuple(sorted((a, b)))
            counts[edge] = counts.get(edge, 0) + 1
    for (a, b), count in counts.items():
        if count == 1:
            first, second = vertices[a], vertices[b]
            surface.face([first, second, (second[0], second[1], second[2] - thickness),
                          (first[0], first[1], first[2] - thickness)])


def _mesh(name, surface, collection, materials, indices=None, cache=None, key=None):
    data = F._new_mesh(name, surface.vertices, surface.faces, materials[0], cache, key)
    if len(data.materials) < len(materials):
        for material in materials[len(data.materials):]:
            data.materials.append(material)
    if indices:
        for polygon, index in zip(data.polygons, indices):
            polygon.material_index = index
    return F._object(name, data, collection, "roof")


def _roof_geometry(name, width, depth, eave, target_top, roof_type, main_material,
                   edge_material, under_material, collection, cache, overhang,
                   corner_lift, storey_index, inner_dimensions=None):
    """Curved hipped/gable roof or a real annular lower eave.

    Juanpeng has a smooth rounded transverse crown and no pointed main ridge.
    Curve, corner lift, edge-band width and tile spacing are study assumptions.
    """
    a, b = width / 2 + overhang, depth / 2 + overhang
    rise = target_top - eave
    if rise <= .25:
        raise ValueError("roof rise must exceed .25m")
    ridge = a * .72 if roof_type != "wudian" else max(.25, a - .78 * b)
    transition = .42
    surface, indices = F._Surface(), []
    annular = inner_dimensions is not None
    across, vertical = 32, 20
    if annular:
        inner_a, inner_b = inner_dimensions[0] / 2, inner_dimensions[1] / 2
        if inner_a >= a or inner_b >= b:
            raise ValueError("annular eave inner footprint must fit inside outer eave")

    def point(side, u, t):
        if annular:
            aa, bb = a + (inner_a - a) * t, b + (inner_b - b) * t
        elif roof_type == "wudian":
            aa, bb = a + (ridge - a) * t, b * (1 - t)
        else:
            aa, bb = a + (ridge - a) * min(1, t / transition), b * (1 - t)
        if roof_type == "juanpeng_xieshan" and not annular:
            elevation = math.sin(t * math.pi / 2) ** 1.5
        else:
            elevation = t ** 1.65
        z = eave + rise * elevation + corner_lift * abs(u) ** 8 * (1 - t) ** 3
        if side == "south": return (aa * u, -bb, z)
        if side == "north": return (-aa * u, bb, z)
        if side == "east": return (aa, bb * u, z)
        return (-aa, -bb * u, z)

    t_values = sorted(set([i / vertical for i in range(vertical + 1)] +
                         ([transition] if not annular and roof_type != "wudian" else [])))
    sides = ("south", "north", "east", "west")
    for side in sides:
        tmax = 1 if annular or side in {"south", "north"} or roof_type == "wudian" else transition
        values = [value for value in t_values if value <= tmax]
        if values[-1] != tmax:
            values.append(tmax)
        for t0, t1 in zip(values, values[1:]):
            for index in range(across):
                u0, u1 = -1 + 2 * index / across, -1 + 2 * (index + 1) / across
                band = t0 < .065 or abs((u0 + u1) / 2) > .94
                _face(surface, indices, 1 if band else 0,
                      [point(side, u0, t0), point(side, u1, t0), point(side, u1, t1), point(side, u0, t1)])
    if not annular and roof_type != "wudian":
        for sign in (-1, 1):
            south = [point("south", sign, t) for t in t_values if t >= transition]
            north = [point("north", -sign, t) for t in reversed(t_values) if t >= transition]
            _face(surface, indices, 2, south + north[1:])
    top_count = len(surface.faces)
    if annular:
        _closed_skin(surface)
    else:
        surface.close_underneath(eave - .13)
    indices.extend([2] * (len(surface.faces) - top_count))

    ridge_surface = F._Surface()
    if not annular and roof_type != "juanpeng_xieshan":
        F._tube(ridge_surface, [(-ridge, 0, target_top + .025), (ridge, 0, target_top + .025)], .085, 8)
    for side in sides:
        F._tube(ridge_surface, [point(side, -1 + 2 * i / 40, 0) for i in range(41)], .065, 6)
    for sign_x in (-1, 1):
        for side in ("south", "north"):
            u = sign_x if side == "south" else -sign_x
            F._tube(ridge_surface, [(x, y, z + .035) for x, y, z in [point(side, u, i / 24) for i in range(25)]], .065, 6)

    ribs_main, ribs_edge = F._Surface(), F._Surface()
    for side in sides:
        tmax = 1 if annular or side in {"south", "north"} or roof_type == "wudian" else transition
        count = max(8, min(150, round((width if side in {"south", "north"} else depth) / .33)))
        for index in range(count + 1):
            u = -1 + 2 * index / count
            for t0, t1, destination in [(0, min(.065, tmax), ribs_edge), (min(.065, tmax), tmax, ribs_main)]:
                if t1 <= t0:
                    continue
                points = [point(side, u, t0 + (t1 - t0) * i / 15) for i in range(16)]
                F._tube(destination, [(x, y, z + .022) for x, y, z in points], .026, 5)

    # Only the new roof coordinates move to reserve ridge/tile thickness. Floors,
    # podium and documented reference column spans are never rescaled or moved.
    all_surfaces = [surface, ridge_surface, ribs_main, ribs_edge]
    actual_peak = max(point[2] for item in all_surfaces for point in item.vertices)
    shift = actual_peak - target_top
    for item in all_surfaces:
        item.vertices = [(x, y, z - shift) for x, y, z in item.vertices]
    key = ("restoration_roof", width, depth, eave, target_top, roof_type, overhang,
           corner_lift, inner_dimensions, main_material.name, edge_material.name)
    objects = []
    obj = _mesh(name + "_曲面屋顶", surface, collection,
                [main_material, edge_material, under_material], indices, cache, key + ("surface",))
    obj["roof_topology"] = "annular_lower_eave" if annular else "curved_complete_roof"
    objects.append(obj)
    for suffix, item, material, role in [("脊与檐口", ridge_surface, edge_material, "ridge"),
                                         ("主体瓦垄", ribs_main, main_material, "tile"),
                                         ("剪边瓦垄", ribs_edge, edge_material, "tile")]:
        if item.faces:
            obj = _mesh(name + "_" + suffix, item, collection, [material], cache=cache, key=key + (suffix,))
            obj["semantic_role"] = role
            objects.append(obj)
    for obj in objects:
        obj["storey_index"] = storey_index
        obj["roof_type"] = roof_type
        obj["roof_tier_index"] = storey_index
        obj["eave_level_model_m"] = eave - shift
        obj["target_top_model_m"] = target_top
        obj["roof_z_only_adjustment_m"] = -shift
        obj["juanpeng_rounded_crown"] = roof_type == "juanpeng_xieshan" and not annular
        obj["has_pointed_main_ridge"] = roof_type != "juanpeng_xieshan" and not annular
    return objects


def build_restoration(profile, collection, materials=None, mesh_cache=None):
    """Build one registered building-type study; no geographic layout inferred.

    See REQUIRED and the production profiles.json for the stable field contract.
    body_width/depth are modelling reference spans, never relabelled wall edges.
    Optional detail_parameters and parameter_evidence make model choices explicit.
    """
    _validate(profile)
    materials = restoration_materials(materials)
    scheme = profile["material_scheme"]
    for key, value in scheme.items():
        if value not in materials:
            raise ValueError("unknown restoration material " + str(value))
    identifier = profile["building_id"]
    building = F.ensure_collection(identifier + "_形制研究", collection)
    structure = F.ensure_collection(identifier + "_柱廊门窗", building)
    roofs = F.ensure_collection(identifier + "_分层曲面屋顶", building)
    root = bpy.data.objects.new(identifier + "_registered_study", None)
    building.objects.link(root)
    root.location = profile["anchor"]
    root.rotation_euler.z = profile["rotation_z_radians"]
    width, depth, total = [float(profile[key]) for key in ("body_width_m", "body_depth_m", "total_height_m")]
    tiers = profile["eaves_tiers"]
    is_stage = profile["roof_type"] == "juanpeng_xieshan"
    parameters = dict(profile.get("detail_parameters", {}))
    assumptions = [{"id": "INPUT-" + str(i + 1), "status": "unmeasured", "note": note}
                   for i, note in enumerate(profile["uncertain_dimensions"] + profile.get("study_only_assumptions", []))]
    parameter_evidence = profile.get("parameter_evidence", {})

    def parameter(key, default, note):
        value = parameters.get(key, default)
        value = F._number(key, value, strictly_positive=True)
        evidence = parameter_evidence.get(key, {})
        assumptions.append({"id": "MODEL-" + key, "parameter": key, "value": value,
                            "status": evidence.get("status", "assumption"), "note": note,
                            "source_refs": evidence.get("source_refs", [])})
        parameters[key] = value
        return value

    platform_default = 1.2 if is_stage else .8
    platform = parameter("platform_height_m", platform_default,
                         "Included within total height. Changyin 1.2m is the cited stage-platform value; interpretation and local datum still need survey." if is_stage else "Platform height has no measured value in the supplied page.")
    if is_stage and "platform_height_m" not in profile.get("detail_parameters", {}):
        assumptions[-1].update({"status": "documented_literature_value_with_model_datum_assumption",
                               "source_refs": ["https://www.dpm.org.cn/Uploads/File/2020/04/21/u5e9eca6368e88.pdf"]})
    corridor = parameter("veranda_depth_m", min(width, depth) * (.075 if is_stage else .09),
                         "Inner walls are inset from the reference column grid; precise corridor depth is unmeasured.")
    wall_thickness = parameter("wall_thickness_m", .38, "Real wall thickness for Boolean apertures, not a surveyed wall section.")
    column_radius = parameter("column_radius_m", min(width, depth) * .012, "Column radius is a study proportion.")
    overhang = parameter("roof_overhang_m", min(width, depth) * .065, "Projection beyond the reference columns is not measured.")
    corner_lift = parameter("corner_lift_m", min(width, depth) * .027, "Corner uplift and roof curvature are visual study parameters.")
    if corridor * 2 + 2 * wall_thickness >= min(width, depth):
        raise ValueError("veranda and walls leave no interior")
    if platform >= total * .25:
        raise ValueError("platform cannot consume the declared building height")
    assumptions.extend([
        {"id": "MODEL-bay_spacing", "status": "assumption", "note": "Bay counts follow supplied facts; regular column spacing is a schematic study, not measured individual bay widths or a certified historical column grid."},
        {"id": "MODEL-roof_curve", "status": "assumption", "note": "Curve exponent, hip/gable transition, tile pitch, edge-band width and ridge profiles are unmeasured; no carved beast or painted motif is claimed reconstructed."},
        {"id": "MODEL-height_scope", "status": "model_interpretation", "note": "Only newly generated roof coordinates are lowered by decorative thickness to meet the requested top. Ground, platform and column spans are never scaled. Leshou terminal is ridge top; Changyin ground-to-highest-point is an explicit interpretation of its unspecified published total-height datum."},
        {"id": "MODEL-interiors", "status": "not_reconstructed", "note": "No measured interior floor plan, theatre wells/lifting machinery, hidden floors, structural joinery or complete southern annex is invented."},
        {"id": "MODEL-openings", "status": "assumption", "note": "Opening categories follow known facade facts where supplied; clear widths/heights, sill levels, lattice sizes, and folded-open leaf pose are study dimensions."},
        {"id": "MODEL-floor_finish", "status": "assumption", "note": "Ground-floor finish is 5mm above podium to avoid coincident finish faces; platform geometry itself retains its declared height."},
    ])
    components, objects, opening_records = {}, [], []

    def register(obj, role, storey=0):
        obj["semantic_role"] = role
        obj["storey_index"] = storey
        obj.parent = root
        objects.append(obj)
        components.setdefault(role, []).append(obj)
        return obj

    def box(name, center, dimensions, material_key, role, storey=0):
        return register(F.box(identifier + "_" + name, center, dimensions, materials[material_key],
                              structure, mesh_cache, role), role, storey)

    box("台基", (0, 0, platform / 2), (width + 2.2, depth + 2.2, platform), "white_stone", "podium")
    if tiers == 1:
        floor_levels = [platform + .005]
        eave_levels = [total * .58]
        widths, depths = [width], [depth]
    elif tiers == 3:
        floor_levels = [platform + .005, total * .39, total * .66]
        eave_levels = [total * .34, total * .61, total * .82]
        widths = [width, width * .88, width * .76]
        depths = [depth, depth * .88, depth * .76]
    else:
        floor_levels = [platform + .005, total * .48]
        eave_levels = [total * .43, total * .74]
        widths, depths = [width, width * .92], [depth, depth * .92]
    assumptions.append({"id": "MODEL-storey_levels", "status": "assumption", "floor_levels_m": floor_levels,
                        "eave_levels_m": eave_levels, "tier_reference_widths_m": widths,
                        "tier_reference_depths_m": depths, "note": "Storey/eave Z and upper-tier setbacks are unmeasured study proportions, independent of verified tier count."})
    semantic_front = profile.get("semantic_front", "negative-y")
    front = "north" if semantic_front == "positive-y" else "south"
    front_sign = 1 if front == "north" else -1
    bays_x, bays_y = profile["bays_x"], profile["bays_y"]

    def detail_box(name, center, dims, key, role, storey):
        return box(name, center, dims, key, role, storey)

    def cut(wall, side, center, clear_width, clear_height, storey, aperture_role, door=False):
        axis = "Y" if side in {"north", "south"} else "X"
        normal = {"north": (0, 1, 0), "south": (0, -1, 0), "east": (1, 0, 0), "west": (-1, 0, 0)}[side]
        schedule = {"id": identifier + "_" + side + "_" + str(storey) + "_" + str(len(opening_records)),
                    "type": "door" if door else "window", "destination": "visible_study_interior" if door else "window_reveal_and_glazing",
                    "center": list(center), "width": clear_width, "height": clear_height,
                    "depth": wall_thickness + .8, "normal_axis": axis}
        record = F.cut_opening(wall, schedule, structure, mesh_cache)
        record.update({"wall_side": side, "storey_index": storey, "clear_width_m": clear_width,
                       "clear_height_m": clear_height, "center_local": list(center), "normal_local": list(normal),
                       "aperture_role": aperture_role, "geometry_status": "Exact Boolean applied",
                       "dimension_status": "study_assumption", "door_leaf_names": [], "window_detail_names": []})
        n = Vector(normal)
        across = Vector((1, 0, 0)) if axis == "Y" else Vector((0, 1, 0))
        center_v = Vector(center)
        face_point = center_v + n * (wall_thickness / 2 + .035)
        # Frames sit against the cut reveal, not over an uncut decorative wall.
        for sign in (-1, 1):
            p = face_point + across * sign * (clear_width / 2 + .045)
            dims = (.10, .13, clear_height + .15) if axis == "Y" else (.13, .10, clear_height + .15)
            frame = detail_box("洞口边框", p, dims, "red_lacquer", "window_detail", storey)
            record["window_detail_names"].append(frame.name)
        for sign in (-1, 1):
            p = face_point + Vector((0, 0, sign * (clear_height / 2 + .04)))
            dims = (clear_width + .18, .13, .10) if axis == "Y" else (.13, clear_width + .18, .10)
            frame = detail_box("洞口横框", p, dims, "red_lacquer", "window_detail", storey)
            record["window_detail_names"].append(frame.name)
        if door and aperture_role == "central_four_leaf_door":
            # Four leaves are folded to both jambs. Their volume remains outside
            # the declared clear opening; this is a study pose, not current-state evidence.
            for side_sign in (-1, 1):
                for pair in range(2):
                    leaf_w = clear_width / 4
                    p = center_v + across * side_sign * (clear_width / 2 + .13 + pair * .11) + n * (.15 + leaf_w / 2)
                    dims = (.075, leaf_w, clear_height * .96) if axis == "Y" else (leaf_w, .075, clear_height * .96)
                    leaf = detail_box("开启槅扇", p, dims, "red_lacquer", "door_leaf", storey)
                    leaf["leaf_pose"] = "folded_open_study_not_surveyed"
                    record["door_leaf_names"].append(leaf.name)
        elif not door:
            # Windows deliberately have backing/glazing and a readable sill.
            # All probing of a clear wall aperture must target the wall mesh itself.
            p = center_v - n * (wall_thickness * .28)
            dims = (clear_width * .94, .035, clear_height * .94) if axis == "Y" else (.035, clear_width * .94, clear_height * .94)
            glass = detail_box("窗内玻璃示意", p, dims, "glass_dark", "window_detail", storey)
            glass["window_backing"] = True
            record["window_detail_names"].append(glass.name)
            for i in range(1, 7):
                p = face_point + across * (-clear_width / 2 + clear_width * i / 7)
                dims = (.035, .065, clear_height * .94) if axis == "Y" else (.065, .035, clear_height * .94)
                lattice = detail_box("窗格竖棂", p, dims, "red_lacquer", "window_detail", storey)
                record["window_detail_names"].append(lattice.name)
            for i in (1, 2):
                p = face_point + Vector((0, 0, -clear_height / 2 + clear_height * i / 3))
                dims = (clear_width, .065, .045) if axis == "Y" else (.065, clear_width, .045)
                lattice = detail_box("三层槛窗横棂", p, dims, "red_lacquer", "window_detail", storey)
                record["window_detail_names"].append(lattice.name)
        opening_records.append(record)
        return record

    for storey, (w, d, floor, eave) in enumerate(zip(widths, depths, floor_levels, eave_levels)):
        if eave - floor <= 1.3:
            raise ValueError("declared height leaves no useful storey")
        box("楼地板_" + str(storey), (0, 0, floor - .075), (w + 1.2, d + 1.2, .15),
            "dark_wood" if is_stage else "white_stone", "floor", storey)
        box("天花_" + str(storey), (0, 0, eave - .38), (w, d, .13), "dark_wood", "ceiling", storey)
        xs = [-w / 2 + w * i / bays_x for i in range(bays_x + 1)]
        ys = [-d / 2 + d * i / bays_y for i in range(bays_y + 1)]
        positions = [(x, -d / 2) for x in xs] + [(x, d / 2) for x in xs]
        positions += [(-w / 2, y) for y in ys[1:-1]] + [(w / 2, y) for y in ys[1:-1]]
        base_height = .23 if not is_stage else .19
        for index, (x, y) in enumerate(positions):
            radius = column_radius * (1 - .07 * storey)
            base = F.column(identifier + "_柱础_" + str(storey) + "_" + str(index),
                            (x, y, floor + base_height / 2), radius * 1.45, base_height,
                            materials["white_stone"], structure, mesh_cache, 20)
            register(base, "column_base", storey)
            column_height = eave - .62 - (floor + base_height)
            column = F.column(identifier + "_檐柱_" + str(storey) + "_" + str(index),
                              (x, y, floor + base_height + column_height / 2), radius, column_height,
                              materials[scheme["column"]], structure, mesh_cache, 20)
            column["support_base"] = base.name
            column["floor_support"] = components["floor"][-1].name
            register(column, "column", storey)
        for sign in (-1, 1):
            box("前后檐枋", (0, sign * d / 2, eave - .46), (w + .35, .42, .42), "paint_blue", "beam", storey)
            box("侧檐枋", (sign * w / 2, 0, eave - .46), (.42, d + .35, .42), "paint_green", "beam", storey)
            box("彩枋金线", (0, sign * (d / 2 + .22), eave - .48), (w + .3, .025, .05), "gilt", "beam", storey)
        inner_w, inner_d = w - 2 * corridor, d - 2 * corridor
        wall_h = eave - .445 - floor
        center_z = floor + wall_h / 2
        walls = {
            "south": box("厚南墙", (0, -inner_d / 2, center_z), (inner_w, wall_thickness, wall_h), scheme["wall"], "wall", storey),
            "north": box("厚北墙", (0, inner_d / 2, center_z), (inner_w, wall_thickness, wall_h), scheme["wall"], "wall", storey),
            "east": box("厚东墙", (inner_w / 2, 0, center_z), (wall_thickness, inner_d, wall_h), scheme["wall"], "wall", storey),
            "west": box("厚西墙", (-inner_w / 2, 0, center_z), (wall_thickness, inner_d, wall_h), scheme["wall"], "wall", storey),
        }
        for wall_side, wall in walls.items():
            wall["wall_side"] = wall_side
            wall["wall_thickness_m"] = wall_thickness
        if is_stage and storey == 0:
            center = (0, front_sign * inner_d / 2, floor + wall_h * .46)
            cut(walls[front], front, center, inner_w * .86, wall_h * .88, storey, "north_open_stage_aperture", True)
            for side, sign in (("east", 1), ("west", -1)):
                cut(walls[side], side, (sign * inner_w / 2, 0, floor + wall_h * .48),
                    inner_d / bays_y * .78, wall_h * .82, storey, "side_stage_aperture", True)
        else:
            for side in ("south", "north"):
                sign = 1 if side == "north" else -1
                for index in range(bays_x):
                    x = -inner_w / 2 + inner_w * (index + .5) / bays_x
                    central = not is_stage and index == bays_x // 2
                    aperture_height = wall_h * (.80 if central else .66)
                    sill = .06 if central else wall_h * .20
                    center = (x, sign * inner_d / 2, floor + sill + aperture_height / 2)
                    cut(walls[side], side, center, inner_w / bays_x * .74, aperture_height, storey,
                        "central_four_leaf_door" if central else "tiered_lattice_window", central)
            for side, sign in (("east", 1), ("west", -1)):
                for index in range(bays_y):
                    y = -inner_d / 2 + inner_d * (index + .5) / bays_y
                    cut(walls[side], side, (sign * inner_w / 2, y, floor + wall_h * .54),
                        inner_d / bays_y * .66, wall_h * .62, storey, "side_lattice_window")
        if is_stage:
            # Front central bay remains a real clear gap; railings occupy the
            # flanking balcony bays and all dimensions remain study assumptions.
            rail_z = floor + .68
            for sign in (-1, 1):
                span = w / 3
                center_x = sign * w / 3
                box("前沿栏杆扶手", (center_x, front_sign * (d / 2 + .10), rail_z), (span - .15, .08, .08), "red_lacquer", "railing", storey)
                for i in range(6):
                    x = center_x - (span - .15) / 2 + (span - .15) * i / 5
                    box("前沿栏杆短柱", (x, front_sign * (d / 2 + .10), floor + .34), (.065, .065, .68), "red_lacquer", "railing", storey)
        if storey < tiers - 1:
            roof_top = floor_levels[storey + 1] - .08
            inner_dimensions = (widths[storey + 1] * .94, depths[storey + 1] * .94)
            main_color = scheme["lower_eaves"]
            edge_color = scheme["lower_eaves"]
        else:
            roof_top = total
            inner_dimensions = None
            main_color, edge_color = scheme["main_roof"], scheme["roof_edge"]
        roof_objects = _roof_geometry(identifier + "_檐层" + str(storey + 1), w, d, eave, roof_top,
                                      profile["roof_type"], materials[main_color], materials[edge_color],
                                      materials["dark_wood"], roofs, mesh_cache, overhang, corner_lift,
                                      storey, inner_dimensions)
        for obj in roof_objects:
            register(obj, obj["semantic_role"], storey)
    bpy.context.view_layer.update()
    for record in opening_records:
        record["center_world"] = list(root.matrix_world @ Vector(record["center_local"]))
        record["normal_world"] = list((root.matrix_world.to_3x3() @ Vector(record["normal_local"])).normalized())
    profile_json = json.dumps(profile, ensure_ascii=False)
    assumptions_json = json.dumps(assumptions, ensure_ascii=False)
    verified_json = json.dumps(profile["verified_facts"], ensure_ascii=False)
    for obj in [root] + objects:
        obj["restoration_profile"] = profile_json
        obj["assumptions"] = assumptions_json
        obj["verified_facts"] = verified_json
        obj["source_part_id"] = profile["source_part_id"]
        obj["building_id"] = identifier
        obj["representation"] = "source-constrained architectural type study; NOT a surveyed or component-complete restoration"
        obj["third_party_cost"] = 0
        obj["semantic_front"] = semantic_front
    root["opening_records"] = json.dumps(opening_records, ensure_ascii=False)
    root["model_reference_column_spans_m"] = [width, depth]
    root["published_dimension_interpretation"] = "Reference column/corridor span only; not a verified wall, eave or platform bounding box"
    return {"root": root, "collection": building, "objects": objects, "components": components,
            "opening_records": opening_records, "assumptions": assumptions,
            "verified_facts": profile["verified_facts"], "parameters": parameters}
