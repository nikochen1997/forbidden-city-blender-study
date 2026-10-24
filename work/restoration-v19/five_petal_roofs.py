"""Biluo fivefold curved roof study only. Caller owns placement, I/O and saving.

The five lobes are an explicit sinusoidal study contour, not a surveyed tracing.
No columns, floors, finial, mountain, bridge or source registration are created.
"""
import hashlib
import json
import math
import re

import forbidden_city_geometry as F
import restoration_buildings as R


def _number(name, value, minimum=None, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name + " must be a finite real number, not bool")
    if positive and value <= 0 or minimum is not None and value < minimum:
        raise ValueError(name + " outside explicit positive/minimum domain")
    return value


def _fact(p, name):
    value = p["known_facts"][name]
    return value.get("value") if isinstance(value, dict) else value


def _validate(p, materials):
    for key in ("building_id", "primitive_id", "symmetry_order", "eaves_tiers", "occupied_storeys",
                "reference_floor_count", "dimension_status", "phase_rad", "segments_per_sector", "radial_steps",
                "roof_tiers", "known_facts", "third_party_cost", "paid_service_calls", "human_approval", "absolute_accuracy_claim"):
        if key not in p:
            raise ValueError("missing explicit five-petal field " + key)
    if p["building_id"] != "biluoting" or not isinstance(p["primitive_id"], str) or not re.fullmatch(r"[A-Za-z0-9_]{1,80}", p["primitive_id"]):
        raise ValueError("qualified Biluo identity and explicit safe primitive name required")
    for key, expected in (("symmetry_order", 5), ("eaves_tiers", 2), ("reference_floor_count", 0), ("third_party_cost", 0), ("paid_service_calls", 0)):
        if type(p[key]) is not int or p[key] != expected:
            raise ValueError(key + " must be strict integer " + str(expected))
    if p["occupied_storeys"] is not None or p["human_approval"] != "pending" or p["absolute_accuracy_claim"] is not False or p["dimension_status"] != "unmeasured_study":
        raise ValueError("roof-only scope must retain null occupied floors, study dimensions and pending approval")
    expected = {"plan_shape": "five_lobed_plum", "roof_type": "double_eaved_five_sector_pyramidal", "eaves_tiers": 2,
                "ridge_count_each_tier": 5, "roof_upper_colour": "jade_green", "roof_lower_colour": "peacock_blue", "roof_both_edges_colour": "amethyst_purple"}
    if any(_fact(p, k) != v for k, v in expected.items()):
        raise ValueError("qualified documentary roof type/count/colour differs")
    for value in p["known_facts"].values():
        if isinstance(value, dict) and value.get("status") == "unknown" and value.get("value") is not None:
            raise ValueError("unknown documentary field promoted")
    phase = _number("phase_rad", p["phase_rad"])
    if not -2*math.pi <= phase <= 2*math.pi:
        raise ValueError("study phase must stay within one signed full turn")
    for key, low, high in (("segments_per_sector", 8, 96), ("radial_steps", 4, 64)):
        if type(p[key]) is not int or not low <= p[key] <= high:
            raise ValueError("invalid explicit tessellation " + key)
    if p["segments_per_sector"] % 4:
        raise ValueError("sector tessellation must sample quarter-sector and lobe maximum")
    if not isinstance(p["roof_tiers"], list) or len(p["roof_tiers"]) != 2:
        raise ValueError("exact lower/upper tiers required")
    for index, t in enumerate(p["roof_tiers"]):
        for key in ("tier_index", "outer_radius_m", "lobe_amplitude_m", "inner_radius_m", "inner_lobe_amplitude_m", "eave_z_m", "top_z_m", "skin_thickness_m", "curve_power",
                    "corner_lift_m", "edge_band_fraction", "ridge_radius_m", "ridge_offset_m", "tile_pitch_m", "tile_radius_m", "tile_offset_m", "tile_stop_fraction", "material_scheme"):
            if key not in t:
                raise ValueError("missing explicit tier field " + key)
        if type(t["tier_index"]) is not int or t["tier_index"] != index:
            raise ValueError("tier order must be strict integer lower0/upper1")
        for key in ("outer_radius_m", "lobe_amplitude_m", "skin_thickness_m", "curve_power", "ridge_radius_m", "tile_pitch_m", "tile_radius_m"):
            _number(key, t[key], positive=True)
        for key in ("inner_radius_m", "inner_lobe_amplitude_m", "corner_lift_m", "ridge_offset_m", "tile_offset_m"):
            _number(key, t[key], minimum=0)
        for key in ("eave_z_m", "top_z_m", "edge_band_fraction", "tile_stop_fraction"):
            _number(key, t[key])
        radius, amplitude = t["outer_radius_m"], t["lobe_amplitude_m"]
        rise = t["top_z_m"]-t["eave_z_m"]
        if not .02*radius <= amplitude <= .30*radius:
            raise ValueError("noncircular curved five-lobe amplitude must be 2..30 percent of junction radius")
        if not 1 <= t["curve_power"] <= 3 or rise <= 0 or t["corner_lift_m"] >= rise/3:
            raise ValueError("inverted/consumed curved roof rise")
        inner_max = t["inner_radius_m"]+t["inner_lobe_amplitude_m"]
        if (index == 0 and not 0 < t["inner_radius_m"] <= inner_max < radius*.8) or (index == 1 and inner_max != 0):
            raise ValueError("lower must have a real inner ring; upper must have one central apex")
        if t["inner_radius_m"] == 0 and t["inner_lobe_amplitude_m"] != 0:
            raise ValueError("zero inner radius cannot retain a lobe amplitude")
        if t["skin_thickness_m"] >= min(radius-inner_max, rise)/4:
            raise ValueError("skin consumes radial span or rise")
        if not .02 <= t["edge_band_fraction"] <= .20 or not t["edge_band_fraction"] < t["tile_stop_fraction"] <= .93:
            raise ValueError("explicit edge band/tile stop outside safe radial domain")
        if t["ridge_radius_m"] >= min(radius-inner_max, rise)/12 or t["ridge_offset_m"] > t["skin_thickness_m"]:
            raise ValueError("ridge tube exceeds controlled study skin envelope")
        if t["tile_radius_m"]*2 >= t["skin_thickness_m"] or t["tile_pitch_m"] <= 4*t["tile_radius_m"] or t["tile_offset_m"] > t["skin_thickness_m"]:
            raise ValueError("tile radius/spacing/offset exceeds explicit skin budget")
        if index == 1 and radius*(1-t["tile_stop_fraction"]) <= 3*t["tile_radius_m"]:
            raise ValueError("upper tile ribs collide at the apex")
        count = math.ceil(2*math.pi*(radius+amplitude*.5)/(5*t["tile_pitch_m"]))
        if not 2 <= count <= 128:
            raise ValueError("tile pitch produces an unsafe per-sector model count")
        scheme = t["material_scheme"]
        if set(scheme) != {"main", "edge", "under"} or any(not isinstance(k, str) or k not in materials or materials[k] is None for k in scheme.values()):
            raise ValueError("explicit caller main/edge/under materials required")
        if any(not isinstance(getattr(materials[k], "name", None), str) for k in scheme.values()):
            raise ValueError("caller materials must be named material datablocks")
        if len({id(materials[scheme[k]]) for k in ("main", "edge", "under")}) != 3:
            raise ValueError("main/edge/under must be distinct material datablocks")
    lower, upper = p["roof_tiers"]
    if upper["outer_radius_m"]+upper["lobe_amplitude_m"] >= lower["outer_radius_m"]:
        raise ValueError("upper eave must fit inside lower five-lobe envelope")
    if upper["outer_radius_m"] <= lower["inner_radius_m"]+lower["inner_lobe_amplitude_m"]+2*lower["ridge_radius_m"]:
        raise ValueError("upper roof does not cover lower ring aperture envelope")
    if upper["eave_z_m"]-upper["skin_thickness_m"] <= lower["top_z_m"]+lower["ridge_offset_m"]+lower["ridge_radius_m"]:
        raise ValueError("actual skin/ridge height envelopes of two tiers collide")
    json.dumps(p, ensure_ascii=False, allow_nan=False)


def _point(t, angle, fraction):
    wave = .5*(1-math.cos(5*angle))
    outer = t["outer_radius_m"]+t["lobe_amplitude_m"]*wave
    inner = t["inner_radius_m"]+t["inner_lobe_amplitude_m"]*wave
    radius = outer+(inner-outer)*fraction
    z = t["eave_z_m"]+(t["top_z_m"]-t["eave_z_m"])*fraction**t["curve_power"]
    z += t["corner_lift_m"]*(1-wave)*(1-fraction)**3
    return (radius*math.cos(angle), radius*math.sin(angle), z)


def build_five_petal_roofs(profile, collection, materials, mesh_cache=None):
    """Return local roof objects/components only; no implicit placement or support.

    outer_radius_m is the radius at five sector junctions, with each curved lobe
    bulging by lobe_amplitude_m midway between junctions. phase is a study axis,
    not an official column angle. Skin thickness is vertical, not tile normal.
    """
    _validate(profile, materials)
    p = profile
    cache = {} if mesh_cache is None else mesh_cache
    objects, components, records = [], {"roof": [], "ridge": [], "tile_ribs": []}, []
    serial = json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    profile_sha = hashlib.sha256(serial.encode()).hexdigest()
    phase, n, steps = p["phase_rad"], 5*p["segments_per_sector"], p["radial_steps"]

    def add(obj, role, index):
        obj.rotation_euler.z = phase
        obj["semantic_role"], obj["building_id"], obj["roof_tier_index"] = role, p["building_id"], index
        obj["profile_sha256"], obj["five_petal_profile"] = profile_sha, serial
        obj["symmetry_order"], obj["historical_ridge_count_each_tier"] = 5, 5
        obj["third_party_cost"], obj["paid_service_calls"], obj["human_approval"] = 0, 0, "pending"
        obj["absolute_accuracy_claim"], obj["reference_floor_only"] = False, False
        obj["scope"] = "unmeasured sinusoidal five-lobe roof study; no source registration, column angles, finial, floor or mountain"
        objects.append(obj)
        components[role].append(obj)
        return obj

    for t in p["roof_tiers"]:
        index, scheme = t["tier_index"], t["material_scheme"]
        triple = [materials[scheme[k]] for k in ("main", "edge", "under")]
        parameters = tuple((k, t[k]) for k in sorted(t) if k != "material_scheme")
        key = ("V19_five_petal_roof", parameters, p["segments_per_sector"], steps, tuple(m.name for m in triple))
        surface, indices = F._Surface(), []
        fractions = sorted(set([i/steps for i in range(steps+1)]+[t["edge_band_fraction"]]))
        for f0, f1 in zip(fractions, fractions[1:]):
            for i in range(n):
                a, b = 2*math.pi*i/n, 2*math.pi*(i+1)/n
                points = [_point(t, a, f0), _point(t, b, f0), _point(t, b, f1), _point(t, a, f1)]
                mi = 1 if f0 < t["edge_band_fraction"] else 0
                if index == 1 and f1 == 1:
                    R._face(surface, indices, mi, [points[0], points[1], (0, 0, t["top_z_m"])])
                else:
                    R._face(surface, indices, mi, [points[0], points[1], points[2]])
                    R._face(surface, indices, mi, [points[0], points[2], points[3]])
        count = len(surface.faces)
        R._closed_skin(surface, t["skin_thickness_m"])
        indices.extend([2]*(len(surface.faces)-count))
        prefix = "V19_"+p["primitive_id"]+"_tier"+str(index)
        roof = add(R._mesh(prefix+"_five_lobed_skin", surface, collection, triple, indices, cache, key+("skin",)), "roof", index)
        roof["annular"], roof["has_single_central_apex"] = index == 0, index == 1
        roof["roof_topology"] = "closed_five_lobed_annular_skin" if index == 0 else "closed_five_sector_skin_single_central_apex"
        ridge_names = []
        for sector in range(5):
            angle = 2*math.pi*sector/5
            points = [_point(t, angle, j/steps) for j in range(steps+1)]
            ridge_surface = F._Surface()
            F._tube(ridge_surface, [(x, y, z+t["ridge_offset_m"]) for x, y, z in points], t["ridge_radius_m"], 8)
            ridge = add(R._mesh(prefix+"_ridge"+str(sector), ridge_surface, collection, [triple[1]], cache=cache, key=key+("ridge", sector)), "ridge", index)
            ridge["sector_index"], ridge["intentionally_intersecting_detail"] = sector, True
            ridge_names.append(ridge.name)
        ribs = [F._Surface(), F._Surface()]
        per_sector = math.ceil(2*math.pi*(t["outer_radius_m"]+t["lobe_amplitude_m"]*.5)/(5*t["tile_pitch_m"]))
        for sector in range(5):
            for i in range(per_sector):
                angle = 2*math.pi*(sector+(i+.5)/per_sector)/5
                for dest, f0, f1 in ((1, 0, t["edge_band_fraction"]), (0, t["edge_band_fraction"], t["tile_stop_fraction"])):
                    points = [_point(t, angle, f0+(f1-f0)*j/steps) for j in range(steps+1)]
                    F._tube(ribs[dest], [(x, y, z+t["tile_offset_m"]) for x, y, z in points], t["tile_radius_m"], 6)
        for material_index, rib in enumerate(ribs):
            obj = add(R._mesh(prefix+"_tile_ribs"+str(material_index), rib, collection, [triple[material_index]], cache=cache, key=key+("tiles", material_index)), "tile_ribs", index)
            obj["intentionally_intersecting_detail"], obj["tile_count_is_model_tessellation"] = True, True
        records.append({"tier_index": index, "roof_object": roof.name, "ridge_objects": ridge_names,
                        "annular": index == 0, "eave_z_m": t["eave_z_m"], "skin_apex_or_inner_top_z_m": t["top_z_m"],
                        "material_scheme": dict(scheme), "dimension_status": "unmeasured_study", "roof_type": "five_lobed_five_sector_pyramidal"})
    return {"objects": objects, "components": components, "roofs": records, "profile": p,
            "occupied_storeys": None, "reference_floor_count": 0, "column_angles": None,
            "unbuilt_features": ["Historical exact lobe contour and physical tile cavity", "Columns, support band, finial and full plum ornament", "Source registration, floors, mountain support and bridge"],
            "third_party_cost": 0, "human_approval": "pending"}
