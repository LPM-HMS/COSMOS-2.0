import signal
import os

TERMINATION_SIGNALS = frozenset({signal.SIGINT, signal.SIGTERM, signal.SIGXCPU})
REPO_DIR = os.path.split(os.path.dirname(os.path.abspath(__file__)))[0]
