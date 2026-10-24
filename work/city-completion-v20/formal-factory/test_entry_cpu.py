"""Entry-only CPU tests with pinned production source; no native/geometry claims."""
import ast
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import formal_contract as K
import check_actual_production as C
import stage20_scene as B


def main():
    parser=__import__('argparse').ArgumentParser();parser.add_argument('--report',type=Path,required=True);a=parser.parse_args()
    K.require(not a.report.exists()and a.report.resolve().parent==K.HERE,'fresh entry-only report required')
    p,palette,*_=K.load_evidence();rows=[]
    def case(id,input,operation,expected,fn):
        try:result=fn();rows.append({'id':id,'input':input,'operation':operation,'expected':expected,'passed':True,'actual':result if result is not None else expected})
        except Exception as e:rows.append({'id':id,'input':input,'operation':operation,'expected':expected,'passed':False,'actual':type(e).__name__+': '+str(e)})
    def reject(fn):
        try:fn()
        except(AssertionError,ValueError,KeyError,TypeError):return '明确拒绝'
        raise AssertionError('negative accepted')
    def assert_true(v):assert v
    case('ENTRY-01','真实生产profile44fd、paletteb07、qualificationaf9、source7/0','按SHA读真实来源并检查schema/全环/场景guard','完整11点source及实际来源7/0通过；不代表factory',lambda:K.validate_profile(p,p))
    def origin():
        original=K.canonical(p);q=K.construction_profile(p)
        assert K.canonical(p)==original and q['anchor']==[0.,0.,0.]and q['rotation_z_rad']==0.
        assert q['source_polygon_world']==p['source_polygon_local']and q['source_holes_world']==p['source_holes_local']and len(q['source_polygon_world'])==11
        assert q['source_polygon_local']==p['source_polygon_local']and q['original_source_record']==p['original_source_record']
        return 'G14施工副本仅坐标框转换，原生产profile/完整原record未变；恢复WORLD仍待实际Blender'
    case('ENTRY-02','真实p与near-origin q','构造深拷贝并核对原p/完整环孔','q仅施工，绝非privatefixture或新来源资格',origin)
    binding={'inputs_sha256':{'entry_only':'not_real_factory_input'}}
    header={'schema':'v20-source-bounded-shouan-recess-actual-world/1','coordinate_space':'WORLD','profile':copy.deepcopy(p),
        'native_opened':False,'native_saved':False,'rendered':False,'production_build':True,'occupied_storeys':None,
        'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False,'source_visibility_changes':[],
        'inputs_sha256':binding['inputs_sha256'],'construction_frame_transform':{'method':'G14 near-origin full-source working copy, restore original p and unique newroot WORLD before observer/adapter',
            'original_anchor':p['anchor'],'original_rotation_z_rad':p['rotation_z_rad'],'working_anchor':[0.,0.,0.],'working_rotation_z_rad':0.,'full_source_rings_retained':True,'original_profile_unchanged':True},
        'protected_global_before':{'Cube':{},'Camera':{},'Light':{}},'protected_global_after':{'Cube':{},'Camera':{},'Light':{}}}
    case('ENTRY-03','明确synthetic header，非factory readout','只跑新入口header合同','header允许；绝不声称几何或native通过',lambda:K.validate_world_header(header,binding,p))
    cases=[('EXTRA-01',('third_party_cost',),False),('EXTRA-02',('third_party_cost',),-1),('EXTRA-03',('paid_service_calls',),1),
        ('EXTRA-04',('human_approval',),'approved'),('EXTRA-05',('native_opened',),True),('EXTRA-06',('production_build',),False),
        ('EXTRA-07',('schema',),'v20-private-shouan-recess-actual-world/1'),
        ('EXTRA-08',('profile','preparation_scope'),'private_fixture'),('EXTRA-09',('profile','allowed_hidden_source_actor_names'),[K.ACTOR]),
        ('EXTRA-10',('profile','eaves_tiers'),1),('EXTRA-11',('profile','occupied_storeys'),2),('EXTRA-12',('profile','factual_height_m'),6),
        ('EXTRA-13',('profile','source_polygon_world'),p['source_polygon_world'][:-1]),
        ('EXTRA-14',('profile','column_bay_widths_y_m'),list(reversed(p['column_bay_widths_y_m']))),
        ('EXTRA-15',('construction_frame_transform','original_anchor'),[0.,0.,0.]),
        ('EXTRA-16',('construction_frame_transform','full_source_rings_retained'),False),
        ('EXTRA-17',('protected_global_after','Cube'),{'global_hidden':True}),('EXTRA-18',('source_visibility_changes',),[K.ACTOR])]
    for id,path,val in cases:
        def invalid(path=path,val=val):
            d=copy.deepcopy(header);target=d
            for key in path[:-1]:target=target[key]
            target[path[-1]]=val
            return reject(lambda:K.validate_world_header(d,binding,p))
        case(id,str(path)+'='+str(val),'仅改private CPU header副本，再跑新source-bound入口','明确拒绝；不走validate_private、不造实际几何',invalid)
    def static():
        code=(K.HERE/'stage20_scene.py').read_text();tree=ast.parse(code)
        calls=[ast.unparse(n.func)for n in ast.walk(tree)if isinstance(n,ast.Call)]
        assert 'G._validate'in calls and 'G.build_hall'in calls and 'A.recess_geometry'in calls and 'build_private_shouan'not in code and 'validate_private'not in code
        assert not any(x in code for x in('open_mainfile','save_as_mainfile','hide_set','hide_viewport ='))
        assert code.index('G._validate(profile)')<code.index('q=K.construction_profile(profile)')<code.index('G.build_hall(q')<code.index('root.location=profile')<code.index('if observe_generated:observe_generated(result)')<code.index('A.recess_geometry')
        return '实际执行顺序静态校验；并非已执行Blender'
    case('ENTRY-04','新scene builder AST','检查near-origin→原WORLD→observer→低层adapter顺序','无privatewrapper/打开保存hide调用',static)
    def names():
        assert K.stable_mesh_name('owner')==K.stable_mesh_name('owner')and K.stable_mesh_name('owner')!=K.stable_mesh_name('other')
        assert K.stable_mesh_name('owner').isascii()and K.stable_mesh_name('owner').startswith('V20_SHOUAN79_MESH_')
        data=SimpleNamespace();objects=[SimpleNamespace(name='b',type='MESH',data=data),SimpleNamespace(name='a',type='MESH',data=data)]
        # Actual Blender datablock rename uses the same stable minimum owner
        # rule. This is a CPU algorithm fixture, not a Blender rename claim.
        assert K.stable_mesh_name(min(o.name for o in objects))==K.stable_mesh_name('a')
        return '稳定唯一V20数据名规则与共享owner最小名选择通过；实际冲突guard待Blender'
    case('ENTRY-05','多owner CPU数据名fixture','验证确定性V20名称/同share最小owner','不依赖factory或city原有mesh自动后缀',names)
    case('ENTRY-06','冻结checker8c0b 与容差','读取当前SHA/固定EPS/Z容差','8c0b原checker及100um/200um未改',lambda:assert_true(K.sha(K.path(C.FROZEN_CHECKER))==C.FROZEN_CHECKER_SHA and C.M.EPS==1e-4 and C.M.CONTACT.Z_TOL==2e-4))
    case('ENTRY-07','正式生产preserve入口源码','禁止调用旧private preserve/validate_private或修改profile为private','只复用未变wall_layout/aperture/support/contact函数',lambda:assert_true('M.preserve('not in(K.HERE/'check_actual_production.py').read_text()and 'validate_private('not in(K.HERE/'check_actual_production.py').read_text()))
    report={'schema':'v20-source-bound-formal-factory-entry-only-CPU/1','checks':rows,
        'summary':{'passed':sum(x['passed']for x in rows),'failed':sum(not x['passed']for x in rows)},
        'inputs_sha256':{str(f.relative_to(K.ROOT)):K.sha(f)for f in sorted(K.HERE.glob('*.py'))},
        'real_source_provenance_SHA_bound':True,'synthetic_header_only':True,'actual_factory_or_native_verified':False,
        'Blender_started':False,'geometry_created':False,'third_party_cost':0,'paid_service_calls':0,'human_approval':'pending','whole_city_complete':False}
    with a.report.open('x')as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(report['summary']))
    if report['summary']['failed']:
        print(json.dumps([x for x in rows if not x['passed']],ensure_ascii=False,indent=2));raise SystemExit(1)


if __name__=='__main__':main()
