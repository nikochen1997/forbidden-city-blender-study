"""Minimal pure interface for a later actual V18 fixture; never builds geometry."""
import math


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def reference_count(profile, axis):
    factual = profile["bays_" + axis]
    study = profile.get("study_bays_" + axis)
    if factual is None:
        require(type(study) is int and 1 <= study <= 30, "explicit study count required for unknown " + axis)
        return study
    require(type(factual) is int and 1 <= factual <= 30, "invalid factual bay count")
    require(study is None or type(study) is int and study == factual, "study count disagrees with known count")
    return factual


def reference_axes(profile):
    axes = []
    for axis, dimension in (("x", "body_width_m"), ("y", "body_depth_m")):
        require(profile.get("column_bay_widths_" + axis + "_m") is None, "nonuniform grid needs a separately bound independent fixture")
        n = reference_count(profile, axis)
        extent = profile["dimensions"][dimension]
        require(type(extent) in (int, float) and math.isfinite(extent) and extent > 0, "positive finite reference extent required")
        axes.append([-extent / 2 + extent * i / n for i in range(n + 1)])
    xs, ys = axes
    perimeter = sorted({(x, y) for x in xs for y in (ys[0], ys[-1])} | {(x, y) for x in (xs[0], xs[-1]) for y in ys[1:-1]})
    return {"x": xs, "y": ys, "perimeter": perimeter,
            "factual_bays_x": profile["bays_x"], "factual_bays_y": profile["bays_y"],
            "reference_count_x": reference_count(profile, "x"), "reference_count_y": reference_count(profile, "y")}


def facade_plan(profile):
    plan = []
    for side in ("south", "north", "east", "west"):
        rows = profile["facades"][side]["schedule"] if side in ("south", "north") else [profile["facades"][side]]
        if side in ("south", "north"):
            require([r["bay_index"] for r in rows] == list(range(profile["bays_x"])), "complete facade reference schedule required")
        for index, row in enumerate(rows):
            require(row["leaf_count"] is None, "unknown leaf count promoted")
            require(row["kind"] in ("unresolved_wall", "door", "window"), "no implicit open passage or invented solid-wall fact")
            if row["kind"] in ("door", "window"):
                plan.append((side, index, row["kind"]))
    return plan


def check_profile_intent(profile, expectation):
    """Expectation is separately source-bound by caller, never inferred from names."""
    require(type(profile["third_party_cost"]) is int and profile["third_party_cost"] == 0, "integer-zero fee")
    require(type(profile["paid_service_calls"]) is int and profile["paid_service_calls"] == 0, "integer-zero service count")
    require(profile["occupied_storeys"] is None and profile["human_approval"] == "pending", "unknown storey or approval promoted")
    require(type(profile["reference_floor_count"]) is int and profile["reference_floor_count"] == 1, "one reference floor only")
    require(type(profile["eaves_tiers"]) is int and profile["eaves_tiers"] == 1, "one factual eave tier")
    require(profile["bays_x"] == expectation["width_bays"] and profile["bays_y"] == expectation["depth_bays"], "fact bay binding differs")
    axes = reference_axes(profile)
    roofs = profile["roof_tiers"]
    require(len(roofs) == 1 and roofs[0]["roof_type"] == expectation["roof_type"] and roofs[0]["annular"] is False, "roof intent differs")
    actual_plan = facade_plan(profile)
    expected_plan = [tuple(row) for row in expectation["apertures"]]
    require(actual_plan == expected_plan, "source-qualified aperture intent differs")
    if expectation["role"] == "common_gate":
        require(profile["bays_x"] == 3 and profile["bays_y"] == 1 and roofs[0]["roof_type"] == "xieshan", "common gate3x1/hip fact differs")
        require(actual_plan == [("south", 1, "door"), ("north", 1, "door")], "common gate central north/south doors required")
    else:
        require(expectation["role"] == "main_hall" and profile["bays_y"] is None and profile.get("study_bays_y") == 1 and roofs[0]["roof_type"] == "yingshan", "main hall factual depth must stay null with explicit study1")
        if actual_plan:
            require(expectation.get("caption_qualified_middle_hall") is True and profile["bays_x"] == 5, "specific caption/source match required before WWDWW")
            allowed = {("south", i, "door" if i == 2 else "window") for i in range(5)}
            require(set(actual_plan) <= allowed, "only individually qualified front-bay categories allowed")
    return {"reference_axes": axes, "expected_apertures": actual_plan,
            "unknown_set_proxy_count_expected": len(actual_plan), "actual_leaf_count": None,
            "runtime_passability_certified": False, "actual_geometry_verified": False}
