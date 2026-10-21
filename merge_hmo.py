#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APLICA a carga HMO NotreDame 21/10/2026 a 31/12/2026 no catalog.json.

Entrada: /tmp/hmo_out_parsed.json (build_hmo_out.py), 10 arquivos, 10 praças —
as 9 da NDI Sede mais São José dos Campos (Pleno Vale do Paraíba), que vem nos
dois arquivos "Demais Praças".

Dois arquivos cobrem o PORTE I 1 VIDA: o da raiz do Downloads (28 páginas,
completo, com HMO e linha Metais) e o de HMO/ (19 páginas, só HMO). Em vez de
descartar um, os dois entram e a trava 6 exige que CONCORDEM — se divergirem,
aborta, porque aí um dos dois está sendo lido errado.

Só o campo `precos` muda. Entrada sem par no catálogo NÃO é criada: aparece no
relatório, porque produto novo precisa de rede, coparticipação e odonto.

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import collections, json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
NOVO = "/tmp/hmo_out_parsed.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
LIMITE = 0.40

# conferidas à mão no texto cru dos PDFs
AMOSTRAS = [
    ("São Paulo", "SP / RMSP", "Nosso Médico", "Enfermaria", "Parcial", 30, "Compulsório", 100.51),
    ("São Paulo", "SP / RMSP", "Smart UP", "Enfermaria", "Parcial", 30, "Compulsório", 120.82),
    ("São Paulo", "SP / RMSP", "Smart UP", "Apartamento", "Parcial", 30, "Compulsório", 151.03),
    ("SJC", "São José Dos Campos - SP", "Pleno Vale do Paraíba", "Enfermaria", "Parcial", 30, None, 213.07),
    ("SJC", "São José Dos Campos - SP", "Pleno Vale do Paraíba", "Apartamento", "Completa", 30, None, 183.67),
]


def chave(e):
    return (e.get("praca"), e["label"], e["acomodacao"], e["coparticipacao"],
            e.get("vmin"), e.get("vmax"), bool(e.get("mei")), e.get("contratacao"),
            e.get("tipo") or "Empresarial")


def main():
    cat = json.load(open(CAT))
    bruto = json.load(open(NOVO))
    pracas = set(bruto)

    idx = {}
    for e in cat:
        if e["operadora"] == "Hapvida":
            idx.setdefault(chave(e), []).append(e)

    # 6. os dois arquivos de 1 vida têm de concordar
    porchave = collections.defaultdict(list)
    for praca, ents in bruto.items():
        for n in ents:
            n["praca"] = praca
            porchave[chave(n)].append(n)
    briga = [k for k, v in porchave.items()
             if any(any(abs(x["precos"][b] - v[0]["precos"][b]) > 0.005 for b in BANDS) for x in v[1:])]

    muda, iguais, sem_par = [], 0, []
    for k, v in porchave.items():
        n = v[0]
        alvos = idx.get(k)
        if not alvos:
            sem_par.append(n); continue
        e = alvos[0]
        if all(abs(e["precos"][b] - n["precos"][b]) < 0.005 for b in BANDS):
            iguais += 1
        else:
            muda.append((e, n))

    erros = []
    print("tabela nova: %d entradas em %d praças (%d chaves distintas)\n"
          % (sum(len(v) for v in bruto.values()), len(pracas), len(porchave)))
    print("travas:")

    print("  1. só Hapvida/Empresarial+Individual das praças da remessa entra na conta")
    for e, _ in muda:
        if e["operadora"] != "Hapvida" or e.get("praca") not in pracas:
            erros.append("fora do escopo: %s" % str(chave(e)))

    print("  2. nenhuma praça fora da remessa é tocada")
    ids = {id(e) for e, _ in muda}
    if any(id(e) in ids for e in cat if e.get("praca") not in pracas):
        erros.append("entrada de praça não coberta seria alterada")

    print("  3. toda variação cabe em ±%d%%" % (LIMITE * 100))
    fora = [(e, n, b) for e, n in muda for b in BANDS
            if e["precos"][b] and abs((n["precos"][b] - e["precos"][b]) / e["precos"][b]) > LIMITE]
    if fora:
        for e, n, b in fora[:8]:
            print("     %-24s %-24s %-12s %-9s [%s] %.2f -> %.2f"
                  % (e["praca"], e["label"], e["acomodacao"], e["coparticipacao"],
                     b, e["precos"][b], n["precos"][b]))
        erros.append("%d valores variam mais de %d%%" % (len(fora), LIMITE * 100))

    print("  4. curva de faixa etária não decresce")
    for _, n in muda:
        if any(n["precos"][BANDS[i+1]] < n["precos"][BANDS[i]] - 0.004 for i in range(9)):
            erros.append("curva decrescente em %s %s" % (n["praca"], n["label"]))

    print("  5. Parcial nunca fica abaixo da Completa do mesmo plano")
    por = {}
    for _, n in muda:
        por.setdefault((n["praca"], n["label"], n["acomodacao"], n.get("vmin"),
                        n.get("contratacao"), bool(n.get("mei"))), {})[n["coparticipacao"]] = n["precos"]
    for k, v in por.items():
        if "Parcial" in v and "Completa" in v:
            if any(v["Parcial"][b] < v["Completa"][b] - 0.005 for b in BANDS):
                erros.append("Parcial < Completa em %s" % str(k))

    print("  6. os dois arquivos de 1 vida concordam entre si")
    if briga:
        for k in briga[:5]: print("     divergem: %s" % str(k))
        erros.append("%d chaves com valor diferente entre arquivos" % len(briga))

    print("  7. %d amostras conferidas à mão contra o PDF" % len(AMOSTRAS))
    for _, praca, label, acom, cop, vmin, contr, p0 in AMOSTRAS:
        h = [n for v in bruto.values() for n in v
             if n["praca"] == praca and n["label"] == label and n["acomodacao"] == acom
             and n["coparticipacao"] == cop and n.get("vmin") == vmin
             and n.get("contratacao") == contr]
        if not h:
            erros.append("amostra ausente: %s %s %s %s" % (praca, label, acom, cop)); continue
        if abs(h[0]["precos"]["00 a 18"] - p0) > 0.005:
            erros.append("amostra diverge: %s %s %.2f (esperado %.2f)"
                         % (praca, label, h[0]["precos"]["00 a 18"], p0))

    print("\n  8. o que a tabela nova traz e o catálogo não tem")
    print("     %d chaves sem par" % len(sem_par))
    for lb, q in collections.Counter(
            "%s · %s · %s · porte %s-%s · %s" % (n["praca"], n["label"], n["acomodacao"],
                                                 n.get("vmin"), n.get("vmax"),
                                                 n.get("contratacao") or ("MEI" if n.get("mei") else "—"))
            for n in sem_par).most_common(12):
        print("        %-76s %d" % (lb, q))

    if erros:
        print("\n" + "!" * 72)
        for x in erros[:12]: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    print("\nresumo: %d entradas mudam, %d já iguais" % (len(muda), iguais))
    if muda:
        d = [(n["precos"][b] - e["precos"][b]) / e["precos"][b] for e, n in muda for b in BANDS
             if e["precos"][b]]
        print("        variação média %+.2f%% (de %+.2f%% a %+.2f%%)"
              % (sum(d)/len(d)*100, min(d)*100, max(d)*100))
        for p, q in collections.Counter(e["praca"] for e, _ in muda).most_common():
            print("        %-28s %d" % (p, q))

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-hmo-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    for e, n in muda:
        e["precos"] = {b: n["precos"][b] for b in BANDS}
    json.dump(cat, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas atualizadas\nbackup: %s" % (len(muda), bak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
