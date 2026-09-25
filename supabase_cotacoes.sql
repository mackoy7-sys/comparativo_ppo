-- ============================================================================
--  COTADOR HapOn — histórico de cotações
--  Roda no MESMO Supabase do HapOn Learn (xqmhzvkzjkkzwqhbyneo), porque é lá
--  que já existe a identidade do vendedor (tabela `perfis`, papéis e equipes).
--
--  Segue o padrão que já está em supabase_schema.sql do Learn: funções
--  meu_papel() / minha_equipe() e a mesma regra de visibilidade da tabela
--  `progresso` — o dono sempre vê; gerente e diretor veem tudo; supervisor vê
--  a própria equipe.
--
--  Idempotente: pode rodar de novo sem quebrar.
-- ============================================================================

create table if not exists cotacoes (
  id           uuid primary key default gen_random_uuid(),
  vendedor_id  uuid not null references perfis(id) on delete cascade,
  criado_em    timestamptz not null default now(),

  -- identificação do cliente ---------------------------------------------
  -- O documento NÃO é gravado por extenso: guardamos o hash (para buscar) e
  -- os 4 últimos dígitos (para o vendedor reconhecer a linha na lista).
  cliente_nome text,
  cliente_fone text,              -- só dígitos, para a busca casar sempre
  doc_tipo     text check (doc_tipo in ('CPF', 'CNPJ')),
  doc_hash     text,              -- sha256(salt + dígitos)
  doc_fim      text,              -- 4 últimos dígitos

  -- resumo, para a lista não precisar abrir o payload ---------------------
  praca        text,
  total        numeric(12,2),
  vidas        integer,
  resumo       text,

  -- estado completo da cotação, para reabrir exatamente como estava -------
  payload      jsonb not null
);

create index if not exists cotacoes_vendedor_idx on cotacoes (vendedor_id, criado_em desc);
create index if not exists cotacoes_doc_idx      on cotacoes (doc_hash);
create index if not exists cotacoes_fone_idx     on cotacoes (cliente_fone);
create index if not exists cotacoes_nome_idx     on cotacoes (lower(cliente_nome));

alter table cotacoes enable row level security;

drop policy if exists cot_self_all  on cotacoes;
drop policy if exists cot_self_ins  on cotacoes;
drop policy if exists cot_gestor_sel on cotacoes;

-- o vendedor manda nas cotações dele (ler, corrigir, apagar)
create policy cot_self_all on cotacoes for all
  using (vendedor_id = auth.uid())
  with check (vendedor_id = auth.uid());

-- gestão enxerga, mas não mexe: mesma regra do `progresso`
create policy cot_gestor_sel on cotacoes for select using (
  meu_papel() in ('gerente', 'diretor')
  or (meu_papel() = 'supervisor'
      and (select equipe_id from perfis where id = cotacoes.vendedor_id) = minha_equipe()));

-- ============================================================================
--  Retenção: cotação é material de trabalho, não arquivo permanente. Apagar o
--  que passou de 2 anos evita acumular dado pessoal sem necessidade. Rodar por
--  cron (pg_cron) ou manualmente.
-- ============================================================================
create or replace function limpa_cotacoes_antigas() returns integer
language sql security definer set search_path = public as $$
  with x as (delete from cotacoes where criado_em < now() - interval '2 years' returning 1)
  select count(*)::int from x;
$$;

-- só o administrador roda a limpeza (sem isso, qualquer usuário logado poderia chamar via RPC)
revoke execute on function limpa_cotacoes_antigas() from public, anon, authenticated;
