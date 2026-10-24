"""Single high halls and a three-vault gate: explicitly provisional studies.

This module neither creates a scene on import nor reads/writes files or networks.
Two eaves never imply two storeys: every monument has exactly one occupied floor.
"""
import json
import math

import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

import forbidden_city_geometry as F
import restoration_buildings as R


def _positive(name, value):
    return F._number(name, value, strictly_positive=True)


def make_vault_cutter(name, width, spring_z=None, crown_z=None, depth=None, center_x=None, collection=None,
                      bottom_z=-.2, center_y=0, mesh_cache=None, y_min=None, y_max=None):
    """Return a closed elliptical-arch tunnel cutter, in unscaled local metres.

    X is the clear-width axis, Y the through direction. spring_z/crown_z/bottom_z
    are absolute local Z coordinates. Assign a parent/world matrix as needed.
    The caller owns applying/removing it; this helper never applies a Boolean.
    """
    if isinstance(width, dict):
        record = width
        collection = spring_z if collection is None else collection
        width, spring_z, crown_z = record["width"], record["spring_z"], record["crown_z"]
        center_x = record.get("center_x", record["local_x"])
        bottom_z = record.get("cutter_bottom_z", record.get("bottom_z", 0) - .2)
        low = record["y_min"] - 1 if y_min is None else y_min
        high = record["y_max"] + 1 if y_max is None else y_max
        depth, center_y = high - low, (low + high) / 2
    width, depth = _positive("vault width", width), _positive("vault depth", depth)
    spring_z, crown_z, bottom_z = [F._number(key, value) for key, value in
                                   (("spring_z", spring_z), ("crown_z", crown_z), ("bottom_z", bottom_z))]
    center_x, center_y = F._number("center_x", center_x), F._number("center_y", center_y)
    if not bottom_z < spring_z < crown_z:
        raise ValueError("vault requires bottom_z < spring_z < crown_z")
    half, rise = width / 2, crown_z - spring_z
    section = [(-half, bottom_z), (half, bottom_z), (half, spring_z)]
    section += [(half * math.cos(math.pi * i / 32), spring_z + rise * math.sin(math.pi * i / 32))
                for i in range(1, 33)]
    count = len(section)
    vertices = [(x + center_x, y + center_y, z) for y in (-depth / 2, depth / 2) for x, z in section]
    faces = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
    faces.extend((i, (i + 1) % count, (i + 1) % count + count, i + count) for i in range(count))
    data = F._new_mesh(name, vertices, faces, None, mesh_cache,
                       ("vault_cutter", width, spring_z, crown_z, depth, bottom_z, center_x, center_y))
    obj = F._object(name, data, collection, "boolean_cutter")
    obj["is_boolean_cutter"] = True
    obj["vault_shape"] = "elliptical_arch_32_segments"
    return obj


def _box_cutter(name, low, high, collection):
    x0,y0,z0=low; x1,y1,z1=high
    vertices=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
              (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    data=F._new_mesh(name,vertices,faces,None)
    obj=F._object(name,data,collection,"boolean_cutter")
    obj["is_boolean_cutter"]=True
    return obj


def make_gate_cutters(name, record, collection, y_min=None, y_max=None):
    """Return [arched tunnel, square south mouth, square north mouth].

    Every coordinate is baked into mesh data; object location/rotation are zero,
    so the caller can assign the registered anchor/rotation directly. Engineering
    extensions y_min/y_max do not move the mouths: south_mouth_y/north_mouth_y
    remain the actual face references, and may be overridden for a wall copy.
    """
    low=record["y_min"]-1 if y_min is None else y_min
    high=record["y_max"]+1 if y_max is None else y_max
    arch=make_vault_cutter(name+"_内券",record,collection,y_min=low,y_max=high)
    x=record.get("center_x",record["local_x"])
    width=record["width"]
    bottom=record.get("cutter_bottom_z",-.2)
    mouth_height=record.get("mouth_height_m",record["crown_z"])
    mouth_depth=record.get("mouth_depth_m",1.0)
    south=record.get("south_mouth_y",record["y_min"])
    north=record.get("north_mouth_y",record["y_max"])
    south_depth=record.get("south_mouth_depth_m",mouth_depth)
    north_depth=record.get("north_mouth_depth_m",mouth_depth)
    for value in (mouth_height,mouth_depth,south_depth,north_depth):_positive("mouth dimension",value)
    mouth_s=_box_cutter(name+"_南方口",(x-width/2,min(low,south-.3),bottom),
                         (x+width/2,south+south_depth,mouth_height),collection)
    mouth_n=_box_cutter(name+"_北方口",(x-width/2,north-north_depth,bottom),
                         (x+width/2,max(high,north+.3),mouth_height),collection)
    for obj in (arch,mouth_s,mouth_n):obj["gate_form"]="square_outer_mouths_with_arched_inner_tunnel"
    return [arch,mouth_s,mouth_n]


def _polygon_y_range_at_x(ring,x):
    intersections=[]
    for first,second in zip(ring,ring[1:]+ring[:1]):
        x0,y0=first; x1,y1=second
        if abs(x1-x0)<1e-10:
            if abs(x-x0)<1e-8:intersections.extend([y0,y1])
        elif min(x0,x1)<=x<=max(x0,x1):
            t=(x-x0)/(x1-x0)
            intersections.append(y0+t*(y1-y0))
    if len(intersections)<2:raise ValueError("vault center line does not cross actual platform polygon")
    return min(intersections),max(intersections)


def clean_boolean_mesh(obj, threshold=1e-6):
    """Controlled weld of Exact-Boolean tangent slivers on the new mesh only.

    Returns the vertex-set displacement bound and stores an audit history.
    Threshold is expressed in object-local metre coordinates. Coordinates are
    never rescaled. Call only on a working copy, never a frozen source object.
    """
    threshold=_positive("cleanup threshold",threshold)
    if threshold>1e-5:
        raise ValueError("Boolean cleanup threshold may not exceed 0.00001m")
    before=[vertex.co.copy() for vertex in obj.data.vertices]
    bm=F.bmesh.new()
    bm.from_mesh(obj.data)
    F.bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=threshold)
    F.bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=threshold)
    F.bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    after=[vertex.co.copy() for vertex in obj.data.vertices]
    kd=KDTree(len(after))
    for index,point in enumerate(after):kd.insert(point,index)
    kd.balance()
    distance=max((kd.find(point)[2] for point in before),default=0)
    world_scale=max(abs(value) for value in obj.matrix_world.to_scale())
    report={"threshold_local_m":threshold,"vertices_before":len(before),"vertices_after":len(after),
            "removed_vertices":len(before)-len(after),"max_vertex_shift_local_m":distance,
            "max_vertex_shift_m":distance*world_scale,
            "measurement":"Maximum pre-clean vertex distance to nearest post-clean vertex; includes merged/removed points, conservative world-scale bound.",
            "scope":"Only micron construction slivers; original source body must be copied before cleanup."}
    if distance>threshold*2:
        raise ValueError("Boolean cleanup moved a construction vertex beyond twice its threshold")
    history=json.loads(obj.get("boolean_cleanup_history","[]"))
    history.append(report)
    obj["boolean_cleanup_history"]=json.dumps(history)
    return report


def _apply_cutter(wall, cutter, name):
    if wall.data.users > 1:
        wall.data = wall.data.copy()
    previous = bpy.context.view_layer.objects.active
    try:
        bpy.context.view_layer.objects.active = wall
        modifier = wall.modifiers.new("Exact_" + name, "BOOLEAN")
        modifier.operation = "DIFFERENCE"
        modifier.solver = "EXACT"
        modifier.object = cutter
        bpy.context.view_layer.update()
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        # Exact compound mouth/vault cuts can leave coincident micron edges at
        # their tangent crown. Weld only sub-micrometre duplicate construction
        # points; preserve source footprint and arch dimensions.
        clean_boolean_mesh(wall,threshold=1e-6)
    finally:
        bpy.context.view_layer.objects.active = previous
        bpy.data.objects.remove(cutter, do_unlink=True)


def _polygon_platform(name, polygon, height, collection, material, cache):
    ring = F._clean_ring(polygon)
    surface = F._Surface()
    surface.face([(x, y, height) for x, y in ring])
    surface.face([(x, y, 0) for x, y in reversed(ring)])
    for first, second in zip(ring, ring[1:] + ring[:1]):
        surface.face([(first[0], first[1], 0), (second[0], second[1], 0),
                      (second[0], second[1], height), (first[0], first[1], height)])
    data = F._new_mesh(name, surface.vertices, surface.faces, material, cache,
                       ("monument_platform", tuple(ring), height))
    obj = F._object(name, data, collection, "gate_platform")
    obj["source_polygon_local"] = json.dumps(ring)
    obj["source_outline_policy"] = "Original local polygon, including collinear boundary points; no rectangle replacement"
    return obj


def build_monument(profile, collection, materials=None, mesh_cache=None):
    """Build a single-floor high hall or a three-arched gate tower.

    Required: building_id,name_zh,kind,anchor,rotation_z_radians,body_width_m,
    body_depth_m,ridge_height_m,platform_height_m,bays_x,bays_y,roof_type,
    material_scheme,dimension_evidence,verified_facts,uncertain_dimensions.
    kind is single_high_hall or gate_tower. Heights are local Z from anchor.
    Optional: platform_polygon_local, build_platform, platform_width_m/depth_m,
    own_plinth_width_m/depth_m, semantic_front, detail_parameters, parameter_evidence.
    The datum notes supplied by the caller are retained verbatim, never upgraded.
    """
    required = ("building_id", "name_zh", "kind", "anchor", "rotation_z_radians", "body_width_m",
                "body_depth_m", "ridge_height_m", "platform_height_m", "bays_x", "bays_y",
                "roof_type", "material_scheme", "dimension_evidence", "verified_facts", "uncertain_dimensions")
    for key in required:
        if key not in profile:
            raise ValueError("monument profile missing " + key)
    if profile["kind"] not in {"single_high_hall", "gate_tower"}:
        raise ValueError("unknown monument kind")
    if profile.get("full_geometry_eligible") is False:
        raise ValueError("profile does not authorize a complete geometry study")
    width, depth, ridge_top, platform_top = [_positive(key, profile[key]) for key in
                                            ("body_width_m", "body_depth_m", "ridge_height_m", "platform_height_m")]
    if platform_top >= ridge_top - 4:
        raise ValueError("height datum leaves no useful single hall")
    anchor = F._point("anchor", profile["anchor"])
    rotation = F._number("rotation_z_radians", profile["rotation_z_radians"])
    for key in ("bays_x", "bays_y"):
        if not isinstance(profile[key], int) or isinstance(profile[key], bool) or not 1 <= profile[key] <= 30:
            raise ValueError("explicit positive bay counts are required")
    if profile["roof_type"] not in {"wudian", "xieshan"}:
        raise ValueError("monuments require wudian or xieshan")
    materials = R.restoration_materials(materials)
    scheme = profile["material_scheme"]
    for key in ("main_roof", "roof_edge", "lower_eaves", "wall", "column"):
        if scheme.get(key) not in materials:
            raise ValueError("missing/unknown material scheme " + key)
    identifier = profile["building_id"]
    building = F.ensure_collection(identifier + "_单厅双檐研究", collection)
    structure = F.ensure_collection(identifier + "_通高主体", building)
    roof_collection = F.ensure_collection(identifier + "_双檐曲面", building)
    root = bpy.data.objects.new(identifier + "_monument_study", None)
    building.objects.link(root)
    root.location, root.rotation_euler.z = anchor, rotation
    objects, components, openings = [], {}, []
    assumptions = [{"id": "INPUT-" + str(index + 1), "status": "unmeasured", "note": note}
                   for index, note in enumerate(profile["uncertain_dimensions"])]
    assumptions += [{"id": "INPUT-STUDY-" + str(index + 1), "status": "assumption", "note": note}
                    for index, note in enumerate(profile.get("study_only_assumptions", []))]
    parameters = dict(profile.get("detail_parameters", {}))
    parameter_evidence = profile.get("parameter_evidence", {})

    def parameter(key, default, note):
        value = _positive(key, parameters.get(key, default))
        parameters[key] = value
        evidence = parameter_evidence.get(key, {})
        assumptions.append({"id": "MODEL-" + key, "value": value,
                            "status": evidence.get("status", "assumption"), "note": note,
                            "source_refs": evidence.get("source_refs", [])})
        return value

    def register(obj, role, tier=None):
        obj.parent = root
        obj["semantic_role"] = role
        obj["storey_index"] = 0
        if tier is not None:
            obj["roof_tier_index"] = tier
        components.setdefault(role, []).append(obj)
        objects.append(obj)
        return obj

    def box(name, center, dims, material, role):
        return register(F.box(identifier + "_" + name, center, dims, materials[material], structure, mesh_cache, role), role)

    corridor = parameter("veranda_depth_m", min(width, depth) * .075, "Wall inset from reference columns; unmeasured veranda depth.")
    wall_thickness = parameter("wall_thickness_m", .48, "Real substrate thickness is a study parameter.")
    column_radius = parameter("column_radius_m", min(width, depth) * .015, "Do not treat a generic column diameter as a surveyed value.")
    column_base_height = parameter("column_base_height_m", .24, "Column-base profile and contact endpoint are unmeasured.")
    overhang = parameter("roof_overhang_m", min(width, depth) * .07, "Roof eave envelope is separate from column-line span.")
    corner_lift = parameter("corner_lift_m", min(width, depth) * .025, "Corner uplift and roof curve are provisional.")
    hall_height = ridge_top - platform_top
    column_height = parameter("column_height_m", hall_height * .48, "Measured column height, if supplied, retains its endpoint note; otherwise a study proportion.")
    lower_eave = platform_top + column_base_height + column_height + .62
    upper_eave = platform_top + hall_height * .78
    lower_inner_top = platform_top + hall_height * .70
    if not lower_eave + .4 < lower_inner_top < upper_eave < ridge_top - .5:
        raise ValueError("column/eave study parameters conflict with supplied height datum")
    floor_z = platform_top
    semantic_front = profile.get("semantic_front", "negative-y")
    if semantic_front not in {"positive-y", "negative-y"}:
        raise ValueError("invalid semantic_front")
    front_sign = 1 if semantic_front == "positive-y" else -1
    platform_polygon = profile.get("platform_polygon_local")
    platform_width = _positive("platform_width_m", profile.get("platform_width_m", width + 8))
    platform_depth = _positive("platform_depth_m", profile.get("platform_depth_m", depth + 8))
    if platform_polygon:
        ring = F._clean_ring(platform_polygon)
        platform_width = max(p[0] for p in ring) - min(p[0] for p in ring)
        platform_depth = max(p[1] for p in ring) - min(p[1] for p in ring)
    else:
        ring = [(-platform_width/2,-platform_depth/2),(platform_width/2,-platform_depth/2),
                (platform_width/2,platform_depth/2),(-platform_width/2,platform_depth/2)]
    platform = None
    if profile["kind"] == "gate_tower" or profile.get("build_platform", True):
        platform = register(_polygon_platform(identifier + "_整体台体", ring, platform_top, structure,
                                               materials["red"] if profile["kind"] == "gate_tower" else materials["white_stone"], mesh_cache),
                            "gate_platform" if profile["kind"] == "gate_tower" else "study_platform")
    if profile["kind"] == "gate_tower":
        vault_width = parameter("vault_width_m", min(platform_width * .115, width / 5 * .78), "Three vault clear widths are not measured.")
        vault_crown = parameter("vault_crown_z_m", platform_top * .72, "Crown Z is a source-labelled study assumption.")
        vault_rise = parameter("vault_rise_m", vault_width / 2, "Semicircular default or caller-supplied ellipse, not a surveyed arch section.")
        spacing = parameter("vault_center_spacing_m", width * .25, "Vault center spacing is a study parameter.")
        mouth_depth=parameter("mouth_depth_m",1.0,"Short outer square entrance depth is unmeasured; engineering extensions do not redefine actual mouth positions.")
        mouth_height=parameter("mouth_height_m",vault_crown,"Outer square mouth head level is a study assumption.")
        spring = vault_crown - vault_rise
        if spring <= .5 or vault_crown >= platform_top - .4 or spacing <= vault_width + .2:
            raise ValueError("vault dimensions leave no spring, lintel or piers")
        for index, center_x in enumerate((-spacing, 0, spacing)):
            name = identifier + "_三券_" + str(index + 1)
            y_min,y_max=_polygon_y_range_at_x(ring,center_x)
            cutter_depth,center_y=y_max-y_min+2,(y_min+y_max)/2
            record = {"id": name, "type": "door", "aperture_role": "arched_gate_tunnel",
                      "kind":"vault","opening_type":"vault",
                      "wall": platform.name, "wall_side": "north_south", "storey_index": 0,
                      "local_x": center_x, "center_x": center_x, "center_y": center_y,
                      "bottom_z": 0, "cutter_bottom_z": -.20, "spring_z": spring, "crown_z": vault_crown,
                      "width": vault_width, "height": vault_crown, "clear_width_m": vault_width,
                      "clear_height_m": vault_crown, "depth": y_max - y_min,
                      "y_min": y_min, "y_max": y_max, "normal_axis": "Y",
                      "center_local": [center_x, center_y, vault_crown / 2], "normal_local": [0, 1, 0],
                      "vault_shape": "elliptical_arch_32_segments", "arch_rise_m": vault_rise,
                      "clearance_interpretation": "Full width below spring; elliptical crown narrows above spring. Width/height are bounding dimensions, not a rectangular net aperture.",
                      "destination": "visible_south_north_gate_tunnel", "geometry_status": "Exact Boolean applied",
                      "dimension_status": "study_assumption", "source_cutter_depth_m": cutter_depth}
            record.update({"mouth_height_m":mouth_height,"mouth_depth_m":mouth_depth,
                           "south_mouth_y":y_min,"north_mouth_y":y_max,
                           "gate_form":"square_outer_mouths_with_arched_inner_tunnel"})
            for part_index,cutter in enumerate(make_gate_cutters("TEMP_"+name,record,structure)):
                cutter.parent=root
                _apply_cutter(platform,cutter,name+"_"+str(part_index))
            openings.append(record)
        platform["applied_openings"] = json.dumps(openings, ensure_ascii=False)
        root["gate_platform_polygon_local"] = json.dumps(ring)
    if profile.get("own_plinth_width_m") and profile.get("own_plinth_depth_m"):
        plinth_h = parameter("own_plinth_height_m", .32, "Body's own Sumeru plinth height is unknown; do not relabel the shared three terraces.")
        box("本身须弥座研究", (0,0,floor_z-plinth_h/2),
            (profile["own_plinth_width_m"],profile["own_plinth_depth_m"],plinth_h), "white_stone", "own_plinth")
    floor = box("唯一殿身地板", (0, 0, floor_z - .075), (width + 2, depth + 2, .15), "white_stone", "floor")
    ceiling_z = lower_eave - .45
    box("通高殿身天花", (0, 0, ceiling_z), (width, depth, .14), "dark_wood", "ceiling")
    xs = [-width/2 + width*i/profile["bays_x"] for i in range(profile["bays_x"]+1)]
    ys = [-depth/2 + depth*i/profile["bays_y"] for i in range(profile["bays_y"]+1)]
    positions = [(x,-depth/2) for x in xs] + [(x,depth/2) for x in xs]
    positions += [(-width/2,y) for y in ys[1:-1]] + [(width/2,y) for y in ys[1:-1]]
    for index,(x,y) in enumerate(positions):
        base = register(F.column(identifier+"_柱础_"+str(index),(x,y,floor_z+column_base_height/2),
                                 column_radius*1.42,column_base_height,materials["white_stone"],structure,mesh_cache,20),"column_base")
        column = register(F.column(identifier+"_檐柱_"+str(index),(x,y,floor_z+column_base_height+column_height/2),
                                   column_radius,column_height,materials[scheme["column"]],structure,mesh_cache,24),"column")
        column["support_base"],column["floor_support"] = base.name,floor.name
    for sign in (-1,1):
        box("前后檐枋",(0,sign*depth/2,lower_eave-.46),(width+.35,.45,.45),"paint_blue","beam")
        box("侧檐枋",(sign*width/2,0,lower_eave-.46),(.45,depth+.35,.45),"paint_green","beam")
    inner_w,inner_d = width-2*corridor,depth-2*corridor
    wall_h = ceiling_z-.07-floor_z
    if min(inner_w,inner_d)<wall_thickness*3 or wall_h<2:
        raise ValueError("reference dimensions leave no usable high-hall shell")
    wall_z = floor_z+wall_h/2
    walls = {"south":box("厚南墙",(0,-inner_d/2,wall_z),(inner_w,wall_thickness,wall_h),scheme["wall"],"wall"),
             "north":box("厚北墙",(0,inner_d/2,wall_z),(inner_w,wall_thickness,wall_h),scheme["wall"],"wall"),
             "east":box("厚东墙",(inner_w/2,0,wall_z),(wall_thickness,inner_d,wall_h),scheme["wall"],"wall"),
             "west":box("厚西墙",(-inner_w/2,0,wall_z),(wall_thickness,inner_d,wall_h),scheme["wall"],"wall")}
    for side,wall in walls.items():wall["wall_side"]=side
    for side in ("south","north"):
        sign=1 if side=="north" else -1
        for index in range(profile["bays_x"]):
            x=-inner_w/2+inner_w*(index+.5)/profile["bays_x"]
            if identifier=="taihedian":
                door_bays=set(range(2,9)) if side=="south" else {4,5,6}
                window_bays={0,1,9,10} if side=="south" else set()
                if index not in door_bays|window_bays:continue
                central=index in door_bays
            elif identifier=="shenwumen":
                central=index in {1,2,3}
            else:
                central=index==profile["bays_x"]//2
            clear_w=inner_w/profile["bays_x"]*.70
            clear_h=wall_h*(.76 if central else .62)
            sill=.06 if central else wall_h*.20
            center=[x,sign*inner_d/2,floor_z+sill+clear_h/2]
            schedule={"id":identifier+"_"+side+"_"+str(index),"type":"door" if central else "window",
                      "center":center,"width":clear_w,"height":clear_h,"depth":wall_thickness+.8,"normal_axis":"Y",
                      "destination":"single_high_hall_interior" if central else "window_reveal_and_backing"}
            record=F.cut_opening(walls[side],schedule,structure,mesh_cache)
            record.update({"wall_side":side,"storey_index":0,"center_local":center,"normal_local":[0,sign,0],
                           "clear_width_m":clear_w,"clear_height_m":clear_h,"aperture_role":"hall_door" if central else "hall_window",
                           "geometry_status":"Exact Boolean applied","dimension_status":"study_assumption"})
            if identifier=="shenwumen":
                record.update({"aperture_role":"tower_facade_door" if central else "tower_end_window",
                               "category_status":"official_known" if central else "study_assumption",
                               "category_source_fact":"tower_front_back_door_bays" if central else None,
                               "category_assumption_id":None if central else "MODEL-shenwu_end_bay_windows"})
            openings.append(record)
            if central:
                record["door_pose"]="closed_reference_proxy_hideable_not_actual_leaf_count"
                panel=box("可隐藏闭门参考下板",(x,sign*(inner_d/2+.02),center[2]-clear_h*.325),
                          (clear_w*.96,.065,clear_h*.35),"red_lacquer","closed_door_reference")
                panel["not_actual_leaf_count"]=True
                panel2=box("可隐藏闭门参考格心",(x,sign*(inner_d/2+.02),center[2]+clear_h*.175),
                           (clear_w*.96,.04,clear_h*.64),"dark_wood","closed_door_reference")
                panel2["not_actual_leaf_count"]=True
                record["closed_reference_names"]=[panel.name,panel2.name]
            else:
                box("窗后暗玻璃",(x,sign*(inner_d/2-wall_thickness*.27),center[2]),(clear_w*.94,.035,clear_h*.94),"glass_dark","window_detail")
                for k in range(1,7):
                    xx=x-clear_w/2+clear_w*k/7
                    box("窗格竖棂",(xx,sign*(inner_d/2+wall_thickness/2+.03),center[2]),(.035,.06,clear_h*.96),"red_lacquer","window_detail")
                for k in (1,2,3):
                    box("窗格横棂",(x,sign*(inner_d/2+wall_thickness/2+.03),center[2]-clear_h/2+clear_h*k/4),(clear_w,.06,.04),"red_lacquer","window_detail")
    if identifier=="shenwumen":
        side_clear_w=parameter("side_door_clear_width_m",inner_d*.22,"Side door net width is a type-study assumption, not a surveyed opening.")
        side_clear_h=parameter("side_door_clear_height_m",wall_h*.76,"Side door net height is unmeasured; only two side leaves per door are source-known.")
        side_sill=parameter("side_door_sill_m",.06,"Side door sill height and floor relation are a model assumption.")
        if side_clear_w>=inner_d-wall_thickness*2 or side_sill+side_clear_h>=wall_h:
            raise ValueError("side door study parameters exceed the side wall")
        for side,sign in (("east",1),("west",-1)):
            center=[sign*inner_w/2,0,floor_z+side_sill+side_clear_h/2]
            schedule={"id":identifier+"_"+side+"_side_door","type":"door","center":center,
                      "width":side_clear_w,"height":side_clear_h,"depth":wall_thickness+.8,"normal_axis":"X",
                      "destination":"city_wall_and_ramp_connection_reference"}
            record=F.cut_opening(walls[side],schedule,structure,mesh_cache)
            record.update({"wall_side":side,"storey_index":0,"center_local":center,"normal_local":[sign,0,0],
                           "clear_width_m":side_clear_w,"clear_height_m":side_clear_h,"aperture_role":"tower_side_door",
                           "geometry_status":"Exact Boolean applied","dimension_status":"study_assumption",
                           "category_status":"official_known","category_source_fact":"tower_side_doors",
                           "leaf_count":2,"leaf_count_status":"official_known",
                           "door_pose":"closed_reference_proxy_hideable_leaf_count_known_shape_unmeasured"})
            leaves=[]
            for index in range(2):
                leaf=box(side+"_可隐藏双扇板门参考_"+str(index+1),
                         (sign*(inner_w/2+.02),side_clear_w*(-.25 if index==0 else .25),center[2]),
                         (.065,side_clear_w*.48,side_clear_h*.96),"red_lacquer","closed_door_reference")
                leaf["not_actual_leaf_count"]=False
                leaf["source_door_leaf_count"]=2
                leaf["door_leaf_index"]=index
                leaf["opening_id"]=record["id"]
                leaf["shape_and_pose_status"]="study_assumption"
                leaves.append(leaf.name)
            record["closed_reference_names"]=leaves
            record["door_leaf_names"]=leaves
            openings.append(record)
        assumptions.extend([
            {"id":"MODEL-shenwu_end_bay_windows","status":"study_assumption",
             "note":"Official evidence confirms three central door bays at each front/back eave, but does not establish the terminal-bay window category. Two end windows on each facade are study proxies, not verified historical window types."},
            {"id":"MODEL-shenwu_side_door_shape_pose","status":"study_assumption",
             "note":"Official evidence gives one double-leaf board door on each east/west side. Net dimensions, sill, thickness, panel proportions, plain material and closed pose are unmeasured study parameters; no exact carpentry or complete wall/ramp route is asserted."},
        ])
    upper_width_ratio=parameter("upper_width_ratio",.84,"Upper/lower reference width ratio is an OSM proxy or study parameter, not a surveyed eave width.")
    upper_depth_ratio=parameter("upper_depth_ratio",.76,"Upper/lower reference depth ratio is an OSM proxy or study parameter, not a surveyed eave depth.")
    if not .3<upper_width_ratio<.99 or not .3<upper_depth_ratio<.99:
        raise ValueError("upper reference ratios must fit inside the lower reference envelope")
    upper_width,upper_depth=width*upper_width_ratio,depth*upper_depth_ratio
    lower_objects=R._roof_geometry(identifier+"_下檐",width,depth,lower_eave,lower_inner_top,profile["roof_type"],
                                   materials[scheme["lower_eaves"]],materials[scheme["lower_eaves"]],materials["dark_wood"],
                                   roof_collection,mesh_cache,overhang,corner_lift,0,(upper_width*.94,upper_depth*.94))
    drum_w,drum_d=upper_width*.94,upper_depth*.94
    drum_bottom=lower_inner_top-.20
    drum_top=upper_eave-.20
    for sign in (-1,1):
        register(F.box(identifier+"_非使用屋顶承托带",(0,sign*drum_d/2,(drum_bottom+drum_top)/2),(drum_w,.35,drum_top-drum_bottom),
                       materials[scheme["wall"]],roof_collection,mesh_cache,"roof_drum"),"roof_drum",1)
        register(F.box(identifier+"_侧屋顶承托带",(sign*drum_w/2,0,(drum_bottom+drum_top)/2),(.35,drum_d,drum_top-drum_bottom),
                       materials[scheme["wall"]],roof_collection,mesh_cache,"roof_drum"),"roof_drum",1)
    upper_objects=R._roof_geometry(identifier+"_上檐",upper_width,upper_depth,upper_eave,ridge_top,profile["roof_type"],
                                   materials[scheme["main_roof"]],materials[scheme["roof_edge"]],materials["dark_wood"],
                                   roof_collection,mesh_cache,overhang*.72,corner_lift*.75,1,None)
    for tier,items in ((0,lower_objects),(1,upper_objects)):
        for obj in items:register(obj,obj["semantic_role"],tier)
    assumptions.extend([
        {"id":"MODEL-one-floor","status":"structural_contract","note":"Exactly one occupied floor and one high ceiling; lower/upper eaves and nonhabitable roof drum do not create a second storey."},
        {"id":"MODEL-column_grid","status":"assumption","note":"Reference spans are caller labelled; regular bay spacing is a type study, never surveyed individual bay widths or certified internal column locations."},
        {"id":"MODEL-height_datum","status":"model_interpretation","note":"Profile datum/evidence notes retained verbatim. Published building/total/ridge/ornament endpoints are not silently equated; local floor at platform top has no assumed extra historical offset."},
        {"id":"MODEL-shared_terraces","status":"not_reconstructed","note":"The three halls share historic three terraces. Only one study block is generated; terrace edge/center drainage elevations, layered widths and exact floor offset remain unresolved."},
        {"id":"MODEL-ornaments","status":"not_reconstructed","note":"No invented roof beasts, chiwen, carved stone, exact dougong or painted historical motifs; specified ornament heights are retained as evidence only."},
        {"id":"MODEL-vault_shape","status":"assumption","note":"Gate vault width, center spacing, spring/crown, tunnel thickness and 32-segment arch ellipse need measurement; actual subtractive openings are still provided."},
    ])
    bpy.context.view_layer.update()
    for record in openings:
        record["center_world"]=list(root.matrix_world@Vector(record["center_local"]))
        record["normal_world"]=list((root.matrix_world.to_3x3()@Vector(record["normal_local"])).normalized())
    for obj in [root]+objects:
        obj["monument_profile"]=json.dumps(profile,ensure_ascii=False)
        obj["assumptions"]=json.dumps(assumptions,ensure_ascii=False)
        obj["verified_facts"]=json.dumps(profile["verified_facts"],ensure_ascii=False)
        obj["building_id"]=identifier
        obj["semantic_front"]=semantic_front
        obj["representation"]="source-constrained single-high-hall monument study; NOT surveyed or complete restoration"
        obj["third_party_cost"]=0
    root["opening_records"]=json.dumps(openings,ensure_ascii=False)
    root["occupied_floor_count"]=1
    root["eave_tiers"]=2
    root["reference_column_center_spans_m"]=[width,depth]
    root["platform_polygon_local"]=json.dumps(ring)
    return {"root":root,"roots":[root],"collection":building,"objects":objects,"components":components,
            "openings":openings,"opening_records":openings,"assumptions":assumptions,
            "verified_facts":profile["verified_facts"],"parameters":parameters,
            "platform_bounds_local":[min(p[0] for p in ring),min(p[1] for p in ring),max(p[0] for p in ring),max(p[1] for p in ring)]}
