"""Unit tests kiểm tra tính toàn vẹn cơ bản của package scholargraph."""

import importlib


def test_package_import():
    """Kiểm tra package scholargraph có thể import và có phiên bản hợp lệ."""
    import scholargraph

    assert hasattr(scholargraph, "__version__")
    assert scholargraph.__version__ == "0.1.0"
    assert hasattr(scholargraph, "__author__")


def test_submodules_import():
    """Kiểm tra các submodule cốt lõi trong kiến trúc đều import được."""
    submodules = [
        "scholargraph.data",
        "scholargraph.ingest",
        "scholargraph.retrieval",
        "scholargraph.graph",
        "scholargraph.evaluation",
        "scholargraph.api",
    ]
    for mod_name in submodules:
        mod = importlib.import_module(mod_name)
        assert mod is not None
