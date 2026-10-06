import os
import re
import math
from collections import Counter

# Curated local knowledge base of common deployment-failure categories.
# Each file is a short markdown doc with a --- frontmatter block (title,
# tags, url) followed by an explanation. This is intentionally NOT scraped
# from the live web at request time: it's small, fast, offline, and every
# fact in it is something we wrote and can vouch for, rather than something
# an LLM might mis-cite from an external page.
_DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "at", "for", "with", "by", "and", "or", "but",
    "this", "that", "it", "its", "as", "from", "not", "no", "if", "then",
    "than", "so", "such", "into", "out", "up", "down", "over", "under",
    "you", "your", "i", "we", "they", "he", "she", "them", "their",
}

_TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_./]*")


def _tokenize(text: str) -> list:
    tokens = _TOKEN_PATTERN.findall(text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _parse_doc(path: str) -> dict:
    """
    Parses a knowledge-base markdown file with a simple frontmatter block:

        ---
        title: ...
        tags: comma, separated, tags
        url: https://...
        ---
        body text...
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    title, tags, url, body = os.path.basename(path), "", "", raw

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.DOTALL)
    if match:
        frontmatter, body = match.group(1), match.group(2)
        for line in frontmatter.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key == "title":
                title = value
            elif key == "tags":
                tags = value
            elif key == "url":
                url = value

    body = body.strip()
    # Tags are indexed alongside the body but not shown in the snippet —
    # they exist purely to nudge matching for short/keyword-heavy queries
    # (e.g. an error string that's mostly a package/error name).
    searchable_text = f"{title} {tags} {body}"

    return {
        "title": title,
        "url": url,
        "body": body,
        "tokens": _tokenize(searchable_text),
    }


def _load_corpus() -> list:
    if not os.path.isdir(_DOCS_DIR):
        return []

    corpus = []
    for filename in sorted(os.listdir(_DOCS_DIR)):
        if filename.endswith(".md"):
            corpus.append(_parse_doc(os.path.join(_DOCS_DIR, filename)))
    return corpus


# Loaded once per process — the knowledge base is small and static, so
# there's no need to re-read and re-tokenize files on every request.
_CORPUS = _load_corpus()


def _build_idf(corpus: list) -> dict:
    doc_count = len(corpus)
    doc_freq = Counter()
    for doc in corpus:
        for term in set(doc["tokens"]):
            doc_freq[term] += 1

    # Standard smoothed IDF so terms appearing in every doc don't zero out.
    return {
        term: math.log((1 + doc_count) / (1 + freq)) + 1
        for term, freq in doc_freq.items()
    }


_IDF = _build_idf(_CORPUS)


def _tfidf_vector(tokens: list, idf: dict) -> dict:
    counts = Counter(tokens)
    total = len(tokens) or 1
    return {
        term: (count / total) * idf.get(term, 0.0)
        for term, count in counts.items()
    }


def _cosine_similarity(vec_a: dict, vec_b: dict) -> float:
    shared_terms = set(vec_a) & set(vec_b)
    if not shared_terms:
        return 0.0

    dot = sum(vec_a[t] * vec_b[t] for t in shared_terms)
    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def docs_rag_agent(query_text: str, top_k: int = 3, min_score: float = 0.05) -> dict:
    """
    Retrieves the most relevant local knowledge-base entries for a given
    query (typically the log error lines, joined into one string).

    Returns a dict with the query and a ranked list of results, each with
    title, url, a short snippet, and its similarity score. Results below
    min_score are dropped rather than forcing irrelevant docs into context —
    an empty result list is a valid, honest answer when nothing matches.
    """
    if not query_text or not _CORPUS:
        return {"query": query_text, "results": []}

    query_vector = _tfidf_vector(_tokenize(query_text), _IDF)

    scored = []
    for doc in _CORPUS:
        doc_vector = _tfidf_vector(doc["tokens"], _IDF)
        score = _cosine_similarity(query_vector, doc_vector)
        if score >= min_score:
            scored.append((score, doc))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    results = [
        {
            "title": doc["title"],
            "url": doc["url"],
            "snippet": doc["body"][:500],
            "score": round(score, 3),
        }
        for score, doc in scored[:top_k]
    ]

    return {"query": query_text, "results": results}