"""Kenya Policy Pressure Index (KPPI) – package root."""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("kppi")
except PackageNotFoundError:
    __version__ = "2.0.0-dev"
