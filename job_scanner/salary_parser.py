"""Salary normalization and parsing."""

import re
from dataclasses import dataclass
from typing import Optional

CURRENCY_PATTERNS = {
    "USD": [r'\$', r'USD'], "EUR": [r'€', r'EUR'],
    "GBP": [r'£', r'GBP'], "CHF": [r'CHF'],
    "CAD": [r'CA\$', r'CAD'], "AUD": [r'AU\$', r'AUD'],
    "INR": [r'₹', r'INR'], "PLN": [r'PLN'],
}

PERIOD_MULTIPLIERS = {
    "hourly": 2080, "daily": 260, "weekly": 52,
    "monthly": 12, "yearly": 1, "annual": 1,
}

PERIOD_PATTERNS = [
    (r'/\s*h(?:ou)?r|per\s+hour|hourly', "hourly"),
    (r'/\s*day|per\s+day|daily', "daily"),
    (r'/\s*w(?:ee)?k|per\s+week|weekly', "weekly"),
    (r'/\s*mo(?:nth)?|per\s+month|monthly|pcm', "monthly"),
    (r'/\s*y(?:ea)?r|per\s+(?:year|annum)|annual|yearly', "yearly"),
]


@dataclass
class ParsedSalary:
    min_annual: Optional[int] = None
    max_annual: Optional[int] = None
    currency: str = "USD"


def parse_salary(raw: str) -> ParsedSalary:
    if not raw or not raw.strip():
        return ParsedSalary()

    text = raw.strip()
    currency = "USD"
    for curr, patterns in CURRENCY_PATTERNS.items():
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                currency = curr
                break

    period = "yearly"
    for p, per in PERIOD_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            period = per
            break

    k_text = re.sub(r'(\d+\.?\d*)\s*[kK]\b', lambda m: str(int(float(m.group(1)) * 1000)), text)
    numbers = []
    for match in re.finditer(r'(\d[\d,]*\.?\d*)', k_text):
        try:
            num = float(match.group(1).replace(',', ''))
            if num > 5:
                numbers.append(num)
        except ValueError:
            continue

    if not numbers:
        return ParsedSalary(currency=currency)

    multiplier = PERIOD_MULTIPLIERS.get(period, 1)
    result = ParsedSalary(currency=currency)

    if len(numbers) >= 2:
        sorted_nums = sorted(numbers[:2])
        result.min_annual = int(sorted_nums[0] * multiplier)
        result.max_annual = int(sorted_nums[1] * multiplier)
    else:
        annual = int(numbers[0] * multiplier)
        result.min_annual = annual
        result.max_annual = annual

    return result
