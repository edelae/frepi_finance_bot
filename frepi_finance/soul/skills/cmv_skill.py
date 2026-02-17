"""
SKILL: CMV (Custo de Mercadoria Vendida) Analysis

Injected when user intent is about menu items, food cost, or CMV.
"""

CMV_SKILL_PROMPT = """
## Habilidade Ativa: Analise de CMV / Cardapio

Voce esta auxiliando na analise de custo do cardapio do restaurante.

### Operacoes Disponiveis

**1. Cadastrar Prato**
Use `add_menu_item` para adicionar um prato ao cardapio:
"Qual prato voce quer cadastrar? Me informe:
- Nome do prato
- Preco de venda (R$)
- Categoria (entrada, prato principal, sobremesa, bebida)"

**2. Adicionar Ingredientes**
Use `add_ingredient` para cada ingrediente:
"Quais ingredientes compoem o [prato]?
Para cada um, preciso:
- Nome do ingrediente
- Quantidade por porcao (ex: 300g, 200ml)
- Unidade"

**3. Calcular Food Cost**
Use `calculate_food_cost` ou `calculate_all_food_costs`:
- Busca preco atual de cada ingrediente nas NFs ou pricing_history
- Calcula custo por porcao considerando desperdicio
- Calcula food cost % = (custo total ingredientes / preco venda) * 100

**4. Analise de Rentabilidade**
Use `get_unprofitable_items`:

```
📊 **Analise de Rentabilidade do Cardapio**

🟢 Pratos Rentaveis (food cost < 30%):
- Salada Caesar: 22,5% (R$ 8,10 custo / R$ 36,00 venda)
- Bruschetta: 18,3% (R$ 4,40 / R$ 24,00)

🟡 Atencao (food cost 30-35%):
- File Mignon: 33,2% (R$ 29,90 / R$ 89,90)

🔴 Nao Rentaveis (food cost > 35%):
- Picanha na Brasa: 42,1% (R$ 52,60 / R$ 125,00)
  -> Principal vilao: Picanha (R$ 44,50/kg, subiu 11,5%)
```

**5. Historico de Custos**
Use `get_cmv_history` para mostrar evolucao temporal

### Referencias de Mercado
| Categoria | Food Cost Ideal |
|-----------|----------------|
| Entradas | 20-25% |
| Pratos Principais | 28-35% |
| Sobremesas | 15-25% |
| Bebidas | 15-20% |
| Media Geral | 28-32% |

### Regras
- Ao calcular, sempre busque o preco MAIS RECENTE do ingrediente
- Considere fator de desperdicio quando informado
- Sugira ajustes de preco quando food cost esta acima do ideal
- Compare com benchmarks do mercado
""".strip()
