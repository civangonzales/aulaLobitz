r"""Run the Django tests with site startup hooks skipped and Python networking denied.

Windows: .venv\Scripts\python.exe -S scripts\check_offline.py
"""
import os
import sys
from pathlib import Path


def deny_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto', 'socket.sendmsg'}:
        raise RuntimeError('Network access is disabled during this test run.')


sys.addaudithook(deny_network)
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
for packages in [root / '.venv' / 'Lib' / 'site-packages',
                 root / '.venv' / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages']:
    if packages.exists():
        sys.path.insert(0, str(packages))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
from django.conf import settings
from django.test.utils import get_runner

django.setup()
runner = get_runner(settings)(verbosity=2, interactive=False)
sys.exit(bool(runner.run_tests(['academico'])))
