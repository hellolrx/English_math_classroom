-- 给已执行 01_rebuild.sql 的项目补充学生登录验证 RPC。
-- 密码明文只在 HTTPS 请求和函数调用期间传递，绝不从 RPC 返回密码哈希。
create or replace function public.app_authenticate_student(
  p_student_number text,
  p_password text
)
returns table (
  student_id uuid,
  name text,
  student_number text,
  school_id uuid,
  grade_id uuid,
  grade_code text,
  class_id uuid,
  class_name text,
  auth_version integer
)
language sql
stable
security definer
set search_path = public, extensions, pg_catalog
as $$
  select s.id, s.name, s.student_number, s.school_id, s.grade_id,
         g.code, s.class_id, c.name, s.auth_version
    from public.students s
    join public.grades g on g.id = s.grade_id and g.school_id = s.school_id
    join public.classes c on c.id = s.class_id and c.grade_id = g.id and c.school_id = s.school_id
   where s.student_number = btrim(p_student_number)
     and s.is_active and g.is_active and c.is_active
     and s.password_hash = crypt(p_password, s.password_hash)
  limit 1;
$$;

revoke all on function public.app_authenticate_student(text, text) from public, anon, authenticated;
grant execute on function public.app_authenticate_student(text, text) to service_role;
notify pgrst, 'reload schema';
