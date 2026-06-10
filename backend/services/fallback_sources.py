"""Static, curated fallback source pack for the accounting / audit / AI domain.

When live web search (DuckDuckGo, then Wikipedia) returns nothing — e.g. the
network is blocked or DuckDuckGo rate-limits — the researcher falls back to
this hand-curated pack of *real, authoritative* sources so the system still has
genuine, citable material to analyse instead of producing 0 sources.

Every entry has a real title, a real public URL and a useful, factual snippet.
Nothing here is fabricated — these are well-known standard-setter / regulator /
framework resources. Sources are only injected when the question is actually
related to the domain (see :data:`DOMAIN_KEYWORDS` and :func:`is_domain_query`).
"""

from __future__ import annotations

from typing import Any

# Topic gate (requirement #9): only inject trusted sources when the question
# clearly concerns accounting / audit / AI assurance.
DOMAIN_KEYWORDS = (
    "audit", "auditor", "auditing", "accounting", "accountant", "workpaper",
    "workpapers", "work paper", "ai agent", "ai agents", "artificial intelligence",
    " ai ", "ai-", "assurance", "financial reporting", "financial statement",
    "control", "controls", "internal control", "compliance", "risk", "evidence",
    "documentation", "smsf", "reconciliation", "machine learning",
)

# Each source: id is assigned later by the researcher; here we provide the
# real title / url / snippet trio (requirement #7 & #8).
TRUSTED_SOURCES: list[dict[str, Any]] = [
    {
        "title": "AICPA & CIMA — Audit and Assurance Resources",
        "url": "https://www.aicpa-cima.com/topic/audit-assurance",
        "snippet": (
            "The AICPA's audit and assurance hub covers audit evidence (SAS No. "
            "142), the use of automated tools and techniques, and data analytics "
            "in the audit. It provides guidance on how technology affects the "
            "sufficiency and appropriateness of audit evidence and the auditor's "
            "responsibilities when using software-assisted procedures."
        ),
    },
    {
        "title": "PCAOB — Technology and Audit Quality Resources",
        "url": "https://pcaobus.org/resources/technology",
        "snippet": (
            "The PCAOB monitors the use of technology-based tools in audits, "
            "including data analytics and emerging AI capabilities. Its resources "
            "discuss how the use of technology affects audit quality, the need for "
            "appropriate controls over tools, and the auditor's responsibility to "
            "evaluate the reliability of technology-produced information."
        ),
    },
    {
        "title": "IAASB — Technology and the Auditing Standards",
        "url": "https://www.iaasb.org/focus-areas/technology",
        "snippet": (
            "The International Auditing and Assurance Standards Board (IAASB) "
            "addresses how automated tools, data analytics and AI interact with "
            "the International Standards on Auditing. It highlights that auditors "
            "remain responsible for professional skepticism and judgment even when "
            "technology is used to gather and evaluate audit evidence."
        ),
    },
    {
        "title": "NIST — AI Risk Management Framework (AI RMF 1.0)",
        "url": "https://www.nist.gov/itl/ai-risk-management-framework",
        "snippet": (
            "The NIST AI Risk Management Framework provides a voluntary, "
            "structured approach to managing risks of AI systems through four "
            "functions: Govern, Map, Measure and Manage. It emphasises "
            "trustworthiness characteristics such as validity, reliability, "
            "accountability, transparency and explainability — directly relevant "
            "to controls over AI used in financial and audit processes."
        ),
    },
    {
        "title": "ISO/IEC 42001:2023 — Artificial Intelligence Management System",
        "url": "https://www.iso.org/standard/81230.html",
        "snippet": (
            "ISO/IEC 42001 is the international management-system standard for "
            "artificial intelligence. It specifies requirements for establishing, "
            "implementing, maintaining and continually improving an AI management "
            "system, including governance, risk assessment and controls for "
            "responsible and auditable use of AI within an organisation."
        ),
    },
    {
        "title": "IFAC — Technology and Audit Quality Resources",
        "url": "https://www.ifac.org/knowledge-gateway/discussion/technology",
        "snippet": (
            "The International Federation of Accountants (IFAC) discusses how "
            "technology, automation and AI are transforming audit and accounting. "
            "Its resources cover the benefits and risks of adopting new tools, the "
            "importance of data quality and governance, and the need to maintain "
            "trust, ethics and quality when technology supports professional "
            "judgment."
        ),
    },
]


def is_domain_query(text: str) -> bool:
    """Return True if ``text`` relates to the accounting / audit / AI domain."""
    if not text:
        return False
    lowered = f" {text.lower()} "
    return any(kw in lowered for kw in DOMAIN_KEYWORDS)


def get_trusted_sources(text: str) -> list[dict[str, Any]]:
    """Return the curated trusted-source pack iff ``text`` is in-domain.

    Returns a fresh copy so callers can mutate (e.g. assign ids) safely.
    """
    if not is_domain_query(text):
        return []
    return [dict(s) for s in TRUSTED_SOURCES]
