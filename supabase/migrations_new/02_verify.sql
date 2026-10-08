-- 第三步：只读验证。每项 passed 应为 true；老师数量可为 0，需要单独关联已有老师账号。
with business_tables(name) as (
  values ('app_schema_state'),('schools'),('teacher_profiles'),('grades'),('classes'),
    ('students'),('student_sessions'),('topics'),('import_jobs'),('math_batches'),('questions'),
    ('practices'),('practice_questions'),('practice_rounds'),('practice_answers'),
    ('classroom_sessions'),('classroom_session_questions'),('classroom_participants'),
    ('classroom_answers'),('word_batches'),('words'),('word_progress')
), checks as (
  select '业务表完整且开启 RLS（22 张）' as check_name,
    (select count(*) = 22 and bool_and(c.relrowsecurity)
     from business_tables b left join pg_namespace n on n.nspname = 'public'
     left join pg_class c on c.relnamespace = n.oid and c.relname = b.name
     where c.relkind = 'r') as passed
  union all select '初始化：1 所学校、6 个年级、36 个班级、61 个主题',
    (select count(*) = 1 from public.schools) and (select count(*) = 6 from public.grades)
    and (select count(*) = 36 from public.classes) and (select count(*) = 61 from public.topics)
  union all select '完整主题编号：00–59 和 99',
    not exists (select lpad(n::text,2,'0') from generate_series(0,59) n
      except select code from public.topics) and exists(select 1 from public.topics where code = '99')
  union all select '本版标记存在', exists(select 1 from public.app_schema_state where version = '20261008_real_students_v1')
  union all select '旧匿名和独立选项表已移除',
    to_regclass('public.anonymous_devices') is null and to_regclass('public.question_options') is null
    and to_regclass('public.question_sets') is null and to_regclass('public.sessions') is null
  union all select '浏览器角色无业务表读取或写入权限', not exists (
    select 1 from business_tables b cross join (values('anon'),('authenticated')) r(role_name)
    where has_table_privilege(r.role_name,'public.' || b.name,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE'))
  union all select '浏览器角色无 app RPC 执行权限', not exists (
    select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    cross join (values('anon'),('authenticated')) r(role_name)
    where n.nspname = 'public' and left(p.proname,4) = 'app_'
      and has_function_privilege(r.role_name,p.oid,'EXECUTE'))
  union all select '后端 service_role 可访问业务表', not exists (
    select 1 from business_tables b where not has_table_privilege('service_role','public.' || b.name,'SELECT')
       or not has_table_privilege('service_role','public.' || b.name,'INSERT'))
  union all select '新图片桶为私有且限制 1MB', exists (
    select 1 from storage.buckets where id = 'question-images-v2' and not public and file_size_limit = 1048576)
)
select * from checks order by check_name;

select (select count(*) from auth.users) as preserved_auth_users,
       (select count(*) from public.teacher_profiles) as linked_teachers,
       (select count(*) from public.students) as students,
       (select count(*) from public.questions) as math_questions;
select p.id,p.display_name,p.is_active,u.email
from public.teacher_profiles p join auth.users u on u.id = p.id;
select code,name from public.topics order by sort_order;
