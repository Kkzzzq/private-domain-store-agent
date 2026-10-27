"""Preserve explicit OR choices from the current authenticated user request."""
import re


def alternatives_from_request(keywords, groups, request):
    words = list(dict.fromkeys(keywords or []))
    parents = list(range(len(words)))
    def root(i):
        while parents[i] != i:
            i = parents[i]
        return i
    for i, left in enumerate(words):
        for j, right in enumerate(words):
            if i == j:
                continue
            pattern = re.escape(left) + r"\s*(?:或者|或)\s*" + re.escape(right)
            for match in re.finditer(pattern, request):
                clause = re.split(r"[，。；,;\n]", request[:match.start()])[-1]
                if re.search(r"不要|不想|不需要|不含|排除|拒绝|不能|不选", clause):
                    continue
                parents[root(j)] = root(i)
    connected = {}
    for i, word in enumerate(words):
        connected.setdefault(root(i), []).append(word)
    inferred = [group for group in connected.values() if len(group) > 1]
    moved = {word for group in inferred for word in group}
    return [word for word in words if word not in moved], [*(groups or []), *inferred]
