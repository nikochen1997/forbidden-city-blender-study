"""Read-only evidence qualification; writes readiness into this directory only.

No Blender, generator import, source hide, native write or network is used.
SHA maps are followed only when the owning JSON explicitly binds path/digest.
"""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V19 = 'work/restoration-v19/'
FIVE = ['fuwangge', 'juanqinzhai', 'yucuixuan', 'zhuxiangguan', 'biluoting']
FOUR = set(FIVE)-{'zhuxiangguan'}
PRODUCER = V19+'produce_city_progress_v19.py'
DOCS = {
    'hall_profiles': V19+'hall-profile-prep/building-profiles-v1.json',
    'hall_palette': V19+'hall-profile-prep/palette-v1.json',
    'fuwang_profiles': V19+'fuwang-profile-prep/prepared-01/production-profiles.json',
    'fuwang_registry': V19+'fuwang-profile-prep/prepared-01/production-registry.json',
    'fuwang_palette': V19+'fuwang-profile-prep/prepared-01/production-palette.json',
    'biluo_profile': V19+'biluo-pavilion-prep/profile-v2.json',
    'biluo_palette': V19+'biluo-pavilion-prep/palette-v1.json',
}
FACTORY = V19+'formal-factory-run-03/actual-world-geometry.json'
BILUO = V19+'biluo-pavilion-prep/run-01/actual-geometry.json'
PROBE = V19+'registration/actual-source-actors.json'
QUAL = V19+'progress-source-qualification/four-progress-source-mapping-01.json'
GROUPS = {
    'formal_factory': (3, V19+'formal-factory-run-03/actual-tests.json'),
    'formal_source': (5, V19+'formal-factory-run-03/actual-source-domains-CPU-01.json'),
    'formal_roof_contact': (100, V19+'formal-factory-run-03/actual-full-roof-contact-CPU-01.json'),
    'formal_support': (10, V19+'formal-support-review/formal-support-CPU-01.json'),
    'biluo_factory': (11, V19+'biluo-pavilion-prep/run-01/actual-tests.json'),
    'biluo_full_domains': (6, V19+'biluo-pavilion-prep/run-01/actual-full-domains-01.json'),
    'source_qualification': (9, V19+'progress-source-qualification/CPU-checks-01.json'),
}
CHECKERS = {
    'formal_source': V19+'check_formal_source_domains.py',
    'formal_roof_contact': V19+'tower-qa/check_actual_contact_domains.py',
    'formal_support': V19+'formal-support-review/review_formal_supports.py',
    'biluo_full_domains': V19+'biluo-pavilion-prep/check_actual_domains.py',
    'source_qualification': V19+'progress-source-qualification/qualify_progress_sources.py',
}
EXPLICIT = [
    PRODUCER, V19+'scene_assemblies.py', V19+'saved-audit/evaluated_geometry_fingerprint.py',
    'work/build_forbidden_city_restoration_v11.py', 'work/build_forbidden_city_restoration_v15.py',
    V19+'check_formal_contacts.py', V19+'formal-support-review/fuwang-support-CPU-01.json',
    V19+'progress-source-qualification/execution-receipt-01.json',
    V19+'biluo-pavilion-prep/render-review-01/root-media-review-01.json',
]


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4194304), b''):
            h.update(block)
    return h.hexdigest()


def read(relative):
    return json.loads((ROOT/relative).read_text())


def write(path, value):
    require(path.parent == HERE and not path.exists(), 'fresh own-directory output required')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def pure_producer():
    tree = ast.parse((ROOT/PRODUCER).read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'require', 'validate_ready'}]
    namespace = {'FIVE': FIVE, 'FOUR': FOUR, 'Path': Path, 'ROOT': ROOT, 'sha': sha,
                 'ACTORS': {'fuwangge': 'way-40629261-p0_原轮廓主体', 'juanqinzhai': 'way-1341826246-p0_原轮廓主体',
                            'yucuixuan': 'way-40629263-p0_原轮廓主体', 'biluoting': 'way-43525093-p0_原轮廓主体'}}
    require(len(nodes) == 2, 'pure function extraction differs')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT/PRODUCER), 'exec'), namespace)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    loops = [n for n in main.body if isinstance(n, ast.For)]
    # The actual pure main binding loops after protected SHA iteration and before
    # qualification. No saving, factory import, base-native load or Blender call.
    main_binding = loops[1:5]
    require(len(main_binding) == 4, 'producer pure binding-loop inventory differs')
    helpers = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'HELPERS' for t in n.targets))
    namespace['HELPERS'] = ast.literal_eval(helpers)
    namespace['read'] = lambda p: json.loads(Path(p).read_text())
    binding_code = compile(ast.Module(body=main_binding, type_ignores=[]), str(ROOT/PRODUCER), 'exec')
    def validate(value):
        namespace['validate_ready'](value)
        local = dict(namespace, ready=value, protected={str((ROOT/p).resolve()): h for p, h in value['protected_inputs'].items()}, documents={})
        exec(binding_code, local)
        return True
    return validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution-receipt', required=True)
    parser.add_argument('--output', default='readiness-02.json')
    parser.add_argument('--test-output', default='CPU-tests-02.json')
    args = parser.parse_args()
    receipt_path = Path(args.execution_receipt)
    if receipt_path.is_absolute():
        receipt_path = receipt_path.resolve().relative_to(ROOT)
    receipt_path = receipt_path.as_posix()
    execution = read(receipt_path)
    protected, provenance, queue, historical_edges = {}, {}, [], []
    # The current actual factories/checkers explicitly pin their prerequisite
    # files. Those bytes are all bound; their old pipeline snapshots are not
    # recursively reinterpreted as current runtime requirements.
    active_map_owners = {FACTORY, BILUO, PROBE, QUAL, receipt_path, *DOCS.values(),
                         *[p for _, p in GROUPS.values()],
                         V19+'formal-support-review/fuwang-support-CPU-01.json',
                         V19+'progress-source-qualification/execution-receipt-01.json',
                         V19+'biluo-pavilion-prep/render-review-01/root-media-review-01.json'}

    def bind(relative, digest=None, owner='explicit input'):
        path = (ROOT/relative).resolve()
        require(path.is_relative_to(ROOT), 'escaped bound file: '+str(relative))
        rel = path.relative_to(ROOT).as_posix()
        if digest is not None and (path.suffix.lower() == '.blend' or rel == 'work/render-delivery-policy.json'):
            historical_edges.append({'path': rel, 'historical_expected_sha256': digest, 'owner': owner,
                'active_dependency': False, 'not_recreated_or_read': True,
                'reason': 'Historical prerequisite snapshot only; producer independently binds accepted V18 native. Old native cleanup and mutable delivery policy do not become current construction dependencies.'})
            return digest
        require(path.is_file(), 'missing bound file: '+str(relative)+' owner '+owner)
        actual = sha(path)
        require(digest is None or actual == digest, 'input SHA drift: '+rel+' bound by '+owner)
        require(rel not in protected or protected[rel] == actual, 'conflicting input digest')
        if rel not in protected:
            protected[rel] = actual
            provenance[rel] = owner
            if path.suffix == '.json' and rel in active_map_owners:
                queue.append(rel)
        return actual

    for path in [*DOCS.values(), FACTORY, BILUO, PROBE, QUAL, receipt_path,
                 *EXPLICIT, *CHECKERS.values(), *[p for _, p in GROUPS.values()],
                 str(Path(__file__).relative_to(ROOT))]:
        bind(path)

    # These explicit path->SHA maps are actual dependencies, not arbitrary work scans.
    def bound_maps(value, owner):
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, dict) and ('sha256' in key or key == 'protected_inputs'):
                    for path, digest in child.items():
                        if (isinstance(path, str) and (path.startswith(('work/', 'outputs/')) or path.startswith(str(ROOT)))
                                and isinstance(digest, str) and len(digest) == 64
                                and all(c in '0123456789abcdef' for c in digest)):
                            bind(path, digest, owner+' -> '+key)
                bound_maps(child, owner)
        elif isinstance(value, list):
            for child in value:
                bound_maps(child, owner)

    while queue:
        relative = queue.pop(0)
        bound_maps(read(relative), relative)

    factory, biluo, probe, qualification = [read(p) for p in (FACTORY, BILUO, PROBE, QUAL)]
    require(factory['schema'] == 'v19-three-formal-body-actual-world/1', 'wrong formal factory schema')
    require(len(factory['objects']) == 431 and {b['building_id'] for b in factory['buildings']} == FOUR-{'biluoting'}, 'formal inventory differs')
    require(len(biluo['geometry']) == 43, 'Biluo actual mesh inventory differs')
    require(qualification['this_mapping_count'] == 4 and qualification['not_equal_to_five_complete'] is True,
            'source qualification scope lost')
    require(qualification['hide_permission_granted_by_this_package'] is False
            and qualification['absolute_historical_identity_approved'] is False, 'source qualification promoted')
    require(qualification['source_probe_native_sha256'] == '1b3d14372e4756432c1f6513e59217a0410afe85b53ca69849cec338be502122', 'qualification base drift')
    actual_actors = {e['actual_actor_name'] for e in qualification['entries']}
    require(len(actual_actors) == 4, 'four distinct source actors required')
    require(set(qualification['proposed_replace_actor_names']) == actual_actors
            and actual_actors.issubset(probe['actor_evidence']), 'qualification/probe actor mismatch')

    evidence_rows = {row['group']: row for row in execution['observations']}
    qualification_execution = read(V19+'progress-source-qualification/execution-receipt-01.json')['actual_CPU']
    evidence_rows['source_qualification'] = {'actual_terminal_exit_code': qualification_execution['terminal_exit_code'],
                                             'report_sha256': qualification_execution['report_sha256']}
    checks = {}
    for group, (count, path) in GROUPS.items():
        report = read(path)
        summary = report.get('summary', report)
        require(type(summary['passed']) is int and summary['passed'] == count
                and type(summary['failed']) is int and summary['failed'] == 0, 'report count differs: '+group)
        require(report.get('human_approval', 'pending') == 'pending'
                and report.get('whole_city_complete', False) is False, 'report approval promoted: '+group)
        if group in {'formal_factory', 'formal_source', 'formal_roof_contact', 'formal_support'}:
            digest = report.get('actual_geometry_sha256', report.get('actual_readout_sha256', report.get('actual_run03_readout_sha256')))
            require(digest == protected[FACTORY], 'wrong formal actual readout chain: '+group)
        elif group in {'biluo_factory', 'biluo_full_domains'}:
            require(report.get('actual_geometry_sha256', report.get('actual_readout_sha256')) == protected[BILUO], 'wrong Biluo actual readout chain: '+group)
        if group in CHECKERS:
            own_sha = report.get('checker_sha256', report.get('script_sha256', report.get('independent_reader_sha256')))
            if group == 'source_qualification':
                own_sha = read(V19+'progress-source-qualification/execution-receipt-01.json')['actual_CPU']['checker_sha256']
            require(own_sha == protected[CHECKERS[group]], 'checker/report SHA mismatch: '+group)
        for list_key in ('checks', 'tests', 'contacts'):
            rows = report.get(list_key)
            if rows:
                require(all(r.get('passed') is True for r in rows), 'a report check is not true: '+group)
        actual = evidence_rows.get(group)
        require(isinstance(actual, dict), 'missing actual terminal evidence: '+group)
        require(type(actual['actual_terminal_exit_code']) is int and actual['actual_terminal_exit_code'] == 0,
                'terminal was not actual integer0: '+group)
        require(actual['report_sha256'] == protected[path], 'terminal receipt/report SHA mismatch: '+group)
        group_receipt = V19+'progress-source-qualification/execution-receipt-01.json' if group == 'source_qualification' else receipt_path
        checks[group] = {'passed': count, 'failed': 0, 'actual_terminal_exit_code': 0,
                         'path': path, 'sha256': protected[path], 'execution_receipt': group_receipt,
                         'execution_receipt_sha256': protected[group_receipt]}

    ready = {'schema': 'v19-four-progress-independent-readiness/1', 'stage19_targets': FIVE,
             'modeled_this_progress': sorted(FOUR), 'pending_registration': ['zhuxiangguan'],
             'all_required_actual_factory_and_CPU_checks_passed': True, 'third_party_cost': 0, 'paid_service_calls': 0,
             'human_approval': 'pending', 'whole_city_complete': False, 'documents': DOCS,
             'source_probe': PROBE, 'source_qualification': QUAL, 'factory_three': FACTORY, 'factory_biluo': BILUO,
             'protected_inputs': dict(sorted(protected.items())), 'checks': checks,
             'qualification_limits': 'Four conditional reversible progress mappings; Bamboo pending. All metrics unmeasured; no whole-city or historical accuracy approval.',
             'dependency_policy': 'All nested path->SHA maps inside current actual factory/report/profiles are bound in full. Their prerequisite files are pinned as bytes; old pipeline snapshots inside those prerequisite documents are historical provenance, not recursively promoted to current runtime inputs.',
             'readiness_only_no_Blender_or_native': True}
    validator = pure_producer()
    validator(ready)
    tests = [{'id': 'READY-01', 'input': 'all seven genuine reports, actual terminal receipts, full SHA dependency chain',
              'operation': 'recursive explicit path->SHA verification and pure AST producer validate_ready',
              'expected': 'accept', 'actual': 'accepted', 'passed': True}]

    def negative(ident, mutate):
        bad = copy.deepcopy(ready)
        mutate(bad)
        try:
            validator(bad)
        except (AssertionError, KeyError, TypeError, FileNotFoundError) as exc:
            tests.append({'id': ident, 'input': 'private deepcopy of verified readiness', 'operation': ident,
                          'expected': 'reject', 'actual': 'rejected: '+str(exc), 'passed': True})
        else:
            tests.append({'id': ident, 'input': 'private deepcopy of verified readiness', 'operation': ident,
                          'expected': 'reject', 'actual': 'accepted', 'passed': False, 'BUG': 'producer validation accepted forbidden readiness'})

    negative('EXTRA-1-COST-BOOL', lambda d: d.update(third_party_cost=False))
    negative('EXTRA-2-COST-NEGATIVE', lambda d: d.update(third_party_cost=-1))
    negative('EXTRA-3-PAID-CALL', lambda d: d.update(paid_service_calls=1))
    negative('EXTRA-4-MISSING-GROUP', lambda d: d['checks'].pop('formal_support'))
    negative('EXTRA-5-MISSING-REPORT', lambda d: d['checks']['formal_source'].update(path='work/restoration-v19/integration-preflight/DOES-NOT-EXIST.json'))
    negative('EXTRA-6-UNBOUND-REPORT', lambda d: d['protected_inputs'].pop(d['checks']['formal_source']['path']))
    negative('EXTRA-7-FALSE-APPROVAL', lambda d: d.update(human_approval='approved'))
    negative('EXTRA-8-WHOLE-CITY', lambda d: d.update(whole_city_complete=True))
    negative('EXTRA-9-WRONG-FIVE-SCOPE', lambda d: d['stage19_targets'].remove('zhuxiangguan'))
    negative('EXTRA-10-DUPLICATE-MODELED', lambda d: d['modeled_this_progress'].append('fuwangge'))
    negative('EXTRA-11-BOOLEAN-EXIT', lambda d: d['checks']['formal_source'].update(actual_terminal_exit_code=False))
    negative('EXTRA-12-FAILED-CHECK', lambda d: d['checks']['formal_source'].update(failed=1))
    negative('EXTRA-13-UNBOUND-PROBE', lambda d: d['protected_inputs'].pop(d['source_probe']))
    negative('EXTRA-14-WRONG-REPORT-SHA', lambda d: d['checks']['formal_source'].update(sha256='0'*64))
    tests.append({'id': 'READY-02', 'input': '431 formal meshes +43 Biluo actual meshes',
                  'operation': 'verify actual inventories, complete source actor mapping and original factory/code inputs',
                  'expected': '474 meshes for4 studies,5 full targets preserved', 'actual': '474; Bamboo pending', 'passed': True})
    # Compile only: no import, no bytecode, no Blender or native saving.
    for path in [PRODUCER, V19+'scene_assemblies.py', V19+'saved-audit/evaluated_geometry_fingerprint.py']:
        compile((ROOT/path).read_text(), str(ROOT/path), 'exec')
    tests.append({'id': 'READY-03', 'input': 'producer, assembly and evaluated helper source', 'operation': 'compile without import',
                  'expected': 'syntactically valid without running Blender', 'actual': 'valid', 'passed': True})
    result = {'schema': 'v19-four-progress-readiness-independent-CPU/1',
              'producer_sha256': protected[PRODUCER], 'evidence_file_count': len(protected),
              'protected_inputs': protected, 'input_provenance': provenance, 'historical_provenance_edges_not_current_inputs': historical_edges, 'tests': tests,
              'summary': {'passed': sum(t['passed'] for t in tests), 'failed': sum(not t['passed'] for t in tests)},
              'Blender_started': False, 'native_opened_or_saved': False, 'third_party_cost': 0,
              'human_approval': 'pending', 'whole_city_complete': False}
    write(HERE/args.test_output, result)
    require(result['summary']['failed'] == 0, 'producer preflight counterexamples still fail; report preserved, no readiness written')
    # Re-read every bound input after qualification; writes never touch inputs.
    require(all(sha(ROOT/p) == digest for p, digest in protected.items()), 'input changed during qualification')
    write(HERE/args.output, ready)
    print(json.dumps({'summary': result['summary'], 'protected_files': len(protected),
                      'readiness': str(HERE/args.output), 'readiness_sha256': sha(HERE/args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
