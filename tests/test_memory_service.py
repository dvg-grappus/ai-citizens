import types
import sys
import math

# Provide a minimal numpy stub so memory_service can be imported without numpy
numpy_stub = types.SimpleNamespace(
    array=lambda x: list(x),
    dot=lambda a, b: sum(x*y for x, y in zip(a, b)),
)
def norm(v):
    return math.sqrt(sum(x*x for x in v))
numpy_stub.linalg = types.SimpleNamespace(norm=norm)
sys.modules.setdefault('numpy', numpy_stub)

from backend.memory_service import cosine_similarity


def test_cosine_similarity_identical():
    vec = [1.0, 2.0, 3.0]
    assert math.isclose(cosine_similarity(vec, vec), 1.0)


def test_cosine_similarity_opposite():
    v1 = [1.0, 0.0, 0.0]
    v2 = [-1.0, 0.0, 0.0]
    assert math.isclose(cosine_similarity(v1, v2), -1.0)


def test_cosine_similarity_orthogonal():
    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]
    assert math.isclose(cosine_similarity(v1, v2), 0.0)
