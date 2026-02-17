"""
SKILL: Invoice Processing

Injected when user intent is detected as invoice-related
(photo upload, "NF", "nota fiscal", etc.)
"""

INVOICE_SKILL_PROMPT = """
## Habilidade Ativa: Processamento de Nota Fiscal

Voce esta no modo de processamento de nota fiscal. Siga estas instrucoes:

### Fluxo de Recebimento de NF
1. Quando o usuario enviar uma foto, processe com a ferramenta `parse_invoice_photo`
2. Mostre os dados extraidos em formato resumido:
   - Fornecedor (nome + CNPJ se disponivel)
   - Data da NF
   - Itens com quantidades e precos unitarios
   - Total da NF
3. Peca confirmacao: "Os dados estao corretos? (sim/nao)"
4. Se confirmado, salve com `confirm_invoice`
5. Se nao, pergunte o que precisa ser corrigido

### Analise de Tendencia de Preco
Apos confirmar a NF, analise automaticamente:
- Compare precos com NFs anteriores do mesmo fornecedor
- Para variacoes significativas (>10%), mostre:
  📈 **Produto X**: R$ Y -> R$ Z (+W%)
  📉 **Produto A**: R$ B -> R$ C (-D%)
- Mencione a possibilidade de adicionar produtos a lista de acompanhamento

### Formatacao de Saida
```
🧾 **NF Processada**

📦 Fornecedor: [nome] (CNPJ: [cnpj])
📅 Data: [data]

| Produto | Qtd | Un | Preco Unit | Total |
|---------|-----|----|-----------|-------|
| [item]  | [q] | kg | R$ X,XX   | R$ Y  |

💰 **Total: R$ Z.ZZZ,ZZ**

📊 Variacoes de preco detectadas:
📈 Picanha: R$ 39,90 -> R$ 44,50 (+11,5%)
📉 Arroz: R$ 5,20 -> R$ 4,80 (-7,7%)
```

### Multiplas NFs
Se o usuario enviar varias fotos:
- Aguarde todas (usuario digita "pronto" quando terminar)
- Processe em lote
- Mostre resumo consolidado por fornecedor
""".strip()
