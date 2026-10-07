"""Instrumentation for the frozen, hand-authored external applicability probes."""
import json
import os
from pathlib import Path
import sys
import time

calls = 0
reports = []
errors = []
module, qualname = os.environ['VALIDATION_TARGET'].split(':')
seed = int(os.environ['VALIDATION_SEED'])


def profile(frame, event, arg):
    global calls
    if event == 'call' and frame.f_globals.get('__name__') == module and frame.f_code.co_qualname == qualname:
        calls += 1
        if module == 'cachetools' and seed % 2:
            time.sleep(0.05)


def pytest_sessionstart(session):
    sys.setprofile(profile)


def pytest_runtest_call(item):
    if module == 'faker.providers':
        import faker.generator
        faker.generator.random.seed(seed)


def pytest_runtest_logreport(report):
    reports.append({'when': report.when, 'outcome': report.outcome})


def pytest_collectreport(report):
    if report.failed:
        errors.append(str(report.longrepr))


def pytest_sessionfinish(session, exitstatus):
    sys.setprofile(None)
    Path(os.environ['VALIDATION_TRACE']).write_text(json.dumps(dict(target_calls=calls, reports=reports,
        collection_errors=errors, collected=session.testscollected, exitstatus=int(exitstatus))), encoding='utf-8')
