# -*- coding: utf-8 -*-
"""Monta a tabela FAIXA DE CEP -> bairro do ranking, para o cotador.

Contexto: casar o bairro pelo NOME que o ViaCEP devolve nao funciona — o CEP
05615-000, que a planilha chama de Morumbi, devolve "Vila Progredior". Entao a
lista de 49 bairros vira FAIXAS DE PREFIXO DE CEP, montadas sobre uma varredura
real da base dos Correios (6.000 prefixos de SP capital e Rio, /tmp/cep_prefixos.json).

Como cada prefixo entra:
  a) NOME EXATO  — o ViaCEP devolve o proprio nome do bairro da lista. Confiavel,
     entra sempre.
  b) NOME POR PREFIXO com limite de palavra ("Brooklin Paulista" -> Brooklin),
     mas SO se estiver a <=200 prefixos do CEP de referencia da planilha. Sem
     essa trava, "Jardim América da Penha" (03090/03704, zona leste) entrava como
     "Jardim América" dos Jardins — 1.642 prefixos de distancia.
  c) EXTRA — prefixos que a sonda XXXXX-000 nao pegou porque o CEP geral do
     prefixo esta vazio ou pertence ao vizinho. Levantados com sonda densa
     (-010/-100): Gloria, Sao Conrado, Lagoa e Gavea so apareceram assim.
  d) SUB-BAIRRO — nome que o ViaCEP devolve e que fica DENTRO do bairro/distrito
     da lista. Curado a mao a partir dos vizinhos de cada ancora; a lista esta
     abaixo e e o unico ponto de julgamento do script.

Ficam de fora, de proposito:
  - Jardins: nao e bairro do ViaCEP. E o conjunto de Jardim Paulista, Jardim
    America, Jardim Europa, Jardim Paulistano e Cerqueira Cesar — todos ja na
    lista, entao o cliente cai neles.
  - Chacara Klabin: os CEPs dela (04111-04113) devolvem "Vila Mariana", que
    tambem esta na lista.
  - Itaguacu: o CEP 04809 da planilha e Vila Santa Maria / Terceira Divisao de
    Interlagos, zona sul distante. Parece erro da planilha — nao inventei faixa.
  - Favela/perfil discrepante colado num bairro nobre (Paraisopolis, Vidigal,
    Cidade de Deus, Rocinha) e os bairros de Jacarepagua colados na Barra
    (Freguesia, Taquara, Tanque, Curicica).

Saida: /tmp/faixas_cep2.json
"""
import json, re, unicodedata, collections
import openpyxl

PREF = json.load(open('/tmp/cep_prefixos.json'))
XLSX = '/Users/marcoscorrea/Downloads/ranking_bairros_PPO.xlsx'
OUT = '/tmp/faixas_cep2.json'
DIST_MAX = 200            # trava do casamento por prefixo de nome

# (c) prefixos achados na sonda densa -010/-100
EXTRA = {
    ('Glória', 'RJ'): [22210, 22211],
    ('São Conrado', 'RJ'): [22610],
    ('Lagoa', 'RJ'): [22470, 22471],
    ('Gávea', 'RJ'): [22470],
}
# a sonda esparsa marcou 22210-000 como "Lagoa"; a densa mostra Gloria em
# 22210-100 e a Lagoa de verdade em 22470/22471. Tira o ponto errado.
REMOVER = {('Lagoa', 'RJ'): [22210]}

# (d) sub-bairro -> bairro da lista. Julgamento humano, revisar com o usuario.
SUB = {
    'SP': {
        # Morumbi (distrito): sub-bairros nobres de dentro dele
        'Vila Progredior': 'Morumbi', 'Jardim Leonor': 'Morumbi',
        'Jardim Everest': 'Morumbi', 'Vila Inah': 'Morumbi',
        'Jardim Morumbi': 'Morumbi', 'Fazenda Morumbi': 'Morumbi',
        'Cidade Jardim': 'Morumbi', 'Real Parque': 'Morumbi',
        # Vila Mariana
        'Vila Clementino': 'Vila Mariana', 'Chácara Klabin': 'Vila Mariana',
        'Jardim Vila Mariana': 'Vila Mariana', 'Jardim Luzitânia': 'Vila Mariana',
        # Moema / Vila Nova Conceição
        'Indianópolis': 'Moema', 'Vila Uberabinha': 'Moema',
        'Ibirapuera': 'Vila Nova Conceição',
        # Brooklin / Campo Belo
        'Cidade Monções': 'Brooklin', 'Vila Cordeiro': 'Brooklin',
        'Parque Colonial': 'Brooklin', 'Vila Congonhas': 'Campo Belo',
        # Jardins
        'Jardim Paulistano': 'Jardim Europa',
        # Pinheiros / Vila Madalena / Alto de Pinheiros
        'Sumarezinho': 'Vila Madalena', 'Jardim das Bandeiras': 'Vila Madalena',
        'Boaçava': 'Alto de Pinheiros', 'Vila Ida': 'Alto de Pinheiros',
        'Jardim Universidade Pinheiros': 'Alto de Pinheiros',
        # Perdizes
        'Vila Pompéia': 'Perdizes',
        # Santo Amaro / Granja Julieta
        'Chácara Santo Antônio (Zona Sul)': 'Granja Julieta',
        'Jardim das Acácias': 'Santo Amaro', 'Alto da Boa Vista': 'Santo Amaro',
        # Tatuapé / Mooca
        'Vila Gomes Cardim': 'Tatuapé', 'Chácara Califórnia': 'Tatuapé',
        'Jardim Anália Franco': 'Tatuapé',
        'Parque da Mooca': 'Mooca', 'Alto da Mooca': 'Mooca',
        # Aclimação / Santana
        'Jardim da Glória': 'Aclimação',
        'Jardim São Paulo(Zona Norte)': 'Santana',
    },
    'RJ': {'Joá': 'São Conrado'},
}


def dea(s):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKD', s or '')
                  .encode('ascii', 'ignore').decode().lower()).strip()


# -------- lista do usuario
wb = openpyxl.load_workbook(XLSX, data_only=True)
lista, vis = [], set()
for rank, b, uf, m2, cep, pop in wb['Ranking Imobiliário'].iter_rows(min_row=2, values_only=True):
    if not b:
        continue
    n = re.sub(r'\s*\(Extra\)\s*$', '', str(b)).strip()
    if (dea(n), uf) in vis:
        continue
    vis.add((dea(n), uf))
    lista.append({'b': n, 'uf': uf, 'r': int(rank), 'm2': int(m2),
                  'ref': int(str(cep).replace('-', '')[:5])})
lista.sort(key=lambda x: x['r'])
idx = {(L['b'], L['uf']): i for i, L in enumerate(lista)}

# -------- varredura
CID = {'SP': 'sao paulo', 'RJ': 'rio de janeiro'}
d = {}
for k, v in PREF.items():
    if isinstance(v, list) and v[2] in CID and dea(v[1]) == CID[v[2]]:
        d[int(k)] = (v[0], v[2])

dono, motivo = {}, {}


def por(p, i, m):
    if p not in dono:
        dono[p] = i; motivo[p] = m


# (a) nome exato
for p, (b, u) in d.items():
    for i, L in enumerate(lista):
        if L['uf'] == u and dea(b) == dea(L['b']):
            por(p, i, 'exato'); break
# (b) nome por prefixo, com trava de distancia
for p, (b, u) in d.items():
    if p in dono:
        continue
    a = dea(b)
    for i, L in enumerate(lista):
        n = dea(L['b'])
        if L['uf'] == u and len(a) > len(n) and a.startswith(n) and a[len(n)] == ' ':
            if abs(p - L['ref']) <= DIST_MAX:
                por(p, i, 'prefixo')
            break
# (d) sub-bairro — MESMA trava de distancia do passo (b): nome de sub-bairro se
# repete em pontas opostas da cidade. Ha dois "Parque Colonial" (04570, Brooklin,
# e 03967, zona leste) e o segundo entrava como Brooklin sem a trava.
for p, (b, u) in d.items():
    if p in dono:
        continue
    alvo = SUB.get(u, {}).get(b)
    if alvo and (alvo, u) in idx and abs(p - lista[idx[(alvo, u)]]['ref']) <= DIST_MAX:
        por(p, idx[(alvo, u)], 'sub')
# (c) extras da sonda densa
for (nome, uf), ps in EXTRA.items():
    for p in ps:
        i = idx[(nome, uf)]
        dono[p] = i; motivo[p] = 'extra'
for (nome, uf), ps in REMOVER.items():
    for p in ps:
        if dono.get(p) == idx[(nome, uf)]:
            del dono[p]; del motivo[p]

# -------- compacta
saida, semfaixa = [], []
for i, L in enumerate(lista):
    ps = sorted(p for p, x in dono.items() if x == i)
    if not ps:
        # entra sem faixa: o casamento por NOME ainda pode pega-lo se o ViaCEP
        # devolver esse nome num CEP fora da area varrida
        semfaixa.append(L['b'] + '/' + L['uf'])
        saida.append({'b': L['b'], 'uf': L['uf'], 'r': L['r'], 'm2': L['m2'], 'fx': []})
        continue
    fx, ini, ant = [], ps[0], ps[0]
    for p in ps[1:]:
        if p == ant + 1:
            ant = p
        else:
            fx.append([ini, ant]); ini = ant = p
    fx.append([ini, ant])
    saida.append({'b': L['b'], 'uf': L['uf'], 'r': L['r'], 'm2': L['m2'], 'fx': fx})
json.dump(saida, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))

print('=== FAIXAS DE CEP POR BAIRRO DO RANKING')
print('prefixos varridos nas 2 capitais: %d | atribuidos: %d | bairros com faixa: %d/%d'
      % (len(d), len(dono), len(saida), len(lista)))
print('sem faixa (de proposito): %s' % ', '.join(semfaixa))
c = collections.Counter(motivo.values())
print('origem dos prefixos: %s' % dict(c))
print('\n%-26s %-3s %-4s %-5s %s' % ('bairro', 'uf', 'rank', 'nº', 'faixas de CEP'))
for e in sorted(saida, key=lambda x: (x['uf'], x['r'])):
    n = sum(b - a + 1 for a, b in e['fx'])
    print('%-26s %-3s %-4d %-5d %s'
          % (e['b'], e['uf'], e['r'], n,
             ', '.join('%05d-%05d' % (a, b) if a != b else '%05d' % a for a, b in e['fx'])))
tam = len(json.dumps(saida, ensure_ascii=False, separators=(',', ':')))
print('\ntamanho da tabela: %.1f KB' % (tam / 1024))
