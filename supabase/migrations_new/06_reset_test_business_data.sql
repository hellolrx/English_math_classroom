-- 测试数据清理脚本：保留老师、学生、班级、年级和主题目录。
-- 仅清理数学题库批次、课堂、练习及答题记录，执行前确认当前项目允许丢弃这些数据。
-- 这是一次性手动脚本，不要作为生产迁移重复执行。

begin;

-- 先删除依赖答题记录的课堂和练习数据。
delete from public.classroom_answers;
delete from public.classroom_participants;
delete from public.classroom_session_questions;
delete from public.classroom_sessions;

delete from public.practice_answers;
delete from public.practice_rounds;
delete from public.practice_questions;
delete from public.practices;

-- 数据库触发器禁止删除已发布/归档批次中的题目；测试清理前先将批次降为草稿。
update public.math_batches
set status = 'draft', published_at = null
where status <> 'draft';

-- 删除题目后才能删除批次；导入任务保留不了已删除的批次，因此一并清理。
delete from public.questions;
delete from public.math_batches;
delete from public.import_jobs where kind = 'math';

commit;

select
  (select count(*) from public.questions) as remaining_questions,
  (select count(*) from public.math_batches) as remaining_math_batches,
  (select count(*) from public.classroom_sessions) as remaining_classrooms,
  (select count(*) from public.practices) as remaining_practices,
  (select count(*) from public.practice_rounds) as remaining_rounds;
