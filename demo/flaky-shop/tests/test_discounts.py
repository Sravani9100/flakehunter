import pytest
from shop.discounts import apply_discount, generate_code


def test_discount_code_format():
    code = generate_code()
    assert len(code) == 6
    assert any(ch.isdigit() for ch in code)


@pytest.mark.parametrize(("total", "percent", "expected"), [(100, 10, 90), (19.99, 0, 19.99)])
def test_apply_discount(total, percent, expected):
    assert apply_discount(total, percent) == expected


def test_apply_discount_rejects_bad_percent():
    with pytest.raises(ValueError):
        apply_discount(10, 120)
