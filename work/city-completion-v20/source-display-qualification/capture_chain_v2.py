"""Pure strengthened exact formal-capture report binding. No geometry/native I/O."""

def require(ok,msg):
 if not ok:raise AssertionError(msg)

def validate_capture_chain(tests,factory_sha,binding_sha,actual_mesh_count):
 require(tests['schema']=='v20-source-bounded-formal-factory-tests/1','wrong actual formal factory-test schema')
 summary=tests['summary'];checks=tests['checks']
 require(type(summary['passed'])is int and type(summary['failed'])is int and summary['passed']>0 and summary['failed']==0,'strict actual capture counts required')
 require(summary['passed']==len(checks)and all(c['passed']is True for c in checks),'actual capture summary/check list differs')
 require(tests['actual_factory_build_completed']is True and tests['full_raw_evaluated_material_profile_capture']is True,'actual full factory capture not completed')
 require(tests['binding_sha256']==binding_sha and tests['native_opened']is False and tests['native_saved']is False,'capture binding/native scope differs')
 captures=[c for c in checks if c.get('factory_state_sha256')is not None]
 require(captures and all(c['factory_state_sha256']==factory_sha and type(c['actual_mesh_count'])is int and c['actual_mesh_count']==actual_mesh_count and c['full_raw_evaluated_material_profile_capture']is True for c in captures),'successful capture is not exact same canonical state/population')
 return True
