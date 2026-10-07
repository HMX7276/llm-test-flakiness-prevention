"""Controlled legal input-state/scheduling diagnostics; no production patches."""
import os
import random
import sys
import time

def pytest_runtest_call(item):
    mode=os.environ.get('CURATION_MODE')
    if mode=='random_state':
        # After module-level seeds; represents an explicitly varied entry RNG state.
        random.seed(int(os.environ['CURATION_SEED']))
    elif mode=='numpy_entry_state_v3':
        import numpy as np
        np.random.seed(int(os.environ['CURATION_SEED']))
    elif mode=='scheduler_delay':
        # Delay between topic construction and its immediate clock assertion.
        # This is an injected scheduling delay, not an unperturbed reproduction.
        seed=int(os.environ['CURATION_SEED'])
        done=False
        def trace(frame,event,arg):
            nonlocal done
            if not done and event=='line' and frame.f_code.co_name=='test_idletime' and frame.f_lineno==183:
                done=True
                time.sleep(0.15 if seed % 2 else 0)
            return trace
        sys.settrace(trace)

def pytest_runtest_teardown(item):
    if os.environ.get('CURATION_MODE')=='scheduler_delay':
        sys.settrace(None)
