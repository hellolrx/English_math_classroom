-- 第二步：业务结构全量重建。仅用于项目 izbxkrxpihubsabijygr 的本次重构。
-- 在 Supabase SQL Editor 整份执行，包括 BEGIN 和 COMMIT，不选中片段运行。
-- 会删除下面明确列出的旧业务数据；保留 auth、storage、扩展和迁移历史。
-- 不兼容目前旧业务代码：执行后旧应用需暂停使用，待新代码配套部署。
-- 一次性脚本：成功后禁止重跑。失败时同一事务回滚，不留下半建结构。
begin;
set local lock_timeout = '10s';
set local statement_timeout = '120s';
set local search_path = public, extensions, pg_catalog;

do $$
begin
  if to_regclass('public.app_schema_state') is not null then
    raise exception '本版业务结构已存在，禁止重复执行重建。请先运行 02_verify.sql。';
  end if;
  if to_regclass('auth.users') is null then
    raise exception '缺少 Supabase auth.users，停止重建。';
  end if;
end $$;

-- 保存原老师身份；若原老师表不存在，不猜测哪些 Auth 用户是老师。
create temporary table rebuild_teachers (
  id uuid primary key, display_name text not null, is_active boolean not null
) on commit drop;
do $$
begin
  if to_regclass('public.teacher_profiles') is not null then
    execute 'insert into rebuild_teachers
      select p.id, coalesce(p.display_name, ''老师''), coalesce(p.is_active, true)
      from public.teacher_profiles p join auth.users u on u.id = p.id';
  end if;
end $$;

-- 只清理已知旧版/回退版业务对象。额外外键或视图依赖这些表时停止，避免 CASCADE 波及未知对象。
-- 所有已知表一起 DROP，彼此依赖不会要求 CASCADE；未知依赖会报错并回滚。
drop table if exists
  public.answers, public.practice_attempts, public.session_participants,
  public.anonymous_devices, public.student_practice_answers,
  public.student_practice_attempts, public.review_progress,
  public.student_answers, public.session_students, public.practice_progress,
  public.student_word_progress, public.vocabulary_words,
  public.classroom_answers, public.classroom_participants,
  public.classroom_session_questions, public.classroom_sessions,
  public.practice_answers, public.practice_rounds, public.practice_questions,
  public.practices, public.word_progress, public.words, public.word_batches,
  public.student_sessions, public.import_jobs,
  public.sessions, public.question_options, public.questions,
  public.question_sets, public.math_batches, public.topics,
  public.students, public.teacher_profiles, public.classes,
  public.grades, public.schools;

-- 清理旧业务函数（按名称白名单，只限 public，保留其他函数与系统 schema）。
do $$
declare f record;
begin
  for f in
    select p.oid::regprocedure as signature from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname = any(array[
      'set_updated_at', 'is_active_teacher', 'current_teacher_school_id',
      'validate_answer_context', 'validate_practice_attempt',
      'validate_attempt_completion', 'prevent_published_question_changes',
      'validate_question_set_publish', 'validate_student_answer',
      'validate_session_source', 'update_practice_progress'
    ])
  loop
    execute format('drop function %s', f.signature);
  end loop;
end $$;

create table public.app_schema_state (
  version text primary key, installed_at timestamptz not null default now()
);
create table public.schools (
  id uuid primary key default gen_random_uuid(), name text not null check (btrim(name) <> ''),
  is_active boolean not null default true, created_at timestamptz not null default now()
);
create table public.teacher_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  school_id uuid not null references public.schools(id),
  display_name text not null, is_active boolean not null default true,
  created_at timestamptz not null default now(), unique (id, school_id)
);
create table public.grades (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id),
  code text not null check (code in ('S1','S2','S3','S4','S5','S6')),
  name text not null, sort_order smallint not null check (sort_order between 1 and 6),
  is_active boolean not null default true,
  unique (school_id, code), unique (id, school_id)
);
create table public.classes (
  id uuid primary key default gen_random_uuid(),
  grade_id uuid not null, school_id uuid not null,
  code text not null check (btrim(code) <> ''), name text not null,
  expected_student_count integer not null default 30 check (expected_student_count >= 0),
  is_active boolean not null default true,
  foreign key (grade_id, school_id) references public.grades(id, school_id),
  unique (grade_id, code), unique (id, grade_id, school_id)
);
create table public.students (
  id uuid primary key default gen_random_uuid(), school_id uuid not null,
  grade_id uuid not null, class_id uuid not null,
  student_number text not null check (btrim(student_number) <> ''),
  name text not null check (btrim(name) <> ''),
  -- bcrypt 哈希由部署脚本生成；应用登录需采用同一算法验证，绝不能直接比较明文。
  password_hash text not null check (password_hash ~ '^\$2[aby]\$[0-9]{2}\$.{53}$'),
  auth_version integer not null default 1 check (auth_version > 0),
  is_active boolean not null default true,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  foreign key (class_id, grade_id, school_id) references public.classes(id, grade_id, school_id),
  unique (school_id, student_number)
);
create table public.student_sessions (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.students(id) on delete cascade,
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  auth_version integer not null check (auth_version > 0),
  expires_at timestamptz not null, revoked_at timestamptz,
  created_at timestamptz not null default now(), check (expires_at > created_at)
);
create table public.topics (
  id uuid primary key default gen_random_uuid(), school_id uuid not null,
  grade_id uuid not null, code text not null check (btrim(code) <> ''),
  name text not null check (btrim(name) <> ''), sort_order integer not null check (sort_order >= 0),
  is_active boolean not null default true,
  foreign key (grade_id, school_id) references public.grades(id, school_id),
  unique (school_id, code)
);
create table public.import_jobs (
  id uuid primary key default gen_random_uuid(),
  created_by uuid not null references public.teacher_profiles(id),
  kind text not null check (kind in ('math','words')),
  topic_id uuid references public.topics(id), grade_id uuid references public.grades(id),
  filename text not null, status text not null default 'preview'
    check (status in ('preview','failed','imported','cancelled')),
  errors jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(), completed_at timestamptz,
  check ((kind = 'math' and topic_id is not null and grade_id is null) or
         (kind = 'words' and grade_id is not null and topic_id is null))
);
create table public.math_batches (
  id uuid primary key default gen_random_uuid(), topic_id uuid not null references public.topics(id),
  created_by uuid not null references public.teacher_profiles(id),
  import_job_id uuid unique references public.import_jobs(id),
  status text not null default 'draft' check (status in ('draft','published','archived')),
  created_at timestamptz not null default now(), published_at timestamptz,
  unique (id, topic_id)
);
create unique index math_batches_one_published on public.math_batches(topic_id) where status = 'published';
create table public.questions (
  id uuid primary key default gen_random_uuid(), batch_id uuid not null references public.math_batches(id),
  sort_order integer not null check (sort_order > 0),
  question_type text not null check (question_type in ('single_choice','text_input')),
  image_bucket text not null default 'question-images-v2',
  image_path text not null check (btrim(image_path) <> ''),
  image_bytes integer not null check (image_bytes between 1 and 1048576),
  correct_option text,
  source_reference text, source_year text, source_paper text, question_year text, source_question_number text,
  created_at timestamptz not null default now(),
  unique (batch_id, sort_order), unique (id, batch_id),
  check ((question_type = 'single_choice' and correct_option is not null and correct_option in ('A','B','C','D'))
     or (question_type = 'text_input' and correct_option is null))
);
create table public.practices (
  id uuid primary key default gen_random_uuid(), batch_id uuid not null references public.math_batches(id),
  created_by uuid not null references public.teacher_profiles(id),
  access_code text not null unique check (access_code ~ '^[A-Z0-9]{6,16}$'),
  status text not null default 'active' check (status in ('active','closed','invalidated')),
  created_at timestamptz not null default now(), unique (id, batch_id)
);
create table public.practice_questions (
  practice_id uuid not null, batch_id uuid not null, question_id uuid not null,
  sort_order integer not null check (sort_order > 0),
  primary key (practice_id, question_id), unique (practice_id, sort_order),
  foreign key (practice_id, batch_id) references public.practices(id, batch_id),
  foreign key (question_id, batch_id) references public.questions(id, batch_id)
);
create table public.practice_rounds (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.students(id),
  batch_id uuid not null references public.math_batches(id), practice_id uuid,
  status text not null default 'in_progress' check (status in ('in_progress','completed','interrupted')),
  started_at timestamptz not null default now(), completed_at timestamptz,
  foreign key (practice_id, batch_id) references public.practices(id, batch_id),
  check ((status = 'completed' and completed_at is not null) or
         (status <> 'completed' and completed_at is null)),
  unique (id, batch_id)
);
create unique index practice_rounds_one_open on public.practice_rounds
  (student_id, batch_id, (coalesce(practice_id, '00000000-0000-0000-0000-000000000000'::uuid)))
  where status = 'in_progress';
create table public.practice_answers (
  round_id uuid not null, batch_id uuid not null, question_id uuid not null,
  selected_option text check (selected_option in ('A','B','C','D')), text_answer text,
  state text not null default 'draft' check (state in ('draft','confirmed','unanswered')),
  is_correct boolean, confirmed_at timestamptz,
  updated_at timestamptz not null default now(), primary key (round_id, question_id),
  foreign key (round_id, batch_id) references public.practice_rounds(id, batch_id),
  foreign key (question_id, batch_id) references public.questions(id, batch_id),
  check ((state = 'draft' and confirmed_at is null and is_correct is null) or
         (state in ('confirmed','unanswered') and confirmed_at is not null)),
  check (state <> 'unanswered' or (selected_option is null and text_answer is null and is_correct is null))
);
create table public.classroom_sessions (
  id uuid primary key default gen_random_uuid(), batch_id uuid not null references public.math_batches(id),
  class_id uuid not null references public.classes(id), created_by uuid not null references public.teacher_profiles(id),
  access_token text not null unique default (replace(gen_random_uuid()::text,'-','')),
  status text not null default 'waiting' check (status in ('waiting','active','closed','invalidated')),
  current_question_id uuid, question_status text not null default 'pending'
    check (question_status in ('pending','open','locked')),
  duration_seconds integer not null default 60 check (duration_seconds between 1 and 3600),
  auto_advance boolean not null default true, question_opened_at timestamptz, deadline_at timestamptz,
  created_at timestamptz not null default now(), expires_at timestamptz not null default (now() + interval '7 days'),
  closed_at timestamptz, unique (id, batch_id),
  check (length(access_token) >= 16), check (expires_at > created_at),
  check (question_status <> 'open' or (status = 'active' and current_question_id is not null
      and question_opened_at is not null and deadline_at > question_opened_at))
);
create table public.classroom_session_questions (
  session_id uuid not null, batch_id uuid not null, question_id uuid not null,
  sort_order integer not null check (sort_order > 0),
  primary key (session_id, question_id), unique (session_id, sort_order),
  foreign key (session_id, batch_id) references public.classroom_sessions(id, batch_id),
  foreign key (question_id, batch_id) references public.questions(id, batch_id)
);
alter table public.classroom_sessions add constraint classroom_current_question_fk
  foreign key (id, current_question_id) references public.classroom_session_questions(session_id, question_id)
  deferrable initially deferred;
create table public.classroom_participants (
  session_id uuid not null references public.classroom_sessions(id),
  student_id uuid not null references public.students(id),
  joined_at timestamptz not null default now(), last_seen_at timestamptz not null default now(),
  primary key (session_id, student_id)
);
create table public.classroom_answers (
  session_id uuid not null, student_id uuid not null, question_id uuid not null,
  selected_option text not null check (selected_option in ('A','B','C','D')),
  is_correct boolean not null, answered_at timestamptz not null default now(),
  primary key (session_id, student_id, question_id),
  foreign key (session_id, student_id) references public.classroom_participants(session_id, student_id),
  foreign key (session_id, question_id) references public.classroom_session_questions(session_id, question_id)
);
create table public.word_batches (
  id uuid primary key default gen_random_uuid(), grade_id uuid not null references public.grades(id),
  created_by uuid not null references public.teacher_profiles(id),
  import_job_id uuid unique references public.import_jobs(id),
  status text not null default 'draft' check (status in ('draft','published')),
  created_at timestamptz not null default now(), unique (id, grade_id)
);
create unique index word_batches_one_published on public.word_batches(grade_id) where status = 'published';
create table public.words (
  id uuid primary key default gen_random_uuid(), batch_id uuid not null, grade_id uuid not null,
  word text not null check (btrim(word) <> ''), meaning text not null check (btrim(meaning) <> ''),
  normalized_word text generated always as (lower(btrim(word))) stored,
  sort_order integer not null check (sort_order > 0),
  foreign key (batch_id, grade_id) references public.word_batches(id, grade_id) on delete cascade,
  unique (batch_id, normalized_word), unique (batch_id, sort_order)
);
create table public.word_progress (
  student_id uuid not null references public.students(id), word_id uuid not null references public.words(id) on delete cascade,
  last_rating text not null check (last_rating in ('forgot','fuzzy','clear')),
  interval_days integer not null check (interval_days between 1 and 30),
  due_at timestamptz not null, review_count integer not null default 1 check (review_count > 0),
  last_reviewed_at timestamptz not null default now(), primary key (student_id, word_id)
);

-- 常用查询及外键访问索引。
create index students_class_idx on public.students(class_id);
create index students_grade_idx on public.students(grade_id);
create index classes_school_idx on public.classes(school_id);
create index topics_grade_idx on public.topics(grade_id);
create index student_sessions_student_idx on public.student_sessions(student_id, expires_at);
create index rounds_latest_idx on public.practice_rounds(student_id, batch_id, completed_at desc) where status = 'completed';
create index rounds_batch_idx on public.practice_rounds(batch_id, status);
create index rounds_practice_idx on public.practice_rounds(practice_id);
create index practice_answers_question_idx on public.practice_answers(question_id);
create index practices_batch_idx on public.practices(batch_id);
create index classroom_batch_idx on public.classroom_sessions(batch_id, status);
create index classroom_class_idx on public.classroom_sessions(class_id, created_at desc);
create index classroom_participants_student_idx on public.classroom_participants(student_id);
create index word_progress_due_idx on public.word_progress(student_id, due_at);
create index word_progress_word_idx on public.word_progress(word_id);

-- 内容快照不可原地改写；已发布或归档数学题必须通过新批次替换。
create function public.app_guard_math_content() returns trigger language plpgsql
set search_path = public, pg_catalog as $$
declare target_batch uuid; target_topic uuid; batch_status text;
begin
  target_batch := case when tg_op = 'DELETE' then old.batch_id else new.batch_id end;
  if tg_op = 'UPDATE' and new.batch_id <> old.batch_id then
    raise exception '不能移动历史题目到其他批次';
  end if;
  select topic_id into target_topic from math_batches where id = target_batch;
  perform 1 from topics where id = target_topic for update;
  select status into batch_status from math_batches where id = target_batch;
  if batch_status is distinct from 'draft' then raise exception '已发布或归档题目不可修改或删除'; end if;
  return case when tg_op = 'DELETE' then old else new end;
end $$;
create trigger questions_guard before insert or update or delete on public.questions
for each row execute function public.app_guard_math_content();

create function public.app_guard_round() returns trigger language plpgsql
set search_path = public, pg_catalog as $$
declare topic uuid; b_status text; student_school uuid; topic_school uuid; grade_code text;
begin
  select topic_id into topic from math_batches where id = new.batch_id;
  perform 1 from topics where id = topic for update;
  if tg_op = 'UPDATE' then
    if (new.student_id, new.batch_id, new.practice_id) is distinct from
       (old.student_id, old.batch_id, old.practice_id) or old.status <> 'in_progress' then
      raise exception '练习身份及结束后的轮次不可修改';
    end if;
    if new.status = 'interrupted' then return new; end if;
  end if;
  select b.status, t.school_id into b_status, topic_school
    from math_batches b join topics t on t.id = b.topic_id where b.id = new.batch_id and t.is_active;
  select s.school_id, g.code into student_school, grade_code
    from students s join grades g on g.id = s.grade_id
    join classes c on c.id = s.class_id join schools sc on sc.id = s.school_id
    where s.id = new.student_id and s.is_active and g.is_active and c.is_active and sc.is_active;
  if b_status is distinct from 'published' or student_school is distinct from topic_school or student_school is null then
    raise exception '学生或题目内容不可用';
  end if;
  if new.practice_id is null and grade_code <> 'S6' then raise exception '自主数学练习仅限 S6'; end if;
  if new.practice_id is not null and not exists
    (select 1 from practices where id = new.practice_id and batch_id = new.batch_id and status = 'active') then
    raise exception '练习码已失效';
  end if;
  if not exists (select 1 from questions where batch_id = new.batch_id) then raise exception '主题暂无题目'; end if;
  if new.status = 'completed' then
    if exists (select 1 from questions q left join practice_answers a
        on a.round_id = new.id and a.question_id = q.id
        where q.batch_id = new.batch_id and (a.state is null or a.state = 'draft')) then
      raise exception '请通过 app_finish_round 完成整份提交';
    end if;
  end if;
  return new;
end $$;
create trigger rounds_guard before insert or update on public.practice_rounds
for each row execute function public.app_guard_round();

create function public.app_guard_practice_answer() returns trigger language plpgsql
set search_path = public, pg_catalog as $$
declare r practice_rounds; q questions; topic uuid;
begin
  select topic_id into topic from math_batches where id = new.batch_id;
  perform 1 from topics where id = topic for update;
  select * into r from practice_rounds where id = new.round_id for update;
  if r.id is null or r.status <> 'in_progress' or r.batch_id <> new.batch_id then raise exception '轮次已结束或失效'; end if;
  if not exists (select 1 from math_batches where id = r.batch_id and status = 'published') then raise exception '题目内容已更新'; end if;
  if r.practice_id is not null and not exists (select 1 from practices where id = r.practice_id and status = 'active') then
    raise exception '练习码已失效';
  end if;
  if tg_op = 'UPDATE' and (old.state <> 'draft' or
      (new.round_id, new.batch_id, new.question_id) is distinct from (old.round_id, old.batch_id, old.question_id)) then
    raise exception '已确认答案不可修改';
  end if;
  select * into q from questions where id = new.question_id and batch_id = new.batch_id;
  if q.id is null then raise exception '题目不属于本轮练习'; end if;
  if r.practice_id is not null and not exists (select 1 from practice_questions where practice_id = r.practice_id and question_id = q.id) then
    raise exception '题目不属于练习码';
  end if;
  if q.question_type = 'single_choice' and new.text_answer is not null then raise exception '选择题不能提交文字答案'; end if;
  if q.question_type = 'text_input' and new.selected_option is not null then raise exception '非选择题不能提交选项'; end if;
  if new.state = 'confirmed' then
    if (q.question_type = 'single_choice' and new.selected_option is null) or
       (q.question_type = 'text_input' and coalesce(btrim(new.text_answer),'') = '') then raise exception '单题确认不能留空'; end if;
    new.is_correct := case when q.question_type = 'single_choice' then new.selected_option = q.correct_option else null end;
    new.confirmed_at := clock_timestamp();
  elsif new.state = 'unanswered' then
    new.selected_option := null; new.text_answer := null; new.is_correct := null;
    new.confirmed_at := clock_timestamp();
  else
    new.is_correct := null; new.confirmed_at := null;
  end if;
  new.updated_at := clock_timestamp();
  return new;
end $$;
create trigger practice_answers_guard before insert or update on public.practice_answers
for each row execute function public.app_guard_practice_answer();

-- 全部 RPC 只授权后端 service_role。参数中的身份必须从后端已验证会话取得，不信任浏览器 student_id。
create function public.app_publish_math_batch(p_batch uuid, p_teacher uuid) returns void
language plpgsql set search_path = public, pg_catalog as $$
declare t topics; old_batch uuid;
begin
  select t0.* into t from topics t0 join math_batches b on b.topic_id = t0.id where b.id = p_batch for update of t0;
  if t.id is null or not t.is_active or not exists (select 1 from teacher_profiles where id = p_teacher and school_id = t.school_id and is_active) then
    raise exception '老师或主题不可用';
  end if;
  if not exists (select 1 from math_batches where id = p_batch and status = 'draft' and created_by = p_teacher) then raise exception '不是本人待发布批次'; end if;
  if not exists (select 1 from questions where batch_id = p_batch) then raise exception '不能发布空题库'; end if;
  select id into old_batch from math_batches where topic_id = t.id and status = 'published';
  if old_batch is not null then
    update practices set status = 'invalidated' where batch_id = old_batch and status = 'active';
    update practice_rounds set status = 'interrupted' where batch_id = old_batch and status = 'in_progress';
    update classroom_sessions set status = 'invalidated', question_status = 'locked', closed_at = clock_timestamp()
      where batch_id = old_batch and status in ('waiting','active');
    update math_batches set status = 'archived' where id = old_batch;
  end if;
  update math_batches set status = 'published', published_at = clock_timestamp() where id = p_batch;
  update import_jobs set status = 'imported', completed_at = clock_timestamp()
    where id = (select import_job_id from math_batches where id = p_batch);
end $$;

create function public.app_create_practice(p_batch uuid, p_teacher uuid, p_code text) returns uuid
language plpgsql set search_path = public, pg_catalog as $$
declare t topics; result uuid;
begin
  select t0.* into t from topics t0 join math_batches b on b.topic_id = t0.id where b.id = p_batch for update of t0;
  if t.id is null or not t.is_active or not exists (select 1 from teacher_profiles where id = p_teacher and school_id = t.school_id and is_active) or
     not exists (select 1 from math_batches where id = p_batch and status = 'published') then raise exception '题目或老师不可用'; end if;
  if not exists (select 1 from questions where batch_id = p_batch) then raise exception '不能生成空练习码'; end if;
  insert into practices(batch_id, created_by, access_code) values(p_batch,p_teacher,upper(btrim(p_code))) returning id into result;
  insert into practice_questions(practice_id,batch_id,question_id,sort_order)
    select result,p_batch,id,sort_order from questions where batch_id = p_batch;
  return result;
end $$;

create function public.app_save_practice_answer(p_round uuid, p_student uuid, p_question uuid,
  p_option text default null, p_text text default null, p_confirm boolean default false) returns jsonb
language plpgsql set search_path = public, pg_catalog as $$
declare r practice_rounds; a practice_answers; topic uuid;
begin
  select b.topic_id into topic from practice_rounds r0 join math_batches b on b.id = r0.batch_id where r0.id = p_round;
  perform 1 from topics where id = topic for update;
  select * into r from practice_rounds where id = p_round and student_id = p_student for update;
  if r.id is null then raise exception '无权访问该轮次'; end if;
  if p_confirm is null then raise exception '缺少确认状态'; end if;
  insert into practice_answers(round_id,batch_id,question_id,selected_option,text_answer,state)
  values(p_round,r.batch_id,p_question,p_option,p_text,case when p_confirm then 'confirmed' else 'draft' end)
  on conflict (round_id,question_id) do update set selected_option = excluded.selected_option,
    text_answer = excluded.text_answer, state = excluded.state
  returning * into a;
  if p_confirm then
    return to_jsonb(a) || jsonb_build_object('correct_option',(select correct_option from questions where id = p_question));
  end if;
  return jsonb_build_object('question_id',p_question,'state','draft','updated_at',a.updated_at);
end $$;

-- 整份提交时可携带尚未保存的最新输入，避免最后一次自动保存尚未完成。
create function public.app_finish_round(p_round uuid, p_student uuid, p_answers jsonb default '[]'::jsonb) returns jsonb
language plpgsql set search_path = public, pg_catalog as $$
declare r practice_rounds; item jsonb; topic uuid; result jsonb;
begin
  if p_answers is null or jsonb_typeof(p_answers) <> 'array' then raise exception 'answers 必须为数组'; end if;
  select b.topic_id into topic from practice_rounds r0 join math_batches b on b.id = r0.batch_id where r0.id = p_round;
  perform 1 from topics where id = topic for update;
  select * into r from practice_rounds where id = p_round and student_id = p_student for update;
  if r.id is null or r.status <> 'in_progress' then raise exception '轮次不存在或已结束'; end if;
  for item in select value from jsonb_array_elements(p_answers) loop
    perform app_save_practice_answer(p_round,p_student,(item->>'question_id')::uuid,item->>'selected_option',item->>'text_answer',false);
  end loop;
  insert into practice_answers(round_id,batch_id,question_id,state)
    select r.id,r.batch_id,q.id,'unanswered' from questions q where q.batch_id = r.batch_id
      and not exists (select 1 from practice_answers a where a.round_id = r.id and a.question_id = q.id);
  update practice_answers set state = case
    when selected_option is null and coalesce(btrim(text_answer),'') = '' then 'unanswered' else 'confirmed' end
    where round_id = r.id and state = 'draft';
  update practice_rounds set status = 'completed', completed_at = clock_timestamp() where id = r.id;
  select coalesce(jsonb_agg(to_jsonb(a) || jsonb_build_object('correct_option',q.correct_option) order by q.sort_order),'[]'::jsonb)
    into result from practice_answers a join questions q on q.id = a.question_id where a.round_id = r.id;
  return result;
end $$;

create function public.app_guard_classroom_question() returns trigger language plpgsql
set search_path = public, pg_catalog as $$
begin
  if not exists (select 1 from questions where id = new.question_id and batch_id = new.batch_id and question_type = 'single_choice') then
    raise exception '课堂首版只允许选择题';
  end if;
  return new;
end $$;
create trigger classroom_questions_guard before insert or update on public.classroom_session_questions
for each row execute function public.app_guard_classroom_question();

create function public.app_guard_classroom_participant() returns trigger language plpgsql
set search_path = public, pg_catalog as $$
begin
  if not exists (select 1 from classroom_sessions c join math_batches b on b.id = c.batch_id
      join topics t on t.id = b.topic_id join students s on s.school_id = t.school_id
      where c.id = new.session_id and s.id = new.student_id and s.is_active and t.is_active
        and b.status = 'published' and c.status in ('waiting','active') and c.expires_at > clock_timestamp()) then
    raise exception '课堂或学生不可用';
  end if;
  return new;
end $$;
create trigger classroom_participants_guard before insert or update on public.classroom_participants
for each row execute function public.app_guard_classroom_participant();

create function public.app_guard_classroom_answer() returns trigger language plpgsql
set search_path = public, pg_catalog as $$
declare c classroom_sessions; topic uuid; correct text;
begin
  select b.topic_id into topic from classroom_sessions s join math_batches b on b.id = s.batch_id where s.id = new.session_id;
  perform 1 from topics where id = topic for update;
  select * into c from classroom_sessions where id = new.session_id for update;
  if c.id is null or c.status <> 'active' or c.question_status <> 'open' or
     c.current_question_id is distinct from new.question_id or c.expires_at <= clock_timestamp() or
     c.deadline_at is null or c.deadline_at <= clock_timestamp() then raise exception '课堂题目已关闭或到时'; end if;
  if tg_op = 'UPDATE' and (new.session_id,new.student_id,new.question_id) is distinct from
      (old.session_id,old.student_id,old.question_id) then raise exception '不能更改答题身份'; end if;
  if not exists (select 1 from students where id = new.student_id and is_active) then raise exception '学生不可用'; end if;
  select correct_option into correct from questions where id = new.question_id and batch_id = c.batch_id and question_type = 'single_choice';
  if correct is null then raise exception '不是该课堂的选择题'; end if;
  new.is_correct := new.selected_option = correct; new.answered_at := clock_timestamp();
  return new;
end $$;
create trigger classroom_answers_guard before insert or update on public.classroom_answers
for each row execute function public.app_guard_classroom_answer();

create function public.app_publish_word_batch(p_batch uuid, p_teacher uuid) returns void
language plpgsql set search_path = public, pg_catalog as $$
declare g grades;
begin
  select g0.* into g from grades g0 join word_batches b on b.grade_id = g0.id where b.id = p_batch for update of g0;
  if g.id is null or not g.is_active or not exists (select 1 from teacher_profiles where id = p_teacher and school_id = g.school_id and is_active) or
     not exists (select 1 from word_batches where id = p_batch and status = 'draft' and created_by = p_teacher) then raise exception '老师或词库不可用'; end if;
  if not exists (select 1 from words where batch_id = p_batch) then raise exception '不能发布空词库'; end if;
  -- 删除旧词库会级联删除该年级所有学生的旧单词进度，不触碰其他年级。
  delete from word_batches where grade_id = g.id and id <> p_batch;
  update word_batches set status = 'published' where id = p_batch;
  update import_jobs set status = 'imported', completed_at = clock_timestamp()
    where id = (select import_job_id from word_batches where id = p_batch);
end $$;

create function public.app_rate_word(p_student uuid, p_word uuid, p_rating text) returns jsonb
language plpgsql set search_path = public, pg_catalog as $$
declare w words; g grades; previous word_progress; days integer; result word_progress;
begin
  if p_rating is null or p_rating not in ('forgot','fuzzy','clear') then raise exception '无效记忆评价'; end if;
  select g0.* into g from grades g0 join words w0 on w0.grade_id = g0.id where w0.id = p_word for update of g0;
  select w0.* into w from words w0 join word_batches b on b.id = w0.batch_id where w0.id = p_word and b.status = 'published';
  if w.id is null or not g.is_active or not exists (select 1 from students where id = p_student and school_id = g.school_id and is_active) then
    raise exception '学生或单词不可用'; end if;
  select * into previous from word_progress where student_id = p_student and word_id = p_word for update;
  if previous.word_id is null then days := case p_rating when 'forgot' then 1 when 'fuzzy' then 3 else 7 end;
  else days := case p_rating when 'forgot' then 1 when 'fuzzy' then previous.interval_days else least(30,previous.interval_days * 2) end; end if;
  insert into word_progress(student_id,word_id,last_rating,interval_days,due_at,last_reviewed_at)
    values(p_student,p_word,p_rating,days,clock_timestamp() + make_interval(days => days),clock_timestamp())
    on conflict (student_id,word_id) do update set last_rating = excluded.last_rating, interval_days = excluded.interval_days,
      due_at = excluded.due_at, last_reviewed_at = excluded.last_reviewed_at, review_count = word_progress.review_count + 1
    returning * into result;
  return to_jsonb(result);
end $$;

-- 改密码时撤销旧会话；学生资料修改由部署人员管理。
create function public.app_revoke_student_sessions() returns trigger language plpgsql
set search_path = public, pg_catalog as $$
begin
  if new.password_hash is distinct from old.password_hash or new.is_active is distinct from old.is_active then
    new.auth_version := old.auth_version + 1;
    update student_sessions set revoked_at = clock_timestamp() where student_id = old.id and revoked_at is null;
  end if;
  new.updated_at := clock_timestamp(); return new;
end $$;
create trigger students_auth_change before update on public.students
for each row execute function public.app_revoke_student_sessions();

-- 后端专用：全部业务表开启 RLS，anon/authenticated/PUBLIC 不授予直接表访问或 RPC 权限。
-- 不配置浏览器学生 RLS：学生不是 Supabase Auth 身份，所有授权由后端会话完成。
do $$
declare t text; f record;
begin
  foreach t in array array[
    'app_schema_state','schools','teacher_profiles','grades','classes','students','student_sessions',
    'topics','import_jobs','math_batches','questions','practices','practice_questions','practice_rounds','practice_answers',
    'classroom_sessions','classroom_session_questions','classroom_participants','classroom_answers',
    'word_batches','words','word_progress'
  ] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on table public.%I from public, anon, authenticated',t);
    execute format('grant select, insert, update, delete on table public.%I to service_role',t);
  end loop;
  for f in select p.oid::regprocedure as signature from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and left(p.proname,4) = 'app_'
  loop
    execute format('revoke all on function %s from public, anon, authenticated',f.signature);
    execute format('grant execute on function %s to service_role',f.signature);
  end loop;
end $$;

insert into public.schools(id,name) values('00000000-0000-0000-0000-000000000001','Default School');
insert into public.grades(id,school_id,code,name,sort_order)
select ('10000000-0000-0000-0000-' || lpad(n::text,12,'0'))::uuid,
  '00000000-0000-0000-0000-000000000001','S' || n,'S' || n,n
from generate_series(1,6) n;
insert into public.classes(grade_id,school_id,code,name)
select g.id,g.school_id,c.code,g.code || c.code from public.grades g
cross join (values('A'),('B'),('C'),('D'),('E'),('F')) c(code);
insert into public.teacher_profiles(id,school_id,display_name,is_active)
select id,'00000000-0000-0000-0000-000000000001',display_name,is_active from rebuild_teachers;

-- 目录名称取历史 manifest 的完整章节列，包含 00 与 99。
insert into public.topics(school_id,grade_id,code,name,sort_order)
select '00000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000006',code,name,code::integer
from (values
 ('00','前置資料'),('01','指數化簡'),('02','多項式運算'),('03','函數'),('04','主項變換'),
 ('05','因式分解'),('06','恆等式求未知係數/常數'),('07','餘式/因式定理'),('08','二元一次聯立方程'),('09','二次方程'),
 ('10','二次函數的圖像'),('11','複合一元一次不等式'),('12','不等式的性質'),('13','百分數'),('14','數列'),
 ('15','比和率'),('16','變數法'),('17','誤差'),('18','近似法'),('19','扇/弓形面積、弧長、周界'),
 ('20','立體的求積法'),('21','直線圖形的面積、邊長、周界'),('22','邊長比與(相似)三角形面積比'),
 ('23','直線圖形的演繹幾何'),('24','圓的演繹幾何(及三角比)'),('25','圓的部份區域的面積'),
 ('26','直角三角形的三角比'),('27','三角比的歸約公式'),('28','方位'),('29','多邊形的性質及對稱性'),
 ('30','點的坐標變換'),('31','軌跡'),('32','直線的坐標幾何'),('33','圓的坐標幾何'),('34','基礎概率'),
 ('35','統計圖及基礎概率'),('36','統計 1'),('37','統計 2'),('38','最大公因式及最小公倍式'),('39','代數分式'),
 ('40','函數圖像的變換'),('41','對數'),('42','線性關係'),('43','指數函數圖像'),('44','不同進制的記數法'),
 ('45','二次方程/函數 (非常規型或 NF)'),('46','複數'),('47','線性規劃'),('48','等 差/比 數列/級數'),
 ('49','三角函數圖像'),('50','三角方程'),('51','立體處境的三角學'),('52','平面圖形的三角學'),
 ('53','圓的性質、平面圖形的三角學'),('54','圓的切線'),('55','直線與圓的相交'),('56','三角形的四心'),
 ('57','排列與組合 (概率)'),('58','概率(加法律、互補律及乘法律) NF'),('59','統計'),('99','答案_甲部')
) v(code,name);

-- 新图片桶使用新路径；旧桶、旧对象和旧 Storage policy 均保留。
-- 私有图片由后端签名访问，避免依赖旧的 public Storage 规则。
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('question-images-v2','question-images-v2',false,1048576,array['image/jpeg','image/png','image/webp'])
on conflict (id) do nothing;
do $$
begin
  if not exists (select 1 from storage.buckets where id = 'question-images-v2' and not public
      and file_size_limit = 1048576 and allowed_mime_types = array['image/jpeg','image/png','image/webp']) then
    raise exception 'question-images-v2 已存在但配置不同，请检查该桶后再重建';
  end if;
end $$;
insert into public.app_schema_state(version) values('20261008_real_students_v1');
notify pgrst, 'reload schema';
commit;

select '重建完成：接着运行 02_verify.sql；不要重复运行本文件' as result;
