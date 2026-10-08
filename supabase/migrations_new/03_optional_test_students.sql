-- 可选：01、02 成功后才执行。创建三个测试账号：hhx001、hhx002、hhx003。
-- 三个账号密码均为 123，仅用于本地/测试环境验证；生产环境不要使用此密码。
-- 不会自动创建老师；不覆盖已经存在的学生或修改其密码。
begin;
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
do $$
declare
  initial_password text := '123';
  crypto_schema text;
  hashed_password text;
begin
  if initial_password is null or length(initial_password) < 3 or octet_length(initial_password) > 72 then
    raise exception '测试密码长度必须为 3 至 72 字节';
  end if;
  select n.nspname into crypto_schema from pg_extension e join pg_namespace n on n.oid = e.extnamespace
    where e.extname = 'pgcrypto';
  execute format('select %I.crypt($1,%I.gen_salt(''bf'',12))',crypto_schema,crypto_schema)
    into hashed_password using initial_password;
  insert into public.students(school_id,grade_id,class_id,student_number,name,password_hash)
  select g.school_id,g.id,c.id,v.student_number,v.student_name,hashed_password
    from (values ('S1','hhx001','测试学生 001'),('S3','hhx002','测试学生 002'),('S6','hhx003','测试学生 003')) v(grade_code,student_number,student_name)
    join public.grades g on g.code = v.grade_code and g.school_id = '00000000-0000-0000-0000-000000000001'
    join public.classes c on c.grade_id = g.id and c.code = 'A'
  on conflict (school_id,student_number) do nothing;
end $$;
commit;
select student_number,name from public.students where student_number in ('hhx001','hhx002','hhx003') order by student_number;
