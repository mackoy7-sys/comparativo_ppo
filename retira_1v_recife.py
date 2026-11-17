#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tira do catalog.json as entradas de 1 VIDA de RECIFE criadas pela remessa de
23/11/2026 — decisao do usuario em 17/11/2026.

Por que: naquela praca a tabela de 1 vida sai ABAIXO da de 2 a 29 (ate -22,7%),
o que faria uma vida custar menos que duas no mesmo produto. Esta no PDF (pag. 2,
cod. 40016 R$ 198,04 e 40017 R$ 157,44), nao e erro de leitura — mas o usuario
decidiu nao publicar Recife ate rever com a operadora.

Tira SO Recife: as outras 15 pracas que ganharam o porte de 1 vida continuam.

Ensaio por padrao; grava so com --gravar (backup com carimbo de hora).
"""
import collections, datetime, json, shutil, sys

CAT = "/Users/marcoscorrea/comparativo-ppo/catalog.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
ESPERADO_SAI = 16          # 8 combinacoes x 2 (simples + "+ Odonto")
ID_MIN = 6594              # faixa de ids criada pela remessa de 23/11

cat = json.load(open(CAT))


def alvo(e):
    return (e.get("operadora") == "Hapvida" and e.get("praca") == "Recife - PE"
            and (e.get("tipo") or "Empresarial") == "Empresarial"
            and e.get("vmin") == 1 and e.get("vmax") == 1)


saem = [e for e in cat if alvo(e)]
print("travas:")

print("  1. só entradas de 1 vida de Recife, Hapvida/Empresarial")
if len(saem) != ESPERADO_SAI:
    raise SystemExit("ABORTADO: esperava %d entradas, achei %d" % (ESPERADO_SAI, len(saem)))

print("  2. todas foram criadas por ESTA remessa (id >= %d) — não mexo no que já existia" % ID_MIN)
antigas = [e for e in saem if e["id"] < ID_MIN]
if antigas:
    raise SystemExit("ABORTADO: %d entradas de id antigo seriam removidas: %s"
                     % (len(antigas), [e["id"] for e in antigas][:5]))

print("  3. saem aos pares simples / \"+ Odonto\"")
s = [e for e in saem if "+ Odonto" not in e["label"]]
o = [e for e in saem if "+ Odonto" in e["label"]]
if len(s) != len(o):
    raise SystemExit("ABORTADO: %d simples x %d '+ Odonto' — deviam ser pares" % (len(s), len(o)))

print("  4. Recife continua cotável nos outros portes")
resto = [e for e in cat if e.get("operadora") == "Hapvida" and e.get("praca") == "Recife - PE"
         and (e.get("tipo") or "Empresarial") == "Empresarial" and e.get("vmin") != 1]
if not resto:
    raise SystemExit("ABORTADO: Recife ficaria sem nenhuma entrada Empresarial")
print("     %d entradas de Recife em 2 a 29 e 30 a 99 ficam intactas" % len(resto))

print("  5. as outras praças que ganharam 1 vida nesta remessa continuam")
outras = [e for e in cat if e["id"] >= ID_MIN and e.get("praca") != "Recife - PE"]
if len(outras) != 228:
    raise SystemExit("ABORTADO: esperava 228 entradas novas fora de Recife, achei %d" % len(outras))
print("     %d entradas em %d praças" % (len(outras), len({e["praca"] for e in outras})))

print("\nsaem %d entradas (faixa 00 a 18):" % len(saem))
for e in sorted(s, key=lambda e: (e["label"], e["acomodacao"], e["coparticipacao"])):
    print("   %-16s %-13s %-9s  %8.2f" % (e["label"], e["acomodacao"],
                                          e["coparticipacao"], e["precos"]["00 a 18"]))

if "--gravar" not in sys.argv:
    print("\n(ensaio — nada gravado. Rode com --gravar.)")
    sys.exit(0)

bak = CAT + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy(CAT, bak)
novo = [e for e in cat if not alvo(e)]
ids = [e["id"] for e in novo]
assert len(set(ids)) == len(ids) and None not in ids
json.dump(novo, open(CAT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("\nbackup: %s" % bak)
print("gravado: %d entradas removidas · catálogo com %d" % (len(saem), len(novo)))
