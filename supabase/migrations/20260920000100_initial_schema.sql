-- 英语数学课堂答题与练习系统首版数据库结构
-- 说明：业务写入由 FastAPI 使用 Supabase service_role 完成；
-- 浏览器端仅通过受保护接口访问业务数据。

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table if not exists public.schools (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.teacher_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default 'admin',
  school_id uuid not null references public.schools(id),
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.grades (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id),
  code text not null,
  name text not null,
  sort_order smallint not null,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint grades_school_code_unique unique (school_id, code),
  constraint grades_sort_order_positive check (sort_order > 0)
);

create table if not exists public.classes (
  id uuid primary key default gen_random_uuid(),
  grade_id uuid not null references public.grades(id),
  code text not null,
  name text not null,
  expected_student_count smallint not null default 30,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint classes_grade_code_unique unique (grade_id, code),
  constraint classes_expected_count_nonnegative check (expected_student_count >= 0)
);

create table if not exists public.question_sets (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id),
  created_by uuid not null references auth.users(id),
  name text not null,
  source_filename text,
  status text not null default 'draft',
  version integer not null default 1,
  source_question_set_id uuid references public.question_sets(id) on delete restrict,
  archived_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint question_sets_status_check check (status in ('draft', 'published', 'archived')),
  constraint question_sets_version_positive check (version > 0),
  constraint question_sets_name_not_blank check (length(btrim(name)) > 0)
);

create table if not exists public.questions (
  id uuid primary key default gen_random_uuid(),
  question_set_id uuid not null references public.question_sets(id) on delete restrict,
  sort_order integer not null,
  question_text text,
  question_image_url text,
  explanation text,
  question_type text not null default 'single_choice',
  content_type text not null default 'text',
  language text not null default 'en',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint questions_set_sort_unique unique (question_set_id, sort_order),
  constraint questions_sort_positive check (sort_order > 0),
  constraint questions_type_check check (question_type in ('single_choice', 'multiple_choice', 'fill_blank', 'subjective')),
  constraint questions_content_type_check check (content_type in ('text', 'image')),
  constraint questions_language_not_blank check (length(btrim(language)) > 0),
  constraint questions_text_or_image check (coalesce(length(btrim(question_text)), 0) > 0 or question_image_url is not null)
);

create table if not exists public.question_options (
  id uuid primary key default gen_random_uuid(),
  question_id uuid not null references public.questions(id) on delete cascade,
  option_key char(1) not null,
  option_text text,
  option_image_url text,
  content_type text not null default 'text',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint question_options_key_unique unique (question_id, option_key),
  constraint question_options_key_check check (option_key in ('A', 'B', 'C', 'D')),
  constraint question_options_content_type_check check (content_type in ('text', 'image')),
  constraint question_options_text_or_image check (coalesce(length(btrim(option_text)), 0) > 0 or option_image_url is not null)
);

alter table public.questions
  add column if not exists correct_option_id uuid;

alter table public.questions
  add constraint questions_correct_option_fk
  foreign key (correct_option_id)
  references public.question_options(id)
  on delete no action
  deferrable initially deferred;

create table if not exists public.sessions (
  id uuid primary key default gen_random_uuid(),
  created_by uuid not null references auth.users(id),
  question_set_id uuid not null references public.question_sets(id) on delete restrict,
  class_id uuid not null references public.classes(id) on delete restrict,
  session_type text not null,
  access_token text not null unique,
  status text not null default 'draft',
  current_question_id uuid references public.questions(id) on delete restrict,
  current_question_status text not null default 'pending',
  starts_at timestamptz,
  expires_at timestamptz not null default (timezone('utc', now()) + interval '7 days'),
  closed_at timestamptz,
  archived_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint sessions_type_check check (session_type in ('classroom', 'homework')),
  constraint sessions_status_check check (status in ('draft', 'waiting', 'active', 'closed', 'archived')),
  constraint sessions_question_status_check check (current_question_status in ('pending', 'open', 'locked')),
  constraint sessions_access_token_not_blank check (length(btrim(access_token)) >= 16),
  constraint sessions_expiry_after_creation check (expires_at > created_at)
);

create table if not exists public.anonymous_devices (
  id uuid primary key default gen_random_uuid(),
  browser_key_hash text not null unique,
  first_seen_at timestamptz not null default timezone('utc', now()),
  last_seen_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.session_participants (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.sessions(id) on delete restrict,
  anonymous_device_id uuid not null references public.anonymous_devices(id) on delete restrict,
  joined_at timestamptz not null default timezone('utc', now()),
  last_seen_at timestamptz not null default timezone('utc', now()),
  constraint session_participants_unique unique (session_id, anonymous_device_id)
);

create table if not exists public.practice_attempts (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.sessions(id) on delete restrict,
  anonymous_device_id uuid not null references public.anonymous_devices(id) on delete restrict,
  status text not null default 'draft',
  started_at timestamptz not null default timezone('utc', now()),
  completed_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint practice_attempts_status_check check (status in ('draft', 'completed')),
  constraint practice_attempts_completion_check check (
    (status = 'draft' and completed_at is null) or
    (status = 'completed' and completed_at is not null)
  )
);

create table if not exists public.answers (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.sessions(id) on delete restrict,
  question_id uuid not null references public.questions(id) on delete restrict,
  selected_option_id uuid not null references public.question_options(id) on delete restrict,
  anonymous_device_id uuid references public.anonymous_devices(id) on delete restrict,
  practice_attempt_id uuid references public.practice_attempts(id) on delete restrict,
  is_correct boolean not null,
  answered_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint answers_context_check check (
    (practice_attempt_id is null and anonymous_device_id is not null) or
    (practice_attempt_id is not null and anonymous_device_id is null)
  )
);

create unique index if not exists answers_classroom_unique
  on public.answers (session_id, anonymous_device_id, question_id)
  where practice_attempt_id is null;

create unique index if not exists answers_practice_unique
  on public.answers (practice_attempt_id, question_id)
  where practice_attempt_id is not null;

create unique index if not exists practice_attempts_one_draft
  on public.practice_attempts (session_id, anonymous_device_id)
  where status = 'draft';

create index if not exists classes_grade_id_idx on public.classes (grade_id);
create index if not exists questions_question_set_id_idx on public.questions (question_set_id, sort_order);
create index if not exists question_options_question_id_idx on public.question_options (question_id, option_key);
create index if not exists sessions_class_id_idx on public.sessions (class_id, created_at desc);
create index if not exists sessions_question_set_id_idx on public.sessions (question_set_id);
create index if not exists session_participants_session_id_idx on public.session_participants (session_id, joined_at);
create index if not exists answers_session_id_idx on public.answers (session_id, question_id);
create index if not exists practice_attempts_session_device_idx on public.practice_attempts (session_id, anonymous_device_id, created_at desc);

create or replace function public.validate_answer_context()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  target_session_type text;
  target_attempt_session uuid;
  target_question_set uuid;
  target_option_question uuid;
  target_correct_option uuid;
  target_session_status text;
  target_current_question uuid;
  target_current_question_status text;
  target_expires_at timestamptz;
begin
  select session_type, question_set_id, status, current_question_id,
         current_question_status, expires_at
    into target_session_type, target_question_set, target_session_status,
         target_current_question, target_current_question_status, target_expires_at
    from public.sessions
   where id = new.session_id;

  if target_session_type is null then
    raise exception 'answer session does not exist';
  end if;

  if target_session_status <> 'active' or target_expires_at <= timezone('utc', now()) then
    raise exception 'answer session is not active';
  end if;

  if not exists (
    select 1 from public.questions q
     where q.id = new.question_id
       and q.question_set_id = target_question_set
  ) then
    raise exception 'answer question does not belong to session question set';
  end if;

  select question_id
    into target_option_question
    from public.question_options
   where id = new.selected_option_id;

  if target_option_question is null or target_option_question <> new.question_id then
    raise exception 'selected option does not belong to answer question';
  end if;

  select correct_option_id
    into target_correct_option
    from public.questions
   where id = new.question_id;

  if target_correct_option is null then
    raise exception 'answer question has no correct option configured';
  end if;

  new.is_correct := new.selected_option_id = target_correct_option;

  if target_session_type = 'classroom' and new.practice_attempt_id is not null then
    raise exception 'classroom answer cannot reference practice attempt';
  end if;

  if target_session_type = 'classroom' and (
    target_current_question is distinct from new.question_id or
    target_current_question_status <> 'open'
  ) then
    raise exception 'classroom question is not open for answering';
  end if;

  if target_session_type = 'classroom' and not exists (
    select 1 from public.session_participants sp
     where sp.session_id = new.session_id
       and sp.anonymous_device_id = new.anonymous_device_id
  ) then
    raise exception 'anonymous device has not joined this session';
  end if;

  if target_session_type = 'homework' and new.practice_attempt_id is null then
    raise exception 'homework answer must reference practice attempt';
  end if;

  if new.practice_attempt_id is not null then
    select session_id
      into target_attempt_session
      from public.practice_attempts
     where id = new.practice_attempt_id;

    if target_attempt_session is null or target_attempt_session <> new.session_id then
      raise exception 'practice attempt does not belong to answer session';
    end if;
  end if;

  return new;
end;
$$;

create or replace function public.validate_practice_attempt()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  target_type text;
  target_status text;
  target_expires_at timestamptz;
begin
  select session_type, status, expires_at
    into target_type, target_status, target_expires_at
    from public.sessions
   where id = new.session_id;

  if target_type <> 'homework' then
    raise exception 'practice attempt requires a homework session';
  end if;

  if target_status <> 'active' or target_expires_at <= timezone('utc', now()) then
    raise exception 'homework session is not active';
  end if;

  if not exists (
    select 1 from public.session_participants sp
     where sp.session_id = new.session_id
       and sp.anonymous_device_id = new.anonymous_device_id
  ) then
    raise exception 'anonymous device has not joined this session';
  end if;

  return new;
end;
$$;

create or replace function public.prevent_published_question_changes()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  parent_status text;
  target_set_id uuid;
begin
  if tg_table_name = 'questions' then
    if tg_op = 'DELETE' then
      target_set_id := old.question_set_id;
    else
      target_set_id := new.question_set_id;
    end if;
  else
    select question_set_id
      into target_set_id
      from public.questions
     where id = case when tg_op = 'DELETE' then old.question_id else new.question_id end;
  end if;

  select status into parent_status
    from public.question_sets
   where id = target_set_id;

  if parent_status in ('published', 'archived') then
    raise exception 'published or archived question set content is immutable';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;

  return new;
end;
$$;

create or replace function public.validate_question_set_publish()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.status = 'published' and old.status <> 'published' then
    if not exists (select 1 from public.questions where question_set_id = new.id) then
      raise exception 'question set must contain at least one question before publishing';
    end if;

    if exists (
      select 1
        from public.questions q
       where q.question_set_id = new.id
         and (
           q.correct_option_id is null or
           not exists (
             select 1 from public.question_options correct_qo
              where correct_qo.id = q.correct_option_id
                and correct_qo.question_id = q.id
           ) or
           (select count(*) from public.question_options qo where qo.question_id = q.id) <> 4
         )
    ) then
      raise exception 'every published question must contain four options and one correct option';
    end if;
  end if;

  return new;
end;
$$;

create or replace function public.validate_attempt_completion()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  required_count integer;
  answered_count integer;
begin
  if new.status = 'completed' and old.status <> 'completed' then
    select count(*)
      into required_count
      from public.sessions s
      join public.questions q on q.question_set_id = s.question_set_id
     where s.id = new.session_id;

    select count(*)
      into answered_count
      from public.answers
     where practice_attempt_id = new.id;

    if answered_count <> required_count then
      raise exception 'all questions must be answered before completing an attempt';
    end if;

    new.completed_at := coalesce(new.completed_at, timezone('utc', now()));
  end if;

  return new;
end;
$$;

drop trigger if exists answers_validate_context on public.answers;
create trigger answers_validate_context
before insert or update on public.answers
for each row execute function public.validate_answer_context();

create trigger practice_attempts_validate_context
before insert or update on public.practice_attempts
for each row execute function public.validate_practice_attempt();

create trigger questions_prevent_published_changes
before insert or update or delete on public.questions
for each row execute function public.prevent_published_question_changes();

create trigger question_options_prevent_published_changes
before insert or update or delete on public.question_options
for each row execute function public.prevent_published_question_changes();

create trigger question_sets_validate_publish
before update on public.question_sets
for each row execute function public.validate_question_set_publish();

create trigger practice_attempts_validate_completion
before update on public.practice_attempts
for each row execute function public.validate_attempt_completion();

create trigger schools_set_updated_at before update on public.schools
for each row execute function public.set_updated_at();
create trigger teacher_profiles_set_updated_at before update on public.teacher_profiles
for each row execute function public.set_updated_at();
create trigger grades_set_updated_at before update on public.grades
for each row execute function public.set_updated_at();
create trigger classes_set_updated_at before update on public.classes
for each row execute function public.set_updated_at();
create trigger question_sets_set_updated_at before update on public.question_sets
for each row execute function public.set_updated_at();
create trigger questions_set_updated_at before update on public.questions
for each row execute function public.set_updated_at();
create trigger question_options_set_updated_at before update on public.question_options
for each row execute function public.set_updated_at();
create trigger sessions_set_updated_at before update on public.sessions
for each row execute function public.set_updated_at();
create trigger practice_attempts_set_updated_at before update on public.practice_attempts
for each row execute function public.set_updated_at();
create trigger answers_set_updated_at before update on public.answers
for each row execute function public.set_updated_at();

create or replace function public.is_active_teacher()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
      from public.teacher_profiles
     where id = (select auth.uid())
       and is_active = true
  );
$$;

create or replace function public.current_teacher_school_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select school_id
    from public.teacher_profiles
   where id = (select auth.uid())
     and is_active = true
;
$$;

alter table public.schools enable row level security;
alter table public.teacher_profiles enable row level security;
alter table public.grades enable row level security;
alter table public.classes enable row level security;
alter table public.question_sets enable row level security;
alter table public.questions enable row level security;
alter table public.question_options enable row level security;
alter table public.sessions enable row level security;
alter table public.anonymous_devices enable row level security;
alter table public.session_participants enable row level security;
alter table public.practice_attempts enable row level security;
alter table public.answers enable row level security;

revoke all on table public.schools, public.teacher_profiles, public.grades,
  public.classes, public.question_sets, public.questions, public.question_options,
  public.sessions, public.anonymous_devices, public.session_participants,
  public.practice_attempts, public.answers
  from anon, authenticated;

grant select on table public.schools, public.teacher_profiles, public.grades,
  public.classes, public.question_sets, public.questions, public.question_options,
  public.sessions, public.session_participants, public.answers to authenticated;

create policy teachers_read_schools on public.schools
  for select to authenticated using (id = (select public.current_teacher_school_id()));
create policy teachers_read_profiles on public.teacher_profiles
  for select to authenticated using (id = (select auth.uid()));
create policy teachers_read_grades on public.grades
  for select to authenticated using (school_id = (select public.current_teacher_school_id()));
create policy teachers_read_classes on public.classes
  for select to authenticated using (
    exists (
      select 1 from public.grades g
       where g.id = classes.grade_id
         and g.school_id = (select public.current_teacher_school_id())
    )
  );
create policy teachers_read_question_sets on public.question_sets
  for select to authenticated using (school_id = (select public.current_teacher_school_id()));
create policy teachers_read_questions on public.questions
  for select to authenticated using (
    exists (
      select 1 from public.question_sets qs
       where qs.id = questions.question_set_id
         and qs.school_id = (select public.current_teacher_school_id())
    )
  );
create policy teachers_read_question_options on public.question_options
  for select to authenticated using (
    exists (
      select 1
        from public.questions q
        join public.question_sets qs on qs.id = q.question_set_id
       where q.id = question_options.question_id
         and qs.school_id = (select public.current_teacher_school_id())
    )
  );
create policy teachers_read_sessions on public.sessions
  for select to authenticated using (
    exists (
      select 1 from public.question_sets qs
       where qs.id = sessions.question_set_id
         and qs.school_id = (select public.current_teacher_school_id())
    )
  );
create policy teachers_read_session_participants on public.session_participants
  for select to authenticated using (
    exists (
      select 1
        from public.sessions s
        join public.question_sets qs on qs.id = s.question_set_id
       where s.id = session_participants.session_id
         and qs.school_id = (select public.current_teacher_school_id())
    )
  );
create policy teachers_read_answers on public.answers
  for select to authenticated using (
    exists (
      select 1
        from public.sessions s
        join public.question_sets qs on qs.id = s.question_set_id
       where s.id = answers.session_id
         and qs.school_id = (select public.current_teacher_school_id())
    )
  );

alter publication supabase_realtime add table public.answers;
alter publication supabase_realtime add table public.session_participants;

comment on table public.question_sets is 'Excel导入形成的题目集合；发布后由应用层复制修改，不原地修改。';
comment on table public.answers is '基础答题记录；课堂修改答案使用更新，课后每个练习轮次独立记录。';
comment on column public.questions.question_image_url is '未来图片题目字段，首版为空。';
comment on column public.question_options.option_image_url is '未来图片选项字段，首版为空。';
