#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pleno Vale do Paraíba — São José dos Campos (arquivos "Demais Praças - SJC").

Produto NOVO no catálogo (SJC só tinha Nosso Plano / Nosso Médico). O rótulo fica
"Pleno Vale do Paraíba", e não "Pleno": já existe um "Pleno" em 22 outras praças
que é produto diferente, e o vendedor vê o nome da tabela.

Layout (1 página por arquivo, bem regular):
  PRODUTO PLENO VALE DO PARAÍBA PLENO VALE DO PARAÍBA
  COPARTICIPAÇÃO ... PARCIAL ... COM COPARTICIPAÇÃO   <- 2 grupos
  ACOMODAÇÃO ENFERM APARTAMENTO ENFERM APARTAMENTO    <- 4 colunas
  00 a 18 anos R$ a R$ b R$ c R$ d   De "00 a 18" ... 4,00% 4,00%
A caixa de REAJUSTE fica na mesma linha, à direita, mas os percentuais não têm
"R$" — por isso basta pegar os 4 primeiros valores prefixados por R$.

Saída: /tmp/sjc_parsed.json
"""
import json, re, collections
import pdfplumber

D = '/Users/marcoscorrea/Downloads/OneDrive_5_08-09-2026/'
OUT = '/tmp/sjc_parsed.json'
PRACA = 'São José Dos Campos - SP'   # grafia usada no catalog.json
LABEL = 'Pleno Vale do Paraíba'
FILES = [
    ('20260908 a 20260930 - Super Simples 2 a 29 vidas - Demais Praças - SJC.pdf',
     dict(vmin=2, vmax=29)),
    ('20260908 a 20260930 - PME - Demais Praças - SJC.pdf',
     dict(vmin=30, vmax=99)),
]
# ordem das 4 colunas da tabela
COLS = [('Parcial', 'Enfermaria'), ('Parcial', 'Apartamento'),
        ('Completa', 'Enfermaria'), ('Completa', 'Apartamento')]
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38", "39 a 43",
         "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
RE_VAL = re.compile(r'R\$\s*([\d][\d\s.]*,\s*\d{2})')

def vals(linha):
    out = []
    for m in RE_VAL.finditer(linha):
        s = m.group(1).replace(' ', '').replace('.', '').replace(',', '.')
        out.append(round(float(s), 2))
    return out

def faixa_de(linha):
    n = linha.strip().lower()
    for b in BANDS[:-1]:
        if n.startswith(b):
            return b
    if n.startswith('59 anos ou mais') or n.startswith('59 ou mais'):
        return '59 ou mais'
    return None

def main():
    precos = {c: {} for c_ in [0] for c in COLS}
    result = collections.defaultdict(list)
    for fn, meta in FILES:
        with pdfplumber.open(D + fn) as doc:
            t = doc.pages[0].extract_text() or ''
        assert 'PLENO VALE DO PARAÍBA' in t.upper(), 'produto nao encontrado em ' + fn
        assert 'São José dos Campos' in t, 'praca inesperada em ' + fn
        col = {c: {} for c in COLS}
        for linha in t.split('\n'):
            b = faixa_de(linha)
            if not b:
                continue
            v = vals(linha)
            if len(v) < 4:
                continue
            for i, c in enumerate(COLS):
                col[c][b] = v[i]
        faltou = [c for c in COLS if len(col[c]) != 10]
        assert not faltou, 'faixas incompletas em %s: %s' % (fn, faltou)
        for (cop, acom) in COLS:
            e = dict(operadora='Hapvida', plano=LABEL, label=LABEL, acomodacao=acom,
                     coparticipacao=cop, categoria='Geral', tipo='Empresarial',
                     mei=False, praca=PRACA, precos=col[(cop, acom)])
            e.update(meta)
            result[PRACA].append(e)
        print('%-62s %d entradas' % (fn[:62], len(COLS)))

    json.dump(result, open(OUT, 'w'), ensure_ascii=False, indent=1)
    print('\nTotal: %d entradas -> %s' % (sum(len(v) for v in result.values()), OUT))

    # spot-checks contra os valores lidos na propria pagina
    def get(vmin, cop, acom, banda='00 a 18'):
        for e in result[PRACA]:
            if e['vmin'] == vmin and e['coparticipacao'] == cop and e['acomodacao'] == acom:
                return e['precos'][banda]
    checks = [(2, 'Parcial', 'Enfermaria', 216.45), (2, 'Parcial', 'Apartamento', 281.02),
              (2, 'Completa', 'Enfermaria', 141.56), (2, 'Completa', 'Apartamento', 183.55),
              (30, 'Parcial', 'Enfermaria', 213.07), (30, 'Completa', 'Apartamento', 183.67),
              (2, 'Parcial', 'Enfermaria', 1297.66)]
    checks[-1] = (2, 'Parcial', 'Enfermaria', 1297.66)   # faixa 59+
    ok = True
    for vmin, cop, acom, esperado in checks[:-1]:
        got = get(vmin, cop, acom)
        if got != esperado:
            ok = False
        print('  %s vmin=%-3d %-9s %-12s esperado=%9.2f obtido=%s'
              % ('OK ' if got == esperado else 'FALHOU', vmin, cop, acom, esperado, got))
    got59 = get(2, 'Parcial', 'Enfermaria', '59 ou mais')
    if got59 != 1297.66:
        ok = False
    print('  %s vmin=2   Parcial   Enfermaria   59+ esperado=  1297.66 obtido=%s'
          % ('OK ' if got59 == 1297.66 else 'FALHOU', got59))
    print('spot-checks:', 'OK' if ok else 'FALHAS')

if __name__ == '__main__':
    main()
