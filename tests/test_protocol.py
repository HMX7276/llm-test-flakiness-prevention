from methods.prevent import transform
from runner.evaluate import classify, screen


SOURCE = 'def variables(self) -> Set[str]:\n    """Return the set of variables."""\n    return set(self.values)\n'


def test_transform_preserves_duplicate_expected_elements():
    code = "def test_a():\n    assert list(g.variables()) == ['a', 'a']\n"
    output, evidence = transform(SOURCE, code)
    assert evidence['changed']
    assert "Counter(['a', 'a'])" in output


def test_does_not_remove_order_for_list_contract():
    code = "def test_a():\n    assert list(g.variables()) == ['a', 'b']\n"
    output, evidence = transform(SOURCE.replace('Set[str]','List[str]'),code)
    assert output == code
    assert not evidence['changed']


def test_leaves_clean_context_unchanged():
    code = "def test_a():\n    assert g.variables() == {'a', 'b'}\n"
    assert transform(SOURCE,code)[0] == code


def test_mixed_pass_fail_is_observed_unstable():
    result = classify([{'status':'pass'},{'status':'fail'}],True)
    assert result['status'] == 'observed_unstable'


def test_timeout_does_not_become_flaky_assertion():
    result = classify([{'status':'pass'},{'status':'timeout'}],True)
    assert result['status'] == 'execution_exception'


def test_all_pass_without_target_call_is_invalid():
    result = classify([{'status':'pass','target_calls':0}]*30,True)
    assert result['status'] == 'stable_proxy_invalid'


def test_all_fail_is_persistent_failure():
    assert classify([{'status':'fail'}]*30,True)['status'] == 'persistent_failure'


def test_no_executions_is_not_failure_or_success():
    assert classify([],True)['status'] == 'incomplete'


def test_empty_test_and_trivial_assertion_do_not_pass_proxy():
    assert not screen('def test_x():\n    assert True')['quality_proxy']


def test_execution_gate_blocks_environment_access():
    assert not screen('import os\ndef test_x():\n    assert os.getenv("KEY")')['runnable']
