-- 课堂统一逐题倒计时：0 表示不限时，其他值为每道题的秒数。
alter table public.sessions
  add column if not exists time_limit_seconds integer not null default 30,
  add column if not exists question_started_at timestamptz;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'sessions_time_limit_seconds_check'
  ) then
    alter table public.sessions
      add constraint sessions_time_limit_seconds_check
      check (time_limit_seconds = 0 or time_limit_seconds between 10 and 600);
  end if;
end $$;

