#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""APLICA a remessa HMO (linha Smart) de 09/11/2026 a 30/11/2026 no catalog.json.

Entrada: /tmp/hmo1109_parsed.json (build_hmo1109.py) — 717 entradas, 10 praças.

CASAMENTO POR `plano`, NÃO POR `label`: o catálogo guarda plano='Nosso Médico
RMSP' com label='Nosso Médico'. Casar por label deixava 51 entradas "sem par".

CADA GRUPO TEM O PAR simples / "+ Odonto": são o mesmo produto, e nestas praças
o odonto sai a R$ 0,00, então o preço médico é o mesmo nos dois (447 dos 451
pares). Por isso o preço da coluna do PDF vai para TODAS as entradas do grupo.
⚠ Se as duas divergirem, é a praça onde o odonto dá desconto no médico
(Médica¹ × Médica²) e uma coluna só não resolve as duas — nesse caso, aborta.

Medido nesta remessa (529 mudanças, 133 iguais):
  ~480 entradas a +2,0% ......... o reajuste geral
   35 entradas a +6% a +11% ..... Smart 500 e Smart Prime APARTAMENTO, em
                                  Jundiaí, Mogi, SP/RMSP, Santos e SBC
   14 entradas a -2,0% .......... Smart Prime 30-99 ADESÃO, em Mogi, SP/RMSP,
                                  Santos e SBC (a tabela de Adesão caiu)

Conferido no PDF pelo CÓD. INTERNO (ver AMOSTRAS).

NÃO cria produto novo: "Basic Referência" (45 entradas) não existe no catálogo e
só entra com --com-novos, porque produto novo muda o que o vendedor pode ofertar.
As 10 entradas sem par também são listadas, não engolidas.

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import collections, datetime, json, shutil, sys

NOVO = "/tmp/hmo1109_parsed.json"
CAT = "/Users/marcoscorrea/comparativo-ppo/catalog.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]

ESPERADO_MUDA = 529
FAIXA_SOBE = (1.019, 1.111)       # 2% geral + o reposicionamento do apartamento
FAIXA_DESCE = (0.9799, 0.9801)    # os -2% do Smart Prime 30-99 Adesão
DESCE_SO = {"Smart Prime"}
# (cód. interno, vmin, MEI, faixa, valor) lidos direto do PDF.
# ⚠ O CÓD. INTERNO NÃO É ÚNICO ENTRE PORTES: 109 dos 159 códigos se repetem (o
# mesmo 40676 vale para 1 vida, 2-29 e 30-99, com preços diferentes). Ele
# identifica a COLUNA dentro da tabela, não a entrada — por isso a amostra leva
# o porte junto.
AMOSTRAS = [
    ("41726", 2, False, "00 a 18", 107.92),   # SS 2-29 Demais Empresas · SP · Nosso Médico RMSP enf parcial
    ("46767", 2, False, "00 a 18", 162.16),   # idem · Smart UP apartamento parcial
    ("41658", 1, False, "00 a 18", 132.20),   # SS 1 vida · SP · Nosso Médico RMSP enf parcial
    ("47122", 1, False, "00 a 18", 198.65),   # idem · Smart UP apartamento parcial
    ("40676", 30, False, "00 a 18", 217.33),  # PME Demais Praças · SJC · Pleno VP enf PARCIAL
    ("40678", 30, False, "00 a 18", 144.50),  # idem · Pleno VP enf TOTAL (a coluna que saía trocada)
    ("40676", 1, False, "00 a 18", 253.90),   # SS 1 vida · SJC · Pleno VP enf PARCIAL
    ("40678", 1, False, "00 a 18", 166.05),   # idem · enf TOTAL (rótulo truncado no PDF)
]


def chave(e, praca=None):
    return (praca or e.get("praca") or "SP / RMSP", e["plano"], e["acomodacao"],
            e["coparticipacao"], e.get("vmin"), e.get("vmax"),
            bool(e.get("mei")), e.get("contratacao") or "")


bruto = json.load(open(NOVO))
cat = json.load(open(CAT))

grupos = collections.defaultdict(list)
for e in cat:
    if e.get("operadora") == "Hapvida" and (e.get("tipo") or "Empresarial") == "Empresarial":
        grupos[chave(e)].append(e)

muda, iguais, sem_par, split, novos = [], 0, [], [], []
for praca, ents in bruto.items():
    for n in ents:
        if n["plano"].startswith("__NOVO__"):
            novos.append((praca, n)); continue
        g = grupos.get(chave(n, praca))
        if not g:
            sem_par.append(chave(n, praca)); continue
        base = g[0]["precos"]
        if any(any(abs(x["precos"][b] - base[b]) >= 0.005 for b in BANDS) for x in g[1:]):
            split.append(chave(n, praca)); continue
        if all(abs(base[b] - n["precos"][b]) < 0.005 for b in BANDS):
            iguais += 1
        else:
            muda.append((g, n, praca))

print("tabela nova: %d entradas em %d praças" % (sum(len(v) for v in bruto.values()), len(bruto)))
print("  iguais: %d · mudam: %d · sem par: %d · produto novo: %d · grupo Médica1/2: %d\n"
      % (iguais, len(muda), len(sem_par), len(novos), len(split)))

erros = []
print("travas:")

print("  1. o par simples / \"+ Odonto\" tem o MESMO preço médico nestas praças")
if split:
    erros.append("%d grupos com Médica1 ≠ Médica2 — uma coluna só não resolve as duas: %s"
                 % (len(split), split[:3]))

print("  2. a mudança é exatamente a medida: %d entradas" % ESPERADO_MUDA)
if len(muda) != ESPERADO_MUDA:
    erros.append("esperava %d mudanças, achei %d" % (ESPERADO_MUDA, len(muda)))

print("  3. quem sobe fica em +%.1f%% a +%.1f%%; quem desce é só %s, a -2,0%%"
      % ((FAIXA_SOBE[0] - 1) * 100, (FAIXA_SOBE[1] - 1) * 100, "/".join(DESCE_SO)))
for g, n, p in muda:
    base = g[0]["precos"]
    for b in BANDS:
        v, w = base[b], n["precos"][b]
        if not v or abs(v - w) < 0.005:
            continue
        r = w / v
        if r > 1:
            if not FAIXA_SOBE[0] <= r <= FAIXA_SOBE[1]:
                erros.append("alta fora da faixa: %s %s %s %.2f->%.2f (%.4f)" % (p, n["plano"], b, v, w, r))
        else:
            if n["plano"] not in DESCE_SO or not FAIXA_DESCE[0] <= r <= FAIXA_DESCE[1]:
                erros.append("queda inesperada: %s %s %s %.2f->%.2f (%.4f)" % (p, n["plano"], b, v, w, r))

print("  4. a curva de faixa etária não decresce em nenhuma entrada gravada")
for g, n, p in muda:
    v = [n["precos"][b] for b in BANDS]
    if any(v[i + 1] < v[i] - 0.005 for i in range(len(v) - 1)):
        erros.append("curva decrescente: %s %s %s" % (p, n["plano"], n["acomodacao"]))

print("  5. %d amostras conferidas no PDF pelo CÓD. INTERNO" % len(AMOSTRAS))
por_cod = {}
for ents in bruto.values():
    for n in ents:
        por_cod[(n.get("cod"), n.get("vmin"), bool(n.get("mei")))] = n
for cod, vmin, mei, b, val in AMOSTRAS:
    n = por_cod.get((cod, vmin, mei))
    if not n:
        erros.append("amostra: cód. %s (porte %s) não saiu do parse" % (cod, vmin))
    elif abs(n["precos"][b] - val) >= 0.005:
        erros.append("amostra: cód. %s porte %s %s = %.2f, esperado %.2f"
                     % (cod, vmin, b, n["precos"][b], val))

print("  6. o parse não tem duas combinações com a mesma chave")
vistas = collections.Counter(chave(n, p) for p, ents in bruto.items() for n in ents
                             if not n["plano"].startswith("__NOVO__"))
dup = [k for k, v in vistas.items() if v > 1]
if dup:
    erros.append("%d chaves duplicadas no parse (coparticipação trocada?): %s" % (len(dup), dup[:3]))

print("  7. nada é criado sem pedido explícito")
if novos and "--com-novos" not in sys.argv:
    print("     %d entradas de produto NOVO ficam de fora: %s"
          % (len(novos), sorted({n["plano"].replace("__NOVO__", "") for _, n in novos})))

if erros:
    print("\n" + "!" * 70)
    for x in erros[:12]:
        print("!! " + x)
    print("!! NADA GRAVADO")
    sys.exit(1)

if sem_par:
    print("\n%d combinações da tabela SEM par no catálogo (não serão gravadas):" % len(sem_par))
    for x in sorted(set(sem_par)):
        print("   %s · %s · %s · %s · %sv%s%s" % (x[0], x[1], x[2], x[3], x[4],
                                                 " MEI" if x[6] else "", " " + x[7] if x[7] else ""))

print("\nmudanças a gravar, por praça (entradas do catálogo afetadas):")
afet = collections.Counter()
for g, n, p in muda:
    afet[p] += len(g)
for p, c in sorted(afet.items()):
    print("  %-28s %3d" % (p, c))
print("  %-28s %3d entradas de catálogo em %d combinações" % ("TOTAL", sum(afet.values()), len(muda)))

if "--gravar" not in sys.argv:
    print("\n(ensaio — nada gravado. Rode com --gravar.)")
    sys.exit(0)

bak = CAT + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy(CAT, bak)
n_ent = 0
for g, n, _ in muda:
    for e in g:
        e["precos"] = dict(n["precos"]); n_ent += 1
json.dump(cat, open(CAT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("\nbackup: %s" % bak)
print("gravado: %d entradas do catálogo atualizadas" % n_ent)
