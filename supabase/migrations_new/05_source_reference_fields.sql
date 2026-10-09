-- 为题目来源补充原始标识、试卷部分和可检索的原题号。
-- 仅在 01_rebuild.sql 已执行后运行一次。
alter table public.questions
  add column if not exists source_reference text,
  add column if not exists source_paper text;

create index if not exists questions_source_year_idx on public.questions(source_year);
create index if not exists questions_source_question_number_idx on public.questions(source_question_number);
create index if not exists questions_source_reference_idx on public.questions(source_reference);

notify pgrst, 'reload schema';
