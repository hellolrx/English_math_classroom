-- 第一步：只读检查。运行结果用于确认目标项目及重建范围，不删除数据。
select current_database() as database_name, current_user as executing_role,
       version() as postgres_version;

select n.nspname as schema_name, c.relname as object_name, c.relkind,
       c.relrowsecurity as rls_enabled
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm')
order by c.relname;

select p.proname, pg_get_function_identity_arguments(p.oid) as arguments
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' order by p.proname;

select tablename, policyname, roles, cmd from pg_policies
where schemaname = 'public' order by tablename, policyname;

-- 保留全部 Auth 用户，但只重新关联原 teacher_profiles 中的老师；不会把所有用户变成老师。
select count(*) as preserved_auth_users from auth.users;
select id, name, public from storage.buckets order by id;
select bucket_id, count(*) as preserved_files from storage.objects group by bucket_id;

-- 返回非空表示已执行过本版重建，不应再次运行 01。
select to_regclass('public.app_schema_state') as rebuild_marker;

-- Supabase SQL Editor 若只显示最后一个结果集，请复制这一条作为单独查询运行。
select jsonb_pretty(jsonb_build_object(
  'database_name', current_database(),
  'executing_role', current_user,
  'rebuild_marker', to_regclass('public.app_schema_state')::text,
  'public_relations', coalesce((
    select jsonb_agg(jsonb_build_object('name', c.relname, 'kind', c.relkind,
      'rls', c.relrowsecurity) order by c.relname)
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind in ('r','p','v','m')
  ), '[]'::jsonb),
  'public_policies', coalesce((
    select jsonb_agg(jsonb_build_object('table', tablename, 'name', policyname,
      'roles', roles, 'command', cmd) order by tablename, policyname)
    from pg_policies where schemaname = 'public'
  ), '[]'::jsonb),
  'auth_user_count', (select count(*) from auth.users),
  'teacher_profiles', case when to_regclass('public.teacher_profiles') is null then null else (
    select coalesce(jsonb_agg(jsonb_build_object('id', id, 'display_name', display_name,
      'active', is_active) order by id), '[]'::jsonb) from public.teacher_profiles
  ) end,
  'storage_buckets', coalesce((
    select jsonb_agg(jsonb_build_object('id', b.id, 'name', b.name, 'public', b.public,
      'objects', (select count(*) from storage.objects o where o.bucket_id = b.id)) order by b.id)
    from storage.buckets b
  ), '[]'::jsonb)
)) as preflight_summary;
