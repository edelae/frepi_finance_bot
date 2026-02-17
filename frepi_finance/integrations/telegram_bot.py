"""
Telegram Bot Integration for Frepi Finance Agent.

Handles incoming messages, routes to the finance agent,
and manages photo uploads for invoice processing.
"""

import logging
from typing import Dict
from dataclasses import dataclass, field

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from frepi_finance.config import get_config
from frepi_finance.shared.user_identification import (
    identify_finance_user,
    FinanceUserIdentification,
)
from frepi_finance.agent.finance_agent import finance_chat
from frepi_finance.memory.session_memory import SessionMemory

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# Store sessions per chat_id
_sessions: Dict[int, SessionMemory] = {}


def get_session(chat_id: int) -> SessionMemory:
    """Get or create a session for a chat."""
    if chat_id not in _sessions:
        _sessions[chat_id] = SessionMemory(telegram_chat_id=chat_id)
    return _sessions[chat_id]


def clear_session(chat_id: int):
    """Clear session for a chat."""
    if chat_id in _sessions:
        del _sessions[chat_id]


async def identify_and_setup_session(
    chat_id: int, session: SessionMemory
) -> FinanceUserIdentification:
    """Identify user and configure session."""
    identification = await identify_finance_user(chat_id)

    session.restaurant_id = identification.restaurant_id
    session.person_id = identification.person_id
    session.person_name = identification.person_name
    session.restaurant_name = identification.restaurant_name
    session.onboarding_complete = identification.onboarding_complete
    session.is_new_user = not identification.is_known

    return identification


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    chat_id = update.effective_chat.id
    clear_session(chat_id)
    session = get_session(chat_id)

    identification = await identify_and_setup_session(chat_id, session)

    if identification.onboarding_complete:
        name_part = f", {identification.person_name}" if identification.person_name else ""
        welcome = f"""📊 Olá{name_part}! Bem-vindo ao **Frepi Financeiro**!

Sou seu assistente de inteligência financeira. Posso ajudar com:

1️⃣ **Enviar nota fiscal (NF)** - processar e analisar
2️⃣ **Fechamento mensal** - relatório financeiro
3️⃣ **Análise de CMV / cardápio** - custo dos pratos
4️⃣ **Lista de acompanhamento de preços** - monitorar variações

Como posso ajudar? 🎯"""
    elif identification.is_known and not identification.onboarding_complete:
        welcome = f"""📊 Olá! Bem-vindo ao **Frepi Financeiro**!

Vejo que você já usa o Frepi para compras. Vamos configurar o módulo financeiro.

Vou precisar de algumas informações rápidas para personalizar sua experiência."""
        session.is_new_user = True
    else:
        welcome = """📊 Olá! Bem-vindo ao **Frepi Financeiro**!

Sou seu assistente de inteligência financeira para restaurantes.
Vou te ajudar a organizar e controlar as finanças do seu restaurante.

Vamos começar com um cadastro rápido!"""
        session.is_new_user = True

    await update.message.reply_text(welcome, parse_mode="Markdown")

    # If new user, trigger onboarding
    if session.is_new_user:
        response = await finance_chat("Olá, quero me cadastrar", session)
        await update.message.reply_text(response, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command."""
    help_text = """📊 **Ajuda - Frepi Financeiro**

**Comandos:**
/start - Iniciar conversa
/help - Ver esta ajuda
/limpar - Limpar histórico

**Como usar:**
• Envie fotos de notas fiscais para processar
• Digite 1-4 para acessar funções do menu
• Pergunte sobre CMV, custos ou fechamento mensal

**Dicas:**
• Envie várias NFs e depois digite "pronto"
• Peça análise de tendência de preços
• Configure alertas para produtos importantes"""

    await update.message.reply_text(help_text, parse_mode="Markdown")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /limpar command."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    session.clear_conversation()

    await update.message.reply_text(
        "✅ Histórico limpo! Pode começar uma nova conversa.",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages."""
    chat_id = update.effective_chat.id
    user_message = update.message.text

    logger.info(f"")
    logger.info(f"{'='*60}")
    logger.info(f"📨 INCOMING MESSAGE from chat_id={chat_id}")
    logger.info(f"   Text: {user_message}")
    logger.info(f"{'='*60}")

    session = get_session(chat_id)

    # Identify user if first message
    if session.restaurant_id is None and not session.is_new_user:
        identification = await identify_and_setup_session(chat_id, session)
        if not identification.is_known:
            session.is_new_user = True
        logger.info(
            f"   Identified: restaurant_id={session.restaurant_id}, "
            f"new_user={session.is_new_user}, "
            f"onboarded={session.onboarding_complete}"
        )

    try:
        await update.message.chat.send_action("typing")

        # Check if user is sending "pronto" to finalize photo batch
        if user_message.lower().strip() == "pronto" and session.uploaded_photos:
            photos = session.get_and_clear_photos()
            response = await finance_chat(
                f"Processar {len(photos)} notas fiscais: {', '.join(photos)}",
                session,
                has_photo=True,
            )
        else:
            response = await finance_chat(user_message, session)

        # Send response (split if too long for Telegram)
        if len(response) > 4096:
            for i in range(0, len(response), 4096):
                chunk = response[i:i + 4096]
                await update.message.reply_text(chunk, parse_mode="Markdown")
        else:
            await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Desculpe, ocorreu um erro. Por favor, tente novamente.",
            parse_mode="Markdown",
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photo messages (invoice uploads)."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)

    try:
        # Get the largest photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_url = file.file_path

        session.add_photo(file_url)
        photo_count = len(session.uploaded_photos)

        await update.message.reply_text(
            f"📸 Foto {photo_count} recebida!\n\n"
            f"Envie mais fotos ou digite **\"pronto\"** quando terminar.",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"Error handling photo: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Erro ao processar a foto. Tente novamente.",
            parse_mode="Markdown",
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}")


def create_application() -> Application:
    """Create and configure the Telegram application."""
    config = get_config()

    if not config.telegram_bot_token:
        raise ValueError("TELEGRAM_FINANCE_BOT_TOKEN not configured")

    application = Application.builder().token(config.telegram_bot_token).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ajuda", help_command))
    application.add_handler(CommandHandler("limpar", clear_command))
    application.add_handler(CommandHandler("clear", clear_command))

    # Message handlers
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_handler(
        MessageHandler(filters.PHOTO, handle_photo)
    )

    # Error handler
    application.add_error_handler(error_handler)

    return application


def run_polling():
    """Run the bot using polling with heartbeat scheduler."""
    logger.info("Starting Frepi Finance Telegram bot (polling mode)...")
    application = create_application()

    # Start heartbeat scheduler for proactive tasks
    try:
        from frepi_finance.services.heartbeat import init_heartbeat
        init_heartbeat(application.bot)
        logger.info("📊 Heartbeat scheduler started")
    except Exception as e:
        logger.warning(f"Heartbeat setup failed (continuing without): {e}")

    application.run_polling(allowed_updates=Update.ALL_TYPES)
