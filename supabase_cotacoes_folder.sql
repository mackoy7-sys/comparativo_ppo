-- ============================================================================
--  COTADOR HapOn — guarda o folder EXATO por 30 dias
--
--  Roda depois de supabase_cotacoes.sql, no mesmo projeto (xqmhzvkzjkkzwqhbyneo).
--
--  Por que: ao rever uma cotação antiga, remontar o folder com a tabela de hoje
--  entregaria ao cliente um valor diferente do combinado. Com o folder gravado,
--  os 30 primeiros dias mostram exatamente o que foi enviado; depois disso o
--  snapshot é apagado e o Cotador volta a remontar, avisando se o preço mudou.
--
--  Tamanho: ~36 KB por cotação (o HTML vai SEM os dois logos, que sozinhos
--  respondiam por 56 dos 92 KB e já estão dentro do index.html). O Postgres
--  ainda comprime a coluna sozinho. Em regime, com 30 dias de retenção:
--  1.000 cotações/mês ≈ 11 MB · 10.000/mês ≈ 110 MB · 30.000/mês ≈ 330 MB.
--
--  Idempotente: pode rodar de novo sem quebrar.
-- ============================================================================

alter table cotacoes add column if not exists folder_html text;
alter table cotacoes add column if not exists folder_cls  text;        -- a classe do #folder muda o estilo (ppo/hmo)
alter table cotacoes add column if not exists folder_em   timestamptz; -- quando o snapshot foi tirado

comment on column cotacoes.folder_html is
  'Folder exato entregue ao cliente, sem os logos (reinjetados na exibição). Apagado após 30 dias por limpa_folders_vencidos().';

-- índice parcial: a limpeza só procura quem ainda tem snapshot
create index if not exists cotacoes_folder_em_idx on cotacoes (folder_em) where folder_html is not null;

-- ============================================================================
--  Limpeza dos 30 dias. O REGISTRO continua (buscável por CPF durante 2 anos);
--  o que expira é só a fotografia do PDF.
-- ============================================================================
create or replace function limpa_folders_vencidos() returns integer
language sql security definer set search_path = public as $$
  with x as (
    update cotacoes set folder_html = null, folder_cls = null, folder_em = null
    where folder_html is not null and folder_em < now() - interval '30 days'
    returning 1)
  select count(*)::int from x;
$$;

-- mesma proteção da outra função: ninguém dispara a limpeza por RPC
revoke execute on function limpa_folders_vencidos() from public, anon, authenticated;

-- ============================================================================
--  Agendamento. Se o pg_cron estiver disponível no projeto, deixa rodando
--  sozinho todo dia às 4h. Se não estiver, não quebra — basta chamar a função
--  manualmente de tempos em tempos.
-- ============================================================================
do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.unschedule('limpa_folders_vencidos')
      where exists (select 1 from cron.job where jobname = 'limpa_folders_vencidos');
    perform cron.schedule('limpa_folders_vencidos', '0 4 * * *',
                          'select limpa_folders_vencidos()');
    raise notice 'limpeza agendada no pg_cron: todo dia as 4h';
  else
    raise notice 'pg_cron nao instalado — chamar limpa_folders_vencidos() manualmente';
  end if;
exception when others then
  raise notice 'nao consegui agendar (%). A funcao existe e pode ser chamada a mao.', sqlerrm;
end $$;
