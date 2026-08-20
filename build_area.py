#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera `area.html` — a aba "Área de comercialização" como página autônoma.

Por que existe: o card do app HapON Vendas apontava para `index.html#area`, o
que obrigava a carregar o cotador inteiro (catalog.json de 1,7 MB) e mostrava o
cabeçalho e as outras 3 abas antes do conteúdo. A aba é ESTÁTICA (o conteúdo das
filiais está no markup; `acFilter()` só filtra e destaca), então dá para servir
sozinha — sem catálogo, sem abas.

Extrai do index.html, para não haver duas fontes da verdade: quando a aba mudar
lá, rodar este script de novo.

    python3 build_area.py
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
FONTE = HERE / "index.html"
SAIDA = HERE / "area.html"

s = FONTE.read_text(encoding="utf-8")

# ---------------------------------------------------- 1. o painel da aba
i = s.find('id="pane-area"')
assert i > 0, "não achei o #pane-area"
i = s.rfind("<div", 0, i)          # volta ao início da tag
j, prof = i, 0
while j < len(s):                   # fecha por balanceamento de <div>
    m = re.compile(r"<(/?)div\b").search(s, j)
    if not m:
        break
    prof += 1 if not m.group(1) else -1
    # avança até o ">" — parar em m.end() cortava a tag ("</div" sem fechar),
    # e o parser passava a engolir tudo o que vinha depois, inclusive o <script>
    j = s.find(">", m.end()) + 1
    if prof == 0:
        break
pane = s[i:j]
# vira o conteúdo principal: sai a classe de aba, entra visível
pane = pane.replace('class="tabpane" id="pane-area"', 'id="pane-area"', 1)
pane = pane.replace('class="tabpane active" id="pane-area"', 'id="pane-area"', 1)

# ------------------------------------------------------------- 2. o CSS
css = re.search(r"<style>(.*?)</style>", s, re.S).group(1)

# ------------------------------------------- 3. a função de filtro
k = s.find("function acFilter")
assert k > 0, "não achei acFilter"
fim = s.find("\n}", k) + 2
acfilter = s[k:fim]

# --------------------------------------------------------- 4. o logo
logo = re.search(r"const LOGO_SVG\s*=\s*'(.*?)';", s, re.S)
logo_html = logo.group(1) if logo else ""

PAGINA = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Área de Comercialização — Hapvida | Vendas Digital</title>
<meta name="description" content="Onde cada produto pode ser vendido: regionais, filiais de vendas e municípios da área de comercialização.">
<meta name="theme-color" content="#013BA6">
<style>
{css}

  /* ---- página autônoma (gerada por build_area.py) ---- */
  body {{ padding-bottom: 28px; }}
  .ac-head {{
    background: linear-gradient(160deg, #0A4FCB 0%, #013BA6 55%, #00246B 100%);
    color: #fff; padding: 16px 18px; display: flex; align-items: center;
    justify-content: space-between; gap: 14px; flex-wrap: wrap;
  }}
  .ac-head h1 {{ margin: 0; font-size: 18px; font-weight: 800; letter-spacing: -.2px; }}
  .ac-head .sub {{ margin: 3px 0 0; font-size: 12.5px; opacity: .85; }}
  .ac-head img {{ height: 30px; border-radius: 6px; }}
  #pane-area {{ display: block; max-width: 1180px; margin: 0 auto; padding: 16px 14px 0; }}
  @media (max-width: 760px) {{
    .ac-head {{ padding: 14px 14px; }}
    .ac-head h1 {{ font-size: 16px; }}
    #pane-area {{ padding: 12px 12px 0; }}
  }}
</style>
</head>
<body>

<header class="ac-head">
  <div>
    <h1>Área de Comercialização</h1>
    <p class="sub">Governança Comercial Varejo Brasil · Hapvida NotreDame</p>
  </div>
  {logo_html}
</header>

{pane}

<script>
{acfilter}
document.addEventListener('DOMContentLoaded', function () {{
  try {{ acFilter(); }} catch (e) {{}}   // pinta a contagem de filiais na abertura
}});
</script>
</body>
</html>
"""

SAIDA.write_text(PAGINA, encoding="utf-8")
kb = SAIDA.stat().st_size / 1024
print(f"OK -> {SAIDA} ({kb:.0f} KB)")
print(f"   painel {len(pane)/1024:.1f} KB · css {len(css)/1024:.1f} KB · acFilter {len(acfilter)} B")
