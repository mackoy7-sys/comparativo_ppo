#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APLICA A TABELA 28/09/2026 a 31/12/2026 no catalog.json.

Lê o que o build_dez.py produziu em /tmp/dez_parsed.json e atualiza SÓ o campo
`precos` das entradas Hapvida/Empresarial das praças cobertas.

Esta carga é diferente das anteriores: ela ALTERA preço que já está no ar. Por
isso as travas são mais duras que as de acréscimo — em especial a trava de
DIREÇÃO: esta tabela desceu em 249 de 249 casos, então qualquer preço que suba
aborta a gravação e aparece na tela. Se a operadora um dia mandar uma tabela de
reajuste, a trava vai acusar e aí se decide com o número na mão.

O que NÃO é tocado:
  - Individual (PF), Coletivo por Adesão e as concorrentes;
  - as 24 entradas que o catálogo tem e a tabela nova não traz (Adapt 300/500
    de BH, Pleno Vale do Paraíba de SJC e o Nosso Plano do Super Simples de
    Brasília) — ficam com o preço da vigência anterior;
  - o campo pr2 (reembolso parcial dos produtos NotreDame).

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import collections, json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
NOVO = "/tmp/dez_parsed.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
VIGENCIA = "28/09/2026 a 31/12/2026"

# conferidas a mao contra o texto cru do PDF (confere_dez.py)
AMOSTRAS = [
    ("Feira De Santana - BA", "Nosso Plano", "Apartamento", "Completa", 30, 256.82, 1508.27),
    ("São Luís - MA", "Nosso Médico", "Apartamento", "Completa", 30, 163.78, 961.83),
    ("Teresina - PI", "Nosso Plano Municipal", "Enfermaria", "Parcial", 2, 108.94, 639.82),
    ("Teresina - PI", "Nosso Médico + Odonto", "Apartamento", "Parcial", 30, 111.11, 652.56),
    ("Salvador - BA", "Nosso Plano", "Apartamento", "Completa", 30, 277.61, 1630.49),
    ("Campo Grande - MS", "Pleno", "Apartamento", "Parcial", 1, 528.84, 3170.44),
    ("Fortaleza - CE", "Nosso Plano + Odonto", "Ambulatorial", "Parcial", 30, 129.52, 760.73),
]


def chave(e):
    return (e.get("praca"), e["label"], e["acomodacao"], e["coparticipacao"],
            e.get("vmin"), e.get("vmax"), bool(e.get("mei")))


def main():
    cat = json.load(open(CAT))
    bruto = json.load(open(NOVO))
    novos = {}
    for praca, ents in bruto.items():
        for n in ents:
            n["praca"] = praca
            novos.setdefault(chave(n), []).append(n)
    cobertas = set(bruto)

    alvo = [e for e in cat if e["operadora"] == "Hapvida" and e.get("tipo") == "Empresarial"
            and (e.get("praca") in cobertas)]
    print("praças na tabela nova: %d · entradas do catálogo nessas praças: %d\n"
          % (len(cobertas), len(alvo)))

    muda, iguais, sem_par = [], 0, []
    for e in alvo:
        k = chave(e)
        if k not in novos:
            sem_par.append(e); continue
        n = novos[k][0]
        if all(abs(n["precos"][b] - e["precos"][b]) < 0.005 for b in BANDS):
            iguais += 1
        else:
            muda.append((e, n))

    erros = []
    print("travas:")

    print("  1. só Hapvida/Empresarial das praças cobertas entram na conta")
    fora = [e for e, _ in muda if e["operadora"] != "Hapvida" or e.get("tipo") != "Empresarial"]
    if fora: erros.append("%d entradas fora do escopo" % len(fora))

    print("  2. Individual, Adesão e concorrentes ficam intocados")
    intocaveis = [e for e in cat if e.get("tipo") != "Empresarial" or e["operadora"] != "Hapvida"]
    ids_muda = {id(e) for e, _ in muda}
    if any(id(e) in ids_muda for e in intocaveis):
        erros.append("uma entrada fora do Empresarial/Hapvida seria alterada")

    print("  3. nenhum preço SOBE (esta tabela é promocional — desceu em 100%)")
    subiu = [(e, n, b) for e, n in muda for b in BANDS if n["precos"][b] > e["precos"][b] + 0.005]
    if subiu:
        erros.append("%d valores SUBIRIAM — conferir antes de gravar" % len(subiu))
        for e, n, b in subiu[:8]:
            print("     %-22s %-26s %-12s %-9s [%s] %.2f -> %.2f"
                  % (e["praca"], e["label"], e["acomodacao"], e["coparticipacao"],
                     b, e["precos"][b], n["precos"][b]))

    print("  4. curva de faixa etária não decresce (regra ANS)")
    mau = [n for _, n in muda
           if any(n["precos"][BANDS[i+1]] < n["precos"][BANDS[i]] - 0.004 for i in range(9))]
    if mau: erros.append("%d entradas novas com curva decrescente" % len(mau))

    print("  5. só o campo `precos` muda; nada de label, porte, praça ou tipo")
    for e, n in muda:
        if chave(e) != chave(n): erros.append("chave divergente em %s" % str(chave(e)))

    print("  6. %d amostras conferidas à mão contra o PDF" % len(AMOSTRAS))
    for praca, label, acom, cop, vmin, p0, p59 in AMOSTRAS:
        k = [n for kk, v in novos.items() for n in v
             if kk[0] == praca and kk[1] == label and kk[2] == acom
             and kk[3] == cop and kk[4] == vmin]
        if not k: erros.append("amostra ausente: %s %s" % (praca, label)); continue
        if abs(k[0]["precos"]["00 a 18"] - p0) > 0.005 or abs(k[0]["precos"]["59 ou mais"] - p59) > 0.005:
            erros.append("amostra diverge: %s %s %.2f/%.2f" %
                         (praca, label, k[0]["precos"]["00 a 18"], k[0]["precos"]["59 ou mais"]))

    print("  7. o que a tabela nova não traz fica com o preço anterior")
    print("     %d entradas mantidas:" % len(sem_par))
    for lb, q in collections.Counter("%s · %s" % (e["praca"], e["label"]) for e in sem_par).most_common():
        print("        %-56s %d" % (lb, q))

    print("  8. o campo pr2 (reembolso parcial NotreDame) não é tocado")
    if any(("pr2" in e) for e, _ in muda):
        erros.append("uma entrada com pr2 seria alterada — não deveria")

    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    d = [(n["precos"][b] - e["precos"][b]) / e["precos"][b] for e, n in muda for b in BANDS]
    print("\nresumo: %d entradas mudam, %d já estavam iguais" % (len(muda), iguais))
    if d:
        print("        variação média %.2f%% (de %.2f%% a %.2f%%)"
              % (sum(d)/len(d)*100, min(d)*100, max(d)*100))
    for p, q in collections.Counter(e["praca"] for e, _ in muda).most_common():
        print("        %-26s %d" % (p, q))

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-dez-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    # só o preço muda. Nao marco vigencia na entrada: o cartao PME passaria a
    # exibir uma linha nova, e mudanca de tela nao foi o que se pediu aqui.
    for e, n in muda:
        e["precos"] = {b: n["precos"][b] for b in BANDS}
    json.dump(cat, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas atualizadas" % len(muda))
    print("backup: " + bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
