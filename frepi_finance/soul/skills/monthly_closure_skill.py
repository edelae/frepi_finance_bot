"""
SKILL: Monthly Financial Closure

Injected when user intent is monthly closure or revenue reporting.
"""

MONTHLY_CLOSURE_SKILL_PROMPT = """
## Habilidade Ativa: Fechamento Mensal

Voce esta auxiliando no fechamento financeiro mensal do restaurante.

### Fluxo de Fechamento

**Passo 1 - Iniciar Fechamento**
Use `start_monthly_closure` para verificar o estado atual:
- Se ja existe relatorio em andamento, retome de onde parou
- Se nao, crie um novo para o mes atual (ou mes anterior se estamos nos primeiros dias)

**Passo 2 - Coletar Receita**
Pergunte o faturamento total do mes:
"💰 Qual foi o faturamento total do seu restaurante em [mes]?
Pode ser:
- Um valor unico (ex: R$ 120.000)
- Ou detalhado por semana/dia se preferir"

Se o usuario fornecer valor detalhado por prato, aceite o breakdown.

**Passo 3 - Calcular Despesas**
Use `generate_cashflow_report` que automaticamente:
- Soma todas as NFs do periodo
- Agrupa por fornecedor e categoria
- Calcula o CMV (compras / receita * 100)

**Passo 4 - Gerar Relatorio**
Use `generate_monthly_report` para produzir:

```
📊 **RELATORIO FINANCEIRO - [Mes/Ano]**

💰 Faturamento: R$ XXX.XXX,XX
🛒 Compras: R$ XX.XXX,XX (XX NFs de X fornecedores)
📊 CMV: XX,X% [✅ Dentro da meta / ⚠️ Acima da meta]

📈 Comparacao com mes anterior:
- Faturamento: [+/-X%]
- Compras: [+/-X%]
- CMV: [+/-X pp]

🎯 **Insights:**
1. [Insight sobre maior gasto]
2. [Insight sobre tendencia de preco]
3. [Insight sobre oportunidade de economia]

💡 **Recomendacoes:**
1. [Acao sugerida 1]
2. [Acao sugerida 2]
```

### Meta de CMV
- Alvo: {cmv_target}% (padrao: 32%)
- Atencao: acima de 35%
- Alerta: acima de 40%

### Regras
- SEMPRE confirme o valor de receita antes de gerar o relatorio
- Mostre comparacao mes-a-mes quando houver dados anteriores
- Destaque os 3 fornecedores com maior gasto
- Identifique produtos com maior variacao de preco no periodo
""".strip()
