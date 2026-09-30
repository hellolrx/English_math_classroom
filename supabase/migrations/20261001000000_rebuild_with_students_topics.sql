-- 学生实名账号、主题、图片题目、非选择题、单词复习重构
-- 删除匿名设备设计，建立实名学生体系
-- 时间：2026-10-01

-- 1. Drop 旧表和触发器（按依赖顺序）
-- 先安全删除触发器（表可能已被删除）
do $$
begin
  if exists (select 1 from information_schema.tables where table_schema = 'public' and table_name = 'review_progress') then
    drop trigger if exists review_progress_set_updated_at on public.review_progress;
  end if;
  if exists (select 1 from information_schema.tables where table_schema = 'public' and table_name = 'student_practice_attempts') then
    drop trigger if exists student_practice_attempts_set_updated_at on public.student_practice_attempts;
  end if;
end $$;

-- 删除学生工作台相关表（依赖匿名设备）
drop table if exists public.review_progress;
drop table if exists public.student_practice_answers;
drop table if exists public.student_practice_attempts;

-- 安全删除触发器（表可能已被删除）
do $$
begin
  if exists (select 1 from information_schema.tables where table_schema = 'public' and table_name = 'answers') then
    drop trigger if exists answers_set_updated_at on public.answers;
    drop trigger if exists answers_validate_context on public.answers;
  end if;
  if exists (select 1 from information_schema.tables where table_schema = 'public' and table_name = 'practice_attempts') then
    drop trigger if exists practice_attempts_set_updated_at on public.practice_attempts;
    drop trigger if exists practice_attempts_validate_context on public.practice_attempts;
    drop trigger if exists practice_attempts_validate_completion on public.practice_attempts;
  end if;
end $$;

-- 删除匿名设备相关表
drop table if exists public.answers;
drop table if exists public.practice_attempts;
drop table if exists public.session_participants;
drop table if exists public.anonymous_devices;

-- Drop 旧索引
drop index if exists answers_classroom_unique;
drop index if exists answers_practice_unique;
drop index if exists practice_attempts_one_draft;
drop index if exists answers_session_id_idx;
drop index if exists practice_attempts_session_device_idx;
drop index if exists session_participants_session_id_idx;
drop index if exists review_progress_due_idx;
drop index if exists question_sets_grade_status_idx;

-- Drop 旧函数
drop function if exists public.validate_answer_context();
drop function if exists public.validate_practice_attempt();
drop function if exists public.validate_attempt_completion();

-- 删除 question_sets.grade_id 列（由 20260925000100 添加）
alter table public.question_sets
  drop column if exists grade_id;

-- 简化 question_options 表，删除不需要的列（题目和选项均为图片，系统只需知道选项标记）
alter table public.question_options
  drop column if exists option_text;
alter table public.question_options
  drop column if exists option_image_url;
alter table public.question_options
  drop column if exists content_type;

-- 删除 question_options 表上依赖已删除列的 constraint
alter table public.question_options
  drop constraint if exists question_options_text_or_image;
alter table public.question_options
  drop constraint if exists question_options_content_type_check;

-- 简化 questions 表，题目均为图片
alter table public.questions
  drop column if exists question_text;
alter table public.questions
  drop column if exists content_type;
alter table public.questions
  drop column if exists language;

-- 删除 questions 表上依赖已删除列的 constraint
alter table public.questions
  drop constraint if exists questions_text_or_image;
alter table public.questions
  drop constraint if exists questions_content_type_check;
alter table public.questions
  drop constraint if exists questions_language_not_blank;

-- 删除 sessions 表上依赖 question_set_id 的 policy
drop policy if exists teachers_read_sessions on public.sessions;
-- 删除 session_students 和 student_answers 表上依赖 sessions.question_set_id 的 policy
drop policy if exists teachers_read_session_students on public.session_students;
drop policy if exists students_read_own_session_students on public.session_students;
drop policy if exists teachers_read_student_answers on public.student_answers;
drop policy if exists students_read_own_answers on public.student_answers;
drop policy if exists students_insert_own_answers on public.student_answers;

-- 删除 topics 表上已简化的列（如果之前版本存在）
alter table public.topics
  drop column if exists grade_id;
alter table public.topics
  drop column if exists sort_order;
alter table public.topics
  drop column if exists is_active;

-- 2. 创建 topics 表（必须先创建，因为 question_sets 和 sessions 会引用它）
create table if not exists public.topics (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id),
  code text not null,
  name text not null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint topics_school_code_unique unique (school_id, code),
  constraint topics_name_not_blank check (length(btrim(name)) > 0)
);

-- 3. 修改 question_sets 表，加 topic_id
alter table public.question_sets
  add column if not exists topic_id uuid;

alter table public.question_sets
  drop constraint if exists question_sets_topic_fk;

alter table public.question_sets
  add constraint question_sets_topic_fk
  foreign key (topic_id)
  references public.topics(id)
  on delete set null;

-- 4. 修改 sessions 表，支持主题或题目集合二选一
alter table public.sessions
  drop constraint if exists sessions_question_set_fk;

alter table public.sessions
  drop column if exists question_set_id;

alter table public.sessions
  add column if not exists question_set_id uuid;

alter table public.sessions
  add column if not exists topic_id uuid;

alter table public.sessions
  drop constraint if exists sessions_question_set_fk;

alter table public.sessions
  add constraint sessions_question_set_fk
  foreign key (question_set_id)
  references public.question_sets(id)
  on delete restrict;

alter table public.sessions
  drop constraint if exists sessions_topic_fk;

alter table public.sessions
  add constraint sessions_topic_fk
  foreign key (topic_id)
  references public.topics(id)
  on delete restrict;

-- 5. 创建 students 表
create table if not exists public.students (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id),
  student_no text not null,
  name text not null,
  grade_id uuid not null references public.grades(id),
  class_id uuid not null references public.classes(id),
  password_hash text not null,
  must_change_password boolean not null default true,
  is_active boolean not null default true,
  last_login_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint students_school_student_no_unique unique (school_id, student_no),
  constraint students_name_not_blank check (length(btrim(name)) > 0),
  constraint students_student_no_not_blank check (length(btrim(student_no)) > 0)
);

-- 6. 创建 session_students 表（替代 session_participants）
create table if not exists public.session_students (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.sessions(id) on delete cascade,
  student_id uuid not null references public.students(id) on delete restrict,
  joined_at timestamptz not null default timezone('utc', now()),
  last_seen_at timestamptz not null default timezone('utc', now()),
  constraint session_students_unique unique (session_id, student_id)
);

-- 7. 创建 student_answers 表（替代 answers）
create table if not exists public.student_answers (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.sessions(id) on delete restrict,
  student_id uuid not null references public.students(id) on delete restrict,
  question_id uuid not null references public.questions(id) on delete restrict,
  answer_type text not null default 'single_choice',
  selected_option_id uuid references public.question_options(id) on delete restrict,
  answer_text text,
  is_correct boolean,
  answered_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint student_answers_type_check check (answer_type in ('single_choice', 'text_input')),
  constraint student_answers_single_choice_check check (
    (answer_type = 'single_choice' and selected_option_id is not null and is_correct is not null and answer_text is null) or
    (answer_type = 'text_input' and selected_option_id is null and is_correct is null and answer_text is not null)
  )
);

-- 8. 创建 practice_progress 表（课后练习进度）
create table if not exists public.practice_progress (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.students(id) on delete cascade,
  session_id uuid references public.sessions(id) on delete restrict,
  question_id uuid not null references public.questions(id) on delete restrict,
  current_question_id uuid references public.questions(id) on delete set null,
  answered_count integer not null default 0,
  total_count integer not null,
  is_completed boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint practice_progress_count_check check (answered_count >= 0 and total_count > 0)
);

-- 9. 创建 vocabulary_words 表（单词库）
create table if not exists public.vocabulary_words (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id),
  grade_id uuid not null references public.grades(id),
  word text not null,
  meaning text not null,
  sort_order integer not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint vocabulary_words_unique unique (school_id, grade_id, word),
  constraint vocabulary_words_word_not_blank check (length(btrim(word)) > 0),
  constraint vocabulary_words_meaning_not_blank check (length(btrim(meaning)) > 0)
);

-- 10. 创建 student_word_progress 表（单词复习进度）
create table if not exists public.student_word_progress (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.students(id) on delete cascade,
  word_id uuid not null references public.vocabulary_words(id) on delete restrict,
  level smallint not null default 1,
  due_at timestamptz not null default timezone('utc', now()),
  last_rating text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint student_word_progress_unique unique (student_id, word_id),
  constraint student_word_progress_level_check check (level between 1 and 10),
  constraint student_word_progress_rating_check check (
    last_rating is null or last_rating in ('forgot', 'fuzzy', 'clear')
  )
);

-- 11. 灌入 60 个主题数据（01-59 + 99）
-- 先获取学校 ID
do $$
declare
  v_school_id uuid;
begin
  select id into v_school_id from public.schools limit 1;
  
  if v_school_id is null then
    raise exception 'school not found';
  end if;
  
  insert into public.topics (school_id, code, name)
  values
    (v_school_id, '01', '指數化簡'),
    (v_school_id, '02', '多項式運算'),
    (v_school_id, '03', '函數'),
    (v_school_id, '04', '主項變換'),
    (v_school_id, '05', '因式分解'),
    (v_school_id, '06', '恆等式求未知係數/常數'),
    (v_school_id, '07', '餘式/因式定理'),
    (v_school_id, '08', '二元一次聯立方程'),
    (v_school_id, '09', '二次方程'),
    (v_school_id, '10', '二次函數的圖像'),
    (v_school_id, '11', '複合一元一次不等式'),
    (v_school_id, '12', '不等式的性質'),
    (v_school_id, '13', '百分數'),
    (v_school_id, '14', '數列'),
    (v_school_id, '15', '比和率'),
    (v_school_id, '16', '變數法'),
    (v_school_id, '17', '誤差'),
    (v_school_id, '18', '近似法'),
    (v_school_id, '19', '扇/弓形面積、弧長、周界'),
    (v_school_id, '20', '立體的求積法'),
    (v_school_id, '21', '直線圖形的面積、邊長、周界'),
    (v_school_id, '22', '邊長比與(相似)三角形面積比'),
    (v_school_id, '23', '直線圖形的演繹幾何'),
    (v_school_id, '24', '圓的演繹幾何(及三角比)'),
    (v_school_id, '25', '圓的部份區域的面積'),
    (v_school_id, '26', '直角三角形的三角比'),
    (v_school_id, '27', '三角比的歸約公式'),
    (v_school_id, '28', '方位'),
    (v_school_id, '29', '多邊形的性質及對稱性'),
    (v_school_id, '30', '點的坐標變換'),
    (v_school_id, '31', '軌跡'),
    (v_school_id, '32', '直線的坐標幾何'),
    (v_school_id, '33', '圓的坐標幾何'),
    (v_school_id, '34', '基礎概率'),
    (v_school_id, '35', '統計圖及基礎概率'),
    (v_school_id, '36', '統計 1'),
    (v_school_id, '37', '統計 2'),
    (v_school_id, '38', '最大公因式及最小公倍式'),
    (v_school_id, '39', '代數分式'),
    (v_school_id, '40', '函數圖像的變換'),
    (v_school_id, '41', '對數'),
    (v_school_id, '42', '線性關係'),
    (v_school_id, '43', '指數函數圖像'),
    (v_school_id, '44', '不同進制的記數法'),
    (v_school_id, '45', '二次方程/函數 (非常規型或 NF)'),
    (v_school_id, '46', '複數'),
    (v_school_id, '47', '線性規劃'),
    (v_school_id, '48', '等 差/比 數列/級數'),
    (v_school_id, '49', '三角函數圖像'),
    (v_school_id, '50', '三角方程'),
    (v_school_id, '51', '立體處境的三角學'),
    (v_school_id, '52', '平面圖形的三角學'),
    (v_school_id, '53', '圓的性質、平面圖形的三角學'),
    (v_school_id, '54', '圓的切線'),
    (v_school_id, '55', '直線與圓的相交'),
    (v_school_id, '56', '三角形的四心'),
    (v_school_id, '57', '排列與組合 (概率)'),
    (v_school_id, '58', '概率(加法律、互補律及乘法律) NF'),
    (v_school_id, '59', '統計'),
    (v_school_id, '99', '答案_甲部')
  on conflict (school_id, code) do nothing;
end $$;

-- 12. 创建索引
create index if not exists topics_school_code_idx on public.topics (school_id, code);
create index if not exists topics_code_idx on public.topics (code);
create index if not exists students_school_student_no_idx on public.students (school_id, student_no);
create index if not exists students_grade_id_idx on public.students (grade_id);
create index if not exists students_class_id_idx on public.students (class_id);
create index if not exists session_students_session_id_idx on public.session_students (session_id, joined_at);
create index if not exists session_students_student_id_idx on public.session_students (student_id);
create index if not exists student_answers_session_id_idx on public.student_answers (session_id, question_id);
create index if not exists student_answers_student_id_idx on public.student_answers (student_id, answered_at desc);
create index if not exists student_answers_question_id_idx on public.student_answers (question_id);
create index if not exists practice_progress_student_id_idx on public.practice_progress (student_id);
create index if not exists practice_progress_session_id_idx on public.practice_progress (session_id);
create unique index if not exists practice_progress_unique_idx on public.practice_progress (student_id, coalesce(session_id::text, question_id::text));
create index if not exists vocabulary_words_school_grade_idx on public.vocabulary_words (school_id, grade_id, sort_order);
create index if not exists student_word_progress_student_id_idx on public.student_word_progress (student_id, due_at);
create index if not exists student_word_progress_word_id_idx on public.student_word_progress (word_id);
create index if not exists question_sets_topic_id_idx on public.question_sets (topic_id);
create index if not exists sessions_topic_id_idx on public.sessions (topic_id);

-- 13. 创建触发器函数
create or replace function public.validate_student_answer()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  target_session_type text;
  target_status text;
  target_expires_at timestamptz;
  target_question_set uuid;
  target_correct_option uuid;
  target_session_question_set uuid;
begin
  select session_type, status, expires_at, question_set_id
    into target_session_type, target_status, target_expires_at, target_session_question_set
    from public.sessions
   where id = new.session_id;

  if target_session_type is null then
    raise exception 'answer session does not exist';
  end if;

  if target_status <> 'active' or target_expires_at <= timezone('utc', now()) then
    raise exception 'answer session is not active';
  end if;

  select question_set_id
    into target_question_set
    from public.questions
   where id = new.question_id;

  if target_session_question_set is not null and target_question_set is not null and target_question_set <> target_session_question_set then
    raise exception 'answer question does not belong to session question set';
  end if;

  if new.answer_type = 'single_choice' then
    select correct_option_id
      into target_correct_option
      from public.questions
     where id = new.question_id;

    if target_correct_option is null then
      raise exception 'single choice question has no correct option configured';
    end if;

    if new.selected_option_id is not null then
      new.is_correct := (new.selected_option_id = target_correct_option);
    end if;
  end if;

  if target_session_type = 'classroom' then
    if not exists (
      select 1 from public.session_students ss
       where ss.session_id = new.session_id
         and ss.student_id = new.student_id
    ) then
      raise exception 'student has not joined this session';
    end if;
  end if;

  return new;
end;
$$;

create or replace function public.validate_session_source()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.question_set_id is null and new.topic_id is null then
    raise exception 'session must have either question_set_id or topic_id';
  end if;

  if new.question_set_id is not null and new.topic_id is not null then
    raise exception 'session cannot have both question_set_id and topic_id';
  end if;

  return new;
end;
$$;

create or replace function public.update_practice_progress()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  total_questions integer;
begin
  if new.session_id is not null then
    select count(*)
      into total_questions
      from public.sessions s
      join public.questions q on q.question_set_id = s.question_set_id
     where s.id = new.session_id;
  else
    select count(*)
      into total_questions
      from public.questions q
      join public.question_sets qs on qs.id = q.question_set_id
     where qs.topic_id = new.question_id;
  end if;

  new.total_count := total_questions;

  return new;
end;
$$;

-- 14. 创建触发器
drop trigger if exists student_answers_validate_context on public.student_answers;
create trigger student_answers_validate_context
before insert or update on public.student_answers
for each row execute function public.validate_student_answer();

drop trigger if exists sessions_validate_source on public.sessions;
create trigger sessions_validate_source
before insert or update on public.sessions
for each row execute function public.validate_session_source();

drop trigger if exists practice_progress_validate on public.practice_progress;
create trigger practice_progress_validate
before insert or update on public.practice_progress
for each row execute function public.update_practice_progress();

-- 15. updated_at 触发器
drop trigger if exists topics_set_updated_at on public.topics;
create trigger topics_set_updated_at before update on public.topics
for each row execute function public.set_updated_at();

drop trigger if exists students_set_updated_at on public.students;
create trigger students_set_updated_at before update on public.students
for each row execute function public.set_updated_at();

drop trigger if exists session_students_set_updated_at on public.session_students;
create trigger session_students_set_updated_at before update on public.session_students
for each row execute function public.set_updated_at();

drop trigger if exists student_answers_set_updated_at on public.student_answers;
create trigger student_answers_set_updated_at before update on public.student_answers
for each row execute function public.set_updated_at();

drop trigger if exists practice_progress_set_updated_at on public.practice_progress;
create trigger practice_progress_set_updated_at before update on public.practice_progress
for each row execute function public.set_updated_at();

drop trigger if exists vocabulary_words_set_updated_at on public.vocabulary_words;
create trigger vocabulary_words_set_updated_at before update on public.vocabulary_words
for each row execute function public.set_updated_at();

drop trigger if exists student_word_progress_set_updated_at on public.student_word_progress;
create trigger student_word_progress_set_updated_at before update on public.student_word_progress
for each row execute function public.set_updated_at();

-- 16. Row Level Security
alter table public.topics enable row level security;
alter table public.students enable row level security;
alter table public.session_students enable row level security;
alter table public.student_answers enable row level security;
alter table public.practice_progress enable row level security;
alter table public.vocabulary_words enable row level security;
alter table public.student_word_progress enable row level security;

-- Drop 旧 policy（仅针对未 drop 的表）
-- session_participants 和 answers 表已被 drop，其 policy 自动删除

-- 17. 教师权限 Policy
drop policy if exists teachers_read_topics on public.topics;
create policy teachers_read_topics on public.topics
  for select to authenticated using (school_id = (select public.current_teacher_school_id()));

drop policy if exists teachers_read_students on public.students;
create policy teachers_read_students on public.students
  for select to authenticated using (school_id = (select public.current_teacher_school_id()));

drop policy if exists teachers_read_session_students on public.session_students;
create policy teachers_read_session_students on public.session_students
  for select to authenticated using (
    exists (
      select 1 from public.sessions s
       where s.id = session_students.session_id
         and (s.question_set_id is null or exists (
           select 1 from public.question_sets qs
            where qs.id = s.question_set_id
              and qs.school_id = (select public.current_teacher_school_id())
         ) or exists (
           select 1 from public.topics t
            where t.id = s.topic_id
              and t.school_id = (select public.current_teacher_school_id())
         ))
    )
  );

drop policy if exists teachers_read_student_answers on public.student_answers;
create policy teachers_read_student_answers on public.student_answers
  for select to authenticated using (
    exists (
      select 1 from public.sessions s
       where s.id = student_answers.session_id
         and (s.question_set_id is null or exists (
           select 1 from public.question_sets qs
            where qs.id = s.question_set_id
              and qs.school_id = (select public.current_teacher_school_id())
         ) or exists (
           select 1 from public.topics t
            where t.id = s.topic_id
              and t.school_id = (select public.current_teacher_school_id())
         ))
    )
  );

drop policy if exists teachers_read_practice_progress on public.practice_progress;
create policy teachers_read_practice_progress on public.practice_progress
  for select to authenticated using (
    exists (
      select 1 from public.students s
       where s.id = practice_progress.student_id
         and s.school_id = (select public.current_teacher_school_id())
    )
  );

drop policy if exists teachers_read_vocabulary_words on public.vocabulary_words;
create policy teachers_read_vocabulary_words on public.vocabulary_words
  for select to authenticated using (school_id = (select public.current_teacher_school_id()));

drop policy if exists teachers_read_student_word_progress on public.student_word_progress;
create policy teachers_read_student_word_progress on public.student_word_progress
  for select to authenticated using (
    exists (
      select 1 from public.students s
       where s.id = student_word_progress.student_id
         and s.school_id = (select public.current_teacher_school_id())
    )
  );

-- 18. 学生权限 Policy
drop policy if exists students_read_self on public.students;
create policy students_read_self on public.students
  for select to authenticated using (id = (select auth.uid()));

drop policy if exists students_update_password on public.students;
create policy students_update_password on public.students
  for update to authenticated using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

drop policy if exists students_read_own_session_students on public.session_students;
create policy students_read_own_session_students on public.session_students
  for select to authenticated using (student_id = (select auth.uid()));

drop policy if exists students_read_own_answers on public.student_answers;
create policy students_read_own_answers on public.student_answers
  for select to authenticated using (student_id = (select auth.uid()));

drop policy if exists students_insert_own_answers on public.student_answers;
create policy students_insert_own_answers on public.student_answers
  for insert to authenticated with check (student_id = (select auth.uid()));

drop policy if exists students_read_own_practice_progress on public.practice_progress;
create policy students_read_own_practice_progress on public.practice_progress
  for select to authenticated using (student_id = (select auth.uid()));

drop policy if exists students_insert_own_practice_progress on public.practice_progress;
create policy students_insert_own_practice_progress on public.practice_progress
  for insert to authenticated with check (student_id = (select auth.uid()));

drop policy if exists students_update_own_practice_progress on public.practice_progress;
create policy students_update_own_practice_progress on public.practice_progress
  for update to authenticated using (student_id = (select auth.uid()))
  with check (student_id = (select auth.uid()));

drop policy if exists students_read_vocabulary on public.vocabulary_words;
create policy students_read_vocabulary on public.vocabulary_words
  for select to authenticated using (
    grade_id = (
      select grade_id from public.students where id = (select auth.uid())
    )
  );

drop policy if exists students_read_own_word_progress on public.student_word_progress;
create policy students_read_own_word_progress on public.student_word_progress
  for select to authenticated using (student_id = (select auth.uid()));

drop policy if exists students_insert_own_word_progress on public.student_word_progress;
create policy students_insert_own_word_progress on public.student_word_progress
  for insert to authenticated with check (student_id = (select auth.uid()));

drop policy if exists students_update_own_word_progress on public.student_word_progress;
create policy students_update_own_word_progress on public.student_word_progress
  for update to authenticated using (student_id = (select auth.uid()))
  with check (student_id = (select auth.uid()));

-- 19. 权限授予
grant select on table public.topics, public.students, public.session_students,
  public.student_answers, public.practice_progress, public.vocabulary_words,
  public.student_word_progress to authenticated;

grant insert, update, delete on table public.student_answers, public.practice_progress,
  public.student_word_progress to authenticated;

-- 20. Realtime
do $$
begin
  if exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'student_answers'
  ) then
    alter publication supabase_realtime drop table public.student_answers;
  end if;
  if exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'session_students'
  ) then
    alter publication supabase_realtime drop table public.session_students;
  end if;
end $$;

alter publication supabase_realtime add table public.student_answers;
alter publication supabase_realtime add table public.session_students;

-- 21. 注释
comment on table public.topics is '题目主题分类，来源于 manifest.csv';
comment on table public.students is '学生实名账号，bcrypt 密码哈希';
comment on table public.session_students is '学生加入课堂/练习的记录';
comment on table public.student_answers is '学生答案，支持选择题和非选择题';
comment on table public.practice_progress is '学生课后练习进度';
comment on table public.vocabulary_words is '单词库，按年级分类';
comment on table public.student_word_progress is '学生单词复习进度，间隔算法';
comment on column public.questions.question_type is '题目类型：single_choice 或 text_input';
comment on column public.student_answers.answer_type is '答案类型：single_choice 或 text_input';
comment on column public.student_answers.is_correct is '选择题自动判分，非选择题为 NULL';
comment on column public.student_word_progress.level is '复习等级 1-10，影响下次复习时间';
