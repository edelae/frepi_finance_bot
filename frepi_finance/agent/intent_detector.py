"""
Intent Detector - Classifies user messages into intent categories.

Each intent maps to a specific skill prompt that gets injected into the system message.
The detection results are logged for feedback loop analysis.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Intent name constants
INTENT_INVOICE = "invoice_upload"
INTENT_MONTHLY = "monthly_closure"
INTENT_CMV = "cmv_query"
INTENT_WATCHLIST = "watchlist"
INTENT_ONBOARDING = "onboarding"
INTENT_GENERAL = "general"


@dataclass
class DetectedIntent:
    """Result of intent detection."""
    intent: str  # invoice_upload, monthly_closure, cmv_query, watchlist, onboarding, general
    confidence: float  # 0.0 to 1.0
    trigger_pattern: Optional[str] = None  # Which pattern matched


# Intent patterns ordered by specificity (most specific first)
INTENT_PATTERNS = {
    "invoice_upload": {
        "keywords": [
            r"\bnf\b", r"\bnota\s*fiscal\b", r"\bcupom\b", r"\brecibo\b",
            r"\bfatura\b", r"\bnota\b", r"\binvoice\b",
        ],
        "phrases": [
            r"enviar\s+nota", r"processar\s+nota", r"recebi\s+uma?\s+nota",
            r"nova\s+nf", r"nota\s+do", r"nota\s+da",
        ],
        "confidence_keyword": 0.85,
        "confidence_phrase": 0.92,
    },
    "monthly_closure": {
        "keywords": [
            r"\bfechamento\b", r"\bfaturamento\b", r"\breceita\b",
            r"\brelat[oó]rio\b", r"\bfluxo\s+de\s+caixa\b", r"\bcashflow\b",
            r"\bresultado\s+do\s+m[eê]s\b",
        ],
        "phrases": [
            r"fechamento\s+(do\s+)?m[eê]s", r"quanto\s+faturou",
            r"receita\s+do\s+m[eê]s", r"relat[oó]rio\s+mensal",
            r"fechar\s+o\s+m[eê]s",
        ],
        "confidence_keyword": 0.82,
        "confidence_phrase": 0.90,
    },
    "cmv_query": {
        "keywords": [
            r"\bcmv\b", r"\bfood\s*cost\b", r"\bcusto\s+do\s+prato\b",
            r"\bcard[aá]pio\b", r"\bingrediente\b", r"\breceita\b",
            r"\bmargem\b", r"\brentabilidade\b",
        ],
        "phrases": [
            r"custo\s+d[eo]\s+card[aá]pio", r"an[aá]lise\s+de\s+cmv",
            r"prato\s+mais\s+caro", r"cadastrar\s+prato",
            r"adicionar\s+ingrediente", r"food\s+cost",
            r"quanto\s+custa\s+o\s+prato", r"margem\s+de\s+contribui",
            r"ficha\s+t[eé]cnica",
        ],
        "confidence_keyword": 0.80,
        "confidence_phrase": 0.90,
    },
    "watchlist": {
        "keywords": [
            r"\bacompanhar\b", r"\bmonitorar\b", r"\balertar?\b",
            r"\bwatchlist\b", r"\bobservar\b", r"\bvigia\b",
            r"\blista\s+de\s+acompanhamento\b",
        ],
        "phrases": [
            r"acompanhar\s+pre[cç]o", r"alertar\s+quando",
            r"monitorar\s+pre[cç]o", r"lista\s+de\s+pre[cç]os",
            r"me\s+avise?\s+quando", r"observar\s+pre[cç]o",
        ],
        "confidence_keyword": 0.82,
        "confidence_phrase": 0.90,
    },
}

# Menu selection patterns (user picks option 1-4)
MENU_PATTERNS = {
    "1": "invoice_upload",
    "2": "monthly_closure",
    "3": "cmv_query",
    "4": "watchlist",
}


def detect_intent(message: str, has_photo: bool = False, is_new_user: bool = False) -> DetectedIntent:
    """
    Detect the user's intent from their message.

    Args:
        message: The user's text message
        has_photo: Whether the message includes a photo
        is_new_user: Whether this is a new/unregistered user

    Returns:
        DetectedIntent with intent category, confidence, and trigger pattern
    """
    # Priority 1: New user always goes to onboarding
    if is_new_user:
        logger.info(f"🎯 INTENT: onboarding (new user)")
        return DetectedIntent(intent="onboarding", confidence=1.0, trigger_pattern="new_user")

    # Priority 2: Photo always means invoice
    if has_photo:
        logger.info(f"🎯 INTENT: invoice_upload (photo detected)")
        return DetectedIntent(intent="invoice_upload", confidence=0.95, trigger_pattern="photo")

    message_lower = message.lower().strip()

    # Priority 3: Direct menu selection (1, 2, 3, 4)
    if message_lower in MENU_PATTERNS:
        intent = MENU_PATTERNS[message_lower]
        logger.info(f"🎯 INTENT: {intent} (menu selection: {message_lower})")
        return DetectedIntent(intent=intent, confidence=0.95, trigger_pattern=f"menu_{message_lower}")

    # Priority 4: Pattern matching against intent categories
    best_intent = "general"
    best_confidence = 0.0
    best_pattern = None

    for intent_name, patterns in INTENT_PATTERNS.items():
        # Check phrases first (higher confidence)
        for phrase in patterns["phrases"]:
            if re.search(phrase, message_lower):
                conf = patterns["confidence_phrase"]
                if conf > best_confidence:
                    best_confidence = conf
                    best_intent = intent_name
                    best_pattern = phrase
                break

        # Check keywords
        if best_intent != intent_name:  # Only if phrase didn't match
            for keyword in patterns["keywords"]:
                if re.search(keyword, message_lower):
                    conf = patterns["confidence_keyword"]
                    if conf > best_confidence:
                        best_confidence = conf
                        best_intent = intent_name
                        best_pattern = keyword
                    break

    logger.info(
        f"🎯 INTENT: {best_intent} "
        f"(confidence={best_confidence:.2f}, pattern={best_pattern})"
    )

    return DetectedIntent(
        intent=best_intent,
        confidence=best_confidence if best_confidence > 0 else 0.5,
        trigger_pattern=best_pattern,
    )
