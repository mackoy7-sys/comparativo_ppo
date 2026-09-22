# -*- coding: utf-8 -*-
"""Extrai o mapa CIDADE -> PRACA da aba "Area de comercializacao" do index.html.

Por que existe: a busca por CEP so resolvia cidade-praca exata (Fortaleza) e a
lista fixa da RMSP. Um CEP de Caucaia (regiao metropolitana de Fortaleza, que a
Hapvida atende) caia em "nao ha tabela de precos para esta cidade no catalogo" e
o vendedor tinha de adivinhar a praca -- reportado em 16/09.

A aba "Area de comercializacao" ja traz o mapa OFICIAL: cada bloco `.ac-fil` tem
<b>a praca</b> e, no <span>, as cidades atendidas separadas por " · ". E a mesma
fonte que gera o area.html do app, entao nao se cria uma segunda verdade --
quando a area mudar, rodar este script de novo.

Saida: ~/comparativo-ppo/cidades.json
    {"cidades": {"caucaia|CE": "Fortaleza - CE", ...},
     "obs":     {"pacajus|CE": "somente ambulatorial", ...}}
A chave e cidade normalizada + UF, porque ha homonimos entre estados.
"""
import json, re, unicodedata
from pathlib import Path

HERE = Path(__file__).parent
FONTE = HERE / "index.html"
CATALOGO = HERE / "catalog.json"
SAIDA = HERE / "cidades.json"


def n(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


html = FONTE.read_text(encoding="utf-8")
i = html.find('id="pane-area"')
assert i > 0, "não achei o #pane-area"
i = html.rfind("<div", 0, i)
j, prof = i, 0
while j < len(html):
    if html.startswith("<div", j):
        prof += 1
    elif html.startswith("</div", j):
        prof -= 1
        if prof == 0:
            break
    j += 1
pane = html[i:j]

# Rótulos da aba que não casam pelo padrão "Cidade - UF":
#   "São Paulo" é como a aba chama a praça RMSP (no catálogo: "SP / RMSP").
# Rótulo SEM praça no catálogo fica de fora e é reportado — é cidade que a
# Hapvida comercializa mas para a qual não há tabela de preços carregada
# (hoje: Leme/Araras). Forçar uma praça vizinha ali seria inventar preço.
ROTULO_PRACA = {"sao paulo": "SP / RMSP"}

# praças do catálogo, para casar o rótulo da aba com a praça que tem tabela
pracas = sorted({c.get("praca") or "SP / RMSP" for c in json.loads(CATALOGO.read_text(encoding="utf-8"))})
por_cidade_uf = {}
for p in pracas:
    m = re.match(r"^(.*?)\s*-\s*([A-Z]{2})$", p)
    if m:
        por_cidade_uf[(n(m.group(1)), m.group(2))] = p

# UF de cada bloco de operadora (o cabeçalho .ac-op-h nomeia o estado)
UF_NOME = {"acre":"AC","alagoas":"AL","amapa":"AP","amazonas":"AM","bahia":"BA","ceara":"CE",
  "distrito federal":"DF","brasilia":"DF","espirito santo":"ES","goias":"GO","maranhao":"MA",
  "mato grosso":"MT","mato grosso do sul":"MS","minas gerais":"MG","para":"PA","paraiba":"PB",
  "parana":"PR","pernambuco":"PE","piaui":"PI","rio de janeiro":"RJ","rio grande do norte":"RN",
  "rio grande do sul":"RS","rondonia":"RO","roraima":"RR","santa catarina":"SC","sao paulo":"SP",
  "sergipe":"SE","tocantins":"TO"}

cidades, obs, sem_praca = {}, {}, []
for bloco in re.finditer(r'<div class="ac-op">(.*?)(?=<div class="ac-op">|$)', pane, re.S):
    b = bloco.group(1)
    cab = re.search(r'<div class="ac-op-h">([^<]*)', b)
    uf_bloco = UF_NOME.get(n(cab.group(1))) if cab else None
    for fil in re.finditer(r'<div class="ac-fil"><b>([^<]+)</b>\s*<span>([^<]*)</span>', b):
        rotulo, lista = fil.group(1).strip(), fil.group(2)
        for item in lista.split("·"):
            item = item.strip()
            if not item:
                continue
            nota = re.search(r"\(([^)]+)\)", item)
            cidade = re.sub(r"\s*\([^)]*\)", "", item).strip()
            # a UF vem do bloco; algumas listas cruzam estado (Brasília pega GO)
            uf = uf_bloco
            praca = ROTULO_PRACA.get(n(rotulo))
            if not praca and uf:
                praca = por_cidade_uf.get((n(rotulo), uf))
            if not praca:  # rótulo pode não ser praça do catálogo (ex.: nome de filial)
                cand = [p for (c, u), p in por_cidade_uf.items() if c == n(rotulo)]
                praca = cand[0] if len(cand) == 1 else None
            if not praca:
                sem_praca.append(f"{rotulo} ({uf})")
                continue
            uf_cidade = "SP" if praca == "SP / RMSP" else praca.rsplit("-", 1)[-1].strip()
            chave = f"{n(cidade)}|{uf_cidade}"
            cidades.setdefault(chave, praca)
            if nota:
                obs[chave] = nota.group(1)

SAIDA.write_text(json.dumps({"cidades": cidades, "obs": obs}, ensure_ascii=False,
                            separators=(",", ":")), encoding="utf-8")
print(f"cidades mapeadas: {len(cidades)}  (com observação: {len(obs)})")
print(f"praças alcançadas: {len(set(cidades.values()))} de {len(pracas)}")
if sem_praca:
    print(f"⚠ rótulos SEM tabela de preços no catálogo: {sorted(set(sem_praca))}")
    print("   (cidades comercializadas cuja praça não tem tabela carregada — reportar ao usuário)")
faltam = [p for p in pracas if p not in set(cidades.values())]
if faltam:
    print(f"⚠ praças que a aba não cobre ({len(faltam)}): {faltam}")
print(f"{SAIDA}  ({SAIDA.stat().st_size/1024:.1f} KB)")
