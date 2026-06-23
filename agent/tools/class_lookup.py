import re

def canonicalize_class_id(text: str) -> str:
    text = text.strip().upper()

    # fix missing space between digit+letter+block
    text = re.sub(r"^(\d+)([A-Z])([A-Z]{2,}(?:/[A-Z]+)?)$", r"\1\2 \3", text)

    # normalize separators
    text = re.sub(r"[^A-Z0-9/]", " ", text)

    # collapse spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


class ClassIndex:
    def __init__(self, class_list):
        self.raw = class_list

        self.norm_map = {
            canonicalize_class_id(c): c for c in class_list
        }

        self.norm_keys = list(self.norm_map.keys())

    def score(self, query: str, candidate: str) -> float:
        q = set(query.split())
        c = set(candidate.split())

        overlap = len(q & c) / max(len(q), 1)
        substring = 1.0 if query in candidate else 0.0
        prefix = 1.0 if candidate.startswith(query[:2]) else 0.0

        return (0.5 * overlap) + (0.3 * substring) + (0.2 * prefix)

    def resolve(self, user_input: str):
        q = canonicalize_class_id(user_input)

        best = None
        best_score = 0

        for key in self.norm_keys:
            s = self.score(q, key)

            if s > best_score:
                best_score = s
                best = key

        if not best:
            return None

        return {
            "input": user_input,
            "resolved": self.norm_map[best],
            "confidence": best_score
        }