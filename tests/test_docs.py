import pytest, pathlib

def test_replan_memory_in_docs():
    text = pathlib.Path('docs/artificial_citizens_readme.md').read_text()
    assert '"replan"' in text
