# Cotação PPO — Calculadora de Planos (Hapvida vs Operadoras)

Calculadora de cotação de planos de saúde PME: informe as **vidas por faixa etária** e compare o **custo mensal** entre um ou mais planos/operadoras — **Hapvida NotreDame** vs **Amil, Bradesco, Porto Seguro e SulAmérica**.

🔗 **Live:** https://comparativo-ppo.vercel.app

## Como funciona
1. **Distribuição de vidas** — informe a quantidade por faixa etária (00 a 18 … 59 ou mais) ou use o **conversor de datas de nascimento** (calcula a idade e distribui nas faixas).
2. **Seleção de planos** — marque um ou mais planos (pode misturar operadoras); planos Hapvida destacados.
3. **Resultado** — custo mensal = Σ (vidas × preço da faixa) por plano, com ranking, R$/vida, diferença vs o menor e melhor opção Hapvida.

## Arquivos
- `index.html` — aplicação (arquivo único, sem dependências externas).
- `catalog.json` — catálogo de planos (31 itens) com preços por faixa.
- `dados.json` — dados brutos extraídos dos 18 PDFs comparativos.

Observação: o custo calculado é a **mensalidade**. Planos Hapvida são com **coparticipação (Parcial)**; concorrentes em geral **sem coparticipação** — a calculadora avisa quando a comparação mistura os regimes.
