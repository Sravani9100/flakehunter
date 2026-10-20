from discounts import generate_discount_code


def test_discount_code_format():
    code = generate_discount_code()
    assert len(code) == 6
    assert any(ch.isdigit() for ch in code)
