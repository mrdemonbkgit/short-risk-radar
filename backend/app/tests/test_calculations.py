import math

def test_basis_calculation():
    mark = 101.0
    index = 100.0
    basis_pct = (mark - index) / index * 100
    assert math.isclose(basis_pct, 1.0)


def test_twap_example():
    # placeholder: average of last 3 basis values
    values = [0.1, 0.2, 0.3]
    twap = sum(values) / len(values)
    assert math.isclose(twap, 0.2)
