"""Pure V19 request validation and typed source selection; no Blender import."""
import hashlib
import json


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def record_sha(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def is_original_source_mesh(obj,sid):
    return obj.type=='MESH' and obj.get('source_building_id')==sid


def validate_request(request,model,manifest):
    require(request['schema']=='v19-readonly-current-V18-source-probe-request/1','wrong V19 request schema')
    require(request['native_sha256']==manifest['model_sha256'],'accepted native SHA differs from manifest')
    for key,expected in (('expected_mesh_count',manifest['scene_mesh_count']),
                         ('expected_source_mesh_count',manifest['original_source_mesh_count'])):
        require(type(request[key]) is int and request[key]==expected and expected>0,'wrong '+key)
    require(type(request['expected_camera_count']) is int and request['expected_camera_count']==136,
            'wrong expected_camera_count')
    selected=request['selected_part_ids'];neighbours=request['nearby_source_part_ids'];anchors=request['anchor_part_ids']
    require(len(selected)==5 and len(neighbours)==21 and anchors==[],'exact five targets and21 neighbours required')
    sids=selected+neighbours+anchors
    require(len(sids)==len(set(sids)),'duplicate source request')
    parts={r['id']:r for r in model['parts']}
    require(set(request['source_record_sha256'])==set(sids),'source hash coverage differs')
    for sid,digest in request['source_record_sha256'].items():
        require(sid in parts and record_sha(parts[sid])==digest,'source record SHA drift: '+sid)
    walls={r['id']:r for r in model['inner_walls']}
    wids=request['source_wall_line_ids']
    require(len(wids)==len(set(wids))==2 and set(request['source_wall_record_sha256'])==set(wids),'two unique walls required')
    for sid,digest in request['source_wall_record_sha256'].items():
        require(sid in walls and record_sha(walls[sid])==digest,'wall record SHA drift: '+sid)
    contexts=request['context_surface_requests']
    require(len(contexts)==5 and len({r['source_id'] for r in contexts})==5,'four paths andone garden context required')
    require(sum(r['layer']=='paths' for r in contexts)==4
            and sum(r['layer']=='landcover_polygons' for r in contexts)==1,'context layer inventory differs')
    for row in contexts:
        layer=row['layer'];sid=row['source_id'];records={r['id']:r for r in model[layer]}
        require(sid in records and record_sha(records[sid])==row['source_record_sha256'],'context source SHA drift: '+sid)
        prefix='路_' if layer=='paths' else '绿地_'
        require(row['recipe_actor_name']==prefix+sid and row['actor_name_is_recipe_expectation'] is True,
                'context actor recipe differs')
    require(request['allowed_hidden_source_actor_names']==[],'read-only request cannot grant hide permission')
    for key in ('third_party_cost','paid_service_calls'):
        require(type(request[key]) is int and request[key]==0,'budget must be integer0')
    require(request['native_save_allowed'] is False and request['render_allowed'] is False
            and request['producer_import_allowed'] is False,'read-only scope changed')
    return {'targets':5,'neighbours':21,'walls':2,'mapped_paths':4,'mapped_garden':1,
            'expected_meshes':request['expected_mesh_count'],'expected_sources':request['expected_source_mesh_count'],
            'expected_cameras_to_verify':136,'actual_native_read':False}
