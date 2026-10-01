#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APLICA a vigência 01/10/2026 a 31/12/2026 (NDI) no catalog.json.

A remessa de 30/09 trouxe 15 PDFs. Os três da Hapvida ("20260928 a 20261231")
são byte a byte os de 27/09, que já estão em produção — o merge_dez.py confirma
0 mudanças em 1.152 entradas. O que entra aqui é o NDI, que faltava:

    Sul (Clinipam PR/SC)  build_out.py     -> /tmp/out_parsed.json
    RS (CCG)              build_out.py     -> /tmp/out_parsed.json
    Minas (NDI MG)        build_mg_out.py  -> /tmp/mg_out_parsed.json

Atualiza SÓ o campo `precos`. Entrada nova (par que o catálogo não tem) NÃO é
criada por este script: ela aparece no relatório para decisão, porque produto
novo precisa de rede, coparticipação e odonto, não só de preço.

Decisão de 30/09/2026 (Diretoria): o Individual de Divinópolis ("Personal 200
Oeste MG", arquivo "20261001 a 20261231 - Individual.pdf") NÃO entra — a praça
está suspensa NESSE produto. O Super Simples e o PME de Divinópolis seguem
normalmente. Como este script não cria par novo, basta não cadastrar o produto.

⚠️ Diferente da carga de 28/09, esta NÃO é promocional: preço pode subir. A
trava de direção não proíbe alta — ela exige que toda variação fique dentro de
±40% e imprime o balanço, para a alta aparecer antes de ir ao ar.

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import collections, json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
FONTES = ["/tmp/out_parsed.json", "/tmp/mg_out_parsed.json"]
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
LIMITE = 0.40     # variação máxima aceita sem revisão manual

# conferidas a mão no texto cru dos PDFs desta vigência
AMOSTRAS = [
    ("Curitiba - PR",           "Nosso Médico",        "Enfermaria",   "Parcial",  30, 174.78),
    ("Curitiba - PR",           "Nosso Médico",        "Apartamento",  "Completa", 30, 170.47),
    ("Maringá - PR",            "Nosso Plano",         "Apartamento",  "Completa",  2, 221.58),
    ("São Leopoldo - RS",       "Nosso Plano",         "Apartamento",  "Completa", 30, 211.08),
    ("Canoas - RS",             "Nosso Plano",         "Ambulatorial", "Parcial",   1,  78.43),
    ("Belo Horizonte - MG",     "Adapt 300 Estadual",  "Enfermaria",   "Completa",  2, 119.72),
    ("Belo Horizonte - MG",     "Adapt 300 Estadual",  "Enfermaria",   "Completa", 30, 146.59),
]


def chave(e):
    return (e.get("praca"), e["label"], e["acomodacao"], e["coparticipacao"],
            e.get("vmin"), e.get("vmax"), bool(e.get("mei")),
            e.get("tipo") or "Empresarial")


def main():
    cat = json.load(open(CAT))
    novos, cobertas = {}, set()
    for f in FONTES:
        if not os.path.exists(f):
            print("!! falta %s — rode os build_*.py antes" % f); return 1
        for praca, ents in json.load(open(f)).items():
            cobertas.add(praca)
            for n in ents:
                n["praca"] = praca
                novos.setdefault(chave(n), []).append(n)

    alvo = [e for e in cat if e["operadora"] == "Hapvida" and e.get("praca") in cobertas]
    print("praças na remessa: %d · entradas do catálogo nessas praças: %d\n"
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
    pares = {chave(e) for e in alvo}
    extras = [v[0] for k, v in novos.items() if k not in pares]

    erros = []
    print("travas:")

    print("  1. só entradas Hapvida das praças da remessa entram na conta")
    if any(e["operadora"] != "Hapvida" or e.get("praca") not in cobertas for e, _ in muda):
        erros.append("entrada fora do escopo seria alterada")

    print("  2. nenhuma praça fora da remessa é tocada")
    ids = {id(e) for e, _ in muda}
    if any(id(e) in ids for e in cat if e.get("praca") not in cobertas):
        erros.append("entrada de praça não coberta seria alterada")

    print("  3. toda variação cabe em ±%d%% (esta tabela NÃO é promocional)" % (LIMITE * 100))
    fora = [(e, n, b, (n["precos"][b] - e["precos"][b]) / e["precos"][b])
            for e, n in muda for b in BANDS
            if e["precos"][b] and abs((n["precos"][b] - e["precos"][b]) / e["precos"][b]) > LIMITE]
    if fora:
        erros.append("%d valores variam mais de %d%% — conferir antes de gravar" % (len(fora), LIMITE * 100))
        for e, n, b, d in fora[:10]:
            print("     %-24s %-30s %-12s %-9s [%s] %.2f -> %.2f (%+.1f%%)"
                  % (e["praca"], e["label"], e["acomodacao"], e["coparticipacao"],
                     b, e["precos"][b], n["precos"][b], d * 100))

    print("  4. curva de faixa etária não decresce (regra ANS)")
    mau = [n for _, n in muda
           if any(n["precos"][BANDS[i + 1]] < n["precos"][BANDS[i]] - 0.004 for i in range(9))]
    if mau:
        erros.append("%d entradas novas com curva decrescente" % len(mau))

    print("  5. Parcial nunca fica abaixo da Completa do mesmo plano")
    porpar = {}
    for e, n in muda:
        porpar.setdefault((e["praca"], e["label"], e["acomodacao"], e.get("vmin"), e.get("tipo")),
                          {})[e["coparticipacao"]] = n["precos"]
    for k, v in porpar.items():
        if "Parcial" in v and "Completa" in v:
            if any(v["Parcial"][b] < v["Completa"][b] - 0.005 for b in BANDS):
                erros.append("Parcial < Completa em %s" % str(k))

    print("  6. só o campo `precos` muda; nada de label, porte, praça ou tipo")
    for e, n in muda:
        if chave(e) != chave(n):
            erros.append("chave divergente em %s" % str(chave(e)))

    print("  7. %d amostras conferidas à mão contra o PDF" % len(AMOSTRAS))
    for praca, label, acom, cop, vmin, p0 in AMOSTRAS:
        h = [n for kk, v in novos.items() for n in v
             if kk[0] == praca and kk[1] == label and kk[2] == acom
             and kk[3] == cop and kk[4] == vmin]
        if not h:
            erros.append("amostra ausente: %s %s %s %s" % (praca, label, acom, cop)); continue
        if abs(h[0]["precos"]["00 a 18"] - p0) > 0.005:
            erros.append("amostra diverge: %s %s %.2f (esperado %.2f)"
                         % (praca, label, h[0]["precos"]["00 a 18"], p0))

    print("  8. o campo pr2 (reembolso parcial NotreDame) não é tocado")
    if any("pr2" in e for e, _ in muda):
        erros.append("uma entrada com pr2 seria alterada")

    print("\n  9. o que a tabela nova não traz fica com o preço anterior")
    print("     %d entradas mantidas" % len(sem_par))
    for lb, q in collections.Counter("%s · %s" % (e["praca"], e["label"]) for e in sem_par).most_common(12):
        print("        %-56s %d" % (lb, q))

    print("\n 10. pares novos que o catálogo NÃO tem (não entram por este script)")
    print("     %d" % len(extras))
    for lb, q in collections.Counter("%s · %s · %s" % (e["praca"], e["label"], e.get("tipo")) for e in extras).most_common(12):
        print("        %-62s %d" % (lb, q))

    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    print("\nresumo: %d entradas mudam, %d já estavam iguais" % (len(muda), iguais))
    if muda:
        d = [(n["precos"][b] - e["precos"][b]) / e["precos"][b]
             for e, n in muda for b in BANDS if e["precos"][b]]
        sobe = sum(1 for x in d if x > 0.0001); desce = sum(1 for x in d if x < -0.0001)
        print("        variação média %+.2f%% (de %+.2f%% a %+.2f%%) · %d sobem, %d descem"
              % (sum(d) / len(d) * 100, min(d) * 100, max(d) * 100, sobe, desce))
        for p, q in collections.Counter(e["praca"] for e, _ in muda).most_common():
            print("        %-26s %d" % (p, q))

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-out-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    for e, n in muda:
        e["precos"] = {b: n["precos"][b] for b in BANDS}
    json.dump(cat, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas atualizadas\nbackup: %s" % (len(muda), bak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
