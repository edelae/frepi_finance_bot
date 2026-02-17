"""Skill-specific prompt injections based on detected user intent."""
from .invoice_skill import INVOICE_SKILL_PROMPT
from .onboarding_skill import ONBOARDING_SKILL_PROMPT
from .monthly_closure_skill import MONTHLY_CLOSURE_SKILL_PROMPT
from .cmv_skill import CMV_SKILL_PROMPT
from .watchlist_skill import WATCHLIST_SKILL_PROMPT

SKILL_PROMPTS = {
    "invoice_upload": INVOICE_SKILL_PROMPT,
    "onboarding": ONBOARDING_SKILL_PROMPT,
    "monthly_closure": MONTHLY_CLOSURE_SKILL_PROMPT,
    "cmv_query": CMV_SKILL_PROMPT,
    "watchlist": WATCHLIST_SKILL_PROMPT,
}
