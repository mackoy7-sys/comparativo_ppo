# -*- coding: utf-8 -*-
"""Nipo Brasileiro passa a constar na rede do Advance 700 (Hapvida|700).

Pedido do usuario (10/09): o hospital aparece no folder com "—" no Advance 700 e
com credenciamento no Premium e no Infinity. Ele pediu para o 700 receber as
MESMAS credenciais.

O codigo nao e digitado: e LIDO do Premium 900 e do Infinity, e o script recusa
gravar se os dois nao concordarem entre si — assim nao ha risco de eu inventar
um credenciamento.

Use --apply para gravar.
"""
import json, sys, shutil, datetime, collections

RJ = '/Users/marcoscorrea/comparativo-ppo/rede.json'
APPLY = '--apply' in sys.argv
ALVO = 'Hapvida|700'
FONTES = ['Hapvida|900', 'Hapvida|Infinity']
NOME = 'Nipo Brasileiro'

d = json.load(open(RJ))


def acha(k):
    return next((h for h in d[k]['hospitais'] if h['nome'] == NOME), None)


refs = [acha(k) for k in FONTES]
assert all(refs), 'Nipo nao encontrado em %s' % [k for k, r in zip(FONTES, refs) if not r]
codes = {r['code'] for r in refs}
assert len(codes) == 1, 'Premium e Infinity divergem: %s — nao vou escolher por conta' % codes
base = refs[0]
print('=== NIPO BRASILEIRO -> ADVANCE 700')
for k, r in zip(FONTES, refs):
    print('  fonte %-18s %-22s %s' % (k, r['bairro'], r['code']))

ja = acha(ALVO)
assert ja is None, '%s ja tem o Nipo (code=%r) — nada a fazer' % (ALVO, ja and ja['code'])

novo = {'nome': base['nome'], 'bairro': base['bairro'],
        'regiao': base['regiao'], 'code': base['code']}

# insere ordenado por (bairro, nome) dentro do bloco da regiao, que e como o
# arquivo ja esta organizado
hs = d[ALVO]['hospitais']
bloco = [i for i, h in enumerate(hs) if h.get('regiao') == novo['regiao']]
assert bloco, 'Advance 700 nao tem bloco de %s' % novo['regiao']
pos = next((i for i in bloco
            if (hs[i]['bairro'], hs[i]['nome']) > (novo['bairro'], novo['nome'])),
           bloco[-1] + 1)
hs.insert(pos, novo)
print('  inserido em %s, posicao %d (bloco %s: %d->%d unidades)'
      % (ALVO, pos, novo['regiao'], len(bloco), len(bloco) + 1))
print('  registro: %s' % json.dumps(novo, ensure_ascii=False))

# confere o resultado
zn = [h for h in d[ALVO]['hospitais'] if h.get('regiao') == novo['regiao']]
print('\n  Zona Norte do Advance 700 agora:')
for h in zn:
    print('     %-30s %-22s %s' % (h['nome'], h['bairro'], h['code']))

# quem mais ainda nao tem o Nipo
falta = [k for k in d if acha(k) is None]
print('\n  planos que seguem SEM o Nipo Brasileiro: %s' % (', '.join(falta) or 'nenhum'))

if APPLY:
    shutil.copy(RJ, RJ + '.bak_' + datetime.datetime.now().strftime('%Y%m%d_%H%M'))
    json.dump(d, open(RJ, 'w'), ensure_ascii=False)
    print('\nGRAVADO: %s' % RJ)
else:
    print('\n(simulacao — use --apply para gravar)')
