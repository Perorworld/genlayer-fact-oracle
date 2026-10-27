"""
Test setup: lets the pure consensus-rule tests run on any computer with pytest.

The oracle imports the GenLayer SDK, which only exists inside GenLayer.
If the SDK is not installed, this file installs a tiny stand-in so the
rule tests (aggregate / normalize / equivalent) can still be imported and run.
The stand-in is only used for testing. It is never used on GenLayer itself.
"""
import sys
import types

try:
    import genlayer  # noqa: F401  (real SDK available, use it)
except ImportError:
    class _Generic:
        def __class_getitem__(cls, item):
            return cls

    class _Public:
        @staticmethod
        def write(fn):
            return fn

        @staticmethod
        def view(fn):
            return fn

    gl = types.SimpleNamespace(Contract=object, public=_Public)
    mod = types.ModuleType("genlayer")
    mod.gl = gl
    mod.allow_storage = lambda cls: cls
    mod.u256 = int
    mod.Address = str
    mod.TreeMap = _Generic
    mod.DynArray = _Generic
    mod.__all__ = ["gl", "allow_storage", "u256", "Address", "TreeMap", "DynArray"]
    sys.modules["genlayer"] = mod
