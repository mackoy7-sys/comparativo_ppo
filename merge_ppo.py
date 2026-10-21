#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APLICA a carga PPO NotreDame 21/10/2026 a 31/12/2026 no catalog.json.

Entrada: /tmp/ppo_out_parsed.json (build_ppo_out.py), 1.507 entradas em 9 praças.

Duas coisas acontecem aqui:

  LINHA TRADICIONAL (já existe) — Advance 600/700, Premium 900 (Care) e Infinity.
      Só `precos` e `pr2` mudam. O catálogo guarda o reembolso TOTAL em `precos`
      e o PARCIAL em `pr2`; a tabela nova traz os dois como blocos separados.

  LINHA METAIS (nova) — Prata, Prata Max, Ouro, Ouro Max, Diamante, Diamante Max.
      Entradas NOVAS. Aqui o reembolso é propriedade do produto, não escolha do
      vendedor: Prata e Ouro só existem com reembolso parcial, Diamante só com
      total. Por isso sai `reembTipo` e NÃO sai `pr2` — o seletor de reembolso
      não aparece, e o folder mostra qual é.

⚠️ Esta carga CONSERTA um defeito antigo: Santos · Premium 900 Care · apartamento ·
coparticipação completa · 1 vida tinha a faixa 19-23 (440,16) MENOR que a 00-18
(460,36) — curva decrescente, o que a ANS não permite. O 440,16 era o valor da
coluna de reembolso PARCIAL, colhido por engano numa carga anterior. É a única
entrada do catálogo inteiro nessa condição.

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import collections, json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
NOVO = "/tmp/ppo_out_parsed.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
TRAD = {"600", "700", "900", "900 Care", "Infinity"}
METAIS = {"Prata", "Prata Max", "Ouro", "Ouro Max", "Diamante", "Diamante Max"}
LIMITE = 0.40

# combinações que a LINHA METAIS deve ter, lidas do cabeçalho das tabelas
MET_ESPERADO = {
    ("Prata", "Enfermaria"): "Parcial", ("Prata", "Apartamento"): "Parcial",
    ("Prata Max", "Enfermaria"): "Parcial", ("Prata Max", "Apartamento"): "Parcial",
    ("Ouro", "Apartamento"): "Parcial", ("Ouro Max", "Apartamento"): "Parcial",
    ("Diamante", "Apartamento"): "Total", ("Diamante Max", "Apartamento"): "Total",
}

# conferidas à mão na página de São Paulo (2 a 29 vidas, Demais Empresas, copart parcial)
AMOSTRAS = [
    ("SP / RMSP", "Prata", "Enfermaria", "Parcial", "Parcial", 2, False, 226.21),
    ("SP / RMSP", "Prata Max", "Apartamento", "Parcial", "Parcial", 2, False, 286.30),
    ("SP / RMSP", "Ouro", "Apartamento", "Parcial", "Parcial", 2, False, 373.68),
    ("SP / RMSP", "Diamante", "Apartamento", "Parcial", "Total", 2, False, 612.89),
    ("SP / RMSP", "Diamante Max", "Apartamento", "Parcial", "Total", 2, False, 875.56),
    ("SP / RMSP", "Adv 600", "Enfermaria", "Parcial", "Parcial", 2, False, 247.22),
    ("SP / RMSP", "Adv 600", "Enfermaria", "Parcial", "Total", 2, False, 257.53),
    ("SP / RMSP", "Infinity", "Apartamento", "Parcial", "Total", 2, False, 916.35),
]


def kchave(e):
    # a chave do catálogo é o LABEL, não o plano: é o que separa "Nosso Plano"
    # de "Nosso Plano + Odonto", que compartilham o mesmo `plano`
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
            idx.setdefault(kchave(e), []).append(e)
    # Repetição só é aceitável quando as entradas são IDÊNTICAS (redundância sem
    # conflito). Duas entradas com a mesma chave e preços diferentes significam
    # que o Cotador escolheria uma arbitrariamente — aí não dá para seguir.
    conflito = [k for k, v in idx.items() if len(v) > 1
                and any(x["precos"] != v[0]["precos"] for x in v[1:])]
    if conflito:
        print("!! chaves com PREÇOS conflitantes no catálogo: %d" % len(conflito))
        for k in conflito[:5]: print("!!   %s" % str(k))
        return 1
    redund = [k for k, v in idx.items() if len(v) > 1]
    if redund:
        print("(aviso: %d chave(s) duplicada(s) com preços idênticos — redundância, "
              "não conflito: %s)\n" % (len(redund), redund[0][:3]))

    muda, iguais, sem_par, criar = [], 0, [], []
    for praca, ents in bruto.items():
        for n in ents:
            n["praca"] = praca
            k = kchave(n)
            if n["plano"] in METAIS:
                criar.append(n); continue
            alvos = idx.get(k)
            if not alvos:
                sem_par.append(n); continue
            e = alvos[0]
            campo = "precos" if n["reembTipo"] == "Total" else "pr2"
            atual = e.get(campo)
            if atual and all(abs(atual[b] - n["precos"][b]) < 0.005 for b in BANDS):
                iguais += 1
            else:
                muda.append((e, campo, n))

    erros = []
    print("tabela nova: %d entradas em %d praças\n" % (sum(len(v) for v in bruto.values()), len(pracas)))
    print("travas:")

    print("  1. só Hapvida/Empresarial das 9 praças da remessa entra na conta")
    for e, _, _ in muda:
        if e["operadora"] != "Hapvida" or (e.get("tipo") or "Empresarial") != "Empresarial" \
           or e.get("praca") not in pracas:
            erros.append("fora do escopo: %s" % str(kchave(e)))

    print("  2. Individual, Adesão e as demais praças ficam intocados")
    ids = {id(e) for e, _, _ in muda}
    for e in cat:
        if id(e) in ids and ((e.get("tipo") or "Empresarial") != "Empresarial"
                             or e.get("praca") not in pracas):
            erros.append("entrada protegida seria alterada")

    print("  3. toda variação cabe em ±%d%%" % (LIMITE * 100))
    fora = [(e, c, n, b) for e, c, n in muda for b in BANDS
            if (e.get(c) or {}).get(b) and
            abs((n["precos"][b] - e[c][b]) / e[c][b]) > LIMITE]
    if fora:
        for e, c, n, b in fora[:6]:
            print("     %-20s %-18s %-12s %-9s %-6s [%s] %.2f -> %.2f"
                  % (e["praca"], e["label"], e["acomodacao"], e["coparticipacao"], c,
                     b, e[c][b], n["precos"][b]))
        erros.append("%d valores variam mais de %d%%" % (len(fora), LIMITE * 100))

    print("  4. curva de faixa etária não decresce em NENHUMA entrada gravada")
    for _, _, n in muda:
        if any(n["precos"][BANDS[i+1]] < n["precos"][BANDS[i]] - 0.004 for i in range(9)):
            erros.append("curva decrescente em %s %s" % (n["praca"], n["label"]))
    for n in criar:
        if any(n["precos"][BANDS[i+1]] < n["precos"][BANDS[i]] - 0.004 for i in range(9)):
            erros.append("curva decrescente (nova) em %s %s" % (n["praca"], n["label"]))

    print("  5. reembolso parcial (pr2) nunca fica acima do total (precos)")
    sim = {}
    for e, c, n in muda:
        sim.setdefault(id(e), {"e": e})[c] = n["precos"]
    for v in sim.values():
        e = v["e"]
        tot = v.get("precos", e.get("precos"))
        par = v.get("pr2", e.get("pr2"))
        if tot and par and any(par[b] > tot[b] + 0.005 for b in BANDS):
            erros.append("pr2 > precos em %s %s %s" % (e["praca"], e["label"], e["acomodacao"]))

    print("  6. a LINHA METAIS só traz as 8 combinações do cabeçalho")
    combos = {(n["plano"], n["acomodacao"]): n["reembTipo"] for n in criar}
    if combos != MET_ESPERADO:
        erros.append("combinações inesperadas na Metais: %s"
                     % sorted(set(combos.items()) ^ set(MET_ESPERADO.items()))[:4])

    print("  7. a linha Metais ainda não existe na Hapvida/NotreDame")
    if any(e["plano"] in METAIS and e["operadora"] == "Hapvida" for e in cat):
        erros.append("já há produto Metais da Hapvida no catálogo — esta carga é a primeira")
    # ⚠️ A AMIL tem "Prata" e "Ouro" em SP/RMSP. Não é conflito de dados (tudo que
    # usa `plano` como chave filtra por operadora antes), mas o isPPO/isMetais do
    # index passou a exigir operadora Hapvida por causa disso.
    amil = [e for e in cat if e["plano"] in METAIS and e["operadora"] != "Hapvida"]
    if amil:
        print("     (a %s também tem %s — por isso o isPPO do index testa a operadora)"
              % (amil[0]["operadora"], sorted({e["plano"] for e in amil})))

    print("  8. %d amostras conferidas à mão contra o PDF" % len(AMOSTRAS))
    for praca, label, acom, cop, rb, vmin, mei, p0 in AMOSTRAS:
        h = [n for v in bruto.values() for n in v
             if n["praca"] == praca and n["label"] == label and n["acomodacao"] == acom
             and n["coparticipacao"] == cop and n["reembTipo"] == rb
             and n.get("vmin") == vmin and bool(n.get("mei")) == mei
             and not n.get("contratacao")]
        if not h:
            erros.append("amostra ausente: %s %s %s %s" % (praca, label, acom, rb)); continue
        if abs(h[0]["precos"]["00 a 18"] - p0) > 0.005:
            erros.append("amostra diverge: %s %s %.2f (esperado %.2f)"
                         % (praca, label, h[0]["precos"]["00 a 18"], p0))

    print("  9. a entrada de curva decrescente de Santos é corrigida por esta carga")
    alvo = [(e, c, n) for e, c, n in muda
            if e.get("praca") == "Santos - SP" and e["label"] == "Premium 900 Care"
            and e["acomodacao"] == "Apartamento" and e["coparticipacao"] == "Completa"
            and e.get("vmin") == 1 and c == "precos"]
    if not alvo:
        erros.append("a entrada defeituosa de Santos NÃO seria corrigida")

    print("\n 10. o que a tabela nova não casou com o catálogo")
    print("     %d entradas sem par" % len(sem_par))
    for lb, q in collections.Counter("%s · %s · porte %s-%s · %s"
                                     % (n["praca"], n["label"], n.get("vmin"), n.get("vmax"),
                                        n.get("contratacao") or ("MEI" if n.get("mei") else "—"))
                                     for n in sem_par).most_common(10):
        print("        %-66s %d" % (lb, q))

    if erros:
        print("\n" + "!" * 72)
        for x in erros[:14]: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    print("\nresumo: %d campos mudam, %d já iguais, %d entradas NOVAS (Metais)"
          % (len(muda), iguais, len(criar)))
    d = [(n["precos"][b] - e[c][b]) / e[c][b] for e, c, n in muda for b in BANDS
         if (e.get(c) or {}).get(b)]
    if d:
        print("        variação média %+.2f%% (de %+.2f%% a %+.2f%%)"
              % (sum(d)/len(d)*100, min(d)*100, max(d)*100))
    for p, q in collections.Counter(n["praca"] for n in criar).most_common():
        print("        novas em %-26s %d" % (p, q))

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-ppo-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    for e, campo, n in muda:
        e[campo] = {b: n["precos"][b] for b in BANDS}
    for n in criar:
        cat.append({k: v for k, v in n.items() if k not in ("fonte", "cod")})
    json.dump(cat, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d campos atualizados, %d entradas criadas\nbackup: %s"
          % (len(muda), len(criar), bak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
