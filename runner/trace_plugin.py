"""Record actual target calls and pytest phase outcomes, not just exit codes."""
import json
import os
import sys
import random
import time
from pathlib import Path

target_calls = 0
reports = []
collection_errors = []
target_module = os.environ.get('TRACE_TARGET_MODULE','penman.graph')
target_qualname = os.environ.get('TRACE_TARGET_QUALNAME','Graph.variables')
perturbation = os.environ.get('DEV_PERTURBATION','hash')
seed = int(os.environ.get('DEV_SEED','0'))


def profile(frame, event, arg):
    global target_calls
    if (event == "call" and frame.f_code.co_qualname == target_qualname
            and frame.f_globals.get("__name__") == target_module):
        target_calls += 1
        if perturbation=='clock_delay' and seed % 2:
            time.sleep(0.15)
        if perturbation=='clock_combined_v2' and seed % 2:
            time.sleep(0.15)
    if (event=='return' and frame.f_globals.get('__name__')=='tale.pubsub'
            and frame.f_code.co_qualname=='Topic.send' and seed % 2
            and perturbation in {'clock_read_gap','clock_combined_v2'}):
        time.sleep(0.02)

def pytest_runtest_call(item):
    if perturbation=='random_state':
        random.seed(seed)


def pytest_sessionstart(session):
    sys.setprofile(profile)


def pytest_runtest_logreport(report):
    reports.append({"nodeid":report.nodeid,"when":report.when,"outcome":report.outcome})


def pytest_collectreport(report):
    if report.failed:
        collection_errors.append(str(report.longrepr))


def pytest_sessionfinish(session, exitstatus):
    sys.setprofile(None)
    Path(os.environ["EXPERIMENT_TRACE_PATH"]).write_text(json.dumps({
        "target_calls":target_calls,"reports":reports,"collection_errors":collection_errors,
        "exitstatus":int(exitstatus),"collected":session.testscollected}),encoding="utf-8")
