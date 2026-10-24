"""Add the actual, complete seven-part alignment proof to the factory gate."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


original = HERE / 'factory-readiness-01.json'
assert sha(original) == 'fa21fd51e713848aea0ccd19334905b9147e24dd22ee87c6fb4429fc93200886'
doc = json.loads(original.read_text())
folder = HERE / 'stage-qa/alignment-run-01'
actual_path, strict_path = folder / 'actual-alignment-tests.json', folder / 'strict-seven-source-assemblies.json'
actual, strict = [json.loads(p.read_text()) for p in (actual_path, strict_path)]
assert (actual['passed'], actual['failed']) == (6, 0)
assert strict['passed'] is True and strict['component_count'] == 7 and strict['original_source_assembly_count'] == 3
readout = folder / 'actual-alignment-world-geometry.json'
assert sha(readout) == actual['actual_world_readout_sha256'] == strict['actual_alignment_readout_sha256']
for rel, expected in actual['pins'].items():
    assert sha(ROOT / rel) == expected
    doc['inputs_sha256'][rel] = expected
for rel, expected in doc['inputs_sha256'].items():
    assert sha(ROOT / rel) == expected
paths = [original, actual_path, strict_path, readout,
         HERE / 'stage-qa/test_actual_slab_alignment.py', HERE / 'source_support_alignment.py',
         ROOT / 'work/build_forbidden_city_restoration_v17_v2.py', Path(__file__).resolve()]
for path in paths:
    doc['inputs_sha256'][str(path.relative_to(ROOT))] = sha(path)
doc['reports']['alignment_actual'] = str(actual_path.relative_to(ROOT))
doc['reports']['alignment_complete_seven_sources'] = str(strict_path.relative_to(ROOT))
doc['source_slab_alignment_actual_pending'] = True
doc['source_slab_alignment_pending_scope'] = 'Actual SAVED CITY only; the lightweight actual factory and complete seven-part assembly CPU have passed.'
doc['source_slab_alignment_factory_verified'] = True
doc['saved_city_verified'] = False
target = HERE / 'factory-readiness-02.json'
with target.open('x') as stream:
    json.dump(doc, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write('\n')
print(target, sha(target))
