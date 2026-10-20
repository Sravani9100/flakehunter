import random
import string


def generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def apply_discount(total: float, percent: int) -> float:
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(total * (100 - percent) / 100, 2)
