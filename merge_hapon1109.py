#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""APLICA a remessa Hapvida de 09/11/2026 a 31/12/2026 no catalog.json.

Entrada: /tmp/hapon1109_parsed.json (build_hapon1109.py) — 995 entradas, 45 praças.

A remessa traz SÓ as 3 tabelas de Empresarial (Super Simples 1 vida, Super
Simples 2 a 29 e PME 30-99). NÃO veio Individual (PF) nem a Promocional
Ambulatorial, então nada de PF é tocado — o parser avisa quais faltaram.

Medido: das 995 entradas, 671 estão IGUAIS ao catálogo e 324 mudam. As 324 estão
TODAS nas 14 praças do interior de SP (Araraquara, Barretos, Bauru, Franca,
Jaboticabal, Limeira, Lins, Marília, Piracicaba, Pirassununga, Ribeirão Preto,
São Carlos, São José dos Campos e Sertãozinho) — nessas praças mudou tudo, e nas
outras 31 não mudou nada.

É REAJUSTE DE 2%: as 3.240 células alteradas ficam entre +1,9874% e +2,0163%
(mediana +1,9993%), nenhuma para baixo. A dispersão é o arredondamento da própria
operadora — NÃO é `antigo × 1,02` arredondado, que erra por centavos em 2.446 das
3.240 células; por isso a trava afere a FAIXA, não uma fórmula inventada.

Conferido no PDF pelo CÓD. INTERNO: Araraquara pág. 37, cód. 38554 → R$ 146,93
na faixa 00 a 18 (catálogo tinha 144,05), e cód. 38553 → R$ 96,31 (tinha 94,42).

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import collections, datetime, json, shutil, sys

NOVO = "/tmp/hapon1109_parsed.json"
CAT = "/Users/marcoscorrea/comparativo-ppo/catalog.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]

PRACAS_REAJUSTE = {
    "Araraquara - SP", "Barretos - SP", "Bauru - SP", "Franca - SP",
    "Jaboticabal - SP", "Limeira - SP", "Lins - SP", "Marília - SP",
    "Piracicaba - SP", "Pirassununga - SP", "Ribeirão Preto - SP",
    "São Carlos - SP", "São José Dos Campos - SP", "Sertãozinho - SP",
}
ESPERADO_MUDA = 324
FAIXA = (1.019, 1.021)          # reajuste de 2% com o arredondamento da operadora
AMOSTRAS = [  # (praça, label, acomodação, vmin, faixa, valor) lidos do PDF pelo cód. interno
    ("Araraquara - SP", "Nosso Médico", "Enfermaria", 2, "00 a 18", 146.93),   # cód. 38554
]


def chave(e, praca=None):
    return (praca or e.get("praca") or "SP / RMSP", e["label"], e["acomodacao"],
            e["coparticipacao"], e.get("vmin"), e.get("vmax"),
            bool(e.get("mei")), e.get("contratacao") or "")


bruto = json.load(open(NOVO))
cat = json.load(open(CAT))

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
        if all(abs(e["precos"][b] - n["precos"][b]) < 0.005 for b in BANDS):
            iguais += 1
        else:
            muda.append((e, n, praca))

print("tabela nova: %d entradas em %d praças" % (sum(len(v) for v in bruto.values()), len(bruto)))
print("  iguais: %d · mudam: %d · sem par no catálogo: %d\n" % (iguais, len(muda), len(sem_par)))

erros = []
print("travas:")

print("  1. nada é criado nem removido — só preço muda")
if sem_par:
    erros.append("%d entradas sem par: %s" % (len(sem_par), sem_par[:5]))

print("  2. a mudança é exatamente a medida: %d entradas" % ESPERADO_MUDA)
if len(muda) != ESPERADO_MUDA:
    erros.append("esperava %d mudanças, achei %d" % (ESPERADO_MUDA, len(muda)))

print("  3. só as 14 praças do interior de SP mudam; as outras 31 ficam intactas")
fora = sorted({p for _, _, p in muda} - PRACAS_REAJUSTE)
if fora:
    erros.append("praça fora do reajuste mudando: %s" % fora)

print("  4. só Hapvida/Empresarial é tocado — nada de Individual (não veio na remessa)")
for e, _, _ in muda:
    if e["operadora"] != "Hapvida" or (e.get("tipo") or "Empresarial") != "Empresarial":
        erros.append("fora do escopo: %s" % str(chave(e)))

print("  5. toda célula SOBE, e dentro de +%.1f%% a +%.1f%%"
      % ((FAIXA[0] - 1) * 100, (FAIXA[1] - 1) * 100))
for e, n, p in muda:
    for b in BANDS:
        v, w = e["precos"][b], n["precos"][b]
        if v and abs(v - w) >= 0.005 and not (FAIXA[0] <= w / v <= FAIXA[1]):
            erros.append("fora da faixa: %s %s %s %.2f->%.2f (%.4f)" % (p, n["label"], b, v, w, w / v))

print("  6. a curva de faixa etária não decresce em nenhuma entrada gravada")
for e, n, p in muda:
    v = [n["precos"][b] for b in BANDS]
    if any(v[i + 1] < v[i] - 0.005 for i in range(len(v) - 1)):
        erros.append("curva decrescente: %s %s" % (p, n["label"]))

print("  7. %d amostra(s) conferida(s) no PDF pelo CÓD. INTERNO" % len(AMOSTRAS))
for praca, label, acom, vmin, faixa, valor in AMOSTRAS:
    achou = [n for e, n, p in muda if p == praca and n["label"] == label
             and n["acomodacao"] == acom and n.get("vmin") == vmin
             and abs(n["precos"][faixa] - valor) < 0.005]
    if not achou:
        erros.append("amostra não bate: %s %s %s %s = %.2f" % (praca, label, acom, faixa, valor))

if erros:
    print("\n" + "!" * 70)
    for x in erros[:12]:
        print("!! " + x)
    print("!! NADA GRAVADO")
    sys.exit(1)

por_praca = collections.Counter(p for _, _, p in muda)
print("\nmudanças a gravar, por praça:")
for p, c in sorted(por_praca.items()):
    print("  %-26s %3d entradas" % (p, c))

if "--gravar" not in sys.argv:
    print("\n(ensaio — nada gravado. Rode com --gravar.)")
    sys.exit(0)

bak = CAT + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy(CAT, bak)
for e, n, _ in muda:
    e["precos"] = n["precos"]
json.dump(cat, open(CAT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("\nbackup: %s" % bak)
print("gravado: %d entradas atualizadas em %s" % (len(muda), CAT))
