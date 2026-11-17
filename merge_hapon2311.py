#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""APLICA a remessa Hapvida de 23/11/2026 a 31/12/2026 no catalog.json.

Entrada: /tmp/hapon2311_parsed.json (build_hapon2311.py) — 152 entradas, 21 praças.

ESTA REMESSA NÃO É REAJUSTE: ela ABRE O PORTE DE 1 VIDA em 16 praças.

  5 praças do Centro-Oeste (Campo Grande, Cuiabá, Dourados, Rondonópolis e Três
  Lagoas) já tinham 1 vida no catálogo e vêm IDÊNTICAS — 30 combinações, zero
  mudança de preço.

  16 praças (Araraquara, Barretos, Bauru, Fortaleza, Franca, Jaboticabal,
  Limeira, Lins, Marília, Piracicaba, Pirassununga, Recife, Ribeirão Preto,
  São Carlos, São José dos Campos e Sertãozinho) NÃO tinham nenhuma entrada de
  1 vida: são 122 combinações NOVAS, em Nosso Plano, Nosso Médico, Pleno e
  Integrado. Isso muda o que o vendedor pode cotar, não só quanto custa.

Cada combinação vira DUAS entradas, como todo o resto do catálogo: a simples e a
"+ Odonto", com o mesmo preço médico e ids distintos. 122 × 2 = 244 entradas.

Os campos que não vêm da tabela (categoria, mei, tipo, plano) são COPIADOS de uma
entrada-modelo do MESMO produto na MESMA praça, noutro porte — não inventados.
Conferido: as 122 têm modelo e gêmea "+ Odonto" disponíveis.

Conferido no PDF pelo CÓD. INTERNO 21217 (Fortaleza pág. 1, Nosso Plano
ambulatorial com coparticipação parcial): R$ 174,96 na faixa 00 a 18.

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import collections, datetime, json, shutil, sys

NOVO = "/tmp/hapon2311_parsed.json"
CAT = "/Users/marcoscorrea/comparativo-ppo/catalog.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]

ESPERADO_IGUAIS = 30
ESPERADO_NOVAS = 122
PRACAS_JA_TINHAM = {"Campo Grande - MS", "Cuiabá - MT", "Dourados - MS",
                    "Rondonópolis - MT", "Três Lagoas - MS"}
AMOSTRAS = [
    ("Fortaleza - CE", "Nosso Plano", "Ambulatorial", "Parcial", "00 a 18", 174.96),   # cód. 21217
    ("Recife - PE", "Nosso Médico", "Enfermaria", "Parcial", "00 a 18", 198.04),       # cód. 40016
    ("Recife - PE", "Nosso Médico", "Enfermaria", "Completa", "00 a 18", 157.44),      # cód. 40017
]
# ⚠ RECIFE É EXCEÇÃO CONFERIDA: a tabela de 1 vida de lá sai ABAIXO da de 2 a 29
# (até -22,6%), o que contraria a lógica de escala. Não é erro de leitura — está
# no PDF, pág. 2, cód. 40016 (R$ 198,04) e 40017 (R$ 157,44), contra 211,06 e
# 167,84 do catálogo para 2 a 29. Nas outras 20 praças a invariante vale
# (144 de 152 combinações); as 8 que violam são todas de Recife.
EXCECAO_1V_MAIS_BARATO = {"Recife - PE"}


def chave(e, praca=None):
    return (praca or e.get("praca") or "SP / RMSP", e["label"], e["acomodacao"],
            e["coparticipacao"], e.get("vmin"), e.get("vmax"),
            bool(e.get("mei")), e.get("contratacao") or "")


bruto = json.load(open(NOVO))
cat = json.load(open(CAT))

por_chave = collections.defaultdict(list)
por_prod = collections.defaultdict(list)
for e in cat:
    if e.get("operadora") == "Hapvida" and (e.get("tipo") or "Empresarial") == "Empresarial":
        por_chave[chave(e)].append(e)
        por_prod[(e.get("praca"), e["label"], e["acomodacao"], e["coparticipacao"])].append(e)

iguais, muda, criar = 0, [], []
for praca, ents in bruto.items():
    for n in ents:
        achou = por_chave.get(chave(n, praca))
        if achou:
            if all(abs(achou[0]["precos"][b] - n["precos"][b]) < 0.005 for b in BANDS):
                iguais += 1
            else:
                muda.append((achou, n, praca))
            continue
        criar.append((praca, n))

print("tabela nova: %d entradas em %d praças" % (sum(len(v) for v in bruto.values()), len(bruto)))
print("  já existem e estão iguais: %d · mudam de preço: %d · combinações NOVAS: %d\n"
      % (iguais, len(muda), len(criar)))

erros = []
print("travas:")

print("  1. as praças que já tinham 1 vida vêm IDÊNTICAS — esta remessa não reajusta")
if iguais != ESPERADO_IGUAIS:
    erros.append("esperava %d iguais, achei %d" % (ESPERADO_IGUAIS, iguais))
if muda:
    erros.append("%d entradas MUDARIAM de preço, e a medição diz que nenhuma muda: %s"
                 % (len(muda), [(p, n["label"]) for _, n, p in muda][:4]))
if {p for p, _ in criar} & PRACAS_JA_TINHAM:
    erros.append("praça do Centro-Oeste entre as novas: %s"
                 % sorted({p for p, _ in criar} & PRACAS_JA_TINHAM))

print("  2. as novas são exatamente %d, e só em praças sem nenhum porte de 1 vida" % ESPERADO_NOVAS)
if len(criar) != ESPERADO_NOVAS:
    erros.append("esperava %d novas, achei %d" % (ESPERADO_NOVAS, len(criar)))
for p, _ in criar:
    if any(e.get("vmin") == 1 for e in cat
           if e.get("operadora") == "Hapvida" and e.get("praca") == p
           and (e.get("tipo") or "Empresarial") == "Empresarial"):
        erros.append("praça %s já tem porte de 1 vida — não deveria ganhar entrada nova" % p)
        break

print("  3. todo campo que não vem da tabela sai de uma entrada-modelo da MESMA praça")
planos = []
for p, n in criar:
    mod = [e for e in por_prod.get((p, n["label"], n["acomodacao"], n["coparticipacao"]), [])
           if e.get("vmin") != 1]
    odo = [e for e in por_prod.get((p, n["label"] + " + Odonto", n["acomodacao"],
                                    n["coparticipacao"]), []) if e.get("vmin") != 1]
    if not mod:
        erros.append("sem modelo: %s %s %s %s" % (p, n["label"], n["acomodacao"], n["coparticipacao"]))
        continue
    if not odo:
        erros.append("sem gêmea + Odonto: %s %s" % (p, n["label"]))
        continue
    planos.append((p, n, mod[0], odo[0]))

print("  4. a curva de faixa etária não decresce em nenhuma entrada nova")
for p, n in criar:
    v = [n["precos"][b] for b in BANDS]
    if any(v[i + 1] < v[i] - 0.005 for i in range(len(v) - 1)):
        erros.append("curva decrescente: %s %s %s" % (p, n["label"], n["acomodacao"]))

print("  5. o preço de 1 vida não fica abaixo do de 2 a 29 — exceto em %s, conferido no PDF"
      % "/".join(EXCECAO_1V_MAIS_BARATO))
abaixo = []
for p, n, mod, _ in planos:
    m2 = [e for e in por_prod[(p, n["label"], n["acomodacao"], n["coparticipacao"])]
          if e.get("vmin") == 2]
    if m2 and any(n["precos"][b] < m2[0]["precos"][b] - 0.005 for b in BANDS):
        if p in EXCECAO_1V_MAIS_BARATO:
            abaixo.append((p, n, m2[0]))
        else:
            erros.append("1 vida mais barato que 2 a 29 FORA da exceção: %s %s %s"
                         % (p, n["label"], n["acomodacao"]))
if abaixo and {p for p, _, _ in abaixo} != EXCECAO_1V_MAIS_BARATO:
    erros.append("a exceção foi declarada para %s mas só %s a usa — reconferir"
                 % (sorted(EXCECAO_1V_MAIS_BARATO), sorted({p for p, _, _ in abaixo})))

print("  6. %d amostra(s) conferida(s) no PDF pelo CÓD. INTERNO" % len(AMOSTRAS))
for pr, lb, ac, cp, b, val in AMOSTRAS:
    hit = [n for p, n in criar if p == pr and n["label"] == lb and n["acomodacao"] == ac
           and n["coparticipacao"] == cp and abs(n["precos"][b] - val) < 0.005]
    if not hit:
        erros.append("amostra não bate: %s %s %s %s = %.2f" % (pr, lb, ac, cp, val))

if erros:
    print("\n" + "!" * 70)
    for x in erros[:12]:
        print("!! " + x)
    print("!! NADA GRAVADO")
    sys.exit(1)

prox = max(e["id"] for e in cat) + 1
print("\nserão CRIADAS %d entradas (%d combinações × 2, com a gêmea \"+ Odonto\"), ids %d a %d:"
      % (len(planos) * 2, len(planos), prox, prox + len(planos) * 2 - 1))
for p, c in sorted(collections.Counter(p for p, _, _, _ in planos).items()):
    print("  %-26s %2d combinações → %2d entradas" % (p, c, c * 2))

if abaixo:
    print("\n⚠ %d combinações de %s saem com 1 vida MAIS BARATO que 2 a 29 (faixa 00 a 18):"
          % (len(abaixo), ", ".join(sorted({p for p, _, _ in abaixo}))))
    for p, n, m2 in sorted(abaixo, key=lambda x: (x[1]["label"], x[1]["acomodacao"])):
        print("   %-16s %-13s %-9s  1 vida %8.2f  ·  2 a 29 %8.2f  (%+.1f%%)"
              % (n["label"], n["acomodacao"], n["coparticipacao"], n["precos"]["00 a 18"],
                 m2["precos"]["00 a 18"],
                 (n["precos"]["00 a 18"] / m2["precos"]["00 a 18"] - 1) * 100))

if "--gravar" not in sys.argv:
    print("\n(ensaio — nada gravado. Rode com --gravar.)")
    sys.exit(0)

bak = CAT + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy(CAT, bak)
novos = []
for p, n, mod, odo in planos:
    for molde in (mod, odo):
        e = dict(molde)
        e["id"] = prox; prox += 1
        e["vmin"] = 1; e["vmax"] = 1
        e["precos"] = dict(n["precos"])
        e.pop("pr2", None)
        novos.append(e)
cat.extend(novos)
ids = [e["id"] for e in cat]
assert len(set(ids)) == len(ids), "id repetido após a criação"
json.dump(cat, open(CAT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("\nbackup: %s" % bak)
print("gravado: %d entradas criadas · catálogo com %d entradas" % (len(novos), len(cat)))
