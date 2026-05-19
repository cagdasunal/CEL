"""Derive a KeywordPlan from page content per /page-summary skill Phase 2.5.

Public API: `derive_keywords(title, h1, url, body_text) -> KeywordPlan`.

Algorithm (from `.claude/skills/page-summary/SKILL.md`):
  1. Candidate A = page title minus brand suffix
  2. Candidate B = H1
  3. Candidate C = URL slug rendered as natural language
  4. Primary = longest phrase common to ≥ 2 of {A, B, C}; fallback to B
  5. Secondary = body-frequency top words (≥ 3 hits, non-stopword) + heading tokens
  6. Entities = matches against a static allowlist
"""
from __future__ import annotations

import collections
import re
import urllib.parse
from dataclasses import dataclass

from tools.summary.prompt_builder import KeywordPlan


# Static entity allowlist (CEL-specific). First mention spells full name + abbreviation.
_ENTITY_TERMS = (
    "CEFR", "A1", "A2", "B1", "B2", "C1", "C2",
    "IELTS", "TOEFL iBT", "TOEFL",
    "Cambridge English", "FCE", "CAE", "B2 First",
    "PGWPP", "DLI", "GIC",
    "ACCET", "CEA", "Languages Canada",
    "San Diego", "Los Angeles", "Vancouver",
    "California", "British Columbia",
)

# Stop-words for body frequency (lower-case).
_STOPWORDS = frozenset(
    """
    the a an and or but if when where why how what who which that this these those
    is are was were be been being have has had do does did can will would should
    could may might must shall to from in on at by for with of as into onto upon
    over under above below than then so just only also even still already yet
    not no nor never very more most much many such other some any all every each
    you your yours their them they our we us i me my him her his she he it its
    """.split()
)

# Per-locale stopword sets. Used by body-frequency to filter the most common
# function words in each language so the surfaced secondaries are content words.
# Lists are intentionally small (30–60 items) — enough to filter dominant noise
# without an external dependency.
_LOCALE_STOPWORDS: dict[str, frozenset[str]] = {
    "en": _STOPWORDS,
    "de": frozenset(
        """
        der die das den dem des ein eine einer einem einen eines und oder aber
        wenn als ob ist sind war waren sein hat haben hatte hatten wird werden
        wurde wurden kann können konnte konnten muss müssen für mit ohne durch
        gegen über unter auf in an zu von bei nach vor seit nur auch schon noch
        nicht kein keine wir uns unser ihr ihre sie er sie es man dieser diese
        dieses jener jene jenes so dass weil dann
        """.split()
    ),
    "fr": frozenset(
        """
        le la les un une des de du au aux et ou mais si quand où qui que quoi
        est sont était étaient être ai as a avons avez ont avait avaient
        sera seront pour avec sans contre sur dans à par chez vers depuis pendant
        ne pas plus moins très tout tous toute toutes ce cette ces cet
        je tu il elle on nous vous ils elles me te se moi toi soi mon ma mes
        ton ta tes son sa ses notre nos votre vos leur leurs
        """.split()
    ),
    "es": frozenset(
        """
        el la los las un una unos unas de del al a y o pero si cuando donde
        que cual quien es son era eran ser estar he ha han habia habian
        sera seran para con sin contra sobre en por hacia desde durante
        no muy mas menos todo todos toda todas este esta estos estas ese esa
        esos esas aquel aquella aquellos aquellas yo tu el ella nosotros vosotros
        ellos ellas me te se mi mis tu tus su sus nuestro nuestra
        """.split()
    ),
    "it": frozenset(
        """
        il lo la i gli le un uno una di del della dello dei degli delle e o ma
        se quando dove chi che cui è sono era erano essere ho hai ha abbiamo avete
        hanno aveva avevano sarà saranno per con senza contro su in a da tra fra
        non più meno molto tutto tutti tutta tutte questo questa questi queste
        quello quella quelli quelle io tu egli ella noi voi essi esse mi ti si
        ci vi lo la li le mio mia miei mie tuo tua tuoi tue suo sua suoi sue
        """.split()
    ),
    "pt": frozenset(
        """
        o a os as um uma uns umas de do da dos das ao à aos às e ou mas se
        quando onde que qual quem é são era eram ser ter tenho tens tem temos
        têm tinha tinham será serão para com sem contra sobre em por desde
        não muito mais menos todo todos toda todas este esta estes estas
        esse essa esses essas aquele aquela aqueles aquelas eu tu ele ela nós
        vós eles elas me te se nos vos lhe lhes meu minha teu tua seu sua
        """.split()
    ),
    "ko": frozenset(
        """
        은 는 이 가 을 를 의 에 에서 도 만 와 과 도 또 그리고 그래서
        하지만 그러나 그런데 그래도 또한 따라서 위해 위한 위해서 이다 있다
        없다 하다 되다 보다 같다 다른 모든 어떤 무슨 이런 그런 저런 정말
        매우 굉장히 너무 아주 좀 잘 못 더 덜 가장 제일 우리 너희 그들 저
        나 너 그 그녀 이것 그것 저것 이거 그거 저거 여기 거기 저기
        """.split()
    ),
    "ja": frozenset(
        """
        は が を に へ で と も や か から まで より だ である です ます ました
        の こと もの ところ それ これ あれ この その あの どの
        私 僕 彼 彼女 我々 あなた 君 たち 達 ない ある いる する なる
        できる また しかし そして だから なお また なぜ どう とても
        非常に 大変 すごく とても 少し まだ もう だけ しか
        """.split()
    ),
    "ar": frozenset(
        """
        في من إلى على عن عند مع بين أمام خلف فوق تحت قبل بعد لدى لدي
        هذا هذه ذلك تلك هؤلاء أولئك الذي التي الذين اللواتي
        أنا نحن أنت أنتم هو هي هم هن
        كان كانت كانوا يكون تكون يكونون سوف قد لقد
        و أو لكن إذا متى أين كيف ما من لماذا
        لا لم لن ليس لست ليست
        كل بعض جميع كثير قليل
        """.split()
    ),
}


# Per-URL primary-keyword overrides (tracker-091 M-12.4).
#
# Some pages (notably the home page) carry brand-slogan copy in both their
# title and H1 — so the candidate-A/B/C heuristic below picks "fluent in
# creating memories" as primary, which has zero search volume. This map
# overrides the heuristic for known slogan-dominated pages with the
# intent-driven keyword the SEO team actually wants to anchor on.
#
# Keys are URL paths after `strip("/")` (so the home page's key is "");
# locale prefixes (de/, fr/, etc.) are stripped before lookup, so the home
# override applies across all 9 locales without per-locale entries.
#
# Grow this map ONLY for pages where the SEO team confirms the heuristic
# misses. Most pages do the right thing without an entry.
_PRIMARY_KEYWORD_OVERRIDES: dict[str, str] = {
    "": "english language school",  # home page — was "fluent in creating memories"
}


# Brand suffix patterns to strip from titles. Includes locale-translated variants
# of the brand name (audit-086 follow-up — tracker-087 F-6).
_BRAND_SUFFIX_RE = re.compile(
    r"\s*[\|\-–—]\s*("
    r"CEL|"
    r"College of English Language|"
    r"English College|"
    r"Escuela de Inglés|"
    r"École d'anglais|"
    r"Englische Schule|"
    r"Scuola di Inglese|"
    r"Escola de Inglês|"
    r"영어 학교|"
    r"英語学校|"
    r"كلية اللغة الإنجليزية"
    r").*$",
    re.IGNORECASE,
)


def derive_keywords(
    title: str, h1: str, url: str, body_text: str = "", locale: str = "en"
) -> KeywordPlan:
    """Derive a KeywordPlan per /page-summary Phase 2.5.

    `locale` selects the stopword set for body-frequency filtering. Defaults to
    English. Falls back to English if the locale is unknown.

    URL-level overrides in `_PRIMARY_KEYWORD_OVERRIDES` take precedence over
    the candidate-A/B/C heuristic (tracker-091 M-12.4) so brand-slogan-dominated
    pages anchor on intent-driven keywords instead of zero-volume marketing copy.
    """
    candidate_a = _strip_brand(title)
    candidate_b = _strip_brand(h1)
    candidate_c = _slug_to_phrase(url)

    primary = _lookup_override_primary(url)
    if not primary:
        primary = _longest_common_phrase([candidate_a, candidate_b, candidate_c])
    if not primary:
        primary = candidate_b or candidate_a or candidate_c or "english school"
    primary = primary.strip().lower()

    # Secondary keywords: body frequency + heading tokens (locale-aware).
    secondaries = _body_frequency_terms(body_text, exclude=primary, limit=5, locale=locale)

    # Entity terms found in the page.
    entities = tuple(
        e for e in _ENTITY_TERMS if e.lower() in (title + " " + h1 + " " + body_text).lower()
    )

    return KeywordPlan(
        primary=primary,
        secondaries=tuple(secondaries),
        entities=entities,
    )


# ---- Internal helpers ----


def _strip_brand(text: str) -> str:
    """Remove `| CEL` or `| College of English Language` suffix patterns."""
    if not text:
        return ""
    cleaned = _BRAND_SUFFIX_RE.sub("", text).strip()
    return cleaned


def _lookup_override_primary(url: str) -> str:
    """Return the SEO-team-curated primary keyword for `url`, or "" if none.

    Path keys in `_PRIMARY_KEYWORD_OVERRIDES` are matched after stripping
    leading/trailing slashes AND any 2-char locale prefix, so a single
    override entry covers all 9 locales (en + de/fr/es/it/pt/ko/ja/ar).

    Empty path ("/" or "") → home page; check the home entry.
    """
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    # Strip locale prefix if present (mirrors _slug_to_phrase).
    if parts and parts[0] in {"de", "fr", "es", "it", "pt", "ko", "ja", "ar"}:
        parts = parts[1:]
    key = "/".join(parts)
    return _PRIMARY_KEYWORD_OVERRIDES.get(key, "")


def _slug_to_phrase(url: str) -> str:
    """Render a URL slug as natural language. /vancouver/how-long-to-learn-english → 'how long to learn english in vancouver'."""
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if not parts:
        return ""
    # Strip locale prefix if present.
    if parts[0] in {"de", "fr", "es", "it", "pt", "ko", "ja", "ar"}:
        parts = parts[1:]
    if not parts:
        return ""
    # Last segment is the "topic"; earlier segments are context.
    topic = parts[-1].replace("-", " ").replace("_", " ").strip()
    context_segments = [p.replace("-", " ").replace("_", " ") for p in parts[:-1]]
    if context_segments:
        return f"{topic} in {' '.join(context_segments)}"
    return topic


def _longest_common_phrase(candidates: list[str]) -> str:
    """Find the longest phrase common to ≥ 2 of the candidate strings.

    A 'phrase' is a contiguous run of 2+ lowercase tokens. Returns "" if no common
    phrase. Single-token overlaps are ignored.
    """
    cleaned = [c.lower().strip() for c in candidates if c and c.strip()]
    if len(cleaned) < 2:
        return ""
    # Build all 2-to-N gram sets per candidate.
    grams_per_candidate: list[set[str]] = []
    for c in cleaned:
        tokens = re.findall(r"[a-z0-9]+", c)
        grams: set[str] = set()
        for n in range(2, min(len(tokens), 8) + 1):
            for i in range(len(tokens) - n + 1):
                grams.add(" ".join(tokens[i : i + n]))
        grams_per_candidate.append(grams)
    # Find grams present in ≥ 2 candidates.
    common: set[str] = set()
    for i, g_i in enumerate(grams_per_candidate):
        for j, g_j in enumerate(grams_per_candidate):
            if i >= j:
                continue
            common |= g_i & g_j
    if not common:
        return ""
    # Longest by word count.
    return max(common, key=lambda g: (len(g.split()), len(g)))


def _body_frequency_terms(
    body_text: str, exclude: str, limit: int = 5, locale: str = "en"
) -> list[str]:
    """Top non-stopword tokens by frequency in body, excluding primary-keyword tokens.

    `locale` selects which stopword set to apply. For non-Latin scripts (ko/ja/ar)
    a Unicode-aware tokenizer is used; for Latin scripts the original regex applies.
    """
    if not body_text:
        return []
    stopwords = _LOCALE_STOPWORDS.get(locale, _STOPWORDS)
    # Tokenizer: for non-Latin scripts use a broader Unicode word regex.
    # For Latin scripts keep the original `[a-zA-Z][a-zA-Z\-]{3,}` to skip short
    # words. KO/JA/AR words can be 1–2 chars (e.g. 비자), so minimum length is 2.
    if locale in ("ko", "ja", "ar"):
        tokens = re.findall(r"\w{2,}", body_text, flags=re.UNICODE)
        tokens = [t.lower() for t in tokens]
    else:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", body_text.lower())
    exclude_tokens = set(re.findall(r"\w+", exclude.lower(), flags=re.UNICODE))
    counts = collections.Counter(
        t for t in tokens if t not in stopwords and t not in exclude_tokens
    )
    # Filter to terms appearing ≥ 3 times.
    common = [w for w, c in counts.most_common() if c >= 3]
    return common[:limit]
