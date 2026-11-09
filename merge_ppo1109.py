#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""APLICA a remessa PPO/Metais de 09/11/2026 a 30/11/2026 no catalog.json.

Entrada: /tmp/ppo1109_parsed.json (build_ppo1109.py) — 1.507 entradas, 9 praças.

Por que não reusa o merge_ppo.py: aquele foi escrito quando a LINHA METAIS era
NOVA (21/10) e CRIA as entradas dela. Aqui ela já existe (864 no catálogo), então
isto é ATUALIZAÇÃO: nada é criado, nada é removido, só `precos`/`pr2` mudam.
Rodar o merge antigo duplicaria a linha Metais inteira.

Onde cada preço entra:
  LINHA TRADICIONAL — o reembolso é eixo do vendedor: total em `precos`,
      parcial em `pr2`.
  LINHA METAIS — o reembolso é propriedade do produto (Prata/Ouro só parcial,
      Diamante só total), então o preço vai sempre em `precos` e não há `pr2`.
      Conferido: as 864 entradas Metais do catálogo têm pr2 vazio.

Medido nesta remessa: 1.491 das 1.507 entradas estão IGUAIS ao catálogo. As 16
que mudam são todas Premium 900 Care · apartamento · MEI · 2 a 29 vidas, em
Americana, Campinas, Jundiaí e Sorocaba, e todas DESCEM. É HARMONIZAÇÃO: as
quatro praças tinham preços diferentes e passam a ter o MESMO — 385,90/300,20 no
parcial e 472,22/367,34 no total (faixa 00 a 18). Conferido no PDF pelo
CÓD. INTERNO 41488, que traz R$ 385,90 nas quatro.

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import collections, datetime, json, os, shutil, sys

NOVO = "/tmp/ppo1109_parsed.json"
CAT = "/Users/marcoscorrea/comparativo-ppo/catalog.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
METAIS = {"Prata", "Prata Max", "Ouro", "Ouro Max", "Diamante", "Diamante Max"}
LIMITE = 0.40

# o que esta remessa PODE mudar, medido antes de gravar. Qualquer coisa fora
# disto é sinal de parse errado, não de tabela nova.
ESPERADO_MUDA = 16
ESPERADO_PROD = {"Premium 900 Care"}
ESPERADO_PRACAS = {"Americana - SP", "Campinas - SP", "Jundiaí - SP", "Sorocaba - SP"}
# os valores para onde as quatro praças convergem, na faixa 00 a 18
ESPERADO_DESTINO = {"pr2": {385.90, 300.20}, "precos": {472.22, 367.34}}


def chave(e, praca=None):
    return (praca or e.get("praca") or "SP / RMSP", e["label"], e["acomodacao"],
            e["coparticipacao"], e.get("vmin"), e.get("vmax"),
            bool(e.get("mei")), e.get("contratacao") or "")


bruto = json.load(open(NOVO))
cat = json.load(open(CAT))
pracas = set(bruto)

idx = collections.defaultdict(list)
for e in cat:
    if e.get("operadora") == "Hapvida":
        idx[chave(e)].append(e)

muda, iguais, sem_par = [], 0, []
for praca, ents in bruto.items():
    for n in ents:
        alvos = idx.get(chave(n, praca))
        if not alvos:
            sem_par.append((praca, n["label"], n["acomodacao"], n.get("vmin"))); continue
        e = alvos[0]
        campo = "precos" if (n["plano"] in METAIS or n["reembTipo"] == "Total") else "pr2"
        atual = e.get(campo)
        if not atual:
            sem_par.append((praca, n["label"], campo + " vazio", n.get("vmin"))); continue
        if all(abs(atual[b] - n["precos"][b]) < 0.005 for b in BANDS):
            iguais += 1
        else:
            muda.append((e, campo, n, praca))

print("tabela nova: %d entradas em %d praças" % (sum(len(v) for v in bruto.values()), len(pracas)))
print("  iguais ao catálogo: %d · mudam: %d · sem par: %d\n" % (iguais, len(muda), len(sem_par)))

erros = []
print("travas:")

print("  1. nada é criado nem removido — isto é atualização de preço")
n_metais = sum(1 for e in cat if e.get("operadora") == "Hapvida" and e.get("plano") in METAIS)
if n_metais == 0:
    erros.append("a linha Metais NÃO está no catálogo — esta carga é de atualização, "
                 "não de inclusão; use o merge_ppo.py")
if sem_par:
    erros.append("%d entradas da tabela sem par no catálogo: %s" % (len(sem_par), sem_par[:5]))
print("     %d entradas Metais já no catálogo, 0 sem par" % n_metais)

print("  2. só Hapvida/Empresarial das praças da remessa é tocado")
for e, _, _, _ in muda:
    if e["operadora"] != "Hapvida" or (e.get("tipo") or "Empresarial") != "Empresarial" \
       or (e.get("praca") or "SP / RMSP") not in pracas:
        erros.append("fora do escopo: %s" % str(chave(e)))

print("  3. a mudança é exatamente a medida: %d entradas, %s, em %s"
      % (ESPERADO_MUDA, "/".join(sorted(ESPERADO_PROD)), ", ".join(sorted(ESPERADO_PRACAS))))
if len(muda) != ESPERADO_MUDA:
    erros.append("esperava %d mudanças, achei %d" % (ESPERADO_MUDA, len(muda)))
prod = {n["label"] for _, _, n, _ in muda}
prac = {p for _, _, _, p in muda}
if prod - ESPERADO_PROD:
    erros.append("produto inesperado mudando: %s" % sorted(prod - ESPERADO_PROD))
if prac - ESPERADO_PRACAS:
    erros.append("praça inesperada mudando: %s" % sorted(prac - ESPERADO_PRACAS))

print("  4. toda variação cabe em ±%d%%" % (LIMITE * 100))
for e, c, n, p in muda:
    for b in BANDS:
        a = (e.get(c) or {}).get(b)
        if a and abs((n["precos"][b] - a) / a) > LIMITE:
            erros.append("variação fora de ±%d%%: %s %s %s %.2f->%.2f"
                         % (LIMITE * 100, p, n["label"], b, a, n["precos"][b]))

print("  5. a curva de faixa etária não decresce em nenhuma entrada gravada")
for e, c, n, p in muda:
    v = [n["precos"][b] for b in BANDS]
    if any(v[i + 1] < v[i] - 0.005 for i in range(len(v) - 1)):
        erros.append("curva decrescente: %s %s" % (p, n["label"]))

print("  6. reembolso parcial nunca fica acima do total")
for e, c, n, p in muda:
    fut = dict(e); fut[c] = n["precos"]
    tot, par = fut.get("precos"), fut.get("pr2")
    if tot and par and any(par[b] > tot[b] + 0.005 for b in BANDS):
        erros.append("parcial acima do total: %s %s" % (p, n["label"]))

print("  8. as quatro praças convergem para o MESMO preço (é harmonização)")
for e, c, n, p in muda:
    v = round(n["precos"]["00 a 18"], 2)
    if v not in ESPERADO_DESTINO[c]:
        erros.append("destino inesperado: %s %s %s 00 a 18 = %.2f" % (p, n["label"], c, v))
if muda and not all(n["precos"]["00 a 18"] < e[c]["00 a 18"] for e, c, n, _ in muda):
    erros.append("alguma entrada SOBE — a medição diz que todas descem")
por_campo = collections.defaultdict(set)
for e, c, n, p in muda:
    por_campo[(c, round(e[c]["00 a 18"] > 400, 0))].add(round(n["precos"]["00 a 18"], 2))

print("  7. a linha Metais não muda de preço nesta remessa")
mm = [n["label"] for _, _, n, _ in muda if n["plano"] in METAIS]
if mm:
    erros.append("Metais mudando, o que a medição não previu: %s" % sorted(set(mm)))

if erros:
    print("\n" + "!" * 70)
    for x in erros[:12]:
        print("!! " + x)
    print("!! NADA GRAVADO")
    sys.exit(1)

print("\nmudanças a gravar:")
for e, c, n, p in muda:
    print("  %-16s %-18s %-12s %-8s %s  %s -> %s"
          % (p, n["label"], n["acomodacao"], c,
             ("%s-%s vidas" % (n.get("vmin"), n.get("vmax"))),
             ("%.2f" % e[c]["00 a 18"]), ("%.2f" % n["precos"]["00 a 18"])))

if "--gravar" not in sys.argv:
    print("\n(ensaio — nada gravado. Rode com --gravar.)")
    sys.exit(0)

bak = CAT + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M")
shutil.copy(CAT, bak)
for e, c, n, _ in muda:
    e[c] = n["precos"]
json.dump(cat, open(CAT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("\nbackup: %s" % bak)
print("gravado: %d entradas atualizadas em %s" % (len(muda), CAT))
