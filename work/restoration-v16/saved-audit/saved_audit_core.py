"""Independent read-only Blender audit primitives. No builder imports or native saves.

This is a framework, not a passing V16 geometry audit. The final runner must bind
the actual V16 native, manifest, profiles and these files by immutable SHA first.
"""
import ast
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path

EPS = 2e-4  # evaluated float construction only; never historical survey accuracy
OLD_HELPER_SHA = "1ccce3fcca040d311f6c48fc52cd38cf053d484e627e20f03ad2f4a1c9eeb130"
BASELINE_NATIVE_SHA = "54a09df9df1030494bf354d06b9dfd96c05023e1f289c8c123579a8c1e673b38"


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4*1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def frozen_helpers(project_root):
    """Read only three pure AST functions; never execute an old producer module."""
    path = Path(project_root)/"work/build_forbidden_city_restoration_v11.py"
    require(sha(path) == OLD_HELPER_SHA, "frozen fingerprint helper drift")
    names = {"visibility", "material_state", "mesh_fingerprint"}
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in names]
    require({n.name for n in nodes} == names, "fingerprint helper AST inventory")
    ns = {"hashlib": hashlib, "json": json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
    return ns


def nonmesh_state(o, visibility):
    return {"type":o.type,"data":o.data.name if o.data else None,
            "matrix_world":[list(r) for r in o.matrix_world],
            "parent":o.parent.name if o.parent else None,"visibility":visibility(o),
            "color":list(o.color),"custom_properties":{k:str(o[k]) for k in o.keys()}}


def mesh_relations(o):
    return {"parent":o.parent.name if o.parent else None,"data_name":o.data.name,
            "collections":sorted(c.name for c in o.users_collection),
            "modifiers":[{"type":m.type,"name":m.name,"show_viewport":m.show_viewport,"show_render":m.show_render} for m in o.modifiers],
            "shape_keys_name":o.data.shape_keys.name if o.data.shape_keys else None}


def camera_state(c):
    keys=("type","lens","lens_unit","ortho_scale","sensor_width","sensor_height","sensor_fit",
          "shift_x","shift_y","clip_start","clip_end","display_size","passepartout_alpha","show_passepartout")
    dof=c.dof
    return {**{k:getattr(c,k) for k in keys},
            "dof":{"use_dof":dof.use_dof,"focus_object":dof.focus_object.name if dof.focus_object else None,
                   **{k:getattr(dof,k) for k in ("focus_distance","aperture_fstop","aperture_blades","aperture_rotation","aperture_ratio")}}}


def local_point(p,v):
    c,s=math.cos(p["rotation_z_rad"]),math.sin(p["rotation_z_rad"])
    x,y=v[0]-p["anchor"][0],v[1]-p["anchor"][1]
    return (c*x+s*y,-s*x+c*y,v[2]-p["anchor"][2])


def world_point(p,v):
    c,s=math.cos(p["rotation_z_rad"]),math.sin(p["rotation_z_rad"])
    return (p["anchor"][0]+c*v[0]-s*v[1],p["anchor"][1]+s*v[0]+c*v[1],p["anchor"][2]+v[2])


def close(a,b,message,tolerance=EPS):
    require(abs(a-b)<=tolerance,message+": "+repr((a,b)))


def bounds(points):
    require(points,"empty actual mesh")
    return ([min(v[i] for v in points) for i in range(3)], [max(v[i] for v in points) for i in range(3)])


def aabb_intersects_segment(start,end,box):
    t0,t1=0.0,1.0
    for axis in range(3):
        delta=end[axis]-start[axis]
        if abs(delta)<1e-12:
            if start[axis]<box[0][axis]-EPS or start[axis]>box[1][axis]+EPS:return False
        else:
            a=(box[0][axis]-EPS-start[axis])/delta;b=(box[1][axis]+EPS-start[axis])/delta
            t0,t1=max(t0,min(a,b)),min(t1,max(a,b))
            if t0>t1:return False
    return True


class MeshReader:
    def __init__(self,bpy):
        self.bpy=bpy
        self.cache={}
        self.box_cache={}
        self.refresh()

    def refresh(self,names=None):
        self.bpy.context.view_layer.update()
        self.depsgraph=self.bpy.context.evaluated_depsgraph_get()
        if names is None:self.cache.clear();self.box_cache.clear()
        else:
            for name in names:self.cache.pop(name,None);self.box_cache.pop(name,None)
        self.visible=sorted(o.name for o in self.bpy.context.scene.objects
                            if o.type=="MESH" and not o.hide_render and o.visible_get())

    def mesh(self,name):
        if name not in self.cache:
            from mathutils.bvhtree import BVHTree
            o=self.bpy.data.objects[name];evaluated=o.evaluated_get(self.depsgraph);mesh=evaluated.to_mesh()
            try:
                mesh.calc_loop_triangles()
                vertices=[evaluated.matrix_world@v.co for v in mesh.vertices]
                triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
                triangle_materials=[t.material_index for t in mesh.loop_triangles]
                require(vertices and triangles,"empty evaluated geometry "+name)
                self.cache[name]={"vertices":vertices,"triangles":triangles,
                                  "triangle_materials":triangle_materials,"bounds":bounds(vertices),
                                  "tree":BVHTree.FromPolygons(vertices,triangles,all_triangles=True,epsilon=0.0)}
            finally:evaluated.to_mesh_clear()
        return self.cache[name]

    def box(self,name):
        if name in self.cache:return self.cache[name]["bounds"]
        if name not in self.box_cache:
            from mathutils import Vector
            o=self.bpy.data.objects[name].evaluated_get(self.depsgraph)
            self.box_cache[name]=bounds([o.matrix_world@Vector(v) for v in o.bound_box])
        return self.box_cache[name]

    def ray(self,names,start,end):
        from mathutils import Vector
        start,end=Vector(start),Vector(end);direction=end-start;length=direction.length
        require(length>1e-12,"zero-length audit ray")
        direction.normalize();nearest=None
        for name in names:
            if not aabb_intersects_segment(start,end,self.box(name)):continue
            m=self.mesh(name)
            point,normal,tri,distance=m["tree"].ray_cast(start,direction,length)
            if point is not None and distance<=length+1e-8 and (nearest is None or distance<nearest["distance"]):
                nearest={"object":name,"point":point,"normal":normal,"triangle":tri,"distance":distance}
        return nearest


def closed_positive_topology(m):
    """All triangle components, direction-paired edges, and stable signed volumes."""
    vertices=m["vertices"];triangles=m["triangles"]
    require(all(math.isfinite(float(v)) for p in vertices for v in p),"nonfinite actual vertex")
    oriented={};adj=[set() for _ in triangles];owners={};degenerate=[]
    for i,tri in enumerate(triangles):
        a,b,c=[vertices[k] for k in tri]
        if ((b-a).cross(c-a)).length<=1e-12:degenerate.append(i)
        require(len(set(tri))==3,"triangle repeats index")
        for a,b in zip(tri,tri[1:]+tri[:1]):
            oriented[(a,b)]=oriented.get((a,b),0)+1
            key=tuple(sorted((a,b)));owners.setdefault(key,[]).append(i)
    require(not degenerate,"zero-area actual triangles "+repr(degenerate[:8]))
    require(all(len(value)==2 for value in owners.values()),"actual boundary/nonmanifold edge")
    require(all(n==1 and oriented.get((b,a))==1 for (a,b),n in oriented.items()),"actual normals/winding disagree")
    for pair in owners.values():
        adj[pair[0]].add(pair[1]);adj[pair[1]].add(pair[0])
    todo=set(range(len(triangles)));volumes=[]
    while todo:
        seed=todo.pop();component={seed};stack=[seed]
        while stack:
            i=stack.pop()
            for j in adj[i]&todo:todo.remove(j);component.add(j);stack.append(j)
        # Translate to one component vertex so large city offsets cannot dominate cancellation.
        origin=vertices[triangles[seed][0]]
        volume=math.fsum((vertices[a]-origin).dot((vertices[b]-origin).cross(vertices[c]-origin))/6
                         for i in component for a,b,c in [triangles[i]])
        require(volume>1e-10,"actual component has zero/negative volume")
        volumes.append(volume)
    return {"triangles":len(triangles),"edge_pairs":len(owners),"component_signed_volumes_m3":volumes,"degenerate_triangles":0}


class BaselineGuard:
    """Binds every old mesh, relationship, material and camera, not just targets."""
    def __init__(self,bpy,project_root,evidence_folder,allowed_visibility):
        self.bpy=bpy;self.functions=frozen_helpers(project_root);self.allowed_visibility=allowed_visibility
        p=Path(evidence_folder)
        self.old=json.loads((p/"base-mesh-fingerprints.json").read_text())
        self.other=json.loads((p/"base-nonmesh-state.json").read_text())
        self.materials=json.loads((p/"base-material-state.json").read_text())
        self.relations=json.loads((p/"base-mesh-relations.json").read_text())
        self.cameras=json.loads((p/"base-camera-state.json").read_text())
        require(len(self.old)==13115 and set(self.relations)==set(self.old),"full old mesh/relations inventory missing")
        require(set(allowed_visibility)<=set(self.old),"allowlist references non-old actor")

    def one_mesh(self,name):
        o=self.bpy.data.objects[name]
        require(self.functions["mesh_fingerprint"](o)==self.old[name]["fingerprint"],"old raw/material/matrix/provenance changed "+name)
        require(mesh_relations(o)==self.relations[name],"old parent/data/collection/modifier/shape relation changed "+name)
        expected=self.allowed_visibility.get(name,self.old[name]["visibility"])
        require(self.functions["visibility"](o)==expected,"old visibility outside exact allowed change "+name)
        require(not o.modifiers and o.data.shape_keys is None,"old evaluation deformation unreviewed "+name)

    def check(self):
        for name in self.old:self.one_mesh(name)
        for name,expected in self.materials.items():
            require(canonical(self.functions["material_state"](self.bpy.data.materials[name]))==canonical(expected),"old material graph changed "+name)
        for name,expected in self.other.items():
            require(nonmesh_state(self.bpy.data.objects[name],self.functions["visibility"])==expected,"old nonmesh changed "+name)
        for name,expected in self.cameras.items():
            obj=self.bpy.data.objects[name]
            require(obj.type=="CAMERA" and obj.data is not None,"old camera object/data binding changed "+name)
            require(canonical(camera_state(obj.data))==canonical(expected),"old actual camera projection/DOF changed "+name)
        return {"all_old_meshes":len(self.old),"all_old_materials":len(self.materials),
                "all_old_nonmesh":len(self.other),"all_old_camera_data":len(self.cameras),
                "exact_visibility_exception_count":len(self.allowed_visibility)}


@contextmanager
def moved_and_restored(bpy,reader,names,axis=0,delta=1000):
    """Infills alone may be moved for wall-only Boolean checks, never neighbors."""
    require(len(set(names))==len(names),"duplicate movement request")
    before={n:bpy.data.objects[n].matrix_basis.copy() for n in names}
    try:
        for n in names:bpy.data.objects[n].location[axis]+=delta
        reader.refresh(names);yield
    finally:
        for n,m in before.items():bpy.data.objects[n].matrix_basis=m
        reader.refresh(names)


def negative_rejected(fn):
    try:fn()
    except AssertionError as exc:return {"same_real_checker_rejected":True,"reason":str(exc)}
    raise AssertionError("negative control accepted by actual checker")


class RunGuard:
    def __init__(self,bpy,baseline,new_names,files):
        self.bpy,self.baseline,self.new_names=bpy,baseline,set(new_names)
        self.files={str(Path(p).resolve()):sha(p) for p in files}
        self.counts={k:len(getattr(bpy.data,k)) for k in ("objects","meshes","materials","collections","cameras","images","curves")}
        self.new=self.snapshot_new()
        self.all_materials={m.name:baseline.functions["material_state"](m) for m in bpy.data.materials}

    def snapshot_new(self):
        f=self.baseline.functions;out={}
        for n in self.new_names:
            o=self.bpy.data.objects[n]
            out[n]={"fingerprint":f["mesh_fingerprint"](o),"visibility":f["visibility"](o),"relations":mesh_relations(o)} if o.type=="MESH" else nonmesh_state(o,f["visibility"])
        return out

    def check(self):
        require(self.counts=={k:len(getattr(self.bpy.data,k)) for k in self.counts},"temporary data blocks remain")
        self.baseline.check()
        require(self.new==self.snapshot_new(),"negative control altered actual new state")
        require(canonical(self.all_materials)==canonical({m.name:self.baseline.functions["material_state"](m) for m in self.bpy.data.materials}),"negative control altered material graph")
        require(all(sha(p)==h for p,h in self.files.items()),"native or input bytes changed")
        return {"all_old_and_new_restored":True,"counts_restored":True,"all_inputs_unchanged":True,"native_saved":False}
