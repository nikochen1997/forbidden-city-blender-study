"""Shared complete evaluated-WORLD fingerprint; no generator/producer imports.

Temporary own-hide changes only, restored in finally. Global viewport-hidden or
view-layer-excluded objects are rejected rather than silently hashed as proxies.
"""
from contextlib import contextmanager
import hashlib
import json

FIELDS=('vertices_world','faces','triangles_with_material_index','material_slots')

def require(ok,message):
    if not ok:raise AssertionError(message)

def evaluated_fingerprint(row):
    payload={key:row[key]for key in FIELDS}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,
        allow_nan=False,separators=(',',':')).encode()).hexdigest()

@contextmanager
def evaluated_batch(objects, bpy_module=None):
    if bpy_module is None:
        import bpy as bpy_module
    objects=list(objects)
    require(len({o.name for o in objects})==len(objects),'duplicate evaluated batch object')
    before={o.name:{'own_hide':bool(o.hide_get()),'hide_render':bool(o.hide_render),
        'global_hide_viewport':bool(o.hide_viewport),'parent':o.parent.name if o.parent else None}
        for o in objects}
    try:
        for o in objects:
            require(o.type=='MESH','evaluated batch requires mesh: '+o.name)
            require(not o.hide_viewport,'global viewport-hidden object cannot be evaluated without changing protected flag: '+o.name)
            require(o.name in bpy_module.context.view_layer.objects,'object excluded from current view layer: '+o.name)
        for o in objects:
            if before[o.name]['own_hide']:o.hide_set(False)
        bpy_module.context.view_layer.update()
        yield bpy_module.context.evaluated_depsgraph_get()
    finally:
        for o in objects:
            if bool(o.hide_get())!=before[o.name]['own_hide']:o.hide_set(before[o.name]['own_hide'])
        bpy_module.context.view_layer.update()
        for o in objects:
            actual={'own_hide':bool(o.hide_get()),'hide_render':bool(o.hide_render),
                'global_hide_viewport':bool(o.hide_viewport),'parent':o.parent.name if o.parent else None}
            require(actual==before[o.name],'temporary evaluated batch failed to restore protected visibility/parent: '+o.name)

def capture_evaluated(obj, graph):
    require(not obj.hide_get() and not obj.hide_viewport,'capture requires enabled own/global viewport state: '+obj.name)
    require(not obj.modifiers and obj.data.shape_keys is None,'unevaluated deformation requires separate evidence: '+obj.name)
    evaluated=obj.evaluated_get(graph)
    require([list(r)for r in evaluated.matrix_world]==[list(r)for r in obj.matrix_world],
        'evaluated WORLD matrix differs from actual object; hidden/layer proxy suspected: '+obj.name)
    mesh=evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        # These checks detect the hidden unit-cube proxy; actual evaluated values
        # below are still captured in full, never replaced by raw geometry.
        require([list(v.co)for v in mesh.vertices]==[list(v.co)for v in obj.data.vertices],
            'evaluated local vertices differ on modifier-free object; hidden/layer proxy suspected: '+obj.name)
        require([list(p.vertices)for p in mesh.polygons]==[list(p.vertices)for p in obj.data.polygons],
            'evaluated faces differ on modifier-free object: '+obj.name)
        return {'vertices_world':[list(evaluated.matrix_world@v.co)for v in mesh.vertices],
            'faces':[list(p.vertices)for p in mesh.polygons],
            'triangles_with_material_index':[[list(t.vertices),mesh.polygons[t.polygon_index].material_index]for t in mesh.loop_triangles],
            'material_slots':[m.name if m else None for m in mesh.materials]}
    finally:evaluated.to_mesh_clear()
