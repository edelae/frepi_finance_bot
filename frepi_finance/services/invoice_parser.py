"""
Invoice Parser - GPT-4 Vision for automatic NF extraction.

Ported from frepi-agent/frepi_agent/restaurant_facing_agent/subagents/onboarding_subagent/tools/image_parser.py
Adapted for the finance agent's invoice processing flow.
"""

import base64
import json
import logging
import re
from typing import Optional, List
from dataclasses import dataclass

import httpx
from openai import OpenAI

from frepi_finance.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class InvoiceItem:
    """Single item from an invoice."""
    product_name: str
    product_code: Optional[str] = None
    quantity: float = 1.0
    unit: str = "un"
    unit_price: float = 0.0
    total_price: float = 0.0
    confidence: float = 0.0


@dataclass
class ParsedInvoice:
    """Structured data extracted from an invoice image."""
    supplier_name: str
    supplier_cnpj: Optional[str] = None
    invoice_date: Optional[str] = None
    invoice_number: Optional[str] = None
    items: Optional[List[InvoiceItem]] = None
    total_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    confidence_score: float = 0.0
    raw_response: Optional[str] = None

    def __post_init__(self):
        if self.items is None:
            self.items = []


def get_openai_client() -> OpenAI:
    """Get the OpenAI client instance."""
    config = get_config()
    return OpenAI(api_key=config.openai_api_key)


async def download_image_as_base64(image_url: str) -> Optional[str]:
    """Download an image from URL and return base64 encoded string."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(image_url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
            return base64.b64encode(response.content).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        return None


async def parse_invoice_image(
    image_url: str,
    restaurant_id: Optional[int] = None,
) -> ParsedInvoice:
    """
    Parse a single invoice image using GPT-4 Vision.

    Args:
        image_url: URL of the invoice photo (from Telegram)
        restaurant_id: Optional restaurant ID for context

    Returns:
        ParsedInvoice with extracted data, or error-state ParsedInvoice on failure
    """
    logger.info(f"Parsing invoice image: {image_url[:50]}...")

    try:
        # Download and encode image
        image_base64 = await download_image_as_base64(image_url)
        if not image_base64:
            logger.error("Failed to download image")
            return ParsedInvoice(
                supplier_name="Error",
                confidence_score=0.0,
                raw_response="Failed to download image",
            )

        client = get_openai_client()
        config = get_config()

        # Call GPT-4 Vision
        response = client.chat.completions.create(
            model=config.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": _build_vision_prompt(),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analise esta nota fiscal e extraia todos os dados em formato JSON.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=4096,
            temperature=0.1,
        )

        content = response.choices[0].message.content
        logger.info(f"GPT-4 Vision response received, length: {len(content)}")

        # Parse JSON from response
        data = _extract_json(content)

        if data is None:
            return ParsedInvoice(
                supplier_name="Parse Error",
                confidence_score=0.0,
                raw_response=content,
            )

        if data.get("error"):
            return ParsedInvoice(
                supplier_name="Not Invoice",
                confidence_score=0.0,
                raw_response=data["error"],
            )

        # Build structured items
        items = []
        for item_data in data.get("items", []):
            items.append(InvoiceItem(
                product_name=item_data.get("product_name", "Unknown"),
                product_code=item_data.get("product_code"),
                quantity=float(item_data.get("quantity", 1)),
                unit=item_data.get("unit", "un"),
                unit_price=float(item_data.get("unit_price", 0)),
                total_price=float(item_data.get("total_price", 0)),
                confidence=float(item_data.get("confidence", 0.8)),
            ))

        result = ParsedInvoice(
            supplier_name=data.get("supplier_name", "Unknown"),
            supplier_cnpj=data.get("supplier_cnpj"),
            invoice_date=data.get("invoice_date"),
            invoice_number=data.get("invoice_number"),
            items=items,
            total_amount=data.get("total_amount"),
            tax_amount=data.get("tax_amount"),
            confidence_score=float(data.get("confidence", data.get("confidence_score", 0.8))),
            raw_response=content,
        )

        logger.info(
            f"Invoice parsed: {result.supplier_name} - "
            f"{len(result.items)} items"
        )

        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from GPT-4 Vision response: {e}")
        return ParsedInvoice(
            supplier_name="Parse Error",
            confidence_score=0.0,
            raw_response=str(e),
        )
    except Exception as e:
        logger.error(f"Error parsing invoice image: {e}", exc_info=True)
        return ParsedInvoice(
            supplier_name="Error",
            confidence_score=0.0,
            raw_response=str(e),
        )


async def parse_multiple_invoices(
    image_urls: List[str],
    restaurant_id: Optional[int] = None,
) -> List[ParsedInvoice]:
    """
    Parse multiple invoice images and return combined results.

    Args:
        image_urls: List of image URLs to parse
        restaurant_id: Optional restaurant ID for context

    Returns:
        List of successfully parsed invoices (errors are filtered out)
    """
    results = []
    for url in image_urls:
        result = await parse_invoice_image(url, restaurant_id=restaurant_id)
        if result.supplier_name not in ("Error", "Parse Error", "Not Invoice"):
            results.append(result)
        else:
            logger.warning(f"Skipping failed parse for {url[:50]}: {result.raw_response}")
    return results


def format_parsed_invoices_for_display(invoices: List[ParsedInvoice]) -> str:
    """
    Format parsed invoices for display to user via Telegram.

    Groups products by supplier and shows price information.
    """
    if not invoices:
        return "Nenhum produto encontrado nas notas fiscais."

    products_by_supplier = {}
    for invoice in invoices:
        supplier = invoice.supplier_name
        if supplier not in products_by_supplier:
            products_by_supplier[supplier] = {
                "cnpj": invoice.supplier_cnpj,
                "date": invoice.invoice_date,
                "total": invoice.total_amount,
                "items": [],
            }
        for item in invoice.items:
            products_by_supplier[supplier]["items"].append(item)

    lines = ["**Produtos encontrados nas notas fiscais:**\n"]

    for supplier, info in products_by_supplier.items():
        cnpj_str = f" ({info['cnpj']})" if info.get("cnpj") else ""
        date_str = f" - {info['date']}" if info.get("date") else ""
        lines.append(f"**{supplier}**{cnpj_str}{date_str}")

        for item in info["items"][:15]:
            price_str = f"R$ {item.unit_price:.2f}/{item.unit}" if item.unit_price > 0 else ""
            qty_str = f"{item.quantity:.1f} {item.unit}" if item.quantity != 1 else ""
            parts = [f"  - {item.product_name}"]
            if qty_str:
                parts.append(qty_str)
            if price_str:
                parts.append(price_str)
            lines.append(" ".join(parts))

        if len(info["items"]) > 15:
            lines.append(f"  ... e mais {len(info['items']) - 15} produtos")

        if info.get("total"):
            lines.append(f"  **Total:** R$ {info['total']:,.2f}")
        lines.append("")

    total_products = sum(len(info["items"]) for info in products_by_supplier.values())
    lines.append(
        f"**Total:** {total_products} produtos de "
        f"{len(products_by_supplier)} fornecedor(es)"
    )

    return "\n".join(lines)


def _build_vision_prompt() -> str:
    """Build the system prompt for GPT-4 Vision invoice parsing."""
    return """Voce e um especialista em extrair dados de notas fiscais brasileiras (NF-e, NFC-e, cupom fiscal).

Analise a imagem da nota fiscal e extraia os seguintes dados em formato JSON:

{
    "supplier_name": "Nome do fornecedor/emitente",
    "supplier_cnpj": "CNPJ do fornecedor (XX.XXX.XXX/XXXX-XX)",
    "invoice_number": "Numero da NF",
    "invoice_date": "Data de emissao (YYYY-MM-DD)",
    "total_amount": 0.00,
    "tax_amount": 0.00,
    "items": [
        {
            "product_name": "Nome do produto como aparece na NF",
            "product_code": "Codigo NCM ou do fornecedor (se visivel)",
            "quantity": 0.000,
            "unit": "kg/un/cx/lt/pct/ml",
            "unit_price": 0.0000,
            "total_price": 0.00,
            "confidence": 0.0
        }
    ],
    "confidence": 0.0
}

REGRAS IMPORTANTES:
1. Extraia TODOS os itens da nota fiscal
2. Mantenha os nomes dos produtos EXATAMENTE como aparecem na NF
3. Converta valores para formato numerico (sem R$, usando ponto como decimal)
4. Se um campo nao estiver legivel, use null
5. O campo confidence (0.0-1.0) indica sua confianca na extracao
6. Para cada item, indique a confianca individual
7. Se a imagem nao for uma nota fiscal, retorne {"error": "Imagem nao parece ser uma nota fiscal"}
8. Formate CNPJ como XX.XXX.XXX/XXXX-XX
9. Formate data como YYYY-MM-DD
10. total_price de cada item = quantity * unit_price

Retorne APENAS o JSON, sem texto adicional."""


def _extract_json(content: str) -> Optional[dict]:
    """Extract JSON from GPT-4 response content."""
    if not content:
        return None

    # Try direct JSON parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding JSON object in text
    brace_start = content.find("{")
    brace_end = content.rfind("}")
    if brace_start != -1 and brace_end != -1:
        try:
            return json.loads(content[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

    logger.error(f"Could not extract JSON from response: {content[:200]}")
    return None
