"""Synthetic-only configuration and fail-closed contract tests."""
import hashlib
import json
from pathlib import Path
import pytest
from mcp.orchestration.private_run_config import RunConfigurationError, require_parameter, verify_input_hash, dependency_records
from mcp.orchestration import stage4_mvp as stage4
from mcp.orchestration import stage6_p2_6_region_semantic_reindexing as p26
from tests.acceptance.run_config_fixture import set_parameter

REF = 'mcp.orchestration.stage4_mvp.reference_sha256'
TGT = 'mcp.orchestration.stage4_mvp.target_sha256'


def configure(monkeypatch, tmp_path, reference=b'original synthetic reference', target=b'original synthetic target'):
    set_parameter(monkeypatch, tmp_path, REF, hashlib.sha256(reference).hexdigest())
    set_parameter(monkeypatch, tmp_path, TGT, hashlib.sha256(target).hexdigest())
    set_parameter(monkeypatch, tmp_path, 'stage45.translation', [12, 24, 0])


def test_valid_original_config(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    source = tmp_path / 'synthetic.txt'; source.write_bytes(b'original synthetic reference')
    assert verify_input_hash(source, REF) == hashlib.sha256(source.read_bytes()).hexdigest()
    assert require_parameter('stage45.translation', 'translation3') == [12, 24, 0]


def test_missing_config_blocks_business_entry_before_io(monkeypatch, tmp_path):
    monkeypatch.delenv('TIANZHENG_RUN_CONFIG', raising=False)
    monkeypatch.setattr(stage4, 'freeze_source', lambda *args: pytest.fail('input accessed before config validation'))
    with pytest.raises(RunConfigurationError): stage4.freeze_inputs(tmp_path/'r.dwg', tmp_path/'t.dwg')


def test_wrong_hash_actual_business_entry_blocks(monkeypatch, tmp_path, synthetic_cad_factory):
    reference = synthetic_cad_factory('reference.dwg', payload=b'original synthetic reference')
    target = synthetic_cad_factory('target.dwg', payload=b'original synthetic target')
    configure(monkeypatch, tmp_path, reference=b'wrong synthetic input')
    result = stage4.freeze_inputs(reference, target)
    assert result['hash_pair_matches'] is False
    # Existing caller gate consumes this false result; no relaxed hash comparison.
    import inspect
    assert 'hash_pair_matches' in inspect.getsource(stage4.run_stage4)


@pytest.mark.parametrize('value', ['{broken', '[]', '{"schema_version":2,"parameters":{}}'])
def test_malformed_config(monkeypatch, tmp_path, value):
    path=tmp_path/'bad.json';path.write_text(value);monkeypatch.setenv('TIANZHENG_RUN_CONFIG',str(path))
    with pytest.raises(RunConfigurationError): require_parameter(REF)


@pytest.mark.parametrize('value', [None, '', 'not-a-hash', 123])
def test_bad_hash_format(monkeypatch, tmp_path, value):
    set_parameter(monkeypatch,tmp_path,REF,value)
    with pytest.raises(RunConfigurationError): require_parameter(REF)


@pytest.mark.parametrize('value', [[1, 2], [1, float('nan'), 0], [1, True, 0], '1,2,3'])
def test_bad_translation(monkeypatch,tmp_path,value):
    set_parameter(monkeypatch,tmp_path,'stage45.translation',value)
    with pytest.raises(RunConfigurationError): require_parameter('stage45.translation','translation3')


def test_missing_bindings_blocks_before_output(monkeypatch,tmp_path):
    monkeypatch.delenv('TIANZHENG_RUN_CONFIG',raising=False)
    with pytest.raises(RunConfigurationError): p26.run_region_semantic_reindexing(tmp_path,{}, {},tmp_path/'r',tmp_path/'t')
    assert not (tmp_path/'region_semantic_reindexing').exists()


def test_poc_handles_come_from_evidence():
    evidence={'approved_reference_handles':['synthetic-source'], 'created_handles':['synthetic-target'], 'approved_dependency_task_ids':['synthetic-task'], 'dependency_mappings':[{'task_id':'synthetic-task','reference_handle':'synthetic-source','target_handle':'synthetic-target','object_name':'TDbPipe'}]}
    assert dependency_records(evidence) == evidence['dependency_mappings']
    evidence['dependency_mappings'][0]['target_handle']='unverified'
    with pytest.raises(RunConfigurationError): dependency_records(evidence)


def test_missing_poc_mapping_is_not_fabricated():
    with pytest.raises(RunConfigurationError): dependency_records({})


@pytest.mark.parametrize('kind', ['primary', 'remaining', 'valve', 'final', 'failed_clone', 'sequential'])
@pytest.mark.parametrize('failure', ['missing', 'wrong_hash', 'missing_translation'])
def test_write_entry_rejects_before_copy_or_cad(monkeypatch,tmp_path,synthetic_cad_factory,kind,failure):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from mcp.acceptance import stage5_2_component_clone_poc as primary
    from mcp.acceptance import stage5_1_remaining_capability_poc as remaining
    from mcp.acceptance import stage5_1_valve_component_diagnostics as valve
    from mcp.orchestration import stage5_1_r3 as r3
    modules={'primary':primary,'remaining':remaining,'valve':valve,'final':r3,'failed_clone':r3,'sequential':r3}
    module=modules[kind]
    reference=synthetic_cad_factory('reference.dwg',payload=b'original synthetic reference')
    target=synthetic_cad_factory('target.dwg',payload=b'original synthetic target')
    monkeypatch.setattr(module,'REFERENCE',reference);monkeypatch.setattr(module,'TARGET',target)
    configure(monkeypatch,tmp_path,reference=b'wrong synthetic input')
    if failure=='missing':monkeypatch.delenv('TIANZHENG_RUN_CONFIG')
    elif failure=='missing_translation':
        config_path=tmp_path/'synthetic_run_config.json';payload=json.loads(config_path.read_text());del payload['parameters']['stage45.translation'];config_path.write_text(json.dumps(payload))
    copy_spy=Mock(side_effect=AssertionError('copy must not run'))
    attach_spy=Mock(side_effect=AssertionError('CAD attach must not run'))
    monkeypatch.setattr(module.shutil,'copy2',copy_spy)
    from mcp.acceptance import stage3_1_runtime
    monkeypatch.setattr(stage3_1_runtime,'attach_existing_autocad',attach_spy)
    if hasattr(module,'attach_existing_autocad'):
        monkeypatch.setattr(module,'attach_existing_autocad',attach_spy)
    paths=SimpleNamespace(root=tmp_path,poc=tmp_path/'poc',capabilities=tmp_path/'capabilities',copies=tmp_path/'copies')
    if kind=='primary':
        monkeypatch.setattr(primary,'read_json',lambda _: {'items':[]})
        monkeypatch.setattr(primary,'select_component_candidate',lambda *_: ({},[]))
        monkeypatch.setattr(primary,'source_lock_files',lambda _: [])
        call=lambda: primary.run_primary_only_component_diagnostic(paths,'TDbPipeValve')
    elif kind=='remaining':
        monkeypatch.setattr(remaining,'read_json',lambda _: {})
        monkeypatch.setattr(remaining,'select_capability_package',lambda *_: {})
        call=lambda: remaining.run_remaining_type_poc(paths,'TDbPump')
    elif kind=='valve':call=lambda: valve.run_valve_variant(paths,{'variant_id':'synthetic'})
    elif kind=='failed_clone':call=lambda: r3.diagnose_failed_component_clone(paths,'synthetic')
    elif kind=='sequential':call=lambda: r3.diagnose_sequential_valve_remap(paths)
    else:call=lambda: r3.execute_final_full_reconstruction(paths)
    with pytest.raises((RunConfigurationError,RuntimeError)):call()
    copy_spy.assert_not_called();attach_spy.assert_not_called()


def test_partial_dependency_map_rejected():
    evidence={'approved_dependency_task_ids':['a','b'],'approved_reference_handles':['source-a'],'created_handles':['target-a'],'dependency_mappings':[{'task_id':'a','reference_handle':'source-a','target_handle':'target-a','object_name':'TDbPipe'}]}
    with pytest.raises(RunConfigurationError):dependency_records(evidence)
