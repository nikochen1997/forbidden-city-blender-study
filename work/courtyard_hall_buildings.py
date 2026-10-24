"""V14 source-qualified companion-hall studies; caller owns saving and visibility.

Facts, unresolved fields and study dimensions remain separate. No I/O or scene
mutation occurs on import. Local +X is frontage; local -Y is the study front.
"""
import hashlib
import json
import math

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import forbidden_city_geometry as F
import restoration_buildings as R
import four_hall_buildings as H


SIDES = ("south", "north", "east", "west")
NORMALS = {"south": (0, -1, 0), "north": (0, 1, 0),
           "east": (1, 0, 0), "west": (-1, 0, 0)}


def _count(p, axis):
    value = p["bays_" + axis]
    if value is None:
        value = p.get("study_bays_" + axis, 1)
    if type(value) is not int or not 1 <= value <= 30:
        raise ValueError("bay reference must be an integer from 1 to 30")
    return value


def _axis_grid(p, axis):
    extent = p["dimensions"]["body_width_m" if axis == "x" else "body_depth_m"]
    spans = p.get("column_bay_widths_" + axis + "_m")
    count = _count(p, axis)
    if spans is None:
        return [-extent / 2 + extent * i / count for i in range(count + 1)]
    if type(spans) is not list or len(spans) != count:
        raise ValueError("column bay width count differs from structural grid")
    widths = [F._number("column bay width", v, strictly_positive=True) for v in spans]
    if abs(sum(widths) - extent) > 1e-6:
        raise ValueError("column bay widths do not sum to full body extent")
    result = [-extent / 2]
    for width in widths:
        result.append(result[-1] + width)
    return result


def _enclosure_grid(p, axis):
    grid = _axis_grid(p, axis)
    indices = p.get("enclosure_column_indices_" + axis)
    d = p["dimensions"]
    lo, hi = d["enclosure_" + axis + "_min_m"], d["enclosure_" + axis + "_max_m"]
    if indices is None:
        return [lo + (hi - lo) * i / _count(p, axis) for i in range(_count(p, axis) + 1)]
    if (type(indices) is not list or len(indices) < 2 or
            any(type(i) is not int or not 0 <= i < len(grid) for i in indices) or
            indices != sorted(set(indices))):
        raise ValueError("enclosure column indices must be a strict ordered grid subset")
    values = [grid[i] for i in indices]
    if abs(values[0] - lo) > 1e-6 or abs(values[-1] - hi) > 1e-6:
        raise ValueError("enclosure subset endpoints differ from wall axes")
    return values


def _upper_grid(p, axis):
    grid = _axis_grid(p, axis)
    indices = p.get("upper_column_indices_" + axis)
    if (type(indices) is not list or len(indices) < 2 or
            any(type(i) is not int or not 0 <= i < len(grid) for i in indices) or
            indices != sorted(set(indices))):
        raise ValueError("upper column indices require an explicit ordered body-grid subset")
    values = [grid[i] for i in indices]
    extent = p["dimensions"]["upper_band"]["width_m" if axis == "x" else "depth_m"]
    if abs(values[0]+extent/2)>1e-6 or abs(values[-1]-extent/2)>1e-6:
        raise ValueError("upper column subset endpoints differ from centered upper band")
    return values


def _rectangle_outside_area(rings, lo_x, hi_x, lo_y, hi_y):
    inside = 0.0
    for triangle in F._triangulate_rings(rings):
        polygon = list(triangle)
        for plane in ((1, 0, -lo_x), (-1, 0, hi_x),
                      (0, 1, -lo_y), (0, -1, hi_y)):
            polygon = F._clip_halfplane(polygon, plane)
        if len(polygon) >= 3:
            inside += abs(F._ring_area(polygon))
    return max(0.0, (hi_x - lo_x) * (hi_y - lo_y) - inside)


def _perimeter_grid(xs, ys):
    return ({(x, y) for x in xs for y in (ys[0], ys[-1])} |
            {(x, y) for x in (xs[0], xs[-1]) for y in ys[1:-1]})


def _shared_support_preflight(p, support):
    if support is None:
        if p.get("reference_support_id") is not None:
            raise ValueError("profile names shared support but caller did not supply it")
        return
    if support.type != "MESH" or not p.get("reference_support_id") or p["reference_support_id"] != support.get("reference_support_id", support.name):
        raise ValueError("caller shared support identifier/type does not match profile")
    if support.modifiers or support.data.shape_keys:
        raise ValueError("shared support must be a resolved plain mesh for actual contact audit")
    bpy.context.view_layer.update()
    tree = BVHTree.FromPolygons([support.matrix_world @ v.co for v in support.data.vertices], [tuple(f.vertices) for f in support.data.polygons])
    d = p["dimensions"]
    grid = _perimeter_grid(_axis_grid(p,"x"), _axis_grid(p,"y"))
    if d.get("upper_band"):
        grid |= _perimeter_grid(_upper_grid(p,"x"), _upper_grid(p,"y"))
    points = [(x+d["column_base_radius_m"]*math.cos(i*math.pi/8), y+d["column_base_radius_m"]*math.sin(i*math.pi/8))
              for x,y in grid for i in range(16)]
    if p.get("additional_front_square_posts_per_bay",0):
        q=d["front_square_post_width_m"]*.6
        xs=_axis_grid(p,"x")
        points += [(a+(b-a)*k/3+sx*q,-d["body_depth_m"]/2+sy*q)
                   for a,b in zip(xs,xs[1:]) for k in (1,2) for sx in (-1,1) for sy in (-1,1)]
    c,s=math.cos(p["rotation_z_rad"]),math.sin(p["rotation_z_rad"])
    for x,y in points:
        point=Vector((p["anchor"][0]+c*x-s*y,p["anchor"][1]+s*x+c*y,p["anchor"][2]+d["floor_z_m"]))
        hit=tree.ray_cast(point+Vector((0,0,.02)),Vector((0,0,-1)),.04)[0]
        if hit is None or abs(hit.z-point.z)>1e-4:
            raise ValueError("shared support lacks complete declared column-base footprint")


def _validate(p):
    H._finite(p)
    for key in ("building_id", "name_zh", "source_part_id", "anchor", "rotation_z_rad",
                "source_polygon_local", "source_polygon_world", "source_holes_local",
                "dimensions", "roof_tiers", "facades", "material_scheme", "known_facts",
                "parameter_evidence", "unbuilt", "bays_x", "bays_y", "eaves_tiers"):
        if key not in p:
            raise ValueError("missing explicit study field " + key)
    for key in ("third_party_cost", "paid_service_calls"):
        if type(p.get(key)) is not int or p[key] != 0:
            raise ValueError(key + " must be integer zero")
    if (p.get("occupied_storeys", "missing") is not None or
            type(p.get("reference_floor_count")) is not int or p["reference_floor_count"] != 1):
        raise ValueError("one support reference does not certify occupied storeys")
    if p.get("human_approval") != "pending":
        raise ValueError("this module cannot confer human approval")
    F._point("anchor", p["anchor"])
    F._number("rotation", p["rotation_z_rad"])
    for axis in ("x", "y"):
        if p["bays_" + axis] is not None and type(p["bays_" + axis]) is not int:
            raise ValueError("factual bay counts must remain integer or null")
        _count(p, axis)
        _axis_grid(p, axis)
        _enclosure_grid(p, axis)
    rings = [F._clean_ring(p["source_polygon_local"])] + [F._clean_ring(r) for r in p["source_holes_local"]]
    F._triangulate_rings(rings)
    if len(p["source_polygon_local"]) != len(p["source_polygon_world"]):
        raise ValueError("source registration vertex count differs")
    c, s = math.cos(p["rotation_z_rad"]), math.sin(p["rotation_z_rad"])
    for local, world in zip(p["source_polygon_local"], p["source_polygon_world"]):
        actual = (p["anchor"][0] + c * local[0] - s * local[1],
                  p["anchor"][1] + s * local[0] + c * local[1])
        if math.dist(actual, world) > 1e-4:
            raise ValueError("local/world source polygon is not registered")
    d = p["dimensions"]
    positive = ("body_width_m", "body_depth_m", "slab_thickness_m", "wall_thickness_m",
                "column_radius_m", "column_base_radius_m", "column_base_height_m",
                "beam_width_m", "beam_height_m", "door_height_m", "window_height_m",
                "opening_frame_width_m", "opening_frame_depth_m", "leaf_panel_depth_m")
    for key in positive:
        F._number(key, d[key], strictly_positive=True)
    for key in ("floor_z_m", "source_reference_slab_bottom_z_m", "source_reference_slab_top_z_m",
                "column_top_z_m", "wall_top_z_m", "enclosure_x_min_m", "enclosure_x_max_m",
                "enclosure_y_min_m", "enclosure_y_max_m"):
        F._number(key, d[key])
    if not d["source_reference_slab_bottom_z_m"] < d["floor_z_m"] == d["source_reference_slab_top_z_m"] < d["column_top_z_m"]:
        raise ValueError("invalid support height order")
    if abs(d["slab_thickness_m"] - (d["floor_z_m"] - d["source_reference_slab_bottom_z_m"])) > 1e-8:
        raise ValueError("reference slab thickness differs")
    if d["floor_z_m"] + d["column_base_height_m"] >= d["column_top_z_m"]:
        raise ValueError("column base consumes column")
    if d["column_top_z_m"] + d["beam_height_m"] > d["wall_top_z_m"] + 1e-8:
        raise ValueError("beam top exceeds wall top")
    w, depth, t = d["body_width_m"], d["body_depth_m"], d["wall_thickness_m"]
    for axis, extent in (("x", w), ("y", depth)):
        lo, hi = d["enclosure_" + axis + "_min_m"], d["enclosure_" + axis + "_max_m"]
        if not -extent / 2 <= lo < hi <= extent / 2 or hi - lo <= 3 * t:
            raise ValueError("invalid enclosure inside body reference")
    margin = max(d["column_base_radius_m"], d["beam_width_m"] / 2, t / 2)
    outside = _rectangle_outside_area(rings, -w / 2 - margin, w / 2 + margin,
                                     -depth / 2 - margin, depth / 2 + margin)
    if outside > 1e-5:
        raise ValueError("support envelope leaves full source polygon or crosses its holes")
    front = F._number("front veranda", d["veranda_front_depth_m"], minimum=0)
    if abs(front - d["enclosure_y_min_m"] - depth / 2) > 1e-7:
        raise ValueError("front veranda and recessed front wall disagree")
    if front > t / 2 + 1e-7 and front <= t / 2 + d["column_radius_m"]:
        raise ValueError("front veranda has no positive open circulation depth")
    for key, actual in (("veranda_rear_depth_m", depth / 2 - d["enclosure_y_max_m"]),
                        ("veranda_west_depth_m", d["enclosure_x_min_m"] + w / 2),
                        ("veranda_east_depth_m", w / 2 - d["enclosure_x_max_m"])):
        if key in d and abs(F._number(key, d[key], minimum=0) - actual) > 1e-7:
            raise ValueError("declared veranda disagrees with recessed wall: " + key)
    extra = p.get("additional_front_square_posts_per_bay", 0)
    if type(extra) is not int or extra not in (0, 2):
        raise ValueError("only explicit zero or two added square front posts per structural bay supported")
    if extra:
        q = F._number("front square post width", d["front_square_post_width_m"], strictly_positive=True)
        if q > min(d["beam_width_m"], min(b-a for a,b in zip(_axis_grid(p,"x"),_axis_grid(p,"x")[1:])) / 3):
            raise ValueError("square post exceeds beam or structural subdivision")
    for key in ("window_sill_height_above_floor_m",):
        F._number(key, d[key], minimum=0)
    for key in ("door_width_fraction_of_bay", "window_width_fraction_of_bay"):
        if not 0 < F._number(key, d[key]) < 1:
            raise ValueError("opening fraction must lie strictly inside its bay")
    for key in ("side_window_width_m", "side_window_height_m"):
        if key in d:
            F._number(key, d[key], strictly_positive=True)
    for side in SIDES:
        facade = p["facades"][side]
        if side in ("east", "west") and facade["kind"] not in ("window", "solid_wall", "unresolved_wall"):
            raise ValueError("this side-wall API supports explicitly supplied windows only")
        rows = facade["schedule"] if side in ("south", "north") else [facade]
        if side in ("south", "north") and [row["bay_index"] for row in rows] != list(range(len(_enclosure_grid(p, "x")) - 1)):
            raise ValueError("front/rear schedule must cover every reference bay")
        for row in rows:
            if row["kind"] not in ("door", "window", "passage", "solid_wall", "unresolved_wall"):
                raise ValueError("unsupported explicit facade kind")
            count = row.get("leaf_count")
            if count is not None and (type(count) is not int or not 1 <= count <= 32):
                raise ValueError("unknown leaf counts must remain null")
            if row["kind"] not in ("door", "window") and count is not None:
                raise ValueError("non-leaf facade cannot invent leaves")
            if row["kind"] not in ("door", "window", "passage"):
                continue
            ex = _enclosure_grid(p, "x")
            span = ((ex[row["bay_index"] + 1] - ex[row["bay_index"]])
                    if side in ("south", "north") else d["enclosure_y_max_m"] - d["enclosure_y_min_m"])
            width = (d.get("side_window_width_m", span / _count(p, "y") * d["window_width_fraction_of_bay"])
                     if side in ("east", "west") else span * d[("door" if row["kind"] == "passage" else row["kind"]) + "_width_fraction_of_bay"])
            height = d.get("side_window_height_m", d["window_height_m"]) if side in ("east", "west") else d[("door" if row["kind"] == "passage" else row["kind"]) + "_height_m"]
            bottom = d["floor_z_m"] + (d["window_sill_height_above_floor_m"] if row["kind"] == "window" else 0)
            if width + 2 * d["opening_frame_width_m"] >= span or bottom + height + d["opening_frame_width_m"] >= d["wall_top_z_m"]:
                raise ValueError("opening/frame consumes supporting wall")
    tiers = len(p["roof_tiers"])
    if tiers not in (0, 1, 2) or (p["eaves_tiers"] is not None and (type(p["eaves_tiers"]) is not int or p["eaves_tiers"] != tiers)):
        raise ValueError("zero unknown, one or two explicitly ordered roof tiers required")
    band = d.get("upper_band")
    if (tiers == 2) != (band is not None):
        raise ValueError("double eaves require explicit upper band; no upper occupied floor")
    if band:
        for key in ("width_m", "depth_m", "wall_thickness_m", "bottom_z_m", "top_z_m"):
            F._number("upper band " + key, band[key], strictly_positive=True)
        if band.get("occupied_floor") is not False or not d["floor_z_m"]+d["column_base_height_m"] < band["bottom_z_m"]-d["beam_height_m"] < band["bottom_z_m"] < band["top_z_m"]:
            raise ValueError("upper band/support height order invalid or occupied floor invented")
        if band["width_m"] >= w or band["depth_m"] >= depth:
            raise ValueError("upper band must be inside the full lower structural body")
        _upper_grid(p, "x")
        _upper_grid(p, "y")
    for index, roof in enumerate(p["roof_tiers"]):
        if type(roof["annular"]) is not bool:
            raise ValueError("annular flag must be explicit boolean")
        if roof["roof_type"] not in ("xieshan", "wudian", "xuanshan", "yingshan", "juanpeng_yingshan", "juanpeng_xieshan") or roof["tier_index"] != index:
            raise ValueError("unsupported roof category")
        if roof["roof_type"] == "juanpeng_xieshan" and p["known_facts"].get("roof_type") != "juanpeng_xieshan":
            raise ValueError("qualified juanpeng xieshan requires explicit profile fact category")
        for key in ("outer_width_m", "outer_depth_m", "eave_z_m", "top_z_m", "corner_lift_m"):
            F._number(key, roof[key])
        if roof["additional_overhang_m"] != 0:
            raise ValueError("duplicate roof overhang is not supported")
        if bool(roof["annular"]) != (tiers == 2 and index == 0):
            raise ValueError("double eaves require lower annular shell and upper full roof")
        if tiers == 2 and roof["roof_type"] != "wudian":
            raise ValueError("this two-tier courtyard study is explicitly wudian")
        if roof["annular"]:
            for axis in ("width", "depth"):
                inner = F._number("annular inner " + axis, roof["inner_"+axis+"_m"], strictly_positive=True)
                if not 0 < inner < roof["outer_"+axis+"_m"] or abs(inner-band[axis+"_m"])>band["wall_thickness_m"]-1e-5:
                    raise ValueError("lower annular inner edge must meet upper-band wall thickness")
        elif roof["inner_width_m"] is not None or roof["inner_depth_m"] is not None:
            raise ValueError("full roof must not declare a lower-ring hole")
        support_top = d["wall_top_z_m"] if index == 0 else band["top_z_m"]
        if roof["top_z_m"] - roof["eave_z_m"] <= .25 or roof["eave_z_m"] <= support_top + .2:
            raise ValueError("roof has insufficient rise or support clearance")
        cover_w, cover_d = (w, depth) if index == 0 else (band["width_m"]+band["wall_thickness_m"],band["depth_m"]+band["wall_thickness_m"])
        if roof["outer_width_m"] < cover_w or roof["outer_depth_m"] < cover_d:
            raise ValueError("roof does not cover reference body")
        if not 0 <= roof["corner_lift_m"] < roof["top_z_m"] - roof["eave_z_m"]:
            raise ValueError("invalid corner lift")
        if roof["roof_type"] in ("yingshan", "juanpeng_yingshan") and (abs(roof["outer_width_m"] - w) > 1e-7 or roof["corner_lift_m"] != 0):
            raise ValueError("hard gable cannot project beyond gable end or acquire hip uplift")
    if tiers == 2 and p["roof_tiers"][1]["eave_z_m"] <= p["roof_tiers"][0]["top_z_m"] + .3:
        raise ValueError("upper roof must clear the complete lower annular edge")
    return rings


def _gable_roof(name, roof, mats, scheme, collection, cache):
    """Closed curved two-slope skin, without an invented hip at either end."""
    a, b = roof["outer_width_m"] / 2, roof["outer_depth_m"] / 2
    eave, peak, lift = roof["eave_z_m"], roof["top_z_m"], roof["corner_lift_m"]
    surface, indices = F._Surface(), []

    def point(side, u, t):
        elevation = math.sin(t * math.pi / 2) ** 1.5 if roof["roof_type"] == "juanpeng_yingshan" else t ** 1.65
        return (a * u if side == "south" else -a * u,
                (-1 if side == "south" else 1) * b * (1 - t),
                eave + (peak - eave) * elevation + lift * abs(u) ** 8 * (1 - t) ** 3)

    for side in ("south", "north"):
        for j in range(20):
            for i in range(32):
                u0, u1, t0, t1 = -1 + 2 * i / 32, -1 + 2 * (i + 1) / 32, j / 20, (j + 1) / 20
                R._face(surface, indices, 1 if j == 0 else 0,
                        [point(side, u0, t0), point(side, u1, t0), point(side, u1, t1), point(side, u0, t1)])
    top_count = len(surface.faces)
    R._closed_skin(surface, .13)
    indices.extend([2] * (len(surface.faces) - top_count))
    ridge, tiles = F._Surface(), F._Surface()
    if roof["roof_type"] != "juanpeng_yingshan":
        F._tube(ridge, [(-a, 0, peak + .025), (a, 0, peak + .025)], .085, 8)
    for side in ("south", "north"):
        F._tube(ridge, [point(side, -1 + 2 * i / 32, 0) for i in range(33)], .06, 6)
        for u in (-1, 1):
            F._tube(ridge, [(x, y, z + .025) for x, y, z in [point(side, u, j / 20) for j in range(21)]], .06, 6)
        count = max(8, min(150, round(2 * a / .33)))
        for i in range(count + 1):
            points = [point(side, -1 + 2 * i / count, j / 20) for j in range(21)]
            F._tube(tiles, [(x, y, z + .022) for x, y, z in points], .026, 5)
    surfaces = (surface, ridge, tiles)
    shift = max(v[2] for item in surfaces for v in item.vertices) - peak
    for item in surfaces:
        item.vertices = [(x, y, z - shift) for x, y, z in item.vertices]
    triple = [mats[scheme[key]] for key in ("roof_main", "roof_edge", "roof_under")]
    key = ("V14_gable_roof", roof["roof_type"], a, b, eave, peak, lift, *(m.name for m in triple))
    result = [R._mesh(name + "_双坡薄壳", surface, collection, triple, indices, cache, key + ("surface",))]
    for label, item, material, role in (("脊檐", ridge, triple[1], "ridge"), ("瓦垄", tiles, triple[0], "tile")):
        obj = R._mesh(name + "_" + label, item, collection, [material], cache=cache, key=key + (label,))
        obj["semantic_role"] = role
        result.append(obj)
    for obj in result:
        obj["roof_type"], obj["roof_tier_index"] = roof["roof_type"], roof["tier_index"]
        obj["eave_level_model_m"], obj["target_top_model_m"] = eave - shift, peak
        obj["roof_z_only_adjustment_m"] = -shift
        obj["juanpeng_rounded_crown"] = roof["roof_type"] == "juanpeng_yingshan"
        obj["has_pointed_main_ridge"] = roof["roof_type"] != "juanpeng_yingshan"
    return result


def build_hall(profile, collection, materials=None, mesh_cache=None, shared_support_object=None):
    rings = _validate(profile)
    _shared_support_preflight(profile, shared_support_object)
    p, d, ident = profile, profile["dimensions"], profile["building_id"]
    mats = R.restoration_materials() if materials is None else dict(materials)
    if "stone" not in mats and "white_stone" in mats:
        mats["stone"] = mats["white_stone"]
    scheme, cache = p["material_scheme"], {} if mesh_cache is None else mesh_cache
    for key in ("base", "column", "beam", "wall", "frame", "infill", "roof_main", "roof_edge", "roof_under"):
        if scheme[key] not in mats:
            raise ValueError("caller material missing " + scheme[key])
    building = F.ensure_collection("V14_" + ident, collection)
    root = bpy.data.objects.new("V14_" + ident + "_root", None)
    building.objects.link(root)
    root.location, root.rotation_euler.z = p["anchor"], p["rotation_z_rad"]
    profile_sha = hashlib.sha256(json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    root["hall_study_profile"] = json.dumps(p, ensure_ascii=False, allow_nan=False)
    objects, components, openings, roofs = [], {}, [], []

    def add(obj, role):
        obj.parent = root
        obj["semantic_role"], obj["building_id"] = role, ident
        obj["restoration_v14_building_id"] = ident
        obj["source_reference_part_id"], obj["profile_sha256"] = p["source_part_id"], profile_sha
        obj["third_party_cost"], obj["human_approval"] = 0, "pending"
        obj["scope"] = "source-qualified unmeasured exterior study; incomplete reconstruction"
        objects.append(obj)
        components.setdefault(role, []).append(obj)
        return obj

    def box(label, center, dims, material, role, cached=True):
        return add(F.box("V14_" + ident + "_" + label, center, dims, mats[scheme[material]], building,
                         cache if cached else None, role), role)

    if shared_support_object is None:
        if p.get("reference_support_id") is not None:
            raise ValueError("profile names shared support but caller did not supply it")
        top = F._Surface()
        for triangle in F._triangulate_rings(rings):
            top.face([(x, y, d["floor_z_m"]) for x, y in triangle])
        F._volume_from_top(top, d["source_reference_slab_bottom_z_m"])
        slab = add(F._object("V14_" + ident + "_source_reference_slab",
                            F._new_mesh("V14_source_slab", top.vertices, top.faces, mats[scheme["base"]]),
                            building, "source_reference_slab"), "source_reference_slab")
        slab["reference_floor_only"], slab["not_measured_platform"] = True, True
    else:
        slab = shared_support_object
        if slab.type != "MESH" or not p.get("reference_support_id") or p["reference_support_id"] != slab.get("reference_support_id", slab.name):
            raise ValueError("caller shared support identifier/type does not match profile")
        components["source_reference_slab"] = [slab]
    w, depth, floor, t = d["body_width_m"], d["body_depth_m"], d["floor_z_m"], d["wall_thickness_m"]
    xs, ys = _axis_grid(p, "x"), _axis_grid(p, "y")
    grid = _perimeter_grid(xs, ys)
    for i, (x, y) in enumerate(sorted(grid)):
        xl, xh, yl, yh = [d["enclosure_" + k + "_m"] for k in ("x_min", "x_max", "y_min", "y_max")]
        attached = ((abs(y-yl) <= t/2+1e-6 or abs(y-yh) <= t/2+1e-6) and xl-t/2 <= x <= xh+t/2 or
                    (abs(x-xl) <= t/2+1e-6 or abs(x-xh) <= t/2+1e-6) and yl-t/2 <= y <= yh+t/2)
        is_front_free = not attached
        role = "column" if is_front_free else "pilaster"
        base = add(F.column("V14_" + ident + "_base_" + str(i), (x, y, floor + d["column_base_height_m"] / 2),
                            d["column_base_radius_m"], d["column_base_height_m"], mats[scheme["base"]], building, cache), "column_base")
        z0, z1 = floor + d["column_base_height_m"], d["column_top_z_m"]
        col = add(F.column("V14_" + ident + "_column_" + str(i), (x, y, (z0 + z1) / 2),
                           d["column_radius_m"], z1 - z0, mats[scheme["column"]], building, cache), role)
        base["support_object"], col["support_object"] = slab.name, base.name
        col["wall_attached_reference"], col["study_column_axis"] = not is_front_free, [x, y]
    for bay, (a, b) in enumerate(zip(xs, xs[1:])):
        for extra in range(p.get("additional_front_square_posts_per_bay", 0)):
            x, y = a + (b-a)*(extra+1)/3, -depth/2
            q, bh = d["front_square_post_width_m"], d["column_base_height_m"]
            base = box("square_base_"+str(bay)+"_"+str(extra), (x,y,floor+bh/2), (q*1.2,q*1.2,bh), "base", "column_base")
            base["support_object"] = slab.name
            col = box("square_post_"+str(bay)+"_"+str(extra), (x,y,(floor+bh+d["column_top_z_m"])/2),
                      (q,q,d["column_top_z_m"]-floor-bh), "column", "additional_front_square_post")
            col["support_object"], col["study_column_axis"], col["structural_bay_index"] = base.name, [x,y], bay
            col["not_additional_structural_bay"], col["cross_section"] = True, "square"
    band = d.get("upper_band")
    upper_grid = _perimeter_grid(_upper_grid(p,"x"), _upper_grid(p,"y")) if band else set()
    if band:
        for i,(x,y) in enumerate(sorted(upper_grid)):
            bh=d["column_base_height_m"]
            base=add(F.column("V14_"+ident+"_inner_base_"+str(i),(x,y,floor+bh/2),d["column_base_radius_m"],bh,
                              mats[scheme["base"]],building,cache),"column_base")
            z0,z1=floor+bh,band["bottom_z_m"]-d["beam_height_m"]
            col=add(F.column("V14_"+ident+"_inner_column_"+str(i),(x,y,(z0+z1)/2),d["column_radius_m"],z1-z0,
                             mats[scheme["column"]],building,cache),"upper_support_column")
            base["support_object"],col["support_object"]=slab.name,base.name
            col["study_column_axis"],col["column_top_z_m"],col["occupied_storey"]= [x,y],z1,False
    if shared_support_object is not None:
        bpy.context.view_layer.update()
        tree = BVHTree.FromPolygons([slab.matrix_world @ v.co for v in slab.data.vertices], [tuple(f.vertices) for f in slab.data.polygons])
        for base in components["column_base"]:
            min_z = min(v.co.z for v in base.data.vertices)
            for v in base.data.vertices:
                if abs(v.co.z-min_z)<1e-6:
                    point = base.matrix_world @ v.co
                    hit = tree.ray_cast(point+Vector((0,0,.02)),Vector((0,0,-1)),.04)[0]
                    if hit is None or abs(hit.z-point.z)>1e-4:
                        raise ValueError("complete column-base bottom rim lacks actual shared support")
    beam_z = d["column_top_z_m"] + d["beam_height_m"] / 2
    bw = d["beam_width_m"]
    for side, x, y, ww, dd in (("south", 0, -depth / 2, w + bw, bw),
                                ("north", 0, depth / 2, w + bw, bw),
                                ("west", -w / 2, 0, bw, depth + bw),
                                ("east", w / 2, 0, bw, depth + bw)):
        obj = box("beam_" + side, (x, y, beam_z), (ww, dd, d["beam_height_m"]), "beam", "beam")
        obj["wall_side"] = side
        obj["roof_tier_index"] = 0
    if band:
        uw,ud=band["width_m"],band["depth_m"]
        for side,x,y,ww,dd in (("south",0,-ud/2,uw+bw,bw),("north",0,ud/2,uw+bw,bw),
                               ("west",-uw/2,0,bw,ud+bw),("east",uw/2,0,bw,ud+bw)):
            obj=box("inner_beam_"+side,(x,y,band["bottom_z_m"]-d["beam_height_m"]/2),(ww,dd,d["beam_height_m"]),"beam","beam")
            obj["wall_side"],obj["roof_tier_index"],obj["occupied_floor"] = side,1,False
        bt=band["wall_thickness_m"]
        for side,x,y,ww,dd in (("south",0,-ud/2,uw+bt,bt),("north",0,ud/2,uw+bt,bt),
                               ("west",-uw/2,0,bt,ud+bt),("east",uw/2,0,bt,ud+bt)):
            obj=box("upper_band_"+side,(x,y,(band["bottom_z_m"]+band["top_z_m"])/2),(ww,dd,band["top_z_m"]-band["bottom_z_m"]),"wall","upper_band_wall")
            obj["wall_side"],obj["roof_tier_index"],obj["occupied_floor"] = side,1,False
    lo, hi = d["enclosure_x_min_m"], d["enclosure_x_max_m"]
    yl, yh, wall_top = d["enclosure_y_min_m"], d["enclosure_y_max_m"], d["wall_top_z_m"]
    walls = {}
    for side, x, y, ww, dd in (("south", (lo + hi) / 2, yl, hi - lo + t, t),
                                ("north", (lo + hi) / 2, yh, hi - lo + t, t),
                                ("west", lo, (yl + yh) / 2, t, yh - yl + t),
                                ("east", hi, (yl + yh) / 2, t, yh - yl + t)):
        wall = box("wall_" + side, (x, y, (floor + wall_top) / 2), (ww, dd, wall_top - floor), "wall", "wall", False)
        wall["wall_side"], wall["wall_thickness_m"] = side, t
        wall["category"] = "mixed_explicit_schedule" if side in ("south", "north") else p["facades"][side]["kind"]
        walls[side] = wall

    def aperture(side, row, span, center_across, index):
        kind = row["kind"]
        axis = "Y" if side in ("south", "north") else "X"
        dim_kind = "door" if kind == "passage" else kind
        width = span * d[dim_kind + "_width_fraction_of_bay"]
        height = d[dim_kind + "_height_m"]
        if axis == "X":
            width = d.get("side_window_width_m", span / _count(p, "y") * d["window_width_fraction_of_bay"])
            height = d.get("side_window_height_m", height)
        z0 = floor + (d["window_sill_height_above_floor_m"] if kind == "window" else 0)
        center = [center_across, yl if side == "south" else yh, z0 + height / 2] if axis == "Y" else [lo if side == "west" else hi, center_across, z0 + height / 2]
        opening_id = ident + "_" + side + "_" + str(index)
        schedule = {"id": opening_id, "type": "window" if kind == "window" else "door",
                    "destination": "open_study_passage" if kind == "passage" else "unmeasured_study_interior",
                    "center": center, "width": width, "height": height,
                    "depth": t + .5, "normal_axis": axis}
        record = F.cut_opening(walls[side], schedule, building, None)
        normal, across = Vector(NORMALS[side]), Vector((1, 0, 0) if axis == "Y" else (0, 1, 0))
        frame_names, infill_names, leaf_names = [], [], []
        for sign in (-1, 1):
            point = Vector(center) + across * sign * (width + d["opening_frame_width_m"]) / 2
            dims = (d["opening_frame_width_m"], d["opening_frame_depth_m"], height) if axis == "Y" else (d["opening_frame_depth_m"], d["opening_frame_width_m"], height)
            frame_names.append(box("jamb", point, dims, "frame", "opening_frame").name)
        point = Vector(center) + Vector((0, 0, (height + d["opening_frame_width_m"]) / 2))
        dims = (width, d["opening_frame_depth_m"], d["opening_frame_width_m"]) if axis == "Y" else (d["opening_frame_depth_m"], width, d["opening_frame_width_m"])
        frame_names.append(box("head", point, dims, "frame", "opening_frame").name)
        if kind == "window":
            point = Vector(center) - Vector((0, 0, (height + d["opening_frame_width_m"]) / 2))
            frame_names.append(box("sill", point, dims, "frame", "opening_frame").name)
        count = row.get("leaf_count")
        if kind != "passage":
            for i in range(count or 1):
                panel_width = width / (count or 1)
                point = Vector(center) + across * (-width / 2 + panel_width * (i + .5))
                dims = (panel_width * .985, d["leaf_panel_depth_m"], height * .99) if axis == "Y" else (d["leaf_panel_depth_m"], panel_width * .985, height * .99)
                role = kind + "_leaf" if count else kind + "_set_infill_proxy"
                leaf = box(role, point, dims, "infill", role)
                leaf["opening_id"], leaf["leaf_count_status"] = opening_id, "known_reference_count" if count else "unknown_not_one_actual_leaf"
                leaf["not_actual_leaf_count"] = count is None
                leaf["pattern_category"] = row.get("pattern_category") or "unresolved"
                leaf["pattern_geometry"] = "unresolved_panel_reference; precise lattice and joinery unbuilt"
                if count:
                    leaf["leaf_count"], leaf["leaf_index"] = count, i
                    leaf_names.append(leaf.name)
                else:
                    infill_names.append(leaf.name)
        record.update({"kind": kind, "wall_side": side, "bay_index": index,
                       "center_local": center, "normal_local": list(normal), "clear_width_m": width,
                       "clear_height_m": height, "bottom_z_m": z0, "leaf_count": count,
                       "leaf_reference_names": leaf_names, "infill_proxy_names": infill_names,
                       "frame_names": frame_names, "wall_segment_names": [walls[side].name],
                       "pattern_category": row.get("pattern_category"), "category_scope": row.get("category_scope", "source-qualified category; study geometry"),
                       "opening_method": "independent Exact Boolean applied before frames; no cached wall or cutter",
                       "dimension_status": "unmeasured_study", "leaf_pose": "closed_study_independently_movable" if count else "unknown"})
        openings.append(record)

    for side in ("south", "north"):
        ex = _enclosure_grid(p, "x")
        for row in p["facades"][side]["schedule"]:
            if row["kind"] in ("door", "window", "passage"):
                index = row["bay_index"]
                aperture(side, row, ex[index+1]-ex[index], (ex[index+1]+ex[index])/2, index)
    for side in ("east", "west"):
        row = p["facades"][side]
        if row["kind"] in ("window", "door", "passage"):
            aperture(side, row, yh - yl, (yl + yh) / 2, 0)
    for roof in p["roof_tiers"]:
        triple = tuple(mats[scheme[k]].name for k in ("roof_main", "roof_edge", "roof_under"))
        roof_cache = cache.setdefault(("V14_roof_material_triple", *triple), {})
        if roof["roof_type"] in ("xieshan", "wudian", "juanpeng_xieshan"):
            parts = R._roof_geometry("V14_" + ident + "_roof", roof["outer_width_m"], roof["outer_depth_m"],
                                     roof["eave_z_m"], roof["top_z_m"], roof["roof_type"], *(mats[scheme[k]] for k in ("roof_main", "roof_edge", "roof_under")),
                                     building, roof_cache, 0, roof["corner_lift_m"], roof["tier_index"],
                                     (roof["inner_width_m"], roof["inner_depth_m"]) if roof["annular"] else None)
        else:
            parts = _gable_roof("V14_" + ident + "_roof", roof, mats, scheme, building, roof_cache)
        for obj in parts:
            H._fixed_roof_surface(obj, cache)
            add(obj, obj.get("semantic_role", "roof"))
            obj["roof_tier_index"] = roof["tier_index"]
        roof_obj = parts[0]
        tree = BVHTree.FromPolygons([v.co for v in roof_obj.data.vertices], [tuple(f.vertices) for f in roof_obj.data.polygons])
        boundary_queries = []
        inner_connections = []
        if roof["annular"]:
            bpy.context.view_layer.update()
            inner_x,inner_y=roof["inner_width_m"]/2,roof["inner_depth_m"]/2
            iz=roof["top_z_m"]+roof_obj["roof_z_only_adjustment_m"]
            for side in SIDES:
                wall=next(o for o in components["upper_band_wall"] if o["wall_side"]==side)
                inv=wall.matrix_local.inverted()
                for i in range(17):
                    u=-1+2*i/16
                    point=Vector((inner_x*u,-inner_y,iz) if side=="south" else (inner_x*u,inner_y,iz) if side=="north" else (inner_x,inner_y*u,iz) if side=="east" else (-inner_x,inner_y*u,iz))
                    nearest=tree.find_nearest(point)
                    contained=inv@point
                    if nearest[0] is None or nearest[3]>1e-5 or max(abs(v) for v in contained)>.50001:
                        raise ValueError("actual annular inner rim does not connect into upper-band solid")
                    inner_connections.append({"point_local":list(point),"upper_band_wall":wall.name,"actual_roof_distance_m":nearest[3]})

        def contact_z(x, y, bottom):
            hit = tree.ray_cast(Vector((x, y, bottom + 1e-5)), Vector((0, 0, 1)), 100)[0]
            if hit is None and roof["roof_type"] in ("yingshan", "juanpeng_yingshan"):
                end = max(abs(v.co.x) for v in roof_obj.data.vertices)
                if abs(abs(x) - end) <= 1e-5:
                    # A vertical query exactly on a vertical end-cap is coplanar.
                    # This unlifted two-slope skin is constant along X. Query its
                    # adjacent interior and independently require the original
                    # edge point to lie on the actual mesh, without moving it.
                    query_x = math.copysign(end - 1e-5, x)
                    candidate = tree.ray_cast(Vector((query_x, y, bottom + 1e-5)), Vector((0, 0, 1)), 100)[0]
                    if candidate is not None:
                        nearest = tree.find_nearest(Vector((x, y, candidate.z)))
                        if nearest[0] is not None and nearest[3] <= 1e-5:
                            hit = Vector((x, y, candidate.z))
                            boundary_queries.append({"original": [x, y, candidate.z], "query_x": query_x,
                                                     "original_point_mesh_distance_m": nearest[3]})
            if hit is None or hit.z <= bottom + 1e-4:
                raise ValueError("no positive actual generated roof underside above support at " + repr((x, y, bottom)) + "; roof=" + roof["roof_type"])
            return hit.z

        if roof["tier_index"] == 0:
            cx0,cx1,cy0,cy1,ct,closure_bottom=lo,hi,yl,yh,t,wall_top
        else:
            cx0,cx1,cy0,cy1,ct,closure_bottom=-band["width_m"]/2,band["width_m"]/2,-band["depth_m"]/2,band["depth_m"]/2,band["wall_thickness_m"],band["top_z_m"]
        closure_sides = (("south", cy0, cx0 - ct / 2, cx1 + ct / 2), ("north", cy1, cx0 - ct / 2, cx1 + ct / 2),
                         ("west", cx0, cy0 - ct / 2, cy1 + ct / 2), ("east", cx1, cy0 - ct / 2, cy1 + ct / 2))
        for side, constant, a, b in closure_sides:
            axis_y = side in ("south", "north")
            stations = [a + (b - a) * i / 40 for i in range(41)]
            surface = F._Surface()
            all_points, contact_records = [], []
            for sign in (-1, 1):
                points = []
                for station in stations:
                    x, y = (station, constant + sign * ct / 2) if axis_y else (constant + sign * ct / 2, station)
                    z = contact_z(x, y, closure_bottom)
                    points.append((x, y, z))
                    contact_records.append([x, y, z])
                bottom_points = [(v[0], v[1], closure_bottom) for v in points]
                for i in range(40):
                    surface.face([bottom_points[i], bottom_points[i+1], points[i+1], points[i]])
                all_points.append((bottom_points, points))
            for i in range(40):
                for row in (0, 1):
                    surface.face([all_points[0][row][i], all_points[0][row][i + 1], all_points[1][row][i + 1], all_points[1][row][i]])
            for i in (0, 40):
                surface.face([all_points[0][0][i], all_points[1][0][i], all_points[1][1][i], all_points[0][1][i]])
            obj = add(F._object("V14_" + ident + "_roof_closure_" + side,
                                F._new_mesh("V14_roof_closure", surface.vertices, surface.faces, mats[scheme["wall"]]), building, "roof_closure_wall"), "roof_closure_wall")
            H._fixed_roof_surface(obj, cache)
            obj["wall_side"], obj["roof_contact_object"] = side, roof_obj.name
            obj["roof_tier_index"],obj["closure_bottom_z_m"] = roof["tier_index"],closure_bottom
            obj["roof_contact_points_local"] = json.dumps(contact_records)
            obj["scope"] = "generated skin junction only; actual concealed end-wall structure unknown"
        beam_top = d["column_top_z_m"] + d["beam_height_m"] if roof["tier_index"]==0 else band["bottom_z_m"]
        radius = min(d["column_radius_m"], d["beam_width_m"] * .45)
        if roof["roof_type"] in ("yingshan", "juanpeng_yingshan"):
            # End supports move inward by their radius to remain under a skin
            # with no gable projection. Their full bottom circle must still fit
            # the original side beam: 2r <= half beam width.
            radius = min(radius, d["beam_width_m"] * .24)
        bearing_grid = grid if roof["tier_index"]==0 else upper_grid
        for i, (x, y) in enumerate(sorted(bearing_grid)):
            bottom_ring, top_ring = [], []
            for j in range(16):
                dx, dy = radius * math.cos(j * math.pi / 8), radius * math.sin(j * math.pi / 8)
                # Hard gable skin ends on body axes; inset its end support footprint.
                cx = min(max(x, -roof["outer_width_m"] / 2 + radius), roof["outer_width_m"] / 2 - radius)
                px, py = cx + dx, y + dy
                bottom_ring.append((px, py, beam_top))
                top_ring.append((px, py, contact_z(px, py, beam_top)))
            surface = F._Surface()
            surface.face(list(reversed(bottom_ring)))
            surface.face(top_ring)
            for j in range(16):
                surface.face([bottom_ring[j], bottom_ring[(j + 1) % 16], top_ring[(j + 1) % 16], top_ring[j]])
            obj = add(F._object("V14_" + ident + "_bearing_" + str(i),
                                F._new_mesh("V14_bearing", surface.vertices, surface.faces, mats[scheme["column"]]), building, "roof_bearing_post"), "roof_bearing_post")
            H._fixed_roof_surface(obj, cache)
            obj["roof_contact_object"], obj["roof_contact_points_local"] = roof_obj.name, json.dumps(top_ring)
            obj["support_bottom_z_m"], obj["contact_scope"] = beam_top, "generated skin vertex contacts, not measured dougong or physical tile cavity"
            obj["roof_tier_index"] = roof["tier_index"]
        roofs.append({"tier_index": roof["tier_index"], "roof_type": roof["roof_type"], "annular": roof["annular"],
                      "roof_object": roof_obj.name, "objects": [o.name for o in parts],
                      "target_group_peak_z_m": roof["top_z_m"], "actual_eave_z_m": roof_obj["eave_level_model_m"],
                      "surface_triangulation": roof_obj["surface_triangulation"],
                      "surface_scope": "mathematical closed skin; not measured physical tile underside",
                      "inner_rim_upper_band_connections":inner_connections,
                      "hard_gable_coplanar_boundary_queries": boundary_queries})
    bpy.context.view_layer.update()
    for opening in openings:
        opening["center_world"] = list(root.matrix_world @ Vector(opening["center_local"]))
        opening["normal_world"] = list(root.matrix_world.to_3x3() @ Vector(opening["normal_local"]))
    assumptions = ["Dimensions and facade locations are study controls except explicitly separated published column references; unknowns remain null. Explicit nonuniform spans are not rescaled.",
                   "Independent Exact Booleans cut all scheduled wall apertures before surrounds; unknown leaf counts use explicitly unresolved set proxies.",
                   "Front verandas have recessed walls and open exterior column bays, not opaque column infill.",
                   "Roof surfaces, closure walls and bearing contacts describe generated mathematical skins; physical tile cavity, joinery and precise lattice are unbuilt.",
                   "Caller-owned fixed roof triangulation preserves all vertex positions; material cache includes the full material triple.",
                   "Source reference slab follows the entire supplied polygon including holes; it does not certify a historic platform or occupied floor."]
    if band:
        assumptions.append("Lower exterior enclosure closes only to the annular lower eave. The narrower upper band has separate inner columns/beams, continuous four-sided walls to its full roof, and no occupied floor.")
    for key, value in (("building_id", ident), ("restoration_v14_building_id", ident), ("profile_sha256", profile_sha),
                       ("third_party_cost", 0), ("human_approval", "pending"), ("complete_reconstruction_proven", False)):
        root[key] = value
    root["openings"], root["assumptions"], root["unbuilt_features"] = json.dumps(openings, ensure_ascii=False), json.dumps(assumptions), json.dumps(p["unbuilt"], ensure_ascii=False)
    manifest = {"building_id": ident, "root": root.name, "objects": [o.name for o in objects], "roofs": roofs,
                "reference_floor": slab.name, "occupied_storeys": None, "reference_floor_count": 1,
                "reference_support_id":p.get("reference_support_id"),"support_owned_by_building":shared_support_object is None,
                "interior_complete": False, "complete_reconstruction_proven": False, "profile_sha256": profile_sha,
                "third_party_cost": 0, "human_approval": "pending"}
    return {"root": root, "collection": building, "objects": objects, "components": components,
            "reference_floor":slab,
            "walls": walls, "openings": openings, "opening_records": openings, "roofs": roofs,
            "assumptions": assumptions, "unbuilt_features": p["unbuilt"], "verified_facts": p["known_facts"],
            "profile": p, "manifest": manifest}
