"""
Heartbeat Service: Scheduled proactive checks using APScheduler.

Runs periodic tasks like price watchlist checks, monthly closure reminders,
and CMV alerts. Sends notifications via Telegram.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from frepi_finance.shared.supabase_client import fetch_many, Tables
from frepi_finance.services.price_trend import check_watchlist_alerts
from frepi_finance.soul.identity import format_brl, format_percent

logger = logging.getLogger(__name__)

# Global scheduler
_scheduler: AsyncIOScheduler = None
_telegram_bot = None


def init_heartbeat(telegram_bot):
    """Initialize the heartbeat scheduler with a Telegram bot instance."""
    global _scheduler, _telegram_bot
    _telegram_bot = telegram_bot

    _scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    # Price watchlist check - every hour during business hours
    _scheduler.add_job(
        _check_price_watchlist,
        IntervalTrigger(hours=1),
        id="price_watchlist",
        name="Price Watchlist Check",
    )

    # Monthly closure reminder - days 25-31 at 9am
    _scheduler.add_job(
        _monthly_closure_reminder,
        CronTrigger(day="25-31", hour=9, timezone="America/Sao_Paulo"),
        id="monthly_reminder",
        name="Monthly Closure Reminder",
    )

    # Revenue request - days 1-5 at 9am
    _scheduler.add_job(
        _revenue_request,
        CronTrigger(day="1-5", hour=9, timezone="America/Sao_Paulo"),
        id="revenue_request",
        name="Revenue Request",
    )

    # CMV alert - daily at 10am
    _scheduler.add_job(
        _cmv_alert,
        CronTrigger(hour=10, timezone="America/Sao_Paulo"),
        id="cmv_alert",
        name="CMV Alert",
    )

    _scheduler.start()
    logger.info("Heartbeat scheduler started with 4 jobs")


def stop_heartbeat():
    """Stop the heartbeat scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Heartbeat scheduler stopped")


async def _check_price_watchlist():
    """Check all restaurants' watchlists for price alerts."""
    now = datetime.now()
    if now.hour < 7 or now.hour > 22:
        return  # Only during business hours

    try:
        # Get all restaurants with active watchlist entries
        entries = await fetch_many(
            Tables.PRODUCT_PRICE_WATCHLIST,
            filters={"is_active": True},
        )

        # Group by restaurant
        by_restaurant = {}
        for entry in entries:
            rid = entry["restaurant_id"]
            if rid not in by_restaurant:
                by_restaurant[rid] = []
            by_restaurant[rid].append(entry)

        for restaurant_id in by_restaurant:
            alerts = await check_watchlist_alerts(restaurant_id)
            if alerts:
                await _send_watchlist_alerts(restaurant_id, alerts)

    except Exception as e:
        logger.error(f"Error in price watchlist check: {e}")


async def _monthly_closure_reminder():
    """Send monthly closure reminders to restaurants without a current month report."""
    try:
        now = datetime.now()
        year, month = now.year, now.month

        # Get all restaurants with finance onboarding
        onboardings = await fetch_many(
            Tables.FINANCE_ONBOARDING,
            filters={"status": "completed"},
        )

        for ob in onboardings:
            restaurant_id = ob.get("restaurant_id")
            chat_id = ob.get("telegram_chat_id")
            if not restaurant_id or not chat_id:
                continue

            # Check if report exists for this month
            from frepi_finance.shared.supabase_client import fetch_one
            report = await fetch_one(Tables.MONTHLY_FINANCIAL_REPORTS, {
                "restaurant_id": restaurant_id,
                "report_year": year,
                "report_month": month,
            })

            if not report:
                message = (
                    "📅 **Lembrete de Fechamento Mensal**\n\n"
                    "Faltam poucos dias para fechar o mês! "
                    "Envie suas notas fiscais pendentes e vamos fazer o fechamento.\n\n"
                    "Digite 2️⃣ para começar o fechamento mensal."
                )
                await _send_telegram_message(chat_id, message)

    except Exception as e:
        logger.error(f"Error in monthly closure reminder: {e}")


async def _revenue_request():
    """Request revenue data for previous month."""
    try:
        now = datetime.now()
        # Previous month
        if now.month == 1:
            prev_year, prev_month = now.year - 1, 12
        else:
            prev_year, prev_month = now.year, now.month - 1

        month_names = [
            "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
        ]
        month_name = month_names[prev_month]

        onboardings = await fetch_many(
            Tables.FINANCE_ONBOARDING,
            filters={"status": "completed"},
        )

        for ob in onboardings:
            restaurant_id = ob.get("restaurant_id")
            chat_id = ob.get("telegram_chat_id")
            if not restaurant_id or not chat_id:
                continue

            from frepi_finance.shared.supabase_client import fetch_one
            report = await fetch_one(Tables.MONTHLY_FINANCIAL_REPORTS, {
                "restaurant_id": restaurant_id,
                "report_year": prev_year,
                "report_month": prev_month,
            })

            if not report or not report.get("total_revenue"):
                message = (
                    f"📊 **Faturamento de {month_name}**\n\n"
                    f"Para completar seu relatório de {month_name}, "
                    f"preciso do faturamento total do mês.\n\n"
                    f"Qual foi o faturamento total em {month_name}?"
                )
                await _send_telegram_message(chat_id, message)

    except Exception as e:
        logger.error(f"Error in revenue request: {e}")


async def _cmv_alert():
    """Alert restaurants with high CMV."""
    try:
        reports = await fetch_many(
            Tables.MONTHLY_FINANCIAL_REPORTS,
            filters={"status": "complete"},
            order_by="-report_year",
        )

        # Get latest per restaurant
        latest_by_restaurant = {}
        for report in reports:
            rid = report["restaurant_id"]
            if rid not in latest_by_restaurant:
                latest_by_restaurant[rid] = report

        for rid, report in latest_by_restaurant.items():
            cmv = report.get("cmv_percent", 0)
            if cmv > 40:
                # Find chat_id
                ob = await fetch_many(
                    Tables.FINANCE_ONBOARDING,
                    filters={"restaurant_id": rid, "status": "completed"},
                    limit=1,
                )
                if ob:
                    chat_id = ob[0].get("telegram_chat_id")
                    if chat_id:
                        message = (
                            f"⚠️ **Alerta de CMV**\n\n"
                            f"Seu CMV está em {cmv:.1f}% — acima da meta de 35%.\n\n"
                            f"Digite 3️⃣ para ver a análise detalhada do cardápio."
                        )
                        await _send_telegram_message(chat_id, message)

    except Exception as e:
        logger.error(f"Error in CMV alert: {e}")


async def _send_watchlist_alerts(restaurant_id: int, alerts: list[dict]):
    """Send watchlist alerts via Telegram."""
    ob = await fetch_many(
        Tables.FINANCE_ONBOARDING,
        filters={"restaurant_id": restaurant_id, "status": "completed"},
        limit=1,
    )
    if not ob:
        return

    chat_id = ob[0].get("telegram_chat_id")
    if not chat_id:
        return

    for alert in alerts:
        emoji = "📈" if alert["direction"] == "up" else "📉"
        direction = "subiu" if alert["direction"] == "up" else "caiu"
        message = (
            f"🔔 **Alerta de Preço**\n\n"
            f"{alert['product_name']}: {emoji} {direction} {abs(alert['change_percent']):.1f}%\n"
            f"De {format_brl(alert['old_price'])} → {format_brl(alert['new_price'])}"
        )
        await _send_telegram_message(chat_id, message)


async def _send_telegram_message(chat_id: int, message: str):
    """Send a Telegram message using the bot instance."""
    if _telegram_bot:
        try:
            await _telegram_bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
    else:
        logger.warning(f"No Telegram bot configured for heartbeat message to {chat_id}")
