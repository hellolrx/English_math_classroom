-- 首版默认学校、年级和班级数据。
-- teacher_profiles 需要关联 Supabase Auth 用户，因此 admin 账号由部署步骤单独创建。
-- students 表的 password_hash 使用 bcrypt，默认密码为 "123456"。

insert into public.schools (id, name)
values ('00000000-0000-0000-0000-000000000001', 'Default School')
on conflict (id) do update
set name = excluded.name,
    is_active = true;

insert into public.grades (id, school_id, code, name, sort_order)
values
  ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'S1', 'S1', 1),
  ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'S2', 'S2', 2),
  ('10000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', 'S3', 'S3', 3),
  ('10000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001', 'S4', 'S4', 4),
  ('10000000-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000001', 'S5', 'S5', 5),
  ('10000000-0000-0000-0000-000000000006', '00000000-0000-0000-0000-000000000001', 'S6', 'S6', 6)
on conflict (id) do update
set school_id = excluded.school_id,
    code = excluded.code,
    name = excluded.name,
    sort_order = excluded.sort_order,
    is_active = true;

insert into public.classes (grade_id, code, name, expected_student_count)
select g.id, c.code, g.code || c.code, 30
from public.grades g
cross join (values ('A'), ('B'), ('C'), ('D'), ('E'), ('F')) as c(code)
where g.school_id = '00000000-0000-0000-0000-000000000001'
on conflict (grade_id, code) do update
set name = excluded.name,
    expected_student_count = excluded.expected_student_count,
    is_active = true;

-- 测试学生账号（密码均为 "123456"，bcrypt hash）
insert into public.students (school_id, student_no, name, grade_id, class_id, password_hash, must_change_password)
values
  ('00000000-0000-0000-0000-000000000001', 'S6A001', '张小明', '10000000-0000-0000-0000-000000000006',
   (select id from public.classes where grade_id = '10000000-0000-0000-0000-000000000006' and code = 'A'),
   '$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy', true),
  ('00000000-0000-0000-0000-000000000001', 'S6A002', '李小红', '10000000-0000-0000-0000-000000000006',
   (select id from public.classes where grade_id = '10000000-0000-0000-0000-000000000006' and code = 'A'),
   '$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy', true),
  ('00000000-0000-0000-0000-000000000001', 'S5A001', '王小强', '10000000-0000-0000-0000-000000000005',
   (select id from public.classes where grade_id = '10000000-0000-0000-0000-000000000005' and code = 'A'),
   '$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy', true)
on conflict (school_id, student_no) do update
set name = excluded.name,
    grade_id = excluded.grade_id,
    class_id = excluded.class_id,
    password_hash = excluded.password_hash,
    must_change_password = excluded.must_change_password,
    is_active = true;
