-- 首版默认学校、年级和班级数据。
-- teacher_profiles 需要关联 Supabase Auth 用户，因此 admin 账号由部署步骤单独创建。

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
