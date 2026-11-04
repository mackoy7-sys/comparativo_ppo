-- ============================================================================
--  COTADOR HapOn — agenda as duas limpezas do histórico (pg_cron)
--
--  Roda depois de supabase_cotacoes.sql e supabase_cotacoes_folder.sql, no
--  mesmo projeto (xqmhzvkzjkkzwqhbyneo). Aplicado em 24/09/2026.
--
--  pg_cron trabalha em UTC: 07:00 UTC = 04:00 em Brasília.
--  As tarefas rodam como `postgres`, dono das duas funções — por isso o
--  revoke para anon/authenticated não as impede.
--
--  Idempotente: pode rodar de novo sem quebrar.
-- ============================================================================

create extension if not exists pg_cron with schema pg_catalog;

select cron.unschedule(jobname) from cron.job
 where jobname in ('limpa_folders_vencidos', 'limpa_cotacoes_antigas');

-- folder original: some depois de 30 dias (o registro continua)
select cron.schedule('limpa_folders_vencidos', '0 7 * * *',  'select public.limpa_folders_vencidos()');
-- cotação inteira: some depois de 2 anos
select cron.schedule('limpa_cotacoes_antigas', '15 7 * * *', 'select public.limpa_cotacoes_antigas()');

-- conferir:   select jobname, schedule, active from cron.job;
-- histórico:  select * from cron.job_run_details order by start_time desc limit 10;
