"""Exercise business endpoints with Supabase responses; no cloud writes."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request


SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))
platform_modules = {
    "js": types.SimpleNamespace(Object=object, Uint8Array=object, fetch=None),
    "pyodide": types.ModuleType("pyodide"),
    "pyodide.ffi": types.SimpleNamespace(to_js=lambda value, **kwargs: value),
    "workers": types.SimpleNamespace(asgi=types.SimpleNamespace(entrypoint=lambda app: app)),
}
spec = importlib.util.spec_from_file_location("business_api", SOURCE / "main.py")
api = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, platform_modules):
    spec.loader.exec_module(api)


class BusinessFlows(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.request = Request({"type": "http", "headers": []})
        self.teacher = patch.object(api, "current_teacher_profile", AsyncMock(return_value={"user_id": "teacher", "school_id": "school"}))
        self.student = patch.object(api, "verify_student_token", AsyncMock(return_value={"id": "student", "school_id": "school"}))
        self.teacher.start()
        self.student.start()
        self.addCleanup(self.teacher.stop)
        self.addCleanup(self.student.stop)

    async def test_classroom_creation_keeps_duration_and_order(self):
        database = AsyncMock(side_effect=[
            (200, [{"id": "batch", "topics": {"school_id": "school", "is_active": True}}]),
            (200, [{"id": "q1", "sort_order": 1}, {"id": "q3", "sort_order": 3}]),
            (200, [{"id": "class"}]),
            (201, [{"id": "session", "access_token": "access"}]),
            (201, []),
        ])
        with patch.object(api, "supabase_request", database):
            result = await api.create_session(api.CreateSessionRequest(batch_id="batch", class_id="class", time_limit_seconds=30), self.request, "Bearer token")
        self.assertEqual(result["question_count"], 2)
        self.assertTrue(result["join_url"].endswith("/student/session/access"))
        self.assertEqual(database.call_args_list[1].kwargs["params"]["question_type"], "eq.single_choice")
        self.assertEqual(database.call_args_list[3].kwargs["body"]["duration_seconds"], 30)
        self.assertEqual([row["sort_order"] for row in database.call_args_list[4].kwargs["body"]], [1, 3])

    async def test_homework_accepts_text_questions_without_class_binding(self):
        database = AsyncMock(side_effect=[
            (200, [{"topics": {"school_id": "school", "is_active": True}}]),
            (200, [{"id": "text", "sort_order": 1}]),
            (200, "practice"),
        ])
        with patch.object(api, "supabase_request", database):
            result = await api.create_session(api.CreateSessionRequest(batch_id="batch", session_type="homework", time_limit_seconds=0), self.request, "Bearer token")
        self.assertEqual(result["id"], "practice")
        self.assertNotIn("question_type", database.call_args_list[1].kwargs["params"])
        self.assertNotIn("class_id", database.call_args_list[2].kwargs["body"])

    async def test_foreign_school_batch_is_rejected_before_any_write(self):
        database = AsyncMock(return_value=(200, [{"topics": {"school_id": "other", "is_active": True}}]))
        with patch.object(api, "supabase_request", database), self.assertRaises(HTTPException) as error:
            await api.create_session(api.CreateSessionRequest(batch_id="batch", class_id="class"), self.request, "Bearer token")
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(database.call_count, 1)

    async def test_failed_question_link_cleans_up_only_new_session(self):
        database = AsyncMock(side_effect=[
            (200, [{"topics": {"school_id": "school", "is_active": True}}]),
            (200, [{"id": "q", "sort_order": 1}]), (200, [{"id": "class"}]),
            (201, [{"id": "new-session", "access_token": "access"}]),
            (409, {}), (204, None),
        ])
        with patch.object(api, "supabase_request", database), self.assertRaises(HTTPException):
            await api.create_session(api.CreateSessionRequest(batch_id="batch", class_id="class"), self.request, "Bearer token")
        cleanup = database.call_args_list[-1]
        self.assertEqual(cleanup.args[1:3], ("DELETE", "/rest/v1/classroom_sessions"))
        self.assertEqual(cleanup.kwargs["params"], {"id": "eq.new-session"})

    async def test_learning_excludes_learned_words_in_selected_grade(self):
        database = AsyncMock(side_effect=[
            (200, [{"id": "s6-grade"}]),
            (200, [{"id": "learned"}, {"id": "new"}]),
            (200, [{"word_id": "learned"}]),
        ])
        with patch.object(api, "supabase_request", database):
            words = await api.student_words(self.request, "S6", "Bearer token")
        self.assertEqual(words, [{"id": "new"}])
        self.assertEqual(database.call_args_list[-1].kwargs["params"]["student_id"], "eq.student")
        self.assertEqual(database.call_args_list[-1].kwargs["params"]["words.grade_id"], "eq.s6-grade")

    async def test_stats_merge_classroom_by_student_class_and_count_text(self):
        database = AsyncMock(side_effect=[
            (200, [{"id": "class"}]),
            (200, [{"topics": {"school_id": "school", "code": "00", "name": "topic"}}]),
            (200, [{"id": "student"}]),
            (200, [{"id": "round", "student_id": "student", "completed_at": "2026-10-10T10:00:00Z"}]),
            (200, [{"round_id": "round", "question_id": "text", "text_answer": "我的答案", "is_correct": None}]),
            (200, [{"id": "text", "sort_order": 1, "question_type": "text_input"}, {"id": "choice", "sort_order": 2, "question_type": "single_choice", "correct_option": "B"}]),
            (200, [{"id": "session-in-another-class"}]),
            (200, [{"student_id": "student", "question_id": "choice", "selected_option": "B", "is_correct": True, "answered_at": "2026-10-10T11:00:00Z"}]),
            (200, [{"student_id": "student"}]),
            (200, [{"id": "student", "name": "测试学生"}]),
        ])
        with patch.object(api, "supabase_request", database):
            result = await api.teacher_practice_summary(self.request, "class", "batch", "Bearer token")
        self.assertEqual(result["participant_count"], 1)
        self.assertEqual(result["questions"][0]["submitted_count"], 1)
        self.assertEqual(result["questions"][0]["unanswered_count"], 0)
        self.assertEqual(result["questions"][0]["text_answers"][0]["answer"], "我的答案")
        self.assertEqual(result["questions"][1]["accuracy"], 100)
        sessions_filter = database.call_args_list[6].kwargs["params"]
        self.assertNotIn("class_id", sessions_filter)
        self.assertEqual(sessions_filter["classes.school_id"], "eq.school")
        for index in (7, 8):
            self.assertEqual(database.call_args_list[index].kwargs["params"]["student_id"], "in.(student)")


if __name__ == "__main__":
    unittest.main()
