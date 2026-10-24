"""Use one world-coordinate path for four new study slabs' shared cutlines."""
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import forbidden_city_geometry as F

TARGETS = {'shufang_front_hall', 'shufang_rear_hall', 'shufang_large_stage', 'baohuadian_main'}


def align_new_reference_floor(profile, result):
    ident = profile['building_id']
    assert ident in TARGETS
    slab, root = result['reference_floor'], result['root']
    if isinstance(slab, str):
        slab = bpy.data.objects[slab]
    assert slab in result['objects'] and slab.parent == root
    assert slab.get('semantic_role') == 'source_reference_slab'
    assert slab.data.users == 1 and not slab.modifiers
    assert 'source_building_id' not in slab
    d = profile['dimensions']
    bottom = d['slab_bottom_z_m'] if profile['builder'] == 'stage' else d['source_reference_slab_bottom_z_m']
    top = d['floor_z_m']
    rings = [F._clean_ring(profile['source_polygon_world'])]
    rings += [F._clean_ring(r) for r in profile['source_holes_world']]
    surface = F._Surface()
    for tri in F._triangulate_rings(rings):
        surface.face([(x, y, profile['anchor'][2] + top) for x, y in tri])
    F._volume_from_top(surface, profile['anchor'][2] + bottom)
    old_data = slab.data
    materials = list(old_data.materials)
    assert len(materials) == 1 and materials[0] is not None
    replacement = F._new_mesh('R17_' + ident + '_world_source_slab', surface.vertices, surface.faces, materials[0])
    slab.data = replacement
    slab.parent = None
    slab.matrix_world = Matrix.Identity(4)
    slab['world_source_slab_parent_exception'] = True
    slab['logical_building_root'] = root.name
    slab['coordinate_scope'] = 'Complete registered source rings in global identity coordinates; all adjoining slab endpoints take the same float32 path.'
    slab['not_measured_platform'] = True
    if old_data.users == 0:
        bpy.data.meshes.remove(old_data)
    bpy.context.view_layer.update()
    assert slab.parent is None and slab.matrix_world == Matrix.Identity(4)
    return {'object': slab.name, 'building_id': ident, 'logical_building_root': root.name,
            'parent': None, 'matrix_world': [list(row) for row in slab.matrix_world],
            'scope': 'Only new full-source reference slab changed; all historical dimensions remain unknown.'}
