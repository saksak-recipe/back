from dataclasses import dataclass

from domains.recipe_detail.normalize import normalize_text


@dataclass(frozen=True)
class SearchCandidate:
    recipe_id: str
    title: str
    author: str


def _score(candidate: SearchCandidate, board_name: str, author_name: str) -> int | None:
    title_n = normalize_text(candidate.title)
    author_n = normalize_text(candidate.author)
    board_n = normalize_text(board_name)
    want_author = normalize_text(author_name)

    author_match = author_n == want_author and want_author != ""
    title_exact = title_n == board_n and board_n != ""
    title_contains = board_n != "" and (board_n in title_n or title_n in board_n)

    # 채택 조건: 작성자 일치 OR 제목 겹침
    if not (author_match or title_contains or title_exact):
        return None

    score = 0
    if author_match:
        score += 100
    if title_exact:
        score += 50
    elif title_contains:
        score += 25
    return score


def pick_best_candidate(
    candidates: list[SearchCandidate],
    board_name: str,
    author_name: str,
) -> SearchCandidate | None:
    ranked: list[tuple[int, SearchCandidate]] = []
    for c in candidates:
        s = _score(c, board_name, author_name)
        if s is not None:
            ranked.append((s, c))
    if not ranked:
        return None
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]
