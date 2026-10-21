# -*- coding: utf-8 -*-
"""Devolve o `id` as entradas do catalogo que entraram sem ele.

O SINTOMA (relatado em 21/10/2026): numa cotacao de tres opcoes NotreDame --
Prata, Ouro Max e Diamante Max -- a matriz mostrava os tres precos, mas embaixo
so apareciam DOIS cards. O Ouro Max sumia da lista, do folder e do PDF, mesmo
com o valor certo na tela.

A CAUSA esta no selectedPlans() do index.html, que deduplica por

    const k = c.id + '|' + (reembTipoDe(c) || '-');

Quem entrou no catalogo sem `id` tem c.id === undefined, entao a chave vira
"undefined|Parcial" para TODOS eles. O primeiro plano de reembolso parcial da
cotacao fica; os demais sao descartados como se fossem repeticao do mesmo. Foi
exatamente o que aconteceu: Prata (parcial) ficou, Ouro Max (parcial) sumiu, e
Diamante Max sobreviveu so porque o reembolso dele e total -- outra chave.

Sem id ficaram 578 entradas: as 576 da linha Metais (merge_ppo.py nunca
atribuiu id as entradas novas) e 2 do Smart Prime Compulsorio (merge_comp.py
fazia `nova.pop("id", None)` para nao repetir o id da entrada-base, mas nao
punha um novo no lugar).

Os ids sao inteiros de 1 a 4440, sem significado alem de identificar a linha --
numeracao segue do maior + 1, na ordem em que as entradas estao no arquivo,
para o resultado ser o mesmo em qualquer maquina. Os dois geradores tambem
foram corrigidos na mesma data, entao a proxima carga ja nasce com id.

Uso: corrige_ids.py [--gravar]
"""
import json, os, shutil, sys, time

CAT = os.path.expanduser("~/comparativo-ppo/catalog.json")


def main():
    cat = json.load(open(CAT, encoding="utf-8"))
    sem = [e for e in cat if not e.get("id")]
    com = [e for e in cat if e.get("id")]

    if not sem:
        print("nada a fazer: as %d entradas do catálogo já têm id" % len(cat))
        return 0

    ids = [e["id"] for e in com]
    if len(set(ids)) != len(ids):
        raise SystemExit("ABORTADO: o catálogo já tem id repetido — conferir antes de numerar")
    if any(not isinstance(i, int) for i in ids):
        raise SystemExit("ABORTADO: há id que não é inteiro — a numeração assume inteiros")

    print("entradas: %d  |  com id: %d  |  SEM id: %d" % (len(cat), len(com), len(sem)))
    import collections
    for (label, praca), q in collections.Counter(
            (e["label"], e.get("praca")) for e in sem).most_common(8):
        print("   %-16s %-28s %d" % (label, praca, q))
    if len(set((e["label"], e.get("praca")) for e in sem)) > 8:
        print("   ...")

    pid = max(ids)
    print("\núltimo id em uso: %d  →  novos de %d a %d" % (pid, pid + 1, pid + len(sem)))

    # o que o sintoma de fato era: planos diferentes colidindo na mesma chave
    chave = lambda e: "%s|%s" % (e.get("id"), e.get("reembTipo") or "-")
    antes = collections.Counter(chave(e) for e in cat)
    colidindo = sum(q for k, q in antes.items() if q > 1 and k.startswith("None"))
    print("entradas que hoje colidem na chave do selectedPlans(): %d" % colidindo)

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-ids-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    for e in sem:
        pid += 1
        e["id"] = pid

    novos = [e["id"] for e in cat]
    if len(set(novos)) != len(novos):
        raise SystemExit("ABORTADO: a numeração gerou id repetido")
    if any(not e.get("id") for e in cat):
        raise SystemExit("ABORTADO: sobrou entrada sem id")
    json.dump(cat, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas numeradas, %d ids únicos no catálogo\nbackup: %s"
          % (len(sem), len(set(novos)), bak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
