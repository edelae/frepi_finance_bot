"""
Frepi Finance CLI - Main entry point.

Provides CLI commands for running the finance agent.
"""

import asyncio
import click
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from frepi_finance.config import get_config

console = Console()


@click.group()
def cli():
    """Frepi Finance - Restaurant Financial Intelligence"""
    pass


@cli.command()
def test():
    """Test configuration and database connection."""
    asyncio.run(_test_connection())


async def _test_connection():
    """Test the database connection."""
    config = get_config()
    missing = config.validate()
    if missing:
        console.print(f"[red]❌ Missing config: {', '.join(missing)}[/red]")
        return

    console.print("[green]✅ Configuration loaded[/green]")
    console.print(f"  Model: {config.chat_model}")
    console.print(f"  Supabase: {config.supabase_url[:40]}...")
    console.print(f"  Telegram: {'Configured' if config.telegram_bot_token else 'Not configured'}")

    from frepi_finance.shared.supabase_client import test_connection

    success = await test_connection()
    if success:
        console.print("[green]✅ Database connection OK[/green]")
    else:
        console.print("[red]❌ Database connection failed[/red]")


@cli.command()
def chat_cli():
    """Start an interactive chat session."""
    asyncio.run(_chat_session())


async def _chat_session():
    """Run an interactive chat session."""
    console.print(Panel.fit(
        "[bold green]Frepi Financeiro[/bold green] - Inteligência Financeira\n"
        "Digite 'sair' para encerrar.",
        title="📊 Bem-vindo!",
    ))

    config = get_config()
    missing = config.validate()
    if missing:
        console.print(f"[red]❌ Missing: {', '.join(missing)}[/red]")
        return

    from frepi_finance.agent.finance_agent import finance_chat
    from frepi_finance.memory.session_memory import SessionMemory

    session = SessionMemory()

    try:
        from frepi_finance.agent.finance_agent import get_finance_agent
        get_finance_agent()
        console.print("[green]✅ Agent initialized[/green]\n")
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        return

    while True:
        try:
            user_input = console.input("[bold blue]Você:[/bold blue] ")
        except (KeyboardInterrupt, EOFError):
            break

        if user_input.lower() in ("sair", "exit", "quit", "q"):
            console.print("\n[yellow]Até logo! 👋[/yellow]")
            break

        if not user_input.strip():
            continue

        try:
            with console.status("[bold green]Pensando..."):
                response = await finance_chat(user_input, session)

            console.print()
            console.print("[bold green]Frepi:[/bold green]")
            console.print(Markdown(response))
            console.print()
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")


@cli.command()
def info():
    """Show configuration information."""
    config = get_config()

    console.print(Panel.fit(
        f"[bold]Model:[/bold] {config.chat_model}\n"
        f"[bold]Supabase:[/bold] {config.supabase_url[:30]}...\n"
        f"[bold]Telegram:[/bold] {'Configured' if config.telegram_bot_token else 'Not configured'}\n"
        f"[bold]Environment:[/bold] {config.environment}",
        title="🔧 Configuration",
    ))

    missing = config.validate()
    if missing:
        console.print(f"[yellow]⚠️ Missing: {', '.join(missing)}[/yellow]")
    else:
        console.print("[green]✅ Configuration complete[/green]")


@cli.command()
def telegram():
    """Start the Telegram bot (polling mode)."""
    from frepi_finance.integrations.telegram_bot import run_polling

    config = get_config()
    if not config.telegram_bot_token:
        console.print("[red]❌ TELEGRAM_FINANCE_BOT_TOKEN not configured[/red]")
        return

    console.print(Panel.fit(
        "Starting Frepi Finance Telegram bot...\n"
        "Press Ctrl+C to stop.",
        title="📊 Frepi Finance Bot",
    ))

    run_polling()


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
