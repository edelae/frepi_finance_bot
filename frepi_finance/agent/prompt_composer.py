"""
Prompt Composer - Builds the final system prompt from layered components.

This is the core of the OpenClaw-inspired architecture. The prompt is composed
from multiple layers, each injected based on context and intent. Every composition
is logged for monitoring and feedback.

Layers:
  0. SOUL (always) - Base personality
  1. User Memory (if available) - Restaurant context from DB
  2. Skill Prompt (based on intent) - Specific instructions
  3. DB Context (dynamic) - Recent invoices, watchlist, CMV status
  4. Conversation History (managed by agent) - Previous messages
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from frepi_finance.soul import SOUL_PROMPT, SOUL_VERSION
from frepi_finance.soul.skills import SKILL_PROMPTS

logger = logging.getLogger(__name__)


@dataclass
class PromptComponent:
    """A single component injected into the prompt."""
    name: str
    layer: int
    content: str
    token_estimate: int = 0

    def __post_init__(self):
        # Rough token estimate: ~4 chars per token
        self.token_estimate = len(self.content) // 4


@dataclass
class ComposedPrompt:
    """The result of prompt composition, ready for logging."""
    system_message: str
    components: list[PromptComponent] = field(default_factory=list)
    detected_intent: Optional[str] = None
    intent_confidence: float = 0.0
    total_token_estimate: int = 0
    prompt_hash: str = ""
    composition_time_ms: int = 0

    def compute_hash(self):
        """Compute SHA256 hash of the final prompt."""
        self.prompt_hash = hashlib.sha256(self.system_message.encode()).hexdigest()[:16]


MAX_CONTEXT_TOKENS = 4000  # Leave room for conversation + response


def compose_prompt(
    intent: str,
    intent_confidence: float,
    user_memory: Optional[dict] = None,
    db_context: Optional[str] = None,
    drip_context: Optional[str] = None,
) -> ComposedPrompt:
    """
    Compose the final system prompt from all layers.

    Args:
        intent: Detected user intent
        intent_confidence: Confidence of intent detection
        user_memory: Dict with user context (restaurant_name, savings_opportunity, etc.)
        db_context: Pre-formatted string with recent DB data

    Returns:
        ComposedPrompt with the full system message and metadata
    """
    start_time = time.time()
    components: list[PromptComponent] = []

    # Layer 0: SOUL (always injected)
    soul_component = PromptComponent(
        name="soul",
        layer=0,
        content=SOUL_PROMPT,
    )
    components.append(soul_component)

    # Layer 1: User Memory (if available)
    if user_memory:
        memory_lines = []
        if user_memory.get("restaurant_name"):
            memory_lines.append(f"Restaurante: {user_memory['restaurant_name']}")
        if user_memory.get("person_name"):
            memory_lines.append(f"Contato: {user_memory['person_name']}")
        if user_memory.get("savings_opportunity"):
            memory_lines.append(f"Oportunidade de economia identificada pelo dono: {user_memory['savings_opportunity']}")
        if user_memory.get("cmv_target"):
            memory_lines.append(f"Meta de CMV: {user_memory['cmv_target']}%")

        if memory_lines:
            memory_content = "## Contexto do Restaurante\n" + "\n".join(f"- {line}" for line in memory_lines)
            components.append(PromptComponent(
                name="user_memory",
                layer=1,
                content=memory_content,
            ))

    # Layer 2: Skill Prompt (based on intent)
    skill_prompt = SKILL_PROMPTS.get(intent)
    if skill_prompt:
        components.append(PromptComponent(
            name=f"skill_{intent}",
            layer=2,
            content=skill_prompt,
        ))

    # Layer 3: DB Context (dynamic data)
    if db_context:
        components.append(PromptComponent(
            name="db_context",
            layer=3,
            content=f"## Dados Recentes\n{db_context}",
        ))

    # Layer 4: Drip Context (preference questions to sneak in)
    if drip_context and intent != "onboarding":
        components.append(PromptComponent(
            name="drip_context",
            layer=4,
            content=drip_context,
        ))

    # Assemble final prompt respecting token limits
    total_tokens = sum(c.token_estimate for c in components)

    # If over budget, trim DB context first, then skill
    if total_tokens > MAX_CONTEXT_TOKENS:
        logger.warning(
            f"Prompt over budget: {total_tokens} tokens > {MAX_CONTEXT_TOKENS}. "
            "Trimming lower-priority components."
        )
        # Remove DB context if still over
        components = [c for c in components if c.name != "db_context"]
        total_tokens = sum(c.token_estimate for c in components)

    # Build final system message
    system_message = "\n\n".join(c.content for c in components)

    elapsed_ms = int((time.time() - start_time) * 1000)

    result = ComposedPrompt(
        system_message=system_message,
        components=components,
        detected_intent=intent,
        intent_confidence=intent_confidence,
        total_token_estimate=total_tokens,
        composition_time_ms=elapsed_ms,
    )
    result.compute_hash()

    # Log the composition
    component_summary = ", ".join(
        f"{c.name}({c.token_estimate}t)" for c in components
    )
    logger.info(
        f"📝 PROMPT COMPOSED: intent={intent}, "
        f"components=[{component_summary}], "
        f"total_tokens≈{total_tokens}, hash={result.prompt_hash}"
    )

    return result
