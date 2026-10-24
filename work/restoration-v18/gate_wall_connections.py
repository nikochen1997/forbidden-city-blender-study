"""V18 caller-only source-context wall extensions; not historical attachments."""
import hashlib
import json
import math

import forbidden_city_geometry as F

PROPOSAL_FILE_SHA256 = "07a3cbc19fe055bd5e472bc1736faa26067d79ba8b29fbfcdc0f27d83b37488a"
PROPOSAL_CANONICAL_SHA256 = "b01de22f06949c8401114b26807703514eb1a151d573a89463db149c8b7b2f23"
ROLE = "gate_wall_connection_reference"


def build_gate_wall_connections(result, materials, connection_doc):
    """Return {objects,components}; also append to result inventory. Caller owns save."""
    canonical = json.dumps(connection_doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if hashlib.sha256(canonical.encode()).hexdigest() != PROPOSAL_CANONICAL_SHA256:
        raise ValueError("frozen wall-connection proposal semantics differ")
    profile = result["profile"]
    if profile["building_id"] != "nansansuo_common_gate" or profile["source_part_id"] != "way-40544875-p0":
        raise ValueError("connections belong only to qualified common gate")
    if profile["dimensions"] != connection_doc["gate_profile_dimensions"]:
        raise ValueError("frozen gate controls differ")
    if profile["source_polygon_world"] != connection_doc["gate_source_polygon_world"] or profile["source_holes_world"] != connection_doc["gate_source_holes_world"]:
        raise ValueError("complete eight-point gate source differs")
    if result["components"].get(ROLE):
        raise ValueError("gate connections already built")
    if "grey" not in materials:
        raise ValueError("caller neutral grey material missing")
    root, collection = result["root"], result["collection"]
    anchor, theta = profile["anchor"], profile["rotation_z_rad"]
    c, s = math.cos(theta), math.sin(theta)
    objects, records = [], []
    for row in connection_doc["rows"]:
        side, proposal = row["side"], row["proposal"]
        ring = proposal["polygon_local"]
        if len(ring) != len(proposal["polygon_world"]):
            raise ValueError("proposal local/world vertices differ")
        for (x, y), world in zip(ring, proposal["polygon_world"]):
            if math.dist((anchor[0]+c*x-s*y, anchor[1]+s*x+c*y), world) > 1e-7:
                raise ValueError("proposal is not registered to actual gate frame")
        holes = [[(c*(x-anchor[0])+s*(y-anchor[1]), -s*(x-anchor[0])+c*(y-anchor[1])) for x,y in hole] for hole in proposal["holes_world"]]
        surface = F._Surface()
        for triangle in F._triangulate_rings([ring] + holes):
            surface.face([(x,y,proposal["top_z_m"]-anchor[2]) for x,y in triangle])
        F._volume_from_top(surface, proposal["bottom_z_m"]-anchor[2])
        name = "V18_nansansuo_common_gate_connection_" + side
        obj = F._object(name, F._new_mesh(name+"_mesh", surface.vertices, surface.faces, materials["grey"]), collection, ROLE)
        obj.parent = root
        obj["semantic_role"] = ROLE
        obj["building_id"] = profile["building_id"]
        obj["restoration_v18_context_id"] = "nansansuo_gate_connection_" + side
        obj["connection_proposal_sha256"] = PROPOSAL_FILE_SHA256
        obj["reference_old_wall_actor"] = row["original_wall_actor"]
        obj["unmeasured_source_context"] = True
        obj["not_historical_attachment"] = True
        obj["original_source_identifiers_not_inherited"] = True
        obj["complete_old_endcap_continuation_claimed"] = False
        obj["third_party_cost"] = 0
        obj["human_approval"] = "pending"
        obj["scope"] = "neutral clipped source-context extension; assumed old wall3m/0.6m; partial endcap join only; not measured masonry or new historical attachment"
        result["objects"].append(obj)
        result["components"].setdefault(ROLE, []).append(obj)
        objects.append(obj)
        slab = result["reference_floor"]
        record = {"component_id":obj["restoration_v18_context_id"], "role":ROLE, "side":side,
                  "objects":[obj.name], "parent":root.name, "gate_building_id":profile["building_id"],
                  "reference_floor":getattr(slab,"name",slab), "proposal_file_sha256":PROPOSAL_FILE_SHA256,
                  "polygon_world":proposal["polygon_world"], "holes_world":proposal["holes_world"],
                  "bottom_z_m":proposal["bottom_z_m"], "top_z_m":proposal["top_z_m"],
                  "reference_old_wall_actor":row["original_wall_actor"], "original_source_identifiers_inherited":False,
                  "full_old_endcap_width_claimed":False, "height_width_scope":"original wall unmeasured3m and0.6m controls; source-clipped partial endcap overlap",
                  "source_context_scope":"base overlaps source reference slab0..0.35; wall-height connection0.35..3.0; no measured floor contact or archaeological dimension",
                  "third_party_cost":0,"human_approval":"pending","not_historical_attachment":True}
        records.append(record)
    result["manifest"]["objects"] = [obj.name for obj in result["objects"]]
    result["gate_wall_connections"] = records
    root["v18_gate_wall_connections"] = json.dumps(records, ensure_ascii=False)
    return {"objects":objects, "components":records, "proposal_file_sha256":PROPOSAL_FILE_SHA256,
            "scope":"two neutral source-context connectors, independently audited; body manifest should be copied before this caller operation"}
