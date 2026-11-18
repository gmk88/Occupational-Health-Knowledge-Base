from __future__ import annotations

import re

CAS = re.compile(r"\bCAS\s*[\-: ]?\s*\d{1,7}[\-]\d{2}[\-]\d\b", re.IGNORECASE)
STANDARD = re.compile(
    r"\b(?:GB|GBZ|GB/T|GBZ/T|WS|AQ|AQ/T)\s*\d+(?:\.\d+)?(?:[—\-–]\d{4})?\b"
)
PC_TWA = re.compile(r"\bPC[-_ ]?TWA\b", re.IGNORECASE)


def extract_exact_terms(query: str) -> list[str]:
    terms = []
    for match in CAS.finditer(query):
        terms.append(match.group(0).upper())
    for match in STANDARD.finditer(query):
        terms.append(match.group(0).upper())
    for _match in PC_TWA.finditer(query):
        terms.append("PC-TWA")
    return list(dict.fromkeys(terms))
