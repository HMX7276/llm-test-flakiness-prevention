import pytest
from runner.import_human_review import validate

MAPPING=[{'review_id':'R001','code_sha256':'hash'}]

def payload(**kwargs):
    return {'schema':'semantic-review-v1','reviewer_type':'human','reviewer':'test-only',
            'items':[{'review_id':'R001','code_sha256':'hash',**kwargs}]}

def test_blank_choices_not_counted_as_human_completion():
    assert validate(payload(),MAPPING)['completed']==[]

def test_incomplete_reason_not_counted_as_completion():
    result=validate(payload(correctness='correct',robustness='robust',adequacy='meaningful',reason=''),MAPPING)
    assert not result['completed']

def test_hash_mismatch_refused():
    data=payload(); data['items'][0]['code_sha256']='changed'
    with pytest.raises(ValueError,match='hash'): validate(data,MAPPING)

def test_one_human_never_creates_agreement_statistic():
    result=validate(payload(correctness='uncertain',robustness='uncertain',adequacy='uncertain',reason='Need clarification'),MAPPING)
    assert len(result['completed'])==1 and result['agreement_coefficient'] is None


def test_second_packet_cannot_be_imported_as_first_packet():
    data=payload(correctness='uncertain',robustness='uncertain',adequacy='uncertain',reason='Synthetic validation only')
    data['schema']='semantic-review-v2'
    with pytest.raises(ValueError,match='schema'):
        validate(data,MAPPING)
    assert len(validate(data,MAPPING,expected_schema='semantic-review-v2')['completed'])==1
