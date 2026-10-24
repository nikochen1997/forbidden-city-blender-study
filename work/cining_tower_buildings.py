"""Source-qualified two-storey Cining towers. Caller owns all I/O and saving.

No interior upper slab is built. Local -Y is front and +X is frontage; dimensions
and opening positions are explicit study controls, not current measured values.
"""
import hashlib
import json
import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import forbidden_city_geometry as F
import restoration_buildings as R


SIDES = ("south", "north", "east", "west")
NORMALS = {"south": (0, -1, 0), "north": (0, 1, 0), "east": (1, 0, 0), "west": (-1, 0, 0)}
TOWERS = {"baoxianglou": 7, "jiyunlou_cininggarden": 7, "ciyinlou": 5}


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite tower parameter")
    if isinstance(value, dict):
        for item in value.values(): _finite(item)
    elif isinstance(value, (list, tuple)):
        for item in value: _finite(item)


def _fact(p, key):
    value = p["known_facts"].get(key)
    return value.get("value") if isinstance(value, dict) else value


def _grid(p, axis):
    count = p["bays_x"] if axis == "x" else p["study_bays_y"]
    span = p["dimensions"]["body_width_m" if axis == "x" else "body_depth_m"]
    widths = p.get("column_bay_widths_" + axis + "_m")
    if widths is None:
        return [-span / 2 + span * i / count for i in range(count + 1)]
    if len(widths) != count or any(type(x) not in (int, float) or x <= 0 for x in widths) or abs(sum(widths)-span) > 1e-7:
        raise ValueError("explicit tower column spans invalid")
    result = [-span/2]
    for width in widths: result.append(result[-1]+width)
    return result


def _perimeter(xs, ys):
    return {(x, y) for x in xs for y in (ys[0], ys[-1])} | {(x, y) for x in (xs[0], xs[-1]) for y in ys[1:-1]}


def _outside_area(polygon, source_triangles):
    if F._ring_area(polygon) < 0: polygon = list(reversed(polygon))
    area = 0
    for triangle in source_triangles:
        clipped = list(triangle)
        for a, b in zip(polygon, polygon[1:]+polygon[:1]):
            dx, dy = b[0]-a[0], b[1]-a[1]
            clipped = F._clip_halfplane(clipped, (-dy, dx, dy*a[0]-dx*a[1]))
            if not clipped: break
        if len(clipped) >= 3: area += abs(F._ring_area(clipped))
    return max(0, abs(F._ring_area(polygon))-area)


def _fixed_surface(obj, cache):
    raw = obj.data
    key = ("V16_tower_fixed", raw.as_pointer())
    if key in cache:
        obj.data = cache[key]
    else:
        fixed = raw.copy()
        before = sorted(tuple(v.co) for v in fixed.vertices)
        mesh = bmesh.new(); mesh.from_mesh(fixed)
        bmesh.ops.triangulate(mesh, faces=list(mesh.faces), quad_method="FIXED", ngon_method="EAR_CLIP")
        mesh.to_mesh(fixed); mesh.free(); fixed.update()
        if sorted(tuple(v.co) for v in fixed.vertices) != before:
            raise ValueError("tower triangulation moved vertices")
        obj.data = fixed; cache[key] = fixed
    obj["surface_triangulation"] = "FIXED quads / EAR_CLIP ngons on caller-owned copy"
    obj["triangulation_vertex_displacement_m"] = 0.0


def _wall_specs(p):
    d = p["dimensions"]
    xl, xh, yl, yh = [d["enclosure_"+k+"_m"] for k in ("x_min", "x_max", "y_min", "y_max")]
    levels = ((d["floor_z_m"], d["level_break_z_m"]), (d["level_break_z_m"], d["wall_top_z_m"]))
    out = {}
    for level, (bottom, top) in enumerate(levels):
        for side in SIDES:
            axis = "Y" if side in ("south", "north") else "X"
            constant = {"south": yl, "north": yh, "west": xl, "east": xh}[side]
            a, b = (xl, xh) if axis == "Y" else (yl, yh)
            ident = "s"+str(level)+"_"+side
            out[ident] = {"id": ident, "storey_index": level, "normal_axis": axis, "constant_m": constant,
                          "min_along_m": a, "max_along_m": b, "bottom_z_m": bottom,
                          "top_z_m": top, "wall_side": side, "boundary_kind": "exterior"}
    for row in p["partitions"]:
        if row["id"] in out: raise ValueError("duplicate wall identifier")
        bottom, top = levels[row["storey_index"]]
        out[row["id"]] = dict(row, bottom_z_m=bottom, top_z_m=top, wall_side=row["id"], boundary_kind="interior_partition")
    return out


def _validate(p):
    _finite(p)
    for key in ("building_id", "name_zh", "source_part_id", "anchor", "rotation_z_rad", "source_polygon_local", "source_polygon_world", "source_holes_local", "source_holes_world", "bays_x", "bays_y", "study_bays_y", "occupied_storeys", "reference_floor_count", "dimensions", "roof", "material_scheme", "partitions", "openings", "known_facts", "parameter_evidence", "unbuilt"):
        if key not in p: raise ValueError("missing explicit tower parameter "+key)
    ident = p["building_id"]
    if ident not in TOWERS or p["bays_x"] != TOWERS[ident] or type(p["bays_x"]) is not int:
        raise ValueError("tower identity/frontage count differs from source")
    for key in ("third_party_cost", "paid_service_calls"):
        if type(p.get(key)) is not int or p[key] != 0: raise ValueError("tower budget must be integer zero")
    if type(p["occupied_storeys"]) is not int or p["occupied_storeys"] != 2 or p["reference_floor_count"] != 1:
        raise ValueError("documented two storeys require one ground reference slab and no upper slab")
    if p["bays_y"] is not None or type(p["study_bays_y"]) is not int or not 1 <= p["study_bays_y"] <= 12:
        raise ValueError("tower depth count is unmeasured, explicit study count required")
    if _fact(p, "floor_stories") != 2 or _fact(p, "roof_type") != "juanpeng_xieshan":
        raise ValueError("documented tower storeys/roof category missing")
    if p["material_scheme"]["roof_main"] != "green" or p["material_scheme"]["roof_edge"] != "yellow":
        raise ValueError("tower requires documented green main/yellow trim categories")
    F._point("anchor", p["anchor"]); F._number("rotation", p["rotation_z_rad"])
    for key, item in p["known_facts"].items():
        if key.endswith("_current_measurement") or key == "elevation_common_datum":
            if (item.get("value") if isinstance(item, dict) else item) is not None:
                raise ValueError("current tower survey value invented")
    rings = [F._clean_ring(p["source_polygon_local"])] + [F._clean_ring(r) for r in p["source_holes_local"]]
    triangles = F._triangulate_rings(rings)
    if len(p["source_polygon_world"]) != len(p["source_polygon_local"]) or len(p["source_holes_world"]) != len(p["source_holes_local"]):
        raise ValueError("tower local/world source ring counts differ")
    c, s = math.cos(p["rotation_z_rad"]), math.sin(p["rotation_z_rad"])
    for local, world in zip([p["source_polygon_local"]]+p["source_holes_local"], [p["source_polygon_world"]]+p["source_holes_world"]):
        if len(local) != len(world): raise ValueError("tower source hole vertices differ")
        for (x, y), (wx, wy) in zip(local, world):
            if math.hypot(p["anchor"][0]+c*x-s*y-wx, p["anchor"][1]+s*x+c*y-wy) > 1e-4:
                raise ValueError("tower source frame mismatch")
    d = p["dimensions"]
    for key in ("body_width_m", "body_depth_m", "column_radius_m", "column_base_radius_m", "column_base_height_m", "beam_width_m", "beam_height_m", "wall_thickness_m", "opening_frame_width_m", "opening_frame_depth_m", "leaf_panel_depth_m"):
        F._number(key, d[key], strictly_positive=True)
    for key in ("source_reference_slab_bottom_z_m", "floor_z_m", "level_break_z_m", "wall_top_z_m", "enclosure_x_min_m", "enclosure_x_max_m", "enclosure_y_min_m", "enclosure_y_max_m"):
        F._number(key, d[key])
    if not d["source_reference_slab_bottom_z_m"] < d["floor_z_m"] < d["floor_z_m"]+d["column_base_height_m"] < d["level_break_z_m"]-d["beam_height_m"] < d["level_break_z_m"] < d["wall_top_z_m"]-d["beam_height_m"] < d["wall_top_z_m"]:
        raise ValueError("tower two-storey support height order invalid")
    if d["beam_width_m"] < 2*d["column_radius_m"] or d["column_base_radius_m"] < d["column_radius_m"]:
        raise ValueError("complete upper column rim cannot fit beam/base")
    for axis, span in (("x", d["body_width_m"]), ("y", d["body_depth_m"])):
        lo, hi = d["enclosure_"+axis+"_min_m"], d["enclosure_"+axis+"_max_m"]
        if not -span/2 <= lo < hi <= span/2: raise ValueError("tower enclosure outside column body")
    grid = _perimeter(_grid(p, "x"), _grid(p, "y"))
    for x, y in grid:
        polygon = [(x+d["column_base_radius_m"]*math.cos(i*math.pi/8), y+d["column_base_radius_m"]*math.sin(i*math.pi/8)) for i in range(16)]
        if _outside_area(polygon, triangles) > 1e-7: raise ValueError("complete base footprint outside source polygon/hole")
    roof = p["roof"]
    for key in ("outer_width_m", "outer_depth_m", "eave_z_m", "top_z_m", "corner_lift_m"): F._number(key, roof[key])
    if roof["roof_type"] != "juanpeng_xieshan" or roof["corner_lift_m"] != 0 or roof["eave_z_m"] <= d["wall_top_z_m"]+.2 or roof["top_z_m"] <= roof["eave_z_m"]+.25:
        raise ValueError("tower rounded roof category/height invalid")
    radius = min(d["column_radius_m"], d["beam_width_m"]*.45)
    if roof["outer_width_m"] < d["body_width_m"]+2*radius or roof["outer_depth_m"] < d["body_depth_m"]+2*radius:
        raise ValueError("roof cannot cover complete bearing rims")
    for row in p["partitions"]:
        if row["storey_index"] not in (0, 1) or row["normal_axis"] not in ("X", "Y") or row["min_along_m"] >= row["max_along_m"]:
            raise ValueError("invalid explicit interior partition")
    walls = _wall_specs(p); seen = set()
    for row in p["openings"]:
        if row["id"] in seen or row["wall_id"] not in walls or row["kind"] not in ("door", "window", "passage"):
            raise ValueError("invalid/duplicate tower opening identity")
        seen.add(row["id"]); wall = walls[row["wall_id"]]
        for key in ("width_m", "height_m"): F._number(key, row[key], strictly_positive=True)
        for key in ("center_along_m", "bottom_z_m"): F._number(key, row[key])
        if row["center_along_m"]-row["width_m"]/2 <= wall["min_along_m"] or row["center_along_m"]+row["width_m"]/2 >= wall["max_along_m"] or row["bottom_z_m"] < wall["bottom_z_m"]-1e-8 or row["bottom_z_m"]+row["height_m"] >= wall["top_z_m"]:
            raise ValueError("opening outside its actual storey wall")
        if row["dimension_status"] != "unmeasured_study" or not row["category_scope"]: raise ValueError("opening evidence boundary absent")
        count = row["leaf_count"]
        if count is not None and (type(count) is not int or not 1 <= count <= 16): raise ValueError("invalid leaf reference count")
    return rings, grid, walls


def build_tower(profile, collection, materials=None, mesh_cache=None):
    p = profile; rings, grid, specs = _validate(p); d = p["dimensions"]; ident = p["building_id"]
    cache = {} if mesh_cache is None else mesh_cache
    mats = F.create_materials("R16_TOWER_") if materials is None else dict(materials)
    scheme = p["material_scheme"]
    for key in ("base", "column", "beam", "wall", "frame", "infill", "roof_main", "roof_edge", "roof_under"):
        if scheme[key] not in mats: raise ValueError("caller tower material missing "+scheme[key])
    building = F.ensure_collection("V16_"+ident, collection)
    root = bpy.data.objects.new("V16_"+ident+"_root", None); building.objects.link(root)
    root.location, root.rotation_euler.z = p["anchor"], p["rotation_z_rad"]
    profile_sha = hashlib.sha256(json.dumps(p, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
    objects, components, openings, walls = [], {}, [], {}

    def add(obj, role, storey=None):
        obj.parent = root; obj["semantic_role"], obj["building_id"] = role, ident
        obj["restoration_v16_building_id"], obj["source_reference_part_id"] = ident, p["source_part_id"]
        obj["profile_sha256"], obj["third_party_cost"], obj["human_approval"] = profile_sha, 0, "pending"
        obj["absolute_accuracy_claim"] = False
        if storey is not None: obj["storey_index"] = storey
        objects.append(obj); components.setdefault(role, []).append(obj); return obj

    def box(label, center, dimensions, material, role, storey=None, cached=True):
        return add(F.box("V16_"+ident+"_"+label, center, dimensions, mats[scheme[material]], building, cache if cached else None, role), role, storey)

    top = F._Surface()
    for triangle in F._triangulate_rings(rings): top.face([(x, y, d["floor_z_m"]) for x, y in triangle])
    F._volume_from_top(top, d["source_reference_slab_bottom_z_m"])
    slab = add(F._object("V16_"+ident+"_source_reference_slab", F._new_mesh("V16_tower_source_slab", top.vertices, top.faces, mats[scheme["base"]]), building, "source_reference_slab"), "source_reference_slab", 0)
    slab["reference_floor_only"], slab["not_measured_platform"] = True, True
    w, depth, bw, bh = d["body_width_m"], d["body_depth_m"], d["beam_width_m"], d["beam_height_m"]
    beams = {}
    for level, beam_top in enumerate((d["level_break_z_m"], d["wall_top_z_m"])):
        for side, x, y, ww, dd in (("south", 0, -depth/2, w+bw, bw), ("north", 0, depth/2, w+bw, bw), ("west", -w/2, 0, bw, depth+bw), ("east", w/2, 0, bw, depth+bw)):
            obj = box("s"+str(level)+"_beam_"+side, (x, y, beam_top-bh/2), (ww, dd, bh), "beam", "beam", level)
            obj["wall_side"], obj["beam_top_z_m"] = side, beam_top; beams[(level, side)] = obj
    for index, (x, y) in enumerate(sorted(grid)):
        base = add(F.column("V16_"+ident+"_base_"+str(index), (x, y, d["floor_z_m"]+d["column_base_height_m"]/2), d["column_base_radius_m"], d["column_base_height_m"], mats[scheme["base"]], building, cache), "column_base", 0)
        base["support_object"] = slab.name
        for level, bottom, top_z in ((0, d["floor_z_m"]+d["column_base_height_m"], d["level_break_z_m"]-bh), (1, d["level_break_z_m"], d["wall_top_z_m"]-bh)):
            t = d["wall_thickness_m"]; xl, xh, yl, yh = [d["enclosure_"+k+"_m"] for k in ("x_min", "x_max", "y_min", "y_max")]
            attached = ((abs(y-yl) <= t/2+1e-6 or abs(y-yh) <= t/2+1e-6) and xl-t/2 <= x <= xh+t/2 or (abs(x-xl) <= t/2+1e-6 or abs(x-xh) <= t/2+1e-6) and yl-t/2 <= y <= yh+t/2)
            role = "pilaster" if attached else "column"
            obj = add(F.column("V16_"+ident+"_s"+str(level)+"_column_"+str(index), (x, y, (bottom+top_z)/2), d["column_radius_m"], top_z-bottom, mats[scheme["column"]], building, cache), role, level)
            side = "south" if abs(y+depth/2) < 1e-6 else "north" if abs(y-depth/2) < 1e-6 else "west" if x < 0 else "east"
            obj["support_object"] = base.name if level == 0 else beams[(0, side)].name
            obj["top_support_object"], obj["study_column_axis"], obj["wall_attached_reference"] = beams[(level, side)].name, [x, y], attached
    for wall_id, spec in specs.items():
        axis_y = spec["normal_axis"] == "Y"; mid = (spec["min_along_m"]+spec["max_along_m"])/2; z = (spec["bottom_z_m"]+spec["top_z_m"])/2; t = d["wall_thickness_m"]
        center = (mid, spec["constant_m"], z) if axis_y else (spec["constant_m"], mid, z)
        dimensions = (spec["max_along_m"]-spec["min_along_m"]+t, t, spec["top_z_m"]-spec["bottom_z_m"]) if axis_y else (t, spec["max_along_m"]-spec["min_along_m"]+t, spec["top_z_m"]-spec["bottom_z_m"])
        obj = box(wall_id, center, dimensions, "wall", "wall", spec["storey_index"], False)
        obj["wall_id"], obj["wall_side"], obj["boundary_kind"], obj["wall_thickness_m"] = wall_id, spec["wall_side"], spec["boundary_kind"], t
        walls[wall_id] = obj
    for row in p["openings"]:
        spec = specs[row["wall_id"]]; axis_y = spec["normal_axis"] == "Y"; z = row["bottom_z_m"]+row["height_m"]/2
        center = (row["center_along_m"], spec["constant_m"], z) if axis_y else (spec["constant_m"], row["center_along_m"], z)
        # A floor-level cutter must cross the lower wall face. Coplanar float32
        # bottom faces left two zero-area ears in the actual Ciyin partition.
        extension = .02 if row["kind"] in ("door", "passage") and abs(row["bottom_z_m"]-spec["bottom_z_m"]) < 1e-7 else 0
        cutter_center = (center[0], center[1], center[2]-extension/2)
        before_meshes = {m.as_pointer() for m in bpy.data.meshes}
        record = F.cut_opening(walls[row["wall_id"]], {"id": row["id"], "type": "window" if row["kind"] == "window" else "door", "destination": "unmeasured_study_interior" if row["kind"] != "passage" else "documented_passage_with_unbuilt_interior_floor_details", "center": cutter_center, "width": row["width_m"], "height": row["height_m"]+extension, "depth": d["wall_thickness_m"]+.5, "normal_axis": spec["normal_axis"], "cutter_bottom_extension_m": extension, "semantic_bottom_z_m": row["bottom_z_m"], "semantic_top_z_m": row["bottom_z_m"]+row["height_m"]}, building)
        record["cutter_center_local"], record["cutter_height_m"] = list(cutter_center), row["height_m"]+extension
        for mesh in list(bpy.data.meshes):
            if mesh.as_pointer() not in before_meshes and mesh.users == 0: bpy.data.meshes.remove(mesh)
        frames, leaves, proxies = [], [], []; fw, fd = d["opening_frame_width_m"], d["opening_frame_depth_m"]
        across = Vector((1, 0, 0) if axis_y else (0, 1, 0))
        for sign in (-1, 1):
            point = Vector(center)+across*sign*(row["width_m"]+fw)/2
            dims = (fw, fd, row["height_m"]) if axis_y else (fd, fw, row["height_m"])
            frames.append(box(row["id"]+"_jamb", point, dims, "frame", "opening_frame", spec["storey_index"]).name)
        point = Vector(center)+Vector((0, 0, (row["height_m"]+fw)/2)); dims = (row["width_m"], fd, fw) if axis_y else (fd, row["width_m"], fw)
        frames.append(box(row["id"]+"_head", point, dims, "frame", "opening_frame", spec["storey_index"]).name)
        if row["kind"] == "window":
            frames.append(box(row["id"]+"_sill", Vector(center)-Vector((0, 0, (row["height_m"]+fw)/2)), dims, "frame", "opening_frame", spec["storey_index"]).name)
        if row["kind"] != "passage":
            count = row["leaf_count"]
            for j in range(count or 1):
                width = row["width_m"]/(count or 1); point = Vector(center)+across*(-row["width_m"]/2+width*(j+.5))
                dims = (width*.985, d["leaf_panel_depth_m"], row["height_m"]*.99) if axis_y else (d["leaf_panel_depth_m"], width*.985, row["height_m"]*.99)
                role = row["kind"]+"_leaf" if count else row["kind"]+"_set_infill_proxy"
                obj = box(row["id"]+"_panel_"+str(j), point, dims, "infill", role, spec["storey_index"])
                obj["opening_id"], obj["not_actual_leaf_count"] = row["id"], count is None
                obj["pattern_category"], obj["pattern_geometry"] = row["pattern_category"] or "unresolved", "unresolved_panel_reference; precise lattice and joinery unbuilt"
                if count: obj["leaf_index"], obj["leaf_count"] = j, count; leaves.append(obj.name)
                else: proxies.append(obj.name)
        normal = NORMALS.get(spec["wall_side"], (1, 0, 0) if not axis_y else (0, 1, 0))
        record.update({"kind": row["kind"], "wall_id": row["wall_id"], "wall_side": spec["wall_side"], "storey_index": spec["storey_index"], "center_local": list(center), "normal_local": list(normal), "clear_width_m": row["width_m"], "clear_height_m": row["height_m"], "bottom_z_m": row["bottom_z_m"], "leaf_count": row["leaf_count"], "leaf_reference_names": leaves, "infill_proxy_names": proxies, "frame_names": frames, "dimension_status": row["dimension_status"], "category_scope": row["category_scope"], "pattern_category": row["pattern_category"], "opening_method": "Independent Exact Boolean applied before surround"})
        openings.append(record)
    roof = p["roof"]; roof_cache = cache.setdefault(("V16_tower_roof_materials", *(mats[scheme[k]].name for k in ("roof_main", "roof_edge", "roof_under"))), {})
    parts = R._roof_geometry("V16_"+ident+"_roof", roof["outer_width_m"], roof["outer_depth_m"], roof["eave_z_m"], roof["top_z_m"], "juanpeng_xieshan", *(mats[scheme[k]] for k in ("roof_main", "roof_edge", "roof_under")), building, roof_cache, 0, 0, 0)
    for obj in parts:
        _fixed_surface(obj, cache); add(obj, obj.get("semantic_role", "roof"), 1); obj["roof_tier_index"] = 0
    roof_obj = parts[0]
    tree = BVHTree.FromPolygons([v.co for v in roof_obj.data.vertices], [tuple(f.vertices) for f in roof_obj.data.polygons])

    def contact_z(x, y):
        hit = tree.ray_cast(Vector((x, y, d["wall_top_z_m"]+1e-5)), Vector((0, 0, 1)), 100)[0]
        if hit is None or hit.z <= d["wall_top_z_m"]+1e-4: raise ValueError("tower support misses actual roof underside")
        return hit.z

    radius = min(d["column_radius_m"], bw*.45)
    for i, (x, y) in enumerate(sorted(grid)):
        bottom = [(x+radius*math.cos(j*math.pi/8), y+radius*math.sin(j*math.pi/8), d["wall_top_z_m"]) for j in range(16)]
        upper = [(a, b, contact_z(a, b)) for a, b, z in bottom]; surface = F._Surface()
        surface.face(list(reversed(bottom))); surface.face(upper)
        for j in range(16): surface.face([bottom[j], bottom[(j+1)%16], upper[(j+1)%16], upper[j]])
        obj = add(F._object("V16_"+ident+"_bearing_"+str(i), F._new_mesh("V16_tower_bearing", surface.vertices, surface.faces, mats[scheme["column"]]), building, "roof_bearing_post"), "roof_bearing_post", 1)
        _fixed_surface(obj, cache)
        obj["roof_contact_object"], obj["roof_contact_points_local"], obj["support_bottom_z_m"] = roof_obj.name, json.dumps(upper), d["wall_top_z_m"]
    for side in SIDES:
        spec = specs["s1_"+side]; axis_y = spec["normal_axis"] == "Y"; t = d["wall_thickness_m"]; surface = F._Surface(); rows = []; contacts = []
        for sign in (-1, 1):
            bottom, upper = [], []
            for i in range(41):
                station = spec["min_along_m"]-t/2+(spec["max_along_m"]-spec["min_along_m"]+t)*i/40
                x, y = (station, spec["constant_m"]+sign*t/2) if axis_y else (spec["constant_m"]+sign*t/2, station)
                bottom.append((x, y, d["wall_top_z_m"])); upper.append((x, y, contact_z(x, y)))
            for i in range(40): surface.face([bottom[i], bottom[i+1], upper[i+1], upper[i]])
            rows.append((bottom, upper)); contacts.extend(upper)
        for i in range(40):
            for row in (0, 1): surface.face([rows[0][row][i], rows[0][row][i+1], rows[1][row][i+1], rows[1][row][i]])
        for i in (0, 40): surface.face([rows[0][0][i], rows[1][0][i], rows[1][1][i], rows[0][1][i]])
        obj = add(F._object("V16_"+ident+"_roof_closure_"+side, F._new_mesh("V16_tower_closure", surface.vertices, surface.faces, mats[scheme["wall"]]), building, "roof_closure_wall"), "roof_closure_wall", 1)
        _fixed_surface(obj, cache)
        obj["wall_side"], obj["roof_contact_object"], obj["roof_contact_points_local"] = side, roof_obj.name, json.dumps(contacts)
        obj["closure_bottom_z_m"] = d["wall_top_z_m"]
    bpy.context.view_layer.update()
    for opening in openings:
        opening["center_world"] = list(root.matrix_world@Vector(opening["center_local"]))
        opening["normal_world"] = list(root.matrix_world.to_3x3()@Vector(opening["normal_local"]))
    assumptions = ["Two occupied storeys are directly documented; individual storey heights and column spans are unmeasured study controls.", "Only full source-shaped ground reference slab is built; no upper slab, interior floor plates or stairs. Bao six vertical rooms remain unobstructed.", "All scheduled apertures are independent Exact Boolean cuts before surrounds. Unknown leaf counts use unresolved set proxies.", "One rounded green/yellow top roof is a category study, not evidence of measured eaves count, physical tile cavity, exact historic joinery or complete interior."]
    unbuilt = list(p["unbuilt"])+["Interior upper floor plates, precise six lightwell sizes and stairs", "Precise lattice, measured storey elevations and physical roof cavity"]
    for key, value in (("building_id", ident), ("restoration_v16_building_id", ident), ("profile_sha256", profile_sha), ("third_party_cost", 0), ("human_approval", "pending"), ("absolute_accuracy_claim", False), ("occupied_storeys", 2), ("upper_floor_slab_created", False)):
        root[key] = value
    root["tower_study_profile"], root["openings"], root["unbuilt_features"] = json.dumps(p, ensure_ascii=False), json.dumps(openings, ensure_ascii=False), json.dumps(unbuilt, ensure_ascii=False)
    roofs = [{"tier_index": 0, "roof_type": "juanpeng_xieshan", "roof_object": roof_obj.name, "objects": [o.name for o in parts], "target_group_peak_z_m": roof["top_z_m"], "surface_triangulation": roof_obj["surface_triangulation"], "surface_scope": "mathematical closed skin, not measured physical tile underside"}]
    manifest = {"building_id": ident, "root": root.name, "objects": [o.name for o in objects], "reference_floor": slab.name, "occupied_storeys": 2, "reference_floor_count": 1, "upper_floor_slab_created": False, "interior_complete": False, "complete_reconstruction_proven": False, "profile_sha256": profile_sha, "third_party_cost": 0, "human_approval": "pending"}
    return {"root": root, "collection": building, "objects": objects, "components": components, "walls": walls, "reference_floor": slab, "openings": openings, "opening_records": openings, "roofs": roofs, "profile": p, "assumptions": assumptions, "unbuilt_features": unbuilt, "verified_facts": p["known_facts"], "manifest": manifest}
