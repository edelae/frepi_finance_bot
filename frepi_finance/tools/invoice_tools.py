"""
Invoice tools - Parse, store, and analyze invoice data.
"""

from typing import Any

from frepi_finance.shared.supabase_client import get_supabase_client, Tables


INVOICE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "parse_invoice_photo",
            "description": "Parse a single invoice photo using GPT-4 Vision. Extracts supplier, CNPJ, products, quantities, and prices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_url": {
                        "type": "string",
                        "description": "URL of the invoice photo from Telegram"
                    }
                },
                "required": ["image_url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_multiple_invoices",
            "description": "Parse multiple invoice photos at once. Use when user has uploaded several photos and said 'pronto'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of invoice photo URLs"
                    }
                },
                "required": ["image_urls"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_invoice",
            "description": "Confirm that a parsed invoice's data is correct and should be saved permanently.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_id": {
                        "type": "string",
                        "description": "UUID of the invoice to confirm"
                    }
                },
                "required": ["invoice_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_invoice_summary",
            "description": "Get a summary of invoices for a restaurant over a time period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "months": {
                        "type": "integer",
                        "description": "Number of months to look back (default: 3)",
                        "default": 3
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_trend",
            "description": "Get the price history and trend for a specific product across invoices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "Name of the product to check"
                    },
                    "months": {
                        "type": "integer",
                        "description": "Number of months to look back (default: 6)",
                        "default": 6
                    }
                },
                "required": ["product_name"]
            }
        }
    },
]


async def execute_invoice_tool(tool_name: str, args: dict[str, Any], session) -> dict:
    """Execute an invoice tool."""

    if tool_name == "parse_invoice_photo":
        from frepi_finance.services.invoice_parser import parse_invoice_image

        result = await parse_invoice_image(args["image_url"])
        if result:
            # Store parsed invoice in DB
            client = get_supabase_client()
            invoice_data = {
                "restaurant_id": session.restaurant_id,
                "telegram_chat_id": session.telegram_chat_id,
                "telegram_file_url": args["image_url"],
                "supplier_name_extracted": result.get("supplier_name"),
                "supplier_cnpj_extracted": result.get("supplier_cnpj"),
                "invoice_number": result.get("invoice_number"),
                "invoice_date": result.get("invoice_date"),
                "total_amount": result.get("total_amount"),
                "status": "parsed",
                "parsing_confidence": result.get("confidence", 0.0),
                "raw_extraction_result": result,
            }

            invoice = client.table(Tables.INVOICES).insert(invoice_data).execute()
            invoice_id = invoice.data[0]["id"] if invoice.data else None

            # Store line items
            if invoice_id and result.get("items"):
                for idx, item in enumerate(result["items"]):
                    line_data = {
                        "invoice_id": invoice_id,
                        "product_name_raw": item.get("product_name"),
                        "quantity": item.get("quantity"),
                        "unit": item.get("unit"),
                        "unit_price": item.get("unit_price"),
                        "total_price": item.get("total_price"),
                        "extraction_confidence": item.get("confidence", 0.0),
                        "line_index": idx,
                    }
                    client.table(Tables.INVOICE_LINE_ITEMS).insert(line_data).execute()

            # Compute price trends for line items
            if invoice_id:
                from frepi_finance.services.price_trend import compute_trends_for_invoice
                trends = await compute_trends_for_invoice(invoice_id, session.restaurant_id)
            else:
                trends = []

            session.current_invoice_id = invoice_id

            return {
                "success": True,
                "invoice_id": invoice_id,
                "supplier": result.get("supplier_name"),
                "cnpj": result.get("supplier_cnpj"),
                "date": result.get("invoice_date"),
                "items_count": len(result.get("items", [])),
                "total": result.get("total_amount"),
                "items": result.get("items", []),
                "price_trends": trends,
            }

        return {"success": False, "error": "Failed to parse invoice"}

    elif tool_name == "parse_multiple_invoices":
        from frepi_finance.services.invoice_parser import parse_invoice_image

        results = []
        for url in args["image_urls"]:
            result = await parse_invoice_image(url)
            if result:
                results.append(result)

        return {
            "success": True,
            "parsed_count": len(results),
            "total_sent": len(args["image_urls"]),
            "invoices": results,
        }

    elif tool_name == "confirm_invoice":
        client = get_supabase_client()
        client.table(Tables.INVOICES).update({
            "status": "confirmed",
            "user_confirmed": True,
        }).eq("id", args["invoice_id"]).execute()

        return {"success": True, "invoice_id": args["invoice_id"], "status": "confirmed"}

    elif tool_name == "get_invoice_summary":
        client = get_supabase_client()
        months = args.get("months", 3)

        result = client.table(Tables.INVOICES).select(
            "id, supplier_name_extracted, invoice_date, total_amount, status"
        ).eq(
            "restaurant_id", session.restaurant_id
        ).gte(
            "invoice_date", f"now() - interval '{months} months'"
        ).order("invoice_date", desc=True).execute()

        invoices = result.data or []
        total = sum(inv.get("total_amount", 0) or 0 for inv in invoices)

        return {
            "invoice_count": len(invoices),
            "total_amount": total,
            "months": months,
            "invoices": invoices[:20],  # Limit to most recent 20
        }

    elif tool_name == "get_price_trend":
        from frepi_finance.services.price_trend import get_product_price_trend

        trends = await get_product_price_trend(
            session.restaurant_id,
            args["product_name"],
            args.get("months", 6),
        )
        return trends

    return {"error": f"Unknown invoice tool: {tool_name}"}
