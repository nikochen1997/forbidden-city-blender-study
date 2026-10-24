"""Two explicitly unmeasured exterior studies; the caller owns all scene I/O.

No source registration, interior storey plates, cameras or materials are created.
Fuwang's upper annular veranda is an exterior walkway, never an interior floor.
"""
import hashlib
import json
import math
import re

import bmesh
import bpy

import forbidden_city_geometry as F
import restoration_buildings as R
import square_garden_pavilions as S


FACT_SHA256 = {
    "fuwangge": "f12ae140c626b24c6e0cc29f09caa1a16991a882312d090e114af804dd9fc56e",
    "zhuxiangguan": "352cf1ae8b23f3137d244a2aa04f07ff5852908b65c415682249582615665d54",
}
SIDES = ("south", "north", "east", "west")
NORMALS = {"south": (0, -1, 0), "north": (0, 1, 0), "east": (1, 0, 0), "west": (-1, 0, 0)}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _number(name, value, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError("invalid finite study parameter " + name)
    return value


def _axes(name, values):
    if not isinstance(values, list) or not 2 <= len(values) <= 16:
        raise ValueError("explicit study grid required " + name)
    for value in values: _number(name, value)
    if any(b <= a for a, b in zip(values, values[1:])) or abs(values[0]+values[-1]) > 1e-8:
        raise ValueError("study grid must be increasing and centered " + name)
    return values


def _perimeter(xs, ys):
    return sorted({(x, y) for x in xs for y in (ys[0], ys[-1])} |
                  {(x, y) for x in (xs[0], xs[-1]) for y in ys[1:-1]})


def _wall_specs(p):
    d = p["study"]
    lower_top = d["level_break_z_m"]-d["walkway_thickness_m"] if p["building_id"] == "fuwangge" else d["level_break_z_m"]
    out = {}
    for level, lo, hi in ((0, d["floor_z_m"], lower_top), (1, d["level_break_z_m"], d["wall_top_z_m"])):
        xs, ys = d[("lower" if level == 0 else "upper")+"_core_grid_x_m"], d[("lower" if level == 0 else "upper")+"_core_grid_y_m"]
        for side in SIDES:
            axis = "Y" if side in ("south", "north") else "X"
            stations = xs if axis == "Y" else ys
            constant = {"south": ys[0], "north": ys[-1], "west": xs[0], "east": xs[-1]}[side]
            ident = "s"+str(level)+"_"+side
            out[ident] = {"wall_id": ident, "wall_side": side, "exterior_level_index": level,
                          "normal_axis": axis, "constant_m": constant, "min_along_m": stations[0],
                          "max_along_m": stations[-1], "bottom_z_m": lo, "top_z_m": hi}
    return out


def _validate(p, materials):
    for key in ("building_id", "primitive_id", "known_facts", "documentary_additions", "visual_reference",
                "study", "roof_tiers", "material_scheme", "openings", "unbuilt_features",
                "dimension_status", "modeled_exterior_levels", "occupied_storeys", "reference_floor_count",
                "interior_floor_count", "third_party_cost", "paid_service_calls", "human_approval", "absolute_accuracy_claim"):
        if key not in p: raise ValueError("missing exterior study parameter " + key)
    ident = p["building_id"]
    if ident not in FACT_SHA256 or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", p["primitive_id"]):
        raise ValueError("unsupported exterior identity or unsafe name")
    if _digest(p["known_facts"]) != FACT_SHA256[ident]:
        raise ValueError("frozen typed facts changed, missing or promoted")
    if p["dimension_status"] != "unmeasured_study" or p["absolute_accuracy_claim"] is not False or p["human_approval"] != "pending":
        raise ValueError("study scope or human status promoted")
    for key, value in (("third_party_cost", 0), ("paid_service_calls", 0), ("modeled_exterior_levels", 2),
                       ("reference_floor_count", 0), ("interior_floor_count", 0)):
        if type(p[key]) is not int or p[key] != value: raise ValueError("strict integer scope required " + key)
    if p["occupied_storeys"] is not None or not isinstance(p["unbuilt_features"], list) or not p["unbuilt_features"]:
        raise ValueError("occupied storeys unresolved and unbuilt list required")
    if ident == "fuwangge":
        evidence = p["documentary_additions"]
        if evidence.get("ground_core_bays_each_side") != 5 or evidence.get("ground_surrounding_veranda") is not True or evidence.get("scope") != "2025_publication_ground_only_not_metric_survey":
            raise ValueError("published five-bay ground core/veranda scope required")
        if p["visual_reference"].get("visible_roof_bands") != 2 or p["visual_reference"].get("status") != "visual_observation_not_documentary_eaves_fact":
            raise ValueError("two roof groups are qualified visual study only")
    d = p["study"]
    for key in ("column_radius_m", "column_base_radius_m", "column_base_height_m", "beam_width_m", "beam_height_m",
                "wall_thickness_m", "frame_width_m", "frame_depth_m", "panel_depth_m"):
        _number(key, d[key], True)
    for key in ("floor_z_m", "level_break_z_m", "wall_top_z_m"):
        _number(key, d[key])
    if not d["floor_z_m"]+d["column_base_height_m"] < d["level_break_z_m"]-2*d["beam_height_m"] < d["wall_top_z_m"]-3*d["beam_height_m"]:
        raise ValueError("invalid exterior support levels")
    if d["beam_width_m"] < 2*d["column_radius_m"] or d["column_base_radius_m"] < d["column_radius_m"]:
        raise ValueError("beam or base cannot support full column rim")
    for level in ("lower", "upper"):
        for axis in ("x", "y"): _axes(level+axis, d[level+"_core_grid_"+axis+"_m"])
    if len(d["lower_core_grid_x_m"]) != (6 if ident == "fuwangge" else 4):
        raise ValueError("published lower core frontage count changed")
    tiers = p["roof_tiers"]
    if len(tiers) != (2 if ident == "fuwangge" else 1): raise ValueError("wrong modeled roof group count")
    scheme = p["material_scheme"]
    for key in ("base", "column", "beam", "wall", "frame", "infill", "railing", "walkway", "roof_main", "roof_edge", "roof_under"):
        if key not in scheme or scheme[key] not in materials: raise ValueError("caller material missing " + key)
    if len({scheme[k] for k in ("roof_main", "roof_edge", "roof_under")}) != 3:
        raise ValueError("roof main, edge and underside must be separate material keys")
    if p.get("roof_colour_categories") != ({"main": "yellow", "edge_ridge": "blue"} if ident == "fuwangge" else {"main": "green", "edge_ridge": "yellow"}):
        raise ValueError("documented colour categories changed")
    if ident == "fuwangge":
        if len(d["lower_core_grid_y_m"]) != 6: raise ValueError("ground square core requires five bays each side")
        if abs(d["lower_core_grid_x_m"][-1]-d["lower_core_grid_y_m"][-1]) > 1e-8:
            raise ValueError("square lower core required")
        if abs(d["upper_core_grid_x_m"][-1]-d["upper_core_grid_y_m"][-1]) > 1e-8:
            raise ValueError("square upper core study required")
        for axis in ("x", "y"):
            outer = _axes("veranda "+axis, d["lower_veranda_grid_"+axis+"_m"])
            core = d["lower_core_grid_"+axis+"_m"]
            if outer[0] >= core[0] or outer[-1] <= core[-1] or any(not any(abs(a-b) < 1e-8 for b in outer) for a in core):
                raise ValueError("veranda grid must separately include core axes and outer corners")
        for key in ("walkway_thickness_m", "walkway_outer_side_m", "walkway_inner_side_m", "railing_height_m", "railing_post_width_m", "railing_bar_height_m"):
            _number(key, d[key], True)
        _number("lower_veranda_beam_top_z_m", d["lower_veranda_beam_top_z_m"])
        if not d["floor_z_m"]+d["column_base_height_m"]+d["beam_height_m"] < d["lower_veranda_beam_top_z_m"] < d["level_break_z_m"]-d["walkway_thickness_m"]:
            raise ValueError("lower veranda support levels invalid")
        core_side = 2*d["lower_core_grid_x_m"][-1]; upper_side = 2*d["upper_core_grid_x_m"][-1]
        margin = d["column_radius_m"]+d["wall_thickness_m"]
        if not 0 < d["walkway_inner_side_m"] <= upper_side-2*margin < upper_side+2*margin < core_side < d["walkway_outer_side_m"]:
            raise ValueError("annular walkway must support core/outer column footprints and retain true core void")
        if d["walkway_outer_side_m"]-core_side < 2*d["column_radius_m"]+d["railing_post_width_m"]:
            raise ValueError("walkway outer edge lacks railing/column bearing width")
        for i, t in enumerate(tiers):
            for key in ("outer_side_m", "skin_thickness_m", "curve_power", "ridge_radius_m"):
                _number(key, t[key], True)
            for key in ("inner_side_m", "eave_z_m", "top_z_m", "corner_lift_m", "ridge_offset_m"):
                _number(key, t[key])
            if type(t["tier_index"]) is not int or t["tier_index"] != i or t["roof_type"] != "four_corner_pyramidal":
                raise ValueError("invalid four-corner roof study")
            if t["corner_lift_m"] < 0 or t["ridge_offset_m"] < 0 or t["eave_z_m"] >= t["top_z_m"] or not 0 <= t["inner_side_m"] < t["outer_side_m"]:
                raise ValueError("invalid square roof dimensions")
            if t["skin_thickness_m"] >= min(t["outer_side_m"], t["top_z_m"]-t["eave_z_m"])/3:
                raise ValueError("square skin too thick")
        if tiers[0]["inner_side_m"] != d["walkway_outer_side_m"] or tiers[1]["inner_side_m"] != 0:
            raise ValueError("lower annulus and complete upper roof required")
        if abs(tiers[0]["top_z_m"]-d["level_break_z_m"]) > 1e-8:
            raise ValueError("lower inner rim must meet exterior deck datum")
        if tiers[0]["outer_side_m"] <= 2*d["lower_veranda_grid_x_m"][-1]+2*d["column_radius_m"] or tiers[0]["outer_side_m"] <= 2*d["lower_veranda_grid_y_m"][-1]+2*d["column_radius_m"]:
            raise ValueError("lower roof misses veranda column rims")
        if tiers[0]["inner_side_m"] >= 2*d["lower_veranda_grid_x_m"][-1]-2*d["column_radius_m"] or tiers[0]["inner_side_m"] >= 2*d["lower_veranda_grid_y_m"][-1]-2*d["column_radius_m"]:
            raise ValueError("annular hole crosses lower veranda bearing")
        if tiers[1]["outer_side_m"] <= d["walkway_outer_side_m"] or tiers[1]["eave_z_m"] <= d["wall_top_z_m"]+.2 or tiers[0]["eave_z_m"]-tiers[0]["skin_thickness_m"] <= d["lower_veranda_beam_top_z_m"]+.05:
            raise ValueError("roof clearance/support height order invalid")
        if d["railing_height_m"] >= d["wall_top_z_m"]-d["level_break_z_m"]:
            raise ValueError("railing exceeds upper exterior height")
    else:
        for axis in ("x", "y"):
            if abs(d["lower_core_grid_"+axis+"_m"][-1]-d["upper_core_grid_"+axis+"_m"][-1]) > 1e-8:
                raise ValueError("two-storey main shell must stack on the same study beam perimeter")
        t = tiers[0]
        for key in ("outer_width_m", "outer_depth_m"): _number(key, t[key], True)
        for key in ("eave_z_m", "top_z_m", "corner_lift_m"): _number(key, t[key])
        if t["roof_type"] != "juanpeng_xieshan" or t["tier_index"] != 0 or t["corner_lift_m"] != 0 or t["eave_z_m"] <= d["wall_top_z_m"]+.2 or t["top_z_m"] <= t["eave_z_m"]+.25:
            raise ValueError("explicit single rolled xieshan roof required")
        if t["outer_width_m"] <= 2*d["upper_core_grid_x_m"][-1]+2*d["beam_width_m"] or t["outer_depth_m"] <= 2*d["upper_core_grid_y_m"][-1]+2*d["beam_width_m"]:
            raise ValueError("rolled roof misses complete support perimeter")
    walls = _wall_specs(p); seen = set()
    if not isinstance(p["openings"], list): raise ValueError("explicit empty or complete study opening schedule required")
    for row in p["openings"]:
        if row["id"] in seen or row["wall_id"] not in walls or row["kind"] not in ("door", "window", "passage"):
            raise ValueError("invalid opening identity/type")
        seen.add(row["id"]); wall = walls[row["wall_id"]]
        for key in ("width_m", "height_m"): _number(key, row[key], True)
        for key in ("center_along_m", "bottom_z_m"): _number(key, row[key])
        if row["dimension_status"] != "unmeasured_study" or row["category_status"] != "study_assumption" or row["leaf_count"] is not None or row["pattern_category"] is not None:
            raise ValueError("full facade/leaf/pattern unknown; only explicit study apertures supported")
        if row["center_along_m"]-row["width_m"]/2 <= wall["min_along_m"] or row["center_along_m"]+row["width_m"]/2 >= wall["max_along_m"] or row["bottom_z_m"] < wall["bottom_z_m"] or row["bottom_z_m"]+row["height_m"] >= wall["top_z_m"]:
            raise ValueError("opening outside its actual exterior wall")
        if not row.get("destination"): raise ValueError("opening destination required")
    json.dumps(p, allow_nan=False)
    return walls


def _fixed(obj):
    """Triangulate caller-owned data without moving any vertex."""
    data = obj.data.copy(); before = sorted(tuple(v.co) for v in data.vertices)
    bm = bmesh.new(); bm.from_mesh(data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="FIXED", ngon_method="EAR_CLIP")
    bm.to_mesh(data); bm.free(); data.update()
    if sorted(tuple(v.co) for v in data.vertices) != before: raise ValueError("triangulation moved vertices")
    obj.data = data
    obj["surface_triangulation"] = "caller copy, FIXED/EAR_CLIP, zero vertex displacement"


def _triangle_plane(points):
    # Mesh coordinates arrive as float32. Keep subsequent differences/cross in
    # Python float64 so shared roof edges retain the same 1e-9 weld identity.
    a, b, c = [tuple(float(v) for v in point) for point in points]
    ab, ac = [tuple(v[i]-a[i] for i in range(3)) for v in (b, c)]
    normal = tuple(ab[i]*ac[j]-ab[j]*ac[i] for i, j in ((1, 2), (2, 0), (0, 1)))
    return a, normal


def _contact_surface(roof, footprint, bottom):
    """Clip actual downward roof triangles to a convex bearing footprint.

    The whole cap is piecewise coplanar with the actual roof underside, rather
    than interpolating a sparse ring of ray hits across roof triangle seams.
    """
    out = F._Surface(); area = 0
    for face in roof.data.polygons:
        points = [roof.data.vertices[i].co for i in face.vertices]
        if len(points) != 3: raise ValueError("roof contact requires fixed triangles")
        a, n = _triangle_plane(points)
        if n[2] >= -1e-10: continue
        clipped = [(v.x, v.y) for v in points]
        for first, second in zip(footprint, footprint[1:]+footprint[:1]):
            dx, dy = second[0]-first[0], second[1]-first[1]
            clipped = F._clip_halfplane(clipped, (-dy, dx, dy*first[0]-dx*first[1]), tolerance=1e-10)
            if not clipped: break
        if len(clipped) < 3 or abs(F._ring_area(clipped)) < 1e-12: continue
        top = [(x, y, a[2]-(n[0]*(x-a[0])+n[1]*(y-a[1]))/n[2]) for x, y in clipped]
        if min(v[2] for v in top) <= bottom+1e-5: raise ValueError("bearing bottom reaches/pierces roof")
        if F._ring_area(clipped) < 0: top.reverse()
        area += abs(F._ring_area(clipped)); out.face(top)
    if abs(area-abs(F._ring_area(footprint))) > 2e-6:
        raise ValueError("actual roof underside does not cover the complete bearing domain")
    F._volume_from_top(out, bottom)
    return out


def build_exterior_tower(profile, collection, materials, mesh_cache=None):
    """Return local geometry only; no source binding or implicit facade schedule."""
    p = profile; specs = _validate(p, materials); d = p["study"]; ident = p["building_id"]
    cache = {} if mesh_cache is None else mesh_cache; mats = dict(materials); scheme = p["material_scheme"]
    prefix = "V19_"+p["primitive_id"]
    col = F.ensure_collection(prefix, collection); root = bpy.data.objects.new(prefix+"_root", None); col.objects.link(root)
    objects, components, walls, opening_records, roof_records, contacts = [], {}, {}, [], [], []
    profile_sha = _digest(p)

    def add(obj, role, level=None):
        obj.parent = root; obj["semantic_role"] = role; obj["building_id"] = ident
        obj["profile_sha256"] = profile_sha; obj["dimension_status"] = "unmeasured_study"
        obj["absolute_accuracy_claim"] = False; obj["human_approval"] = "pending"; obj["third_party_cost"] = 0
        obj["not_current_survey_or_complete_exterior"] = True
        if level is not None: obj["exterior_level_index"] = level
        objects.append(obj); components.setdefault(role, []).append(obj)
        return obj

    def box(label, center, dims, material, role, level=None, cached=True):
        return add(F.box(prefix+"_"+label, center, dims, mats[scheme[material]], col, cache if cached else None, role), role, level)

    def beams(label, xs, ys, top, level):
        bw, bh = d["beam_width_m"], d["beam_height_m"]
        for axis in ("X", "Y"):
            for sign in (-1, 1):
                c = (0, sign*ys[-1], top-bh/2) if axis == "X" else (sign*xs[-1], 0, top-bh/2)
                dims = (2*xs[-1]+bw, bw, bh) if axis == "X" else (bw, 2*ys[-1]+bw, bh)
                obj = box(label+"_"+axis+str(sign), c, dims, "beam", "beam", level)
                obj["beam_top_z_m"] = top

    def columns(label, xs, ys, bottom, beam_top, level, base=False, role="column"):
        for i, (x, y) in enumerate(_perimeter(xs, ys)):
            start = bottom
            if base:
                bh = d["column_base_height_m"]
                obj = add(F.column(prefix+"_"+label+"_base"+str(i), (x, y, bottom+bh/2), d["column_base_radius_m"], bh, mats[scheme["base"]], col, cache, 24), "column_base", level)
                obj["support_scope"] = "caller must separately qualify the external base plane/source support"; start += bh
            end = beam_top-d["beam_height_m"]
            obj = add(F.column(prefix+"_"+label+"_column"+str(i), (x, y, (start+end)/2), d["column_radius_m"], end-start, mats[scheme["column"]], col, cache, 24), role, level)
            obj["study_axis_local"] = [x, y]; obj["bottom_z_m"] = start; obj["top_z_m"] = end
            obj["support_top_beam_z_m"] = beam_top-d["beam_height_m"]

    lx, ly, ux, uy = [d[k] for k in ("lower_core_grid_x_m", "lower_core_grid_y_m", "upper_core_grid_x_m", "upper_core_grid_y_m")]
    lower_top = specs["s0_south"]["top_z_m"]
    beams("lower_core", lx, ly, lower_top, 0); columns("lower_core", lx, ly, d["floor_z_m"], lower_top, 0, True, "core_pilaster")
    beams("upper_core", ux, uy, d["wall_top_z_m"], 1); columns("upper_core", ux, uy, d["level_break_z_m"], d["wall_top_z_m"], 1, False, "core_pilaster")
    if ident == "fuwangge":
        vx, vy = d["lower_veranda_grid_x_m"], d["lower_veranda_grid_y_m"]
        beams("lower_veranda", vx, vy, d["lower_veranda_beam_top_z_m"], 0)
        columns("lower_veranda", vx, vy, d["floor_z_m"], d["lower_veranda_beam_top_z_m"], 0, True, "open_veranda_column")
        # Upper exterior column positions are explicitly the study outer ring,
        # not an assertion that the upper core has five documentary bays.
        beams("upper_veranda", lx, ly, d["wall_top_z_m"], 1)
        columns("upper_veranda", lx, ly, d["level_break_z_m"], d["wall_top_z_m"], 1, False, "open_veranda_column")
        bw, bh = d["beam_width_m"], d["beam_height_m"]
        for axis, axes in (("X", uy), ("Y", ux)):
            for i, pos in enumerate(axes):
                c = (0, pos, lower_top-bh/2) if axis == "X" else (pos, 0, lower_top-bh/2)
                dims = (2*lx[-1]+bw, bw, bh) if axis == "X" else (bw, 2*ly[-1]+bw, bh)
                box("annular_deck_support_"+axis+str(i), c, dims, "beam", "walkway_support_beam", 0)
        outer, inner = d["walkway_outer_side_m"]/2, d["walkway_inner_side_m"]/2
        rings = [[(-outer, -outer), (outer, -outer), (outer, outer), (-outer, outer)],
                 [(-inner, -inner), (-inner, inner), (inner, inner), (inner, -inner)]]
        surf = F._Surface()
        for tri in F._triangulate_rings(rings): surf.face([(x, y, d["level_break_z_m"]) for x, y in tri])
        F._volume_from_top(surf, lower_top)
        deck = add(F._object(prefix+"_upper_exterior_annular_walkway", F._new_mesh(prefix+"_walkway", surf.vertices, surf.faces, mats[scheme["walkway"]]), col, "exterior_walkway"), "exterior_walkway", 1)
        deck["interior_floor"] = False; deck["annular_inner_side_m"] = 2*inner
        rw, rh, railh = d["railing_post_width_m"], d["railing_bar_height_m"], d["railing_height_m"]
        for i, (x, y) in enumerate(_perimeter(lx, ly)):
            box("railing_post"+str(i), (x, y, d["level_break_z_m"]+railh/2), (rw, rw, railh), "railing", "railing_post", 1)
        for axis, axes, constant in (("X", lx, ly[-1]), ("Y", ly, lx[-1])):
            for sign in (-1, 1):
                for i, (a, b) in enumerate(zip(axes, axes[1:])):
                    for label, h in (("top", railh-rh/2), ("low", railh*.30)):
                        c = ((a+b)/2, sign*constant, d["level_break_z_m"]+h) if axis == "X" else (sign*constant, (a+b)/2, d["level_break_z_m"]+h)
                        dims = (b-a, rw, rh) if axis == "X" else (rw, b-a, rh)
                        box("railing_"+axis+str(sign)+"_"+str(i)+label, c, dims, "railing", "railing_bar", 1)
    for wall_id, row in specs.items():
        ay = row["normal_axis"] == "Y"; span = row["max_along_m"]-row["min_along_m"]; t = d["wall_thickness_m"]
        c = (0, row["constant_m"], (row["bottom_z_m"]+row["top_z_m"])/2) if ay else (row["constant_m"], 0, (row["bottom_z_m"]+row["top_z_m"])/2)
        dims = (span+t, t, row["top_z_m"]-row["bottom_z_m"]) if ay else (t, span+t, row["top_z_m"]-row["bottom_z_m"])
        obj = box(wall_id, c, dims, "wall", "study_enclosure_wall", row["exterior_level_index"], False)
        obj["wall_id"] = wall_id; obj["not_documented_current_wall_or_facade"] = True; walls[wall_id] = obj
    for row in p["openings"]:
        spec = specs[row["wall_id"]]; ay = spec["normal_axis"] == "Y"; z = row["bottom_z_m"]+row["height_m"]/2
        center = (row["center_along_m"], spec["constant_m"], z) if ay else (spec["constant_m"], row["center_along_m"], z)
        extension = .02 if row["kind"] != "window" and row["bottom_z_m"] == spec["bottom_z_m"] else 0
        cutter_center = (center[0], center[1], center[2]-extension/2)
        # Always detach even if users==1: F's unit cache may own the same mesh.
        walls[row["wall_id"]].data = walls[row["wall_id"]].data.copy()
        record = F.cut_opening(walls[row["wall_id"]], {"id": row["id"], "type": "window" if row["kind"] == "window" else "door", "destination": row["destination"], "center": cutter_center, "width": row["width_m"], "height": row["height_m"]+extension, "depth": d["wall_thickness_m"]+.5, "normal_axis": spec["normal_axis"]}, col, None)
        proxies = []
        if row["kind"] != "passage":
            dims = (row["width_m"]*.98, d["panel_depth_m"], row["height_m"]*.98) if ay else (d["panel_depth_m"], row["width_m"]*.98, row["height_m"]*.98)
            obj = box(row["id"]+"_unresolved_set", center, dims, "infill", "unresolved_opening_set_proxy", spec["exterior_level_index"])
            obj["not_actual_leaf_count"] = True; obj["leaf_count"] = "unknown"; proxies.append(obj.name)
        fw, fd = d["frame_width_m"], d["frame_depth_m"]; frames = []
        for sign in (-1, 1):
            c = list(center); c[0 if ay else 1] += sign*(row["width_m"]+fw)/2
            dims = (fw, fd, row["height_m"]) if ay else (fd, fw, row["height_m"])
            frames.append(box(row["id"]+"_jamb"+str(sign), c, dims, "frame", "opening_frame", spec["exterior_level_index"]).name)
        c = (center[0], center[1], center[2]+(row["height_m"]+fw)/2)
        dims = (row["width_m"], fd, fw) if ay else (fd, row["width_m"], fw)
        frames.append(box(row["id"]+"_head", c, dims, "frame", "opening_frame", spec["exterior_level_index"]).name)
        record.update(row, center_local=list(center), normal_local=NORMALS[spec["wall_side"]], normal_axis=spec["normal_axis"],
                      clear_width_m=row["width_m"], clear_height_m=row["height_m"], infill_proxy_names=proxies,
                      frame_names=frames, opening_method="Exact Boolean applied on independent caller-owned mesh")
        opening_records.append(record)
    roof_objects = []
    if ident == "fuwangge":
        for tier in p["roof_tiers"]:
            q = {"building_id": p["primitive_id"], "material_scheme": {"roof_main": scheme["roof_main"], "roof_edge": scheme["roof_edge"]}}
            roof = S._roof(q, tier, col, {**mats, "dark_wood": mats[scheme["roof_under"]]})
            roof.name = prefix+"_square_roof_"+str(tier["tier_index"]); _fixed(roof); add(roof, "roof", tier["tier_index"])
            surf = F._Surface(); a = tier["outer_side_m"]/2; stop = 1-tier["inner_side_m"]/tier["outer_side_m"]
            for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                pts = []
                for i in range(25):
                    f = i/24; r = a*(1-stop*f)
                    z = tier["eave_z_m"]+(tier["top_z_m"]-tier["eave_z_m"])*f**tier["curve_power"]+tier["corner_lift_m"]*(1-f)**3+tier["ridge_offset_m"]
                    pts.append((sx*r, sy*r, z))
                F._tube(surf, pts, tier["ridge_radius_m"], 8)
            ridge = add(F._object(prefix+"_four_blue_ridges_"+str(tier["tier_index"]), F._new_mesh(prefix+"_ridges", surf.vertices, surf.faces, mats[scheme["roof_edge"]]), col, "ridge"), "ridge", tier["tier_index"])
            ridge["grouped_ridge_count"] = 4; ridge["not_measured_ridge_section"] = True
            roof_objects.append(roof)
            roof_records.append({"tier_index": tier["tier_index"], "object": roof.name, "ridge_object": ridge.name,
                                 "topology": "true_annular_closed_skin" if tier["inner_side_m"] else "complete_single_apex_closed_skin", **tier})
    else:
        t = p["roof_tiers"][0]
        # R's old key omits under-material; isolate all three exact material names.
        roof_cache = cache.setdefault(("V19_complete_roof_materials", *(mats[scheme[k]].name for k in ("roof_main", "roof_edge", "roof_under"))), {})
        parts = R._roof_geometry(prefix+"_rolled_roof", t["outer_width_m"], t["outer_depth_m"], t["eave_z_m"], t["top_z_m"], "juanpeng_xieshan",
                                 *(mats[scheme[k]] for k in ("roof_main", "roof_edge", "roof_under")), col, roof_cache, 0, 0, 1)
        for obj in parts: _fixed(obj); add(obj, obj.get("semantic_role", "roof"), 1)
        roof_objects.append(parts[0]); roof_records.append({"object": parts[0].name, "objects": [o.name for o in parts], **t,
            "underside_scope": "inherited R closed mathematical envelope, not a physical tile cavity or measured underside"})

    def contact_prism(label, roof, footprint, bottom, role, level):
        surf = _contact_surface(roof, footprint, bottom)
        obj = add(F._object(prefix+"_"+label, F._new_mesh(prefix+"_contact", surf.vertices, surf.faces, mats[scheme["beam"]]), col, role), role, level)
        _fixed(obj); obj["roof_contact_object"] = roof.name; obj["bottom_z_m"] = bottom
        obj["support_footprint_local"] = json.dumps(footprint); obj["not_measured_dougong"] = True
        contacts.append({"object": obj.name, "roof": roof.name, "footprint_local": footprint, "bottom_z_m": bottom,
                         "method": "whole convex footprint clipped against actual downward roof triangles"})

    radius = min(d["column_radius_m"], d["beam_width_m"]*.45)
    groups = [(roof_objects[-1], sorted(set(_perimeter(ux, uy)+( _perimeter(lx, ly) if ident == "fuwangge" else []))), d["wall_top_z_m"], 1)]
    if ident == "fuwangge": groups.insert(0, (roof_objects[0], _perimeter(d["lower_veranda_grid_x_m"], d["lower_veranda_grid_y_m"]), d["lower_veranda_beam_top_z_m"], 0))
    for roof, axes, bottom, level in groups:
        for i, (x, y) in enumerate(axes):
            footprint = [(x+radius*math.cos(j*math.pi/12), y+radius*math.sin(j*math.pi/12)) for j in range(24)]
            contact_prism("s"+str(level)+"_bearing"+str(i), roof, footprint, bottom, "roof_bearing_post", level)
    for side in SIDES:
        row = specs["s1_"+side]; t = d["wall_thickness_m"]; lo, hi, k = row["min_along_m"]-t/2, row["max_along_m"]+t/2, row["constant_m"]
        footprint = [(lo, k-t/2), (hi, k-t/2), (hi, k+t/2), (lo, k+t/2)] if row["normal_axis"] == "Y" else [(k-t/2, lo), (k+t/2, lo), (k+t/2, hi), (k-t/2, hi)]
        contact_prism("roof_closure_"+side, roof_objects[-1], footprint, d["wall_top_z_m"], "study_roof_closure_wall", 1)
    assumptions = [
        "All spans, grids, exterior height breaks, wall positions, roof curves and RGB are explicit unmeasured study controls.",
        "Two exterior layers do not certify occupied storeys, documentary eaves count or interior floor elevations; no interior floor plate or stair is created.",
        "Opaque core enclosure is a study substrate, not proof of current wall/door/window arrangement. Empty schedule invents no facade features.",
        "Plain columns, spanning beams and actual-roof-contact caps are research supports, not surveyed dougong or hidden historical framing.",
        "No source actor is registered/hidden; complete source-domain, base contacts and world placement require later independent registration.",
    ]
    if ident == "fuwangge": assumptions.append("Five ground core bays each side exclude the separate outer veranda grid. Upper grid is unmeasured; annular upper exterior walkway retains an interior void and is not one of three documentary interior floors.")
    else: assumptions.append("Documented two storeys do not resolve the frozen occupied_storeys=null field. R's rolled roof includes an inherited mathematical closed underside, not a measured physical tile cavity.")
    unbuilt = list(p["unbuilt_features"])+["interior floors and stairs", "measured facade joinery/lattice/leaf counts", "surveyed dougong and precise framing", "source registration and external ground support"]
    if ident == "zhuxiangguan": unbuilt += ["two ear towers and their unknown roof types", "sloping galleries", "bow wall and real octagonal gate"]
    else: unbuilt += ["three documentary interior storeys and internal partitions", "unresolved finial", "individual physical tiles and ridge beasts"]
    for key, value in (("building_id", ident), ("profile_sha256", profile_sha), ("modeled_exterior_levels", 2),
                       ("occupied_storeys", "unknown"), ("reference_floor_count", 0), ("interior_floor_count", 0),
                       ("third_party_cost", 0), ("human_approval", "pending"), ("absolute_accuracy_claim", False)):
        root[key] = value
    root["profile_json"] = json.dumps(p, ensure_ascii=False, allow_nan=False)
    root["assumptions"] = json.dumps(assumptions, ensure_ascii=False); root["unbuilt_features"] = json.dumps(unbuilt, ensure_ascii=False)
    root["documentary_internal_storeys"] = 3 if ident == "fuwangge" else "unknown"
    root["documentary_eaves_tiers"] = "unknown"; root["source_registration_verified"] = False
    bpy.context.view_layer.update()
    manifest = {"building_id": ident, "root": root.name, "objects": [o.name for o in objects], "profile_sha256": profile_sha,
                "modeled_exterior_levels": 2, "modeled_roof_groups": len(roof_records), "interior_floor_count": 0,
                "exterior_annular_walkway_count": 1 if ident == "fuwangge" else 0, "occupied_storeys": None,
                "source_registration_verified": False, "third_party_cost": 0, "human_approval": "pending", "absolute_accuracy_claim": False}
    return {"root": root, "collection": col, "objects": objects, "components": components, "walls": walls,
            "opening_records": opening_records, "openings": opening_records, "roofs": roof_records, "contacts": contacts,
            "profile": p, "assumptions": assumptions, "unbuilt_features": unbuilt, "manifest": manifest}
