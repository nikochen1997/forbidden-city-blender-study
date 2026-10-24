"""Explicit four-hall exterior studies. Caller owns saving and source visibility."""
import hashlib
import json
import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import forbidden_city_geometry as F
import restoration_buildings as R


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite profile value")
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _finite(item)


def _aperture_pattern(profile, row, kind):
    if kind == "upper_transom":
        return profile["known_facts"]["front_door_upper_transom"]
    return row["pattern_category"]


def _fixed_roof_surface(obj, cache):
    raw = obj.data
    fixed = raw.copy()
    mesh = bmesh.new()
    mesh.from_mesh(fixed)
    bmesh.ops.triangulate(mesh, faces=list(mesh.faces), quad_method="FIXED", ngon_method="EAR_CLIP")
    mesh.to_mesh(fixed)
    mesh.free()
    fixed.update()
    key = ("V9_fixed_roof_surface", raw.as_pointer())
    if key in cache:
        obj.data = cache[key]
        bpy.data.meshes.remove(fixed)
    else:
        obj.data = fixed
        cache[key] = fixed
    obj["surface_triangulation"] = "FIXED quads / EAR_CLIP ngons on caller-owned copy"
    obj["triangulation_vertex_displacement_m"] = 0.0


def _validate(p):
    _finite(p)
    for key in ("building_id", "name_zh", "source_part_id", "anchor", "rotation_z_rad", "source_polygon_local",
                "source_polygon_world", "source_holes_local", "dimensions", "roof_tiers", "facades", "material_scheme",
                "known_facts", "parameter_evidence", "unbuilt"):
        if key not in p:
            raise ValueError("missing explicit hall parameter " + key)
    for key in ("third_party_cost", "paid_service_calls"):
        if type(p.get(key)) is not int or p[key] != 0:
            raise ValueError(key + " must be integer zero")
    F._point("anchor", p["anchor"])
    F._number("rotation", p["rotation_z_rad"])
    if p["occupied_storeys"] is not None or type(p["reference_floor_count"]) is not int or p["reference_floor_count"] != 1:
        raise ValueError("one reference floor cannot certify occupied storeys")
    if type(p["bays_x"]) is not int or not 1 <= p["bays_x"] <= 30:
        raise ValueError("invalid front bay count")
    if p["bays_y"] is not None and (type(p["bays_y"]) is not int or not 1 <= p["bays_y"] <= 30):
        raise ValueError("invalid depth bay count")
    rings = [F._clean_ring(p["source_polygon_local"])] + [F._clean_ring(r) for r in p["source_holes_local"]]
    F._triangulate_rings(rings)
    if len(p["source_polygon_world"]) != len(p["source_polygon_local"]):
        raise ValueError("source ring vertex count differs")
    c, s = math.cos(p["rotation_z_rad"]), math.sin(p["rotation_z_rad"])
    for local, world in zip(p["source_polygon_local"], p["source_polygon_world"]):
        actual = (p["anchor"][0] + c * local[0] - s * local[1], p["anchor"][1] + s * local[0] + c * local[1])
        if math.dist(actual, world) > 1e-4:
            raise ValueError("source local/world ring is not registered")
    d = p["dimensions"]
    for key, value in d.items():
        if key not in {"body_span_meaning", "upper_band"}:
            F._number(key, value)
    positive = ("body_width_m", "body_depth_m", "slab_thickness_m", "wall_thickness_m", "column_radius_m",
                "column_base_height_m", "column_base_radius_m", "beam_width_m", "beam_height_m",
                "door_height_m", "window_height_m", "opening_frame_width_m", "opening_frame_depth_m",
                "leaf_panel_depth_m", "lattice_bar_width_m", "upper_transom_height_m",
                "upper_transom_separation_m", "simplified_lattice_cell_m")
    for key in positive:
        F._number(key, d[key], strictly_positive=True)
    if not d["source_reference_slab_bottom_z_m"] < d["floor_z_m"] == d["source_reference_slab_top_z_m"] < d["column_top_z_m"] < d["wall_top_z_m"]:
        raise ValueError("invalid support and body height order")
    if abs(d["slab_thickness_m"] - d["floor_z_m"] + d["source_reference_slab_bottom_z_m"]) > 1e-8:
        raise ValueError("reference slab thickness mismatch")
    if d["floor_z_m"] + d["column_base_height_m"] >= d["column_top_z_m"]:
        raise ValueError("column base consumes column")
    if d["column_top_z_m"] + d["beam_height_m"] > d["wall_top_z_m"] + 1e-8:
        raise ValueError("beam above declared wall top")
    for axis, extent in (("x", d["body_width_m"]), ("y", d["body_depth_m"])):
        lo, hi = d["enclosure_" + axis + "_min_m"], d["enclosure_" + axis + "_max_m"]
        if not -extent / 2 - 1e-8 <= lo < hi <= extent / 2 + 1e-8 or hi - lo <= 2 * d["wall_thickness_m"]:
            raise ValueError("enclosure consumes reference grid")
    if type(p["eaves_tiers"]) is not int or p["eaves_tiers"] not in (1, 2) or len(p["roof_tiers"]) != p["eaves_tiers"]:
        raise ValueError("invalid roof tier count")
    for i, roof in enumerate(p["roof_tiers"]):
        for key in ("outer_width_m", "outer_depth_m", "eave_z_m", "top_z_m", "corner_lift_m", "additional_overhang_m"):
            F._number(key, roof[key])
        if roof["roof_type"] not in ("xieshan", "wudian") or roof["tier_index"] != i:
            raise ValueError("unsupported or unordered roof")
        if min(roof["outer_width_m"], roof["outer_depth_m"]) <= 0 or roof["top_z_m"] - roof["eave_z_m"] <= .25:
            raise ValueError("invalid roof dimensions")
        if not 0 <= roof["corner_lift_m"] < roof["top_z_m"] - roof["eave_z_m"] or roof["additional_overhang_m"] != 0:
            raise ValueError("invalid roof lift or duplicate overhang")
        if roof["annular"]:
            for axis in ("width", "depth"):
                inner = F._number("inner " + axis, roof["inner_" + axis + "_m"], strictly_positive=True)
                if inner >= roof["outer_" + axis + "_m"]:
                    raise ValueError("inner roof consumes outer")
        elif roof["inner_width_m"] is not None or roof["inner_depth_m"] is not None:
            raise ValueError("full roof cannot have annular dimensions")
    band = d["upper_band"]
    if (p["eaves_tiers"] == 2) != (band is not None):
        raise ValueError("upper band and roof tier mismatch")
    if band:
        for key, value in band.items():
            if key != "occupied_floor":
                F._number("upper band " + key, value, strictly_positive=True)
        if band["occupied_floor"] is not False or not band["bottom_z_m"] < band["top_z_m"] < p["roof_tiers"][1]["eave_z_m"]:
            raise ValueError("upper band is not an occupied floor")
    bay = (d["enclosure_x_max_m"] - d["enclosure_x_min_m"]) / p["bays_x"]
    for side in ("south", "north"):
        schedule = p["facades"][side]["schedule"]
        if [r["bay_index"] for r in schedule] != list(range(p["bays_x"])):
            raise ValueError("facade must explicitly cover each west-to-east bay")
        for row in schedule:
            if row["kind"] not in ("door", "window", "solid_wall", "unresolved_wall", "unresolved_sill_infill"):
                raise ValueError("unknown facade category")
            for key in ("leaf_count", "upper_transom_leaves"):
                if row[key] is not None and (type(row[key]) is not int or not 1 <= row[key] <= 32):
                    raise ValueError("unknown leaf counts must remain null")
            if row["upper_transom_leaves"] and not isinstance(_aperture_pattern(p, row, "upper_transom"), str):
                raise ValueError("upper transom category must be explicit in supplied facts")
            if row["kind"] in ("door", "window"):
                fraction = d[row["kind"] + "_width_fraction_of_bay"]
                F._number("opening fraction", fraction, strictly_positive=True)
                bottom = d["floor_z_m"] + (d["window_sill_height_above_floor_m"] if row["kind"] == "window" else 0)
                top = bottom + d[row["kind"] + "_height_m"]
                if row["upper_transom_leaves"]:
                    top += d["upper_transom_separation_m"] + d["upper_transom_height_m"]
                if not 0 < fraction < 1 or (1 - fraction) * bay <= d["opening_frame_width_m"] * 2 or top + d["opening_frame_width_m"] >= d["wall_top_z_m"]:
                    raise ValueError("opening or frame consumes bay/wall")
    for side in ("east", "west"):
        if p["facades"][side]["kind"] not in ("solid_wall", "unresolved_wall"):
            raise ValueError("side opening location must be explicitly known before modelling")


def build_hall(profile, collection, materials=None, mesh_cache=None):
    _validate(profile)
    p, d = profile, profile["dimensions"]
    mats = R.restoration_materials() if materials is None else dict(materials)
    if "stone" not in mats and "white_stone" in mats:
        mats["stone"] = mats["white_stone"]
    for value in p["material_scheme"].values():
        if value not in mats:
            raise ValueError("caller material missing " + value)
    scheme, cache = p["material_scheme"], {} if mesh_cache is None else mesh_cache
    ident = p["building_id"]
    building = F.ensure_collection("V9_" + ident, collection)
    root = bpy.data.objects.new("V9_" + ident + "_root", None)
    building.objects.link(root)
    root.location, root.rotation_euler.z = p["anchor"], p["rotation_z_rad"]
    profile_sha = hashlib.sha256(json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    root["hall_study_profile"] = json.dumps(p, ensure_ascii=False, allow_nan=False)
    root["building_id"] = ident
    root["restoration_v9_building_id"] = ident
    root["occupied_storeys_status"] = "unknown; source slab is one support reference only"
    objects, components, openings, roofs = [], {}, [], []

    def add(obj, role):
        obj.parent = root
        obj["semantic_role"] = role
        obj["building_id"] = ident
        obj["restoration_v9_building_id"] = ident
        obj["source_reference_part_id"] = p["source_part_id"]
        obj["profile_sha256"] = profile_sha
        obj["third_party_cost"] = 0
        obj["scope"] = "source-qualified unmeasured exterior study, not a complete current building"
        obj["storey_index"] = 0
        objects.append(obj)
        components.setdefault(role, []).append(obj)
        return obj

    def box(label, centre, dims, key, role):
        return add(F.box("V9_" + ident + "_" + label, centre, dims, mats[scheme[key]], building, cache, role), role)

    rings = [F._clean_ring(p["source_polygon_local"])] + [F._clean_ring(r) for r in p["source_holes_local"]]
    surface = F._Surface()
    for triangle in F._triangulate_rings(rings):
        surface.face([(x, y, d["floor_z_m"]) for x, y in triangle])
    F._volume_from_top(surface, d["source_reference_slab_bottom_z_m"])
    slab = add(F._object("V9_" + ident + "_source_reference_slab",
                        F._new_mesh("V9_source_slab", surface.vertices, surface.faces, mats[scheme["base"]]), building, "source_reference_slab"), "source_reference_slab")
    slab["reference_floor_only"] = True
    slab["not_measured_platform"] = True
    w, depth, floor = d["body_width_m"], d["body_depth_m"], d["floor_z_m"]
    xs = [-w / 2] + [-w / 2 + w * i / p["bays_x"] for i in range(1, p["bays_x"])] + [w / 2]
    grid = {(x, y): {side} for side, y in (("south", -depth / 2), ("north", depth / 2)) for x in xs}
    if p["bays_y"] is not None:
        for i in range(1, p["bays_y"]):
            for side, x in (("west", -w / 2), ("east", w / 2)):
                grid[(x, -depth / 2 + depth * i / p["bays_y"])] = {side}
    for i, ((x, y), sides) in enumerate(sorted(grid.items())):
        free = any(d[{"south": "veranda_front_depth_m", "north": "veranda_rear_depth_m", "east": "veranda_side_depth_m", "west": "veranda_side_depth_m"}[side]] > 0 for side in sides)
        role = "column" if free else "pilaster"
        base = add(F.column("V9_" + ident + "_base_" + str(i), (x, y, floor + d["column_base_height_m"] / 2),
                            d["column_base_radius_m"], d["column_base_height_m"], mats[scheme["base"]], building, cache), "column_base")
        bottom = floor + d["column_base_height_m"]
        obj = add(F.column("V9_" + ident + "_" + role + "_" + str(i), (x, y, (bottom + d["column_top_z_m"]) / 2),
                           d["column_radius_m"], d["column_top_z_m"] - bottom, mats[scheme["column"]], building, cache), role)
        obj["support_object"], base["support_object"] = base.name, slab.name
        obj["wall_attached_reference"] = not free
    for side, x, y, bw, bd in (("south", 0, -depth / 2, w, d["beam_width_m"]), ("north", 0, depth / 2, w, d["beam_width_m"]),
                                ("west", -w / 2, 0, d["beam_width_m"], depth), ("east", w / 2, 0, d["beam_width_m"], depth)):
        obj = box("beam_" + side, (x, y, d["column_top_z_m"] + d["beam_height_m"] / 2), (bw, bd, d["beam_height_m"]), "beam", "beam")
        obj["wall_side"] = side

    wall_by_side = {side: [] for side in ("south", "north", "east", "west")}
    lo, hi, thick = d["enclosure_x_min_m"], d["enclosure_x_max_m"], d["wall_thickness_m"]

    def wall_piece(side, bay, a, b, bottom, top, category):
        if b - a <= 1e-8 or top - bottom <= 1e-8:
            return
        y = d["enclosure_y_min_m"] if side == "south" else d["enclosure_y_max_m"]
        obj = box(side + "_wall_" + str(bay), ((a + b) / 2, y, (bottom + top) / 2), (b - a, thick, top - bottom), "wall", "wall_segment")
        obj["wall_side"], obj["bay_index"], obj["category"] = side, bay, category
        wall_by_side[side].append(obj)

    def infill(side, row, centre, width, height, kind, count, parent_id):
        cx, cy, cz = centre
        pattern = _aperture_pattern(p, row, kind)
        sign = -1 if side == "south" else 1
        references = []
        role = ("door_leaf" if kind == "door" else "window_leaf") if count else kind + "_set_infill_proxy"
        if kind == "upper_transom":
            role = "transom_leaf"
        divisions = count or 1
        for i in range(divisions):
            x = cx - width / 2 + width * (i + .5) / divisions
            material = "column" if pattern == "plain_board" else "infill"
            obj = box(side + "_" + role, (x, cy, cz), (width / divisions, d["leaf_panel_depth_m"], height), material, role)
            obj["opening_id"], obj["bay_index"], obj["wall_side"] = parent_id, row["bay_index"], side
            obj["leaf_count_status"] = "known_count_reference_geometry" if count else "unknown_not_one_actual_leaf"
            obj["not_actual_leaf_count"] = count is None
            if count:
                obj["leaf_index"], obj["leaf_count"] = i, count
            obj["pattern_category"] = pattern or "unresolved"
            obj["geometric_pattern_accuracy"] = "simplified_category_proxy_not_measured_joinery"
            references.append(obj.name)
        if pattern != "plain_board":
            n = max(2, math.ceil(width / d["simplified_lattice_cell_m"]))
            for i in range(1, n):
                x = cx - width / 2 + width * i / n
                obj = box(side + "_lattice_reference", (x, cy + sign * d["leaf_panel_depth_m"], cz),
                          (d["lattice_bar_width_m"], d["leaf_panel_depth_m"], height), "frame", "lattice_reference")
                obj["opening_id"] = parent_id
            if pattern != "vertical_diaoda":
                n = max(2, math.ceil(height / d["simplified_lattice_cell_m"]))
                for i in range(1, n):
                    obj = box(side + "_lattice_reference", (cx, cy + sign * d["leaf_panel_depth_m"], cz - height / 2 + height * i / n),
                              (width, d["leaf_panel_depth_m"], d["lattice_bar_width_m"]), "frame", "lattice_reference")
                    obj["opening_id"] = parent_id
        return references

    for side in ("south", "north"):
        y = d["enclosure_y_min_m"] if side == "south" else d["enclosure_y_max_m"]
        for row in p["facades"][side]["schedule"]:
            index, kind = row["bay_index"], row["kind"]
            a, b = lo + (hi - lo) * index / p["bays_x"], lo + (hi - lo) * (index + 1) / p["bays_x"]
            if kind not in ("door", "window"):
                if kind == "unresolved_sill_infill":
                    sill = floor + d["window_sill_height_above_floor_m"]
                    wall_piece(side, index, a, b, floor, sill, "known_sill_wall")
                    wall_piece(side, index, a, b, sill, d["wall_top_z_m"], "unresolved_upper_infill_reference")
                else:
                    wall_piece(side, index, a, b, floor, d["wall_top_z_m"], kind)
                continue
            width = (b - a) * d[kind + "_width_fraction_of_bay"]
            bottom = floor + (d["window_sill_height_above_floor_m"] if kind == "window" else 0)
            top = bottom + d[kind + "_height_m"]
            cx = (a + b) / 2
            wall_piece(side, index, a, cx - width / 2, floor, d["wall_top_z_m"], kind)
            wall_piece(side, index, cx + width / 2, b, floor, d["wall_top_z_m"], kind)
            wall_piece(side, index, cx - width / 2, cx + width / 2, floor, bottom, kind)
            holes = [(kind, bottom, top, row["leaf_count"])]
            if row["upper_transom_leaves"]:
                transom_bottom = top + d["upper_transom_separation_m"]
                wall_piece(side, index, cx - width / 2, cx + width / 2, top, transom_bottom, kind)
                holes.append(("upper_transom", transom_bottom, transom_bottom + d["upper_transom_height_m"], row["upper_transom_leaves"]))
            wall_piece(side, index, cx - width / 2, cx + width / 2, holes[-1][2], d["wall_top_z_m"], kind)
            for aperture, z0, z1, count in holes:
                opening_id = ident + "_" + side + "_" + str(index) + "_" + aperture
                centre = [cx, y, (z0 + z1) / 2]
                refs = infill(side, row, centre, width, z1 - z0, aperture, count, opening_id)
                for x in (cx - width / 2 - d["opening_frame_width_m"] / 2, cx + width / 2 + d["opening_frame_width_m"] / 2):
                    box("opening_jamb", (x, y, (z0 + z1) / 2), (d["opening_frame_width_m"], d["opening_frame_depth_m"], z1 - z0), "frame", "opening_frame")
                for z in (z0 - d["opening_frame_width_m"] / 2, z1 + d["opening_frame_width_m"] / 2):
                    box("opening_head_sill", (cx, y, z), (width, d["opening_frame_depth_m"], d["opening_frame_width_m"]), "frame", "opening_frame")
                openings.append({"id": opening_id, "kind": aperture, "type": aperture, "wall_side": side, "bay_index": index,
                                 "center_local": centre, "normal_local": [0, -1 if side == "south" else 1, 0],
                                 "clear_width_m": width, "clear_height_m": z1 - z0, "bottom_z_m": z0,
                                 "leaf_count": count, "leaf_reference_names": refs if count else [],
                                 "infill_proxy_names": [] if count else refs, "pattern_category": _aperture_pattern(p, row, aperture),
                                 "category_scope": row["category_scope"], "geometric_pattern_accuracy": row["geometric_pattern_accuracy"],
                                 "opening_method": "closed wall segments around real aperture; no Boolean or source mesh edit"})
    for side in ("east", "west"):
        x = d["enclosure_x_max_m"] if side == "east" else d["enclosure_x_min_m"]
        yl, yh = d["enclosure_y_min_m"], d["enclosure_y_max_m"]
        obj = box(side + "_unresolved_wall", (x, (yl + yh) / 2, (floor + d["wall_top_z_m"]) / 2),
                  (thick, yh - yl, d["wall_top_z_m"] - floor), "wall", "wall_segment")
        obj["wall_side"], obj["category"] = side, p["facades"][side]["kind"]
        wall_by_side[side].append(obj)
    for roof in p["roof_tiers"]:
        triple = tuple(mats[scheme[k]].name for k in ("roof_main", "roof_edge", "roof_under"))
        roof_cache = cache.setdefault(("V9_roof_material_triple", *triple), {})
        parts = R._roof_geometry("V9_" + ident + "_roof_" + str(roof["tier_index"]), roof["outer_width_m"], roof["outer_depth_m"],
                                 roof["eave_z_m"], roof["top_z_m"], roof["roof_type"], mats[scheme["roof_main"]], mats[scheme["roof_edge"]],
                                 mats[scheme["roof_under"]], building, roof_cache, roof["additional_overhang_m"], roof["corner_lift_m"],
                                 roof["tier_index"], (roof["inner_width_m"], roof["inner_depth_m"]) if roof["annular"] else None)
        _fixed_roof_surface(parts[0], cache)
        for obj in parts:
            role = obj.get("semantic_role", "roof")
            add(obj, role)
            obj["roof_tier_index"] = roof["tier_index"]
        roofs.append({"tier_index": roof["tier_index"], "roof_type": roof["roof_type"], "annular": roof["annular"],
                      "roof_object": parts[0].name, "objects": [o.name for o in parts], "target_group_peak_z_m": roof["top_z_m"],
                      "actual_eave_z_m": parts[0]["eave_level_model_m"], "surface_triangulation": parts[0]["surface_triangulation"],
                      "surface_scope": "mathematical closed skin, not measured physical tile underside"})
    if d["upper_band"]:
        band = d["upper_band"]
        bw, bd, t = band["width_m"], band["depth_m"], band["wall_thickness_m"]
        for side, x, y, ww, dd in (("south", 0, -bd / 2 + t / 2, bw, t), ("north", 0, bd / 2 - t / 2, bw, t),
                                  ("west", -bw / 2 + t / 2, 0, t, bd), ("east", bw / 2 - t / 2, 0, t, bd)):
            obj = box("upper_band_" + side, (x, y, (band["bottom_z_m"] + band["top_z_m"]) / 2),
                      (ww, dd, band["top_z_m"] - band["bottom_z_m"]), "wall", "upper_band_wall")
            obj["occupied_floor"] = False
            obj["roof_tier_index"] = 1
    if p["eaves_tiers"] == 2:
        lower = bpy.data.objects[roofs[0]["roof_object"]]
        tree = BVHTree.FromPolygons([v.co for v in lower.data.vertices], [tuple(f.vertices) for f in lower.data.polygons])
        bottom = d["column_top_z_m"] + d["beam_height_m"]
        radius = d["column_radius_m"]
        for i, (x, y) in enumerate(sorted(grid)):
            samples = [(0, 0)] + [(radius * math.cos(j * math.pi / 8), radius * math.sin(j * math.pi / 8)) for j in range(16)]
            levels = []
            for dx, dy in samples:
                point, _, _, _ = tree.ray_cast(Vector((x + dx, y + dy, bottom)), Vector((0, 0, 1)), 40)
                if point is None:
                    raise ValueError("no actual lower roof support surface")
                levels.append(point.z)
            top = min(levels)
            if top <= bottom + 1e-4:
                raise ValueError("invalid derived bearing height")
            obj = add(F.column("V9_" + ident + "_study_bearing_" + str(i), (x, y, (top + bottom) / 2), radius,
                               top - bottom, mats[scheme["column"]], building, cache), "roof_bearing_post")
            obj["support_bottom_z_m"], obj["support_top_z_m"] = bottom, top
            obj["roof_contact_object"] = lower.name
            obj["contact_sample_count"] = 17
            obj["contact_scope"] = "minimum first generated surface over full top rim, not dougong or physical tile underside"
    bpy.context.view_layer.update()
    for opening in openings:
        opening["wall_segment_names"] = [o.name for o in wall_by_side[opening["wall_side"]]]
        opening["center_world"] = list(root.matrix_world @ Vector(opening["center_local"]))
        opening["normal_world"] = list(root.matrix_world.to_3x3() @ Vector(opening["normal_local"]))
    assumptions = ["All metric controls and uniform grid are explicit unmeasured study parameters.",
                   "Known categories and leaf counts use simplified closed reference geometry, not exact lattice or joinery.",
                   "R curvature, tile pitch, closure and peak normalization are helper presets; no physical tile cavity is reconstructed.",
                   "Roof surfaces use caller-owned fixed triangulation with unchanged vertices so local and evaluated-world contact rays share one topology; helper cache meshes stay unchanged.",
                   "Materials are caller visualization presets, not calibrated colour or paint survey.",
                   "Upper band has four walls and no occupied floor; unknown lofts and side features remain in unbuilt."]
    root["profile_sha256"] = profile_sha
    root["openings"] = json.dumps(openings, ensure_ascii=False)
    root["assumptions"] = json.dumps(assumptions, ensure_ascii=False)
    root["unbuilt_features"] = json.dumps(p["unbuilt"], ensure_ascii=False)
    root["material_preset"] = json.dumps({key: {"profile_key": value, "actual_material": mats[value].name} for key, value in scheme.items()})
    manifest = {"building_id": ident, "root": root.name, "objects": [o.name for o in objects], "roofs": roofs,
                "reference_floor": slab.name, "occupied_storeys": None, "interior_complete": False,
                "complete_reconstruction_proven": False, "profile_sha256": profile_sha}
    return {"root": root, "collection": building, "objects": objects, "components": components, "openings": openings,
            "opening_records": openings, "roofs": roofs, "assumptions": assumptions, "unbuilt_features": p["unbuilt"],
            "verified_facts": p["known_facts"], "profile": p, "manifest": manifest}
