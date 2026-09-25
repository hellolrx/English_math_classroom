-- 学生工作台：按年级浏览题目集合、匿名刷题与记忆复习
alter table public.question_sets
  add column if not exists grade_id uuid references public.grades(id);

-- 舊有題目集合沒有年級欄位時，先歸入第一個年級，之後老師可在重新匯入時選擇正確年級。
update public.question_sets
set grade_id = (select id from public.grades order by sort_order asc limit 1)
where grade_id is null;

create index if not exists question_sets_grade_status_idx
  on public.question_sets (grade_id, status, created_at desc);

create table if not exists public.student_practice_attempts (
  id uuid primary key default gen_random_uuid(),
  question_set_id uuid not null references public.question_sets(id) on delete restrict,
  anonymous_device_id uuid not null references public.anonymous_devices(id) on delete restrict,
  started_at timestamptz not null default timezone('utc', now()),
  completed_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.student_practice_answers (
  id uuid primary key default gen_random_uuid(),
  attempt_id uuid not null references public.student_practice_attempts(id) on delete cascade,
  question_id uuid not null references public.questions(id) on delete restrict,
  selected_option_id uuid not null references public.question_options(id) on delete restrict,
  is_correct boolean not null default false,
  submitted_at timestamptz not null default timezone('utc', now()),
  constraint student_practice_answers_unique unique (attempt_id, question_id)
);

create table if not exists public.review_progress (
  id uuid primary key default gen_random_uuid(),
  anonymous_device_id uuid not null references public.anonymous_devices(id) on delete cascade,
  question_id uuid not null references public.questions(id) on delete cascade,
  interval_level smallint not null default 0,
  due_at timestamptz not null default timezone('utc', now()),
  last_rating text not null default 'forgot',
  review_count integer not null default 0,
  last_selected_option_id uuid references public.question_options(id) on delete set null,
  last_is_correct boolean,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint review_progress_unique unique (anonymous_device_id, question_id),
  constraint review_progress_level_check check (interval_level between 0 and 6),
  constraint review_progress_rating_check check (last_rating in ('forgot', 'fuzzy', 'clear'))
);

create index if not exists review_progress_due_idx
  on public.review_progress (anonymous_device_id, due_at);

alter table public.student_practice_attempts enable row level security;
alter table public.student_practice_answers enable row level security;
alter table public.review_progress enable row level security;

drop trigger if exists student_practice_attempts_set_updated_at on public.student_practice_attempts;
create trigger student_practice_attempts_set_updated_at
before update on public.student_practice_attempts
for each row execute function public.set_updated_at();

drop trigger if exists review_progress_set_updated_at on public.review_progress;
create trigger review_progress_set_updated_at
before update on public.review_progress
for each row execute function public.set_updated_at();
