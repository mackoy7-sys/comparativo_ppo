# Comparativo PPO — Hapvida vs Operadoras

Dashboard comparativo de planos de saúde PME: **Hapvida NotreDame** vs **Amil, Bradesco, Porto Seguro e SulAmérica**, com preços por faixa etária.

🔗 **Live:** https://comparativo-ppo.vercel.app

## Conteúdo
- `index.html` — dashboard (arquivo único, Chart.js via CDN).
- `dados.json` — dados estruturados extraídos dos 18 PDFs comparativos.

## Dados
18 comparativos · 51 planos · 4 operadoras concorrentes. Para cada plano: operadora, modalidade, acomodação, coparticipação, preços das 10 faixas etárias (00 a 18 … 59 ou mais) e total mensal (1 vida/faixa).

## Recursos
- KPIs (comparativos, operadoras, planos, win-rate Hapvida).
- Visão geral: barras Hapvida × concorrente por comparativo, com filtros de operadora e acomodação (apartamento/enfermaria).
- Detalhe: cards lado a lado, diferença R$/%, gráfico por faixa etária e tabela com a faixa vencedora destacada.
- Ressalva automática quando os regimes de coparticipação diferem (Hapvida = Parcial; concorrentes em geral Sem Coparticipação).
