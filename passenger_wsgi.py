import sys
import os

VENV = "/home/rind1083/virtualenv/RindangDigifarm/3.11/bin/python"
if sys.executable != VENV:
    os.execl(VENV, VENV, *sys.argv)

sys.path.insert(0, '/home/rind1083/RindangDigifarm')

# Import app factory dan Config, bukan ProductionConfig
from App import create_app
from App.config import Config

# Gunakan Config biasa
application = create_app(Config)