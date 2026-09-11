"""
AIDSE Platform — AI Evaluation Scoring Strategies (Phase 13)

Four strategies, all returning {score: 0..1, detail: {...}}:

    exact_match        deterministic string equality
    regex              rule-based pattern match
    semantic           TF-IDF cosine similarity (offline, deterministic)
    llm_judge          provider-graded when configured; otherwise falls back
                       to semantic similarity and SAYS SO in the detail

The provider integration is configurable via the shared LLM settings
(LLM_PROVIDER / LLM_API_KEY / LLM_MODEL). No strategy ever raises on
content mismatch — mismatches are scores, not errors.
"""
from __future__ import annotations

import json
import re
from typing import Any

STRATEGIES = ("exact", "regex", "semantic", "llm_judge")

DEFAULT_SEMANTIC_THRESHOLD = 0.80
DEFAULT_REGEX_FLAGS = re.IGNORECASE

# Longest string a regex strategy will match against. Bounds the cost of a
# pattern that backtracks catastrophically; well above any realistic LLM output.
_REGEX_SUBJECT_LIMIT = 100_000


# ──────────────────────────────────────────────────────────────────────────────
# Individual strategies
# ──────────────────────────────────────────────────────────────────────────────

def score_exact(expected: str, actual: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    case_insensitive = bool(params.get("case_insensitive", True))
    a, b = (actual or ""), (expected or "")
    if case_insensitive:
        equal = a.strip().lower() == b.strip().lower()
    else:
        equal = a.strip() == b.strip()
    return {
        "score": 1.0 if equal else 0.0,
        "detail": {"method": "exact_match", "case_insensitive": case_insensitive},
    }


def score_regex(expected: str, actual: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    The EXPECTED output field holds the regex pattern for this strategy.
    Optional params.full_match anchors the whole string.
    """
    params = params or {}
    flags = re.IGNORECASE if params.get("case_insensitive", True) else 0

    # Python's `re` has no execution timeout, so a catastrophically backtracking
    # pattern would run unbounded. Capping the subject length bounds the blow-up
    # to something a user can wait out. The caller also runs this off the event
    # loop, so a slow pattern degrades one evaluation rather than the whole app.
    subject = (actual or "")[:_REGEX_SUBJECT_LIMIT]

    try:
        matched = (
            re.fullmatch(expected or "", subject, flags)
            if params.get("full_match")
            else re.search(expected or "", subject, flags)
        )
    except re.error as exc:
        return {
            "score": 0.0,
            "detail": {"method": "regex", "error": f"Invalid pattern: {exc}"},
        }
    return {
        "score": 1.0 if matched else 0.0,
        "detail": {"method": "regex", "pattern": expected},
    }


def score_semantic(expected: str, actual: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    TF-IDF cosine similarity between expected and actual.
    Deterministic and offline; threshold decides pass/fail.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    params = params or {}
    threshold = float(params.get("threshold", DEFAULT_SEMANTIC_THRESHOLD))
    a, b = (actual or "").strip(), (expected or "").strip()
    if not a and not b:
        sim = 1.0
    elif not a or not b:
        sim = 0.0
    else:
        try:
            # Unigrams only: word order changes ("Paris is..." vs "...is Paris")
            # must not tank an otherwise equivalent answer.
            vec = TfidfVectorizer(ngram_range=(1, 1))
            tfidf = vec.fit_transform([b, a])
            sim = float(cosine_similarity(tfidf[0], tfidf[1])[0][0])
        except ValueError:  # no shared vocabulary at all
            sim = 0.0

    return {
        "score": round(sim, 6),
        "detail": {
            "method": "semantic_tfidf",
            "threshold": threshold,
            "passed_threshold": sim >= threshold,
        },
    }


JUDGE_PROMPT = (
    "You are grading an AI system's output against a reference answer.\n"
    "Return STRICT JSON only: {\"score\": <0..1 float>, \"reason\": \"<one sentence>\"}\n"
    "Score 1.0 means semantically equivalent to the reference; 0.0 means wrong "
    "or contradictory. Partial credit allowed.\n\n"
    "Question/context: {question}\n"
    "Reference answer: {expected}\n"
    "Actual output: {actual}"
)


def score_llm_judge(expected: str, actual: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Provider-graded when configured. Falls back to TF-IDF similarity with an
    explicit note so users always know HOW their run was graded.
    """
    settings_checked = _provider_ready()
    if not settings_checked:
        fallback = score_semantic(expected, actual, params)
        fallback["detail"]["method"] = "llm_judge_fallback_semantic"
        fallback["detail"]["note"] = (
            "No evaluation provider configured — graded by offline semantic "
            "similarity instead of an LLM judge."
        )
        return fallback

    import httpx
    from apps.api.core.config import get_settings

    settings = get_settings()
    params = params or {}
    prompt = JUDGE_PROMPT.format(
        question=params.get("question") or "(none provided)",
        expected=expected,
        actual=actual,
    )
    try:
        if settings.LLM_PROVIDER == "openai":
            url = (settings.LLM_BASE_URL or "https://api.openai.com/v1") + "/chat/completions"
            headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
            payload = {
                "model": settings.LLM_MODEL or "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 120,
            }
        else:  # anthropic
            url = settings.LLM_BASE_URL or "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": settings.LLM_API_KEY, "anthropic-version": "2023-06-01"}
            payload = {
                "model": settings.LLM_MODEL or "claude-3-5-haiku-latest",
                "max_tokens": 120,
                "messages": [{"role": "user", "content": prompt}],
            }
        resp = httpx.post(url, headers=headers, json=payload, timeout=settings.LLM_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        text = (
            data["choices"][0]["message"]["content"]
            if settings.LLM_PROVIDER == "openai"
            else data["content"][0]["text"]
        )
        parsed = _parse_judge_json(text)
        if parsed is None:
            raise ValueError(f"Judge returned non-JSON: {text[:200]}")
        score = max(0.0, min(1.0, float(parsed["score"])))
        return {
            "score": score,
            "detail": {"method": "llm_judge", "reason": parsed.get("reason"), "model": settings.LLM_MODEL or "default"},
        }
    except Exception as exc:
        fallback = score_semantic(expected, actual, params)
        fallback["score"] = round(fallback["score"] * 0.9, 6)  # slight conservatism
        fallback["detail"]["method"] = "llm_judge_fallback_semantic"
        fallback["detail"]["note"] = f"Judge unavailable ({exc}); offline semantic used."
        return fallback


def _parse_judge_json(text: str) -> dict | None:
    """Extract the first JSON object from judge output."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _provider_ready() -> bool:
    from apps.api.core.config import get_settings
    s = get_settings()
    return s.LLM_PROVIDER in ("openai", "anthropic") and bool(s.LLM_API_KEY)


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────────────

PASS_THRESHOLD = 0.5


def score_case(strategy: str, expected: str, actual: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Score one golden case. Returns {score, passed, detail}.
    Unknown strategy → ValueError with supported list.
    """
    if strategy == "exact":
        result = score_exact(expected, actual, params)
    elif strategy == "regex":
        result = score_regex(expected, actual, params)
    elif strategy == "semantic":
        result = score_semantic(expected, actual, params)
    elif strategy == "llm_judge":
        result = score_llm_judge(expected, actual, params)
    else:
        raise ValueError(
            f"Unknown scoring strategy '{strategy}'. Supported: {', '.join(STRATEGIES)}."
        )

    threshold = PASS_THRESHOLD
    if strategy == "semantic" or result.get("detail", {}).get("threshold"):
        threshold = float(result.get("detail", {}).get("threshold", PASS_THRESHOLD))

    result["passed"] = result["score"] >= threshold
    result["pass_threshold"] = threshold
    return result
