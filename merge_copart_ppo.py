#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CARREGA a coparticipação da linha METAIS (e a da TRADICIONAL) no copart.json,
nas 9 praças da remessa de 21/10/2026.

Por que modelo-e-verificação, e não parser de célula: o quadro NÃO tem réguas
próprias (as linhas verticais da página são da tabela de preços acima), o
agrupamento de produtos MUDA entre a página de copart parcial e a de total, e em
uma das páginas do Rio as duas faixas vêm LADO A LADO num quadro só. Em vez de
adivinhar geometria, a tabela abaixo foi lida da fonte e o script CONFERE, página
por página, que o que está escrito bate com ela.

Os valores se organizam em três conjuntos, e cada produto cai em um:

    A  Prata · Prata Max · Ouro            Adv 600 · Adv 700
    B  Ouro Max · Diamante                 Premium 900 · Premium 900 Care
    C  Diamante Max                        Infinity

⚠️ Nas 9 praças a coparticipação do PPO Empresarial NUNCA tinha sido carregada —
`copart.json` só tinha a do Coletivo por Adesão. Então isto também tapa um buraco
antigo: hoje o folder de um Advance em SP sai sem a tabela de coparticipação.

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import collections, glob, json, os, re, shutil, sys, time, unicodedata
import pdfplumber

AQUI = os.path.dirname(os.path.abspath(__file__))
COP = os.path.join(AQUI, "copart.json")
CAT = os.path.join(AQUI, "catalog.json")
D = "/Users/marcoscorrea/Downloads/PPO/"
PRACAS = ["SP / RMSP", "Mogi das Cruzes - SP", "São Bernardo do Campo - SP", "Santos - SP",
          "Jundiaí - SP", "Sorocaba - SP", "Campinas - SP", "Americana - SP", "Rio de Janeiro - RJ"]
PROCS = ["Consultas eletivas", "Consultas de urgência", "Exames simples", "Exames complexos",
         "Terapias especiais", "Demais terapias", "Internações"]

PARCIAL = {
    "A": [None, None, None, None, "Valor fixo R$ 79,00", "Valor fixo R$ 42,00", None],
    "B": [None, None, None, None, "Valor fixo R$ 129,00", "Valor fixo R$ 66,00", None],
    "C": [None, None, None, None, "Valor fixo R$ 129,00", "Valor fixo R$ 66,00", None],
}
TOTAL = {
    "A": ["30% limitado a R$ 30,00", "30% limitado a R$ 90,00", "30% limitado a R$ 25,00",
          "30% limitado a R$ 110,00", "Valor fixo R$ 79,00", "Valor fixo R$ 42,00",
          "Valor fixo R$ 220,00"],
    "B": ["30% limitado a R$ 55,00", "30% limitado a R$ 165,00", "30% limitado a R$ 35,00",
          "30% limitado a R$ 130,00", "Valor fixo R$ 129,00", "Valor fixo R$ 66,00",
          "Valor fixo R$ 400,00"],
    "C": ["30% limitado a R$ 166,00", "30% limitado a R$ 355,00", "30% limitado a R$ 84,00",
          "30% limitado a R$ 150,00", "Valor fixo R$ 129,00", "Valor fixo R$ 66,00",
          "Valor fixo R$ 570,00"],
}
CONJ = {"Prata": "A", "Prata Max": "A", "Ouro": "A", "Ouro Max": "B", "Diamante": "B",
        "Diamante Max": "C", "600": "A", "700": "A", "900": "B", "900 Care": "B", "Infinity": "C"}
METAIS = {"Prata", "Prata Max", "Ouro", "Ouro Max", "Diamante", "Diamante Max"}

PRODS_RE = re.compile(r'ADVANCE 600 ?/ ?700|PRATA MAX|PRATA|OURO MAX|OURO|DIAMANTE MAX|DIAMANTE|'
                      r'ADVANCE 600|ADVANCE 700|ADVANCE|PREMIUM 900 CARE|PREMIUM 900|CARE|INFINITY')
NOME = {'ADVANCE 600 / 700': ['600', '700'], 'ADVANCE 600/700': ['600', '700'],
        'ADVANCE': ['600', '700'], 'ADVANCE 600': ['600'], 'ADVANCE 700': ['700'],
        'PRATA': ['Prata'], 'PRATA MAX': ['Prata Max'], 'OURO': ['Ouro'], 'OURO MAX': ['Ouro Max'],
        'DIAMANTE': ['Diamante'], 'DIAMANTE MAX': ['Diamante Max'],
        'PREMIUM 900': ['900'], 'PREMIUM 900 CARE': ['900 Care'], 'CARE': ['900 Care'],
        'INFINITY': ['Infinity']}
VAL = re.compile(r'Valor fixo R\$ ?[\d.]+,\d\d|\d+% limitado a R\$ ?[\d.]+,\d\d|--|-')
CORTE = re.compile(r'ODONTO PREMIUM|\* Valor Promocional|OBS:|- 60 dias|ATENÇÃO|O contrato')


def ne(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn').upper().replace(' ', '')


def grupos(txt):
    t = re.sub(r'\s+', ' ', txt)
    gs, atual, fim = [], [], 0
    for m in PRODS_RE.finditer(t):
        sep = t[fim:m.start()]
        if atual and '|' not in sep and '/' not in sep:
            gs.append(atual); atual = []
        atual.append(m.group(0)); fim = m.end()
    if atual: gs.append(atual)
    return [[p for x in g for p in NOME.get(x, [])] for g in gs]


def confere():
    """Lê as 45 páginas e verifica que o escrito bate com o modelo.

    ⚠️ A comparação é por SEQUÊNCIA do quadro inteiro, não linha a linha pelo
    rótulo: em algumas páginas o extrator de texto perde o rótulo da primeira
    linha e desloca todos os outros em um. Os VALORES e a ORDEM continuam
    certos, então o teste é: a sequência encontrada tem de ser um trecho
    contíguo da sequência que o modelo prevê para aquela página.
    """
    ROTS = ('CONSULTASELETIVAS', 'CONSULTASDEURGENCIA', 'EXAMESSIMPLES', 'EXAMESCOMPLEXOS',
            'TERAPIASESPECIAIS', 'DEMAISTERAPIAS', 'INTERNACOES', 'INTERNACAO')
    probs, pgs = [], 0
    for f in sorted(glob.glob(D + '*.pdf')):
        for pg in pdfplumber.open(f).pages:
            ls = (pg.extract_text() or '').split('\n')
            if len(ls) < 2: continue
            praca = 'SP / RMSP' if ls[1].strip() == 'São Paulo - SP' else ls[1].strip()
            cab = next((l for l in ls if ne(l[:13]).startswith('PROCEDIMENTO')
                        and any(x in ne(l) for x in ('PRATA', 'ADVANCE'))), None)
            if not cab: continue
            gs = grupos(CORTE.split(cab, 1)[0])
            if not gs: continue
            # ⚠️ EXCEÇÃO: nessa página do Rio as duas faixas vêm LADO A LADO num
            # quadro só, e o extrator perde o rótulo da 2ª coluna — o cabeçalho
            # sai "ADVANCE ADVANCE" em vez de "ADVANCE | PREMIUM 900 / CARE".
            # Os valores conferidos à mão são os conjuntos A e B, nesta ordem.
            if [g for g in gs] == [['600', '700'], ['600', '700']]:
                gs = [['600'], ['900']]
            pgs += 1
            dois = 'COPARTICIPAÇÃO PARCIAL COPARTICIPAÇÃO TOTAL' in ' '.join(ls)
            tier = 'parcial' if 'COM COPARTICIPAÇÃO PARCIAL' in '\n'.join(ls[:7]) else 'total'
            tiers = ['parcial', 'total'] if dois else [tier]

            esperado = []
            for idx in range(7):
                linha = []
                for t in tiers:
                    tab = PARCIAL if t == 'parcial' else TOTAL
                    for g in gs:
                        linha.append(tab[CONJ[g[0]]][idx] or '-')
                esperado.append(linha)

            achado = []
            for ln in ls:
                if not ne(ln[:24]).startswith(ROTS): continue
                vs = VAL.findall(CORTE.split(ln, 1)[0])
                if len(vs) == len(esperado[0]):
                    achado.append(vs)
            if not achado:
                probs.append('%s/%s: nenhuma linha legível' % (praca, '+'.join(tiers))); continue
            ok = any(esperado[k:k + len(achado)] == achado
                     for k in range(0, 8 - len(achado)))
            if not ok:
                probs.append('%s/%s: sequência do quadro não bate com o modelo'
                             % (praca, '+'.join(tiers)))
    return pgs, probs


def main():
    pgs, probs = confere()
    print("conferência: %d quadros lidos nos 5 PDFs" % pgs)
    if probs:
        print("\n" + "!" * 72)
        for x in collections.Counter(probs).most_common(10): print("!! %s x%d" % x)
        print("!! o escrito não bate com o modelo — NADA GRAVADO")
        return 1
    print("  nenhuma divergência entre o modelo e o que está escrito\n")

    cop = json.load(open(COP))
    cat = json.load(open(CAT))
    vende = collections.defaultdict(set)
    for e in cat:
        if e["operadora"] == "Hapvida" and (e.get("tipo") or "Empresarial") == "Empresarial":
            vende[e.get("praca")].add(e["plano"])

    antes = json.dumps(cop, ensure_ascii=False, sort_keys=True)
    criados, atualizados = [], []
    for praca in PRACAS:
        for plano, conj in CONJ.items():
            if plano not in vende.get(praca, ()):
                continue
            novo = {"parcial": dict(zip(PROCS, PARCIAL[conj])),
                    "total": dict(zip(PROCS, TOTAL[conj])),
                    "fonte": "PPO NotreDame 21/10 a 31/12/2026"}
            alvo = cop.setdefault(praca, {})
            if plano in alvo:
                if alvo[plano] != novo: atualizados.append((praca, plano))
            else:
                criados.append((praca, plano))
            alvo[plano] = novo

    erros = []
    print("travas:")
    print("  1. nenhuma praça fora das 9 da remessa é tocada")
    a, b = json.loads(antes), cop
    mud = sorted(p for p in set(a) | set(b) if a.get(p) != b.get(p))
    if any(p not in PRACAS for p in mud):
        erros.append("praça fora da remessa alterada: %s" % [p for p in mud if p not in PRACAS])

    print("  2. o Coletivo por Adesão (chaves '· Adesão') não é tocado")
    for p in mud:
        for k, v in (a.get(p) or {}).items():
            if "· Adesão" in k and b[p].get(k) != v:
                erros.append("%s · %s (Adesão) seria alterado" % (p, k))

    print("  3. só entram planos que a praça realmente vende no Empresarial")
    for praca, plano in criados + atualizados:
        if plano not in vende.get(praca, ()):
            erros.append("%s não vende %s" % (praca, plano))

    print("  4. Parcial nunca cobra mais que Total")
    for praca, plano in criados + atualizados:
        d = cop[praca][plano]
        for proc in PROCS:
            pa, to = d["parcial"][proc], d["total"][proc]
            if pa and not to:
                erros.append("%s · %s · %s: parcial cobra e total não" % (praca, plano, proc))

    if erros:
        print("\n" + "!" * 72)
        for x in erros[:10]: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    met = [(p, pl) for p, pl in criados + atualizados if pl in METAIS]
    trad = [(p, pl) for p, pl in criados + atualizados if pl not in METAIS]
    print("\nresumo: %d blocos criados, %d atualizados" % (len(criados), len(atualizados)))
    print("        linha Metais ...... %d" % len(met))
    print("        linha Tradicional . %d  (não existiam: o folder do PPO saía sem coparticipação)"
          % len(trad))
    for praca in PRACAS:
        ps = sorted(pl for p, pl in criados + atualizados if p == praca)
        print("        %-28s %s" % (praca, ', '.join(ps)))

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = COP + ".bak-ppo-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(COP, bak)
    json.dump(cop, open(COP, "w"), ensure_ascii=False)
    print("\ngravado. backup: %s" % bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
