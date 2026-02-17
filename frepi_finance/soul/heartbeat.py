"""
HEARTBEAT - Proactive scheduled task definitions.

Inspired by OpenClaw's HEARTBEAT pattern. Defines tasks that run
on a schedule to proactively assist the user.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class HeartbeatTask:
    """Definition of a periodic proactive task."""
    name: str
    description: str
    schedule_type: str  # 'interval', 'cron'
    # For interval type
    interval_minutes: Optional[int] = None
    # For cron type
    cron_day: Optional[str] = None
    cron_hour: Optional[int] = None
    cron_minute: Optional[int] = None


# Define all heartbeat tasks
HEARTBEAT_TASKS = [
    HeartbeatTask(
        name="price_watchlist_check",
        description="Check price watchlist for alerts on significant changes or better competitor prices",
        schedule_type="interval",
        interval_minutes=60,
    ),
    HeartbeatTask(
        name="monthly_closure_reminder",
        description="Remind about monthly closure between day 25 and end of month",
        schedule_type="cron",
        cron_day="25-31",
        cron_hour=9,
        cron_minute=0,
    ),
    HeartbeatTask(
        name="revenue_request",
        description="Request revenue input for previous month between day 1-5",
        schedule_type="cron",
        cron_day="1-5",
        cron_hour=9,
        cron_minute=0,
    ),
    HeartbeatTask(
        name="cmv_alert",
        description="Alert if any month CMV exceeds 40%",
        schedule_type="cron",
        cron_hour=10,
        cron_minute=0,
    ),
    HeartbeatTask(
        name="pending_invoices_check",
        description="Check for invoices stuck in 'uploaded' status (not yet parsed)",
        schedule_type="interval",
        interval_minutes=120,
    ),
]

# Heartbeat prompt injected during proactive wake-ups
HEARTBEAT_PROMPT = """
## Tarefa de Heartbeat

Voce esta sendo ativado proativamente para verificar tarefas pendentes.
Verifique o seguinte e notifique o restaurante SE houver algo relevante:

1. **Lista de Acompanhamento de Precos**: Verifique se algum produto monitorado teve variacao significativa
2. **Fechamento Mensal**: Se estamos entre dia 25 e fim do mes, lembre sobre NFs pendentes
3. **Pedido de Receita**: Se estamos entre dia 1-5, peca o faturamento do mes anterior
4. **Alerta de CMV**: Se o CMV do mes atual esta acima de 40%, alerte
5. **NFs Pendentes**: Verifique se ha notas fiscais aguardando processamento

IMPORTANTE: So envie mensagem se houver algo RELEVANTE. Nao envie mensagens vazias.
""".strip()
