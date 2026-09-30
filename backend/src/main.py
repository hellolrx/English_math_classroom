from __future__ import annotations

import json
import hashlib
import hmac
import base64
import secrets
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from js import Object, fetch
from pyodide.ffi import to_js
from workers import asgi

from services.excel_parser import ExcelImportError, ParsedQuestion, parse_question_excel
from services.auth import StudentLoginRequest, ChangePasswordRequest, hash_password, verify_password, create_student_token, decode_jwt
from services.student_api import router as student_router
from services.topics_api import router as topics_router
from services.vocabulary_api import router as vocabulary_router
from services.session_api import router as session_router


app = FastAPI(title="HHX English Math Classroom API", version="0.1.0")

# Include routers
app.include_router(student_router)
app.include_router(topics_router)
app.include_router(vocabulary_router)
app.include_router(session_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_origin_regex=r"https://[a-z0-9-]+\.pages\.dev",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    mode: str = Field(default="teacher", pattern="^(teacher|student)$")


class StudentLoginPayload(BaseModel):
    student_no: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class CreateSessionRequest(BaseModel):
    topic_id: str | None = None
    question_set_id: str | None = None
    class_id: str = Field(min_length=1)
    session_type: str = Field(default="classroom")
    time_limit_seconds: int | None = Field(default=30, ge=0, le=600)
    
    def __init__(self, **data):
        super().__init__(**data)
        # Validate: exactly one of topic_id or question_set_id must be provided
        if not self.topic_id and not self.question_set_id:
            raise ValueError("必須提供 topic_id 或 question_set_id")
        if self.topic_id and self.question_set_id:
            raise ValueError("不能同時提供 topic_id 和 question_set_id")


class StudentLoginPayload(BaseModel):
    student_no: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def public_question(question: dict[str, Any], options: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": question["id"],
        "sort_order": question["sort_order"],
        "question_text": question.get("question_text"),
        "question_image_url": question.get("question_image_url"),
        "explanation": question.get("explanation"),
        "question_type": question.get("question_type"),
        "content_type": question.get("content_type"),
        "options": [
            {
                "id": option["id"],
                "option_key": option["option_key"],
                "option_text": option.get("option_text"),
                "option_image_url": option.get("option_image_url"),
                "content_type": option.get("content_type"),
            }
            for option in options
        ],
    }


def request_env(request: Request) -> Any:
    return request.scope.get("env")


def env_value(request: Request, name: str, default: str = "") -> str:
    runtime_env = request_env(request)
    value = getattr(runtime_env, name, None) if runtime_env is not None else None
    return str(value or default)


def student_token_secret(request: Request) -> bytes:
    secret = env_value(request, "STUDENT_SESSION_SECRET") or env_value(request, "SUPABASE_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=503, detail="後端尚未設定學生登入密鑰")
    return secret.encode("utf-8")


def supabase_headers(
    request: Request,
    access_token: str | None = None,
    *,
    service_role: bool = False,
    prefer_representation: bool = False,
) -> dict[str, str]:
    if service_role:
        api_key = env_value(request, "SUPABASE_SECRET_KEY") or env_value(request, "SUPABASE_SERVICE_ROLE_KEY")
    else:
        api_key = env_value(request, "SUPABASE_ANON_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="後端尚未設定 Supabase API Key")
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    if service_role:
        headers["Authorization"] = f"Bearer {api_key}"
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if prefer_representation:
        headers["Prefer"] = "return=representation"
    return headers


def supabase_url(request: Request) -> str:
    value = env_value(request, "SUPABASE_URL").rstrip("/")
    if not value:
        raise HTTPException(status_code=503, detail="後端尚未設定 Supabase URL")
    return value


async def supabase_request(
    request: Request,
    method: str,
    path: str,
    *,
    access_token: str | None = None,
    body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
    service_role: bool = False,
    prefer_representation: bool = False,
) -> tuple[int, Any]:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            url = f"{supabase_url(request)}{path}"
            if params:
                from urllib.parse import urlencode
                url = f"{url}?{urlencode(params)}"
            request_headers = supabase_headers(
                request,
                access_token,
                service_role=service_role,
                prefer_representation=prefer_representation,
            )
            request_init: dict[str, Any] = {"method": method, "headers": request_headers}
            if body is not None:
                request_init["body"] = json.dumps(body)
            response = await fetch(url, to_js(request_init, dict_converter=Object.fromEntries))
            response_text = str(await response.text())
            try:
                payload = json.loads(response_text)
            except json.JSONDecodeError:
                payload = {"message": response_text[:300]}
            return int(response.status), payload
        except Exception as exc:
            last_error = exc
            if attempt == 1:
                return 599, {"message": str(exc)[:300]}
            await asyncio.sleep(0.05)
    return 599, {"message": str(last_error)[:300] if last_error else "Supabase request failed"}


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="請先登入")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="登入狀態無效")
    return token


async def current_teacher_profile(request: Request, token: str) -> dict[str, Any]:
    user_status, user = await supabase_request(request, "GET", "/auth/v1/user", access_token=token)
    if user_status >= 400 or not user.get("id"):
        raise HTTPException(status_code=401, detail="登入狀態已失效，請重新登入")
    profile_status, profiles = await supabase_request(
        request,
        "GET",
        "/rest/v1/teacher_profiles",
        access_token=token,
        params={"id": f"eq.{user['id']}", "select": "id,display_name,school_id,is_active"},
    )
    if profile_status >= 400 or not profiles:
        raise HTTPException(status_code=403, detail="此帳號尚未建立老師資料")
    profile = profiles[0]
    if not profile.get("is_active"):
        raise HTTPException(status_code=403, detail="此老師帳號已停用")
    return {"user_id": user["id"], **profile}


def import_error_response(error: ExcelImportError) -> HTTPException:
    return HTTPException(status_code=422, detail={"message": str(error), "errors": error.errors})


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "hhx-backend"}


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, Any]:
    username = payload.username.strip()
    
    if payload.mode == "student":
        # Student login with bcrypt
        status, students = await supabase_request(
            request,
            "GET",
            "/rest/v1/students",
            params={
                "select": "id,student_no,password_hash,grade_id,class_id,must_change_password,is_active",
                "student_no": f"eq.{username}",
                "is_active": "eq:true",
                "limit": "1",
            },
        )
        if status >= 400:
            raise HTTPException(status_code=502, detail="服務器錯誤")
        
        if not isinstance(students, list) or not students:
            raise HTTPException(status_code=401, detail="帳號或密碼不正確")
        
        student = students[0]
        
        # Verify password with bcrypt
        if not verify_password(payload.password, student["password_hash"]):
            raise HTTPException(status_code=401, detail="帳號或密碼不正確")
        
        # Create JWT token
        token = create_student_token(
            student_id=student["id"],
            student_no=student["student_no"],
            grade_id=student["grade_id"]
        )
        
        # Update last_login_at
        await supabase_request(
            request,
            "PATCH",
            "/rest/v1/students",
            params={"id": f"eq.{student['id']}"},
            body={"last_login_at": utc_now().isoformat()},
        )
        
        return {
            "mode": "student",
            "access_token": token,
            "user": {
                "id": student["id"],
                "student_no": student["student_no"],
                "display_name": f"學生{student['student_no']}",
                "must_change_password": student.get("must_change_password", False),
            },
        }
    else:
        # Teacher login via Supabase Auth
        configured_email = env_value(request, "TEACHER_LOGIN_EMAIL", "admin@hhx.local")
        email = configured_email if username.lower() == "admin" else username
        if "@" not in email:
            raise HTTPException(status_code=401, detail="帳號或密碼不正確")
        
        status, result = await supabase_request(
            request,
            "POST",
            "/auth/v1/token",
            params={"grant_type": "password"},
            body={"email": email, "password": payload.password},
        )
        if status >= 400:
            raise HTTPException(status_code=401, detail="帳號或密碼不正確")
        
        return {
            "mode": "teacher",
            "access_token": result.get("access_token"),
            "expires_in": result.get("expires_in"),
            "user": result.get("user"),
        }


@app.get("/api/auth/me")
async def current_teacher(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    profile = await current_teacher_profile(request, token)
    return profile


@app.get("/api/question-sets")
async def list_question_sets(
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    status, result = await supabase_request(
        request,
        "GET",
        "/rest/v1/question_sets",
        access_token=token,
        params={
            "select": "id,name,source_filename,status,version,grade_id,created_at,updated_at,archived_at,questions(count)",
            "status": "neq.archived",
            "order": "created_at.desc",
        },
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="无法读取题目集合")
    normalized_sets: list[dict[str, Any]] = []
    for question_set in result:
        count_rows = question_set.pop("questions", [{"count": 0}])
        normalized_sets.append({**question_set, "question_count": (count_rows[0] or {}).get("count", 0)})
    return normalized_sets


@app.post("/api/question-sets/{question_set_id}/archive")
async def archive_question_set(
    question_set_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    status, sets = await supabase_request(
        request,
        "GET",
        "/rest/v1/question_sets",
        access_token=token,
        params={"id": f"eq.{question_set_id}", "select": "id,name,status"},
    )
    if status >= 400 or not sets:
        raise HTTPException(status_code=404, detail="找不到題目集合")
    if sets[0]["status"] == "archived":
        return sets[0]
    update_status, updated = await supabase_request(
        request,
        "PATCH",
        "/rest/v1/question_sets",
        service_role=True,
        prefer_representation=True,
        params={"id": f"eq.{question_set_id}"},
        body={"status": "archived", "archived_at": utc_now().isoformat()},
    )
    if update_status >= 400 or not updated:
        raise HTTPException(status_code=502, detail="題目集合归档失败")
    return updated[0]


@app.post("/api/question-sets/{question_set_id}/publish")
async def publish_question_set(
    question_set_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    status, sets = await supabase_request(
        request,
        "GET",
        "/rest/v1/question_sets",
        access_token=token,
        params={"id": f"eq.{question_set_id}", "select": "id,name,status"},
    )
    if status >= 400 or not sets:
        raise HTTPException(status_code=404, detail="找不到题目集合")
    if sets[0]["status"] == "published":
        return sets[0]
    if sets[0]["status"] == "archived":
        raise HTTPException(status_code=409, detail="已归档的题目集合不能发布")
    update_status, updated = await supabase_request(
        request,
        "PATCH",
        "/rest/v1/question_sets",
        service_role=True,
        prefer_representation=True,
        params={"id": f"eq.{question_set_id}"},
        body={"status": "published"},
    )
    if update_status >= 400 or not updated:
        raise HTTPException(status_code=422, detail="题目集合内容不完整，无法发布")
    return updated[0]


@app.get("/api/question-sets/{question_set_id}")
async def get_question_set(
    question_set_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    set_status, sets = await supabase_request(
        request,
        "GET",
        "/rest/v1/question_sets",
        access_token=token,
        params={"id": f"eq.{question_set_id}", "select": "id,name,source_filename,status,version,grade_id,created_at,updated_at,archived_at"},
    )
    if set_status >= 400 or not sets:
        raise HTTPException(status_code=404, detail="找不到题目集合")
    question_status, questions = await supabase_request(
        request,
        "GET",
        "/rest/v1/questions",
        access_token=token,
        params={
            "question_set_id": f"eq.{question_set_id}",
            "select": "id,sort_order,question_text,question_image_url,explanation,question_type,content_type,language,correct_option_id",
            "order": "sort_order.asc",
        },
    )
    if question_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取题目")
    question_ids = [question["id"] for question in questions]
    options: list[dict[str, Any]] = []
    if question_ids:
        option_status, options = await supabase_request(
            request,
            "GET",
            "/rest/v1/question_options",
            access_token=token,
            params={
                "question_id": f"in.({','.join(question_ids)})",
                "select": "id,question_id,option_key,option_text,option_image_url,content_type",
                "order": "option_key.asc",
            },
        )
        if option_status >= 400:
            raise HTTPException(status_code=502, detail="无法读取选项")
    options_by_question: dict[str, list[dict[str, Any]]] = {}
    for option in options:
        options_by_question.setdefault(option["question_id"], []).append(option)
    return {
        **sets[0],
        "questions": [
            {**question, "options": options_by_question.get(question["id"], [])}
            for question in questions
        ],
    }


@app.post("/api/question-sets/preview")
async def preview_question_set(
    request: Request,
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="只支持 .xlsx 格式的 Excel 文件")
    try:
        questions = parse_question_excel(await file.read())
    except ExcelImportError as error:
        raise import_error_response(error) from error
    return {
        "filename": file.filename,
        "question_count": len(questions),
        "questions": [
            {
                "row_number": question.row_number,
                "question_text": question.question_text,
                "question_image_url": question.question_image_url,
                "options": question.options,
                "option_image_urls": question.option_image_urls,
                "correct_answer": question.correct_answer,
                "explanation": question.explanation,
            }
            for question in questions
        ],
    }


async def cleanup_question_set(request: Request, question_set_id: str, question_ids: list[str]) -> None:
    if question_ids:
        await supabase_request(
            request,
            "DELETE",
            "/rest/v1/question_options",
            params={"question_id": f"in.({','.join(question_ids)})"},
            service_role=True,
            prefer_representation=True,
        )
        await supabase_request(
            request,
            "DELETE",
            "/rest/v1/questions",
            params={"id": f"in.({','.join(question_ids)})"},
            service_role=True,
            prefer_representation=True,
        )
    await supabase_request(
        request,
        "DELETE",
        "/rest/v1/question_sets",
        params={"id": f"eq.{question_set_id}"},
        service_role=True,
        prefer_representation=True,
    )


@app.post("/api/question-sets/import")
async def import_question_set(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    grade_id: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    teacher = await current_teacher_profile(request, token)
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="题目集合名称不能为空")
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="只支持 .xlsx 格式的 Excel 文件")
    try:
        file_content = await file.read()
        questions = parse_question_excel(file_content)
    except ExcelImportError as error:
        raise import_error_response(error) from error

    question_set_id = str(uuid4())
    question_ids = [str(uuid4()) for _ in questions]
    set_status, set_result = await supabase_request(
        request,
        "POST",
        "/rest/v1/question_sets",
        service_role=True,
        prefer_representation=True,
        body={
            "id": question_set_id,
            "school_id": teacher["school_id"],
            "created_by": teacher["user_id"],
            "name": clean_name,
            "source_filename": file.filename,
            "grade_id": grade_id or None,
            # 导入期间先使用内部草稿状态，等待题目、选项和正确答案全部写入后再发布。
            # 这样不会触发已发布题目的不可修改保护；该中间状态不会返回给前端。
            "status": "draft",
            "version": 1,
        },
    )
    if set_status >= 400:
        raise HTTPException(status_code=502, detail="创建题目集合失败")

    question_rows = [
        {
            "id": question_id,
            "question_set_id": question_set_id,
            "sort_order": order,
            "question_text": question.question_text,
            "question_image_url": question.question_image_url,
            "explanation": question.explanation,
            "question_type": "single_choice",
            "content_type": "image" if question.question_image_url else "text",
            "language": "en",
        }
        for order, (question_id, question) in enumerate(zip(question_ids, questions), start=1)
    ]
    option_rows: list[dict[str, Any]] = []
    answer_option_ids: list[tuple[str, str]] = []
    for question_id, question in zip(question_ids, questions):
        options_by_key: dict[str, str] = {}
        for key in ("A", "B", "C", "D"):
            option_id = str(uuid4())
            options_by_key[key] = option_id
            option_rows.append(
                {
                    "id": option_id,
                    "question_id": question_id,
                    "option_key": key,
                    "option_text": question.options[key],
                    "option_image_url": question.option_image_urls[key],
                    "content_type": "image" if question.option_image_urls[key] else "text",
                }
            )
        answer_option_ids.append((question_id, options_by_key[question.correct_answer]))

    try:
        question_status, _ = await supabase_request(
            request,
            "POST",
            "/rest/v1/questions",
            service_role=True,
            prefer_representation=True,
            body=question_rows,
        )
        option_status, _ = await supabase_request(
            request,
            "POST",
            "/rest/v1/question_options",
            service_role=True,
            prefer_representation=True,
            body=option_rows,
        )
        if question_status >= 400 or option_status >= 400:
            raise RuntimeError("写入题目或选项失败")
        for question_id, option_id in answer_option_ids:
            update_status, _ = await supabase_request(
                request,
                "PATCH",
                "/rest/v1/questions",
                service_role=True,
                prefer_representation=True,
                params={"id": f"eq.{question_id}"},
                body={"correct_option_id": option_id},
            )
            if update_status >= 400:
                raise RuntimeError("写入正确答案失败")

        publish_status, _ = await supabase_request(
            request,
            "PATCH",
            "/rest/v1/question_sets",
            service_role=True,
            prefer_representation=True,
            params={"id": f"eq.{question_set_id}"},
            body={"status": "published"},
        )
        if publish_status >= 400:
            raise RuntimeError("发布题目集合失败")
    except Exception as exc:
        await cleanup_question_set(request, question_set_id, question_ids)
        raise HTTPException(status_code=502, detail="题目导入失败，未保留不完整数据") from exc

    return {
        "id": question_set_id,
        "name": clean_name,
        "status": "published",
        "question_count": len(questions),
        "source_filename": file.filename,
    }


async def find_session_by_token(request: Request, access_token: str) -> dict[str, Any]:
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        service_role=True,
        params={
            "access_token": f"eq.{access_token}",
            "select": "id,created_by,question_set_id,class_id,session_type,access_token,status,current_question_id,current_question_status,starts_at,expires_at,closed_at,time_limit_seconds,question_started_at",
        },
    )
    if status >= 400 or not sessions:
        raise HTTPException(status_code=404, detail="找不到课堂场次或二维码已失效")
    session = sessions[0]
    if session["expires_at"] <= utc_now().isoformat():
        raise HTTPException(status_code=410, detail="二维码已过期")
    return session


async def session_questions(request: Request, question_set_id: str) -> list[dict[str, Any]]:
    status, questions = await supabase_request(
        request,
        "GET",
        "/rest/v1/questions",
        service_role=True,
        params={
            "question_set_id": f"eq.{question_set_id}",
            "select": "id,sort_order,question_text,question_image_url,explanation,question_type,content_type,language,correct_option_id",
            "order": "sort_order.asc",
        },
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="无法读取课堂题目")
    return questions


def elapsed_seconds(started_at: str | None) -> float | None:
    if not started_at:
        return None
    try:
        value = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        return (utc_now() - value).total_seconds()
    except (TypeError, ValueError):
        return None


async def advance_expired_session(request: Request, session: dict[str, Any]) -> dict[str, Any]:
    """在课堂请求到达时兜底推进到下一题，避免只依赖老师浏览器计时。"""
    if session.get("session_type") != "classroom" or session.get("status") != "active":
        return session
    limit = int(session.get("time_limit_seconds") or 0)
    elapsed = elapsed_seconds(session.get("question_started_at"))
    current_id = session.get("current_question_id")
    if limit <= 0 or elapsed is None or elapsed < limit or not current_id:
        return session
    questions = await session_questions(request, session["question_set_id"])
    current_index = next((index for index, question in enumerate(questions) if question["id"] == current_id), -1)
    now = utc_now().isoformat()
    if current_index < 0 or current_index + 1 >= len(questions):
        body = {"status": "closed", "current_question_status": "locked", "closed_at": now, "question_started_at": None}
    else:
        body = {"status": "active", "current_question_id": questions[current_index + 1]["id"], "current_question_status": "open", "question_started_at": now}
    update_status, updated = await supabase_request(
        request,
        "PATCH",
        "/rest/v1/sessions",
        service_role=True,
        prefer_representation=True,
        params={"id": f"eq.{session['id']}", "current_question_id": f"eq.{current_id}"},
        body=body,
    )
    if update_status < 400 and updated:
        return updated[0]
    if update_status < 400:
        latest_status, latest = await supabase_request(
            request,
            "GET",
            "/rest/v1/sessions",
            service_role=True,
            params={
                "id": f"eq.{session['id']}",
                "select": "id,question_set_id,class_id,session_type,access_token,status,current_question_id,current_question_status,starts_at,expires_at,closed_at,time_limit_seconds,question_started_at",
            },
        )
        if latest_status < 400 and latest:
            return latest[0]
    return session


async def question_options(request: Request, question_id: str) -> list[dict[str, Any]]:
    status, options = await supabase_request(
        request,
        "GET",
        "/rest/v1/question_options",
        service_role=True,
        params={
            "question_id": f"eq.{question_id}",
            "select": "id,question_id,option_key,option_text,option_image_url,content_type",
            "order": "option_key.asc",
        },
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="无法读取题目选项")
    return options


def session_public_payload(session: dict[str, Any], question: dict[str, Any] | None, options: list[dict[str, Any]], participant_count: int = 0) -> dict[str, Any]:
    return {
        "id": session["id"],
        "session_type": session["session_type"],
        "status": session["status"],
        "current_question_status": session["current_question_status"],
        "starts_at": session.get("starts_at"),
        "expires_at": session.get("expires_at"),
        "time_limit_seconds": int(session.get("time_limit_seconds") or 0),
        "question_started_at": session.get("question_started_at"),
        "participant_count": participant_count,
        "question": public_question(question, options) if question else None,
    }


@app.get("/api/classes")
async def list_classes(
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    status, classes = await supabase_request(
        request,
        "GET",
        "/rest/v1/classes",
        access_token=token,
        params={"select": "id,code,name,grade_id,grades(code,name)", "order": "grade_id.asc,code.asc"},
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="无法读取班级列表")
    return classes


@app.get("/api/sessions")
async def list_sessions(
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        access_token=token,
        params={
            "status": "neq.archived",
            "select": "id,question_set_id,class_id,session_type,access_token,status,current_question_id,current_question_status,starts_at,expires_at,closed_at,archived_at,created_at,time_limit_seconds,question_started_at,classes(code,name),question_sets(name)",
            "order": "created_at.desc",
        },
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="无法读取课堂场次")
    app_url = env_value(request, "PUBLIC_APP_URL", "http://localhost:5173").rstrip("/")
    return [{**session, "join_url": f"{app_url}/student/session/{session['access_token']}"} for session in sessions]


@app.post("/api/sessions/{session_id}/archive")
async def archive_session(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        access_token=token,
        params={"id": f"eq.{session_id}", "select": "id,status,session_type"},
    )
    if status >= 400 or not sessions:
        raise HTTPException(status_code=404, detail="找不到课堂场次")
    if sessions[0]["session_type"] == "classroom" and sessions[0]["status"] != "closed":
        raise HTTPException(status_code=409, detail="只有已结束的课堂可以归档")
    update_status, updated = await supabase_request(
        request,
        "PATCH",
        "/rest/v1/sessions",
        service_role=True,
        prefer_representation=True,
        params={"id": f"eq.{session_id}"},
        body={"status": "archived", "archived_at": utc_now().isoformat()},
    )
    if update_status >= 400 or not updated:
        raise HTTPException(status_code=502, detail="课堂归档失败")
    return updated[0]


@app.post("/api/sessions")
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    teacher = await current_teacher_profile(request, token)
    if payload.session_type not in {"classroom", "homework"}:
        raise HTTPException(status_code=422, detail="不支持的场次类型")
    time_limit_seconds = 0 if payload.session_type == "homework" else int(payload.time_limit_seconds or 0)
    if time_limit_seconds and time_limit_seconds < 10:
        raise HTTPException(status_code=422, detail="课堂限时最少为 10 秒，或选择不限时")
    set_status, sets = await supabase_request(
        request,
        "GET",
        "/rest/v1/question_sets",
        access_token=token,
        params={"id": f"eq.{payload.question_set_id}", "select": "id,name,status"},
    )
    if set_status >= 400 or not sets:
        raise HTTPException(status_code=404, detail="找不到题目集合")
    if sets[0]["status"] != "published":
        raise HTTPException(status_code=409, detail="请先发布题目集合，再创建课堂场次")
    class_status, classes = await supabase_request(
        request,
        "GET",
        "/rest/v1/classes",
        access_token=token,
        params={"id": f"eq.{payload.class_id}", "select": "id,name,code"},
    )
    if class_status >= 400 or not classes:
        raise HTTPException(status_code=404, detail="找不到班级")
    questions = await session_questions(request, payload.question_set_id)
    if not questions:
        raise HTTPException(status_code=409, detail="题目集合没有题目")
    access_token = secrets.token_urlsafe(24)
    status, result = await supabase_request(
        request,
        "POST",
        "/rest/v1/sessions",
        service_role=True,
        prefer_representation=True,
        body={
            "created_by": teacher["user_id"],
            "question_set_id": payload.question_set_id,
            "class_id": payload.class_id,
            "session_type": payload.session_type,
            "access_token": access_token,
            "status": "waiting" if payload.session_type == "classroom" else "active",
            "current_question_status": "pending",
            "starts_at": utc_now().isoformat() if payload.session_type == "homework" else None,
            "time_limit_seconds": time_limit_seconds,
            "question_started_at": None,
        },
    )
    if status >= 400 or not result:
        raise HTTPException(status_code=502, detail="创建课堂场次失败")
    app_url = env_value(request, "PUBLIC_APP_URL", "http://localhost:5173").rstrip("/")
    return {
        **result[0],
        "join_url": f"{app_url}/student/session/{access_token}",
        "question_count": len(questions),
        "practice_code": access_token if payload.session_type == "homework" else None,
    }


@app.post("/api/sessions/{session_id}/start")
async def start_session(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        access_token=token,
        params={"id": f"eq.{session_id}", "select": "id,question_set_id,status,time_limit_seconds"},
    )
    if status >= 400 or not sessions:
        raise HTTPException(status_code=404, detail="找不到课堂场次")
    questions = await session_questions(request, sessions[0]["question_set_id"])
    if not questions:
        raise HTTPException(status_code=409, detail="课堂没有可用题目")
    update_status, result = await supabase_request(
        request,
        "PATCH",
        "/rest/v1/sessions",
        service_role=True,
        prefer_representation=True,
        params={"id": f"eq.{session_id}"},
        body={"status": "active", "current_question_id": questions[0]["id"], "current_question_status": "open", "starts_at": utc_now().isoformat(), "question_started_at": utc_now().isoformat()},
    )
    if update_status >= 400 or not result:
        raise HTTPException(status_code=502, detail="开始课堂失败")
    return result[0]


@app.post("/api/sessions/{session_id}/next")
async def next_session_question(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        access_token=token,
        params={"id": f"eq.{session_id}", "select": "id,question_set_id,current_question_id,status,time_limit_seconds,question_started_at"},
    )
    if status >= 400 or not sessions:
        raise HTTPException(status_code=404, detail="找不到课堂场次")
    session = sessions[0]
    questions = await session_questions(request, session["question_set_id"])
    current_index = next((index for index, question in enumerate(questions) if question["id"] == session.get("current_question_id")), -1)
    if current_index < 0 or current_index + 1 >= len(questions):
        update_status, result = await supabase_request(
            request,
            "PATCH",
            "/rest/v1/sessions",
            service_role=True,
            prefer_representation=True,
            params={"id": f"eq.{session_id}"},
            body={"status": "closed", "current_question_status": "locked", "closed_at": utc_now().isoformat(), "question_started_at": None},
        )
    else:
        update_status, result = await supabase_request(
            request,
            "PATCH",
            "/rest/v1/sessions",
            service_role=True,
            prefer_representation=True,
            params={"id": f"eq.{session_id}"},
            body={"status": "active", "current_question_id": questions[current_index + 1]["id"], "current_question_status": "open", "question_started_at": utc_now().isoformat()},
        )
    if update_status >= 400 or not result:
        raise HTTPException(status_code=502, detail="切换题目失败")
    return result[0]


@app.post("/api/sessions/{session_id}/previous")
async def previous_session_question(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        access_token=token,
        params={"id": f"eq.{session_id}", "select": "id,question_set_id,current_question_id,status,time_limit_seconds,question_started_at"},
    )
    if status >= 400 or not sessions:
        raise HTTPException(status_code=404, detail="找不到课堂场次")
    session = sessions[0]
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="课堂尚未开始或已经结束")
    questions = await session_questions(request, session["question_set_id"])
    current_index = next((index for index, question in enumerate(questions) if question["id"] == session.get("current_question_id")), -1)
    if current_index <= 0:
        raise HTTPException(status_code=409, detail="已经是第一题")
    update_status, result = await supabase_request(
        request,
        "PATCH",
        "/rest/v1/sessions",
        service_role=True,
        prefer_representation=True,
        params={"id": f"eq.{session_id}"},
        body={"current_question_id": questions[current_index - 1]["id"], "current_question_status": "open", "question_started_at": utc_now().isoformat()},
    )
    if update_status >= 400 or not result:
        raise HTTPException(status_code=502, detail="返回上一题失败")
    return result[0]


@app.get("/api/sessions/{session_id}/stats")
async def session_stats(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        access_token=token,
        params={"id": f"eq.{session_id}", "select": "id,question_set_id,current_question_id,status,current_question_status,time_limit_seconds,question_started_at"},
    )
    if status >= 400 or not sessions:
        raise HTTPException(status_code=404, detail="找不到课堂场次")
    session = await advance_expired_session(request, sessions[0])
    participant_status, participants = await supabase_request(
        request,
        "GET",
        "/rest/v1/session_students",
        access_token=token,
        params={"session_id": f"eq.{session_id}", "select": "id"},
    )
    answers: list[dict[str, Any]] = []
    answer_status = 200
    if session.get("current_question_id"):
        answer_status, answers = await supabase_request(
            request,
            "GET",
            "/rest/v1/student_answers",
            access_token=token,
            params={"session_id": f"eq.{session_id}", "question_id": f"eq.{session['current_question_id']}", "select": "selected_option_id,is_correct"},
        )
    if participant_status >= 400 or answer_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取课堂统计")
    distribution: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    correct_count = 0
    if answers:
        for answer in answers:
            if answer.get("is_correct"):
                correct_count += 1
            if answer.get("selected_option_id"):
                # For the new model, we need to map option_id to option_key
                # This is a simplification - in production we'd need to query the options
                option_status, option = await supabase_request(
                    request,
                    "GET",
                    "/rest/v1/question_options",
                    access_token=token,
                    params={"id": f"eq.{answer['selected_option_id']}", "select": "option_key"},
                )
                if option_status < 400 and isinstance(option, list) and option:
                    key = option[0].get("option_key")
                    if key in distribution:
                        distribution[key] += 1
    return {"session_id": session_id, "status": session["status"], "current_question_status": session["current_question_status"], "current_question_id": session.get("current_question_id"), "time_limit_seconds": int(session.get("time_limit_seconds") or 0), "question_started_at": session.get("question_started_at"), "participant_count": len(participants), "submitted_count": len(answers), "correct_count": correct_count, "distribution": distribution}


@app.get("/api/sessions/{session_id}/report")
async def session_report(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    await current_teacher_profile(request, token)
    session_status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        access_token=token,
        params={"id": f"eq.{session_id}", "select": "id,status,session_type,created_at,closed_at,question_set_id,topic_id,class_id,classes(code,name),question_sets(name)"},
    )
    if session_status >= 400 or not sessions:
        raise HTTPException(status_code=404, detail="找不到课堂场次")
    session = sessions[0]
    
    # Get questions - handle both topic_id and question_set_id
    if session.get("question_set_id"):
        questions = await session_questions(request, session["question_set_id"])
    elif session.get("topic_id"):
        # Get questions for the topic
        qs_status, question_sets = await supabase_request(
            request,
            "GET",
            "/rest/v1/question_sets",
            service_role=True,
            params={"topic_id": f"eq.{session['topic_id']}", "status": "eq.published", "select": "id"},
        )
        if qs_status < 400 and isinstance(question_sets, list) and question_sets:
            question_set_ids = [qs["id"] for qs in question_sets]
            q_status, all_questions = await supabase_request(
                request,
                "GET",
                "/rest/v1/questions",
                service_role=True,
                params={"question_set_id": f"in.({','.join(question_set_ids)})", "select": "id,sort_order,question_text,question_image_url,explanation,question_type,content_type,correct_option_id", "order": "sort_order.asc"},
            )
            questions = all_questions if q_status < 400 and isinstance(all_questions, list) else []
        else:
            questions = []
    else:
        questions = []
    
    question_ids = [question["id"] for question in questions]
    answers: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    
    if question_ids:
        # For the new model, we use student_answers directly
        answer_status, answers = await supabase_request(
            request,
            "GET",
            "/rest/v1/student_answers",
            service_role=True,
            params={"session_id": f"eq.{session_id}", "question_id": f"in.({','.join(question_ids)})", "select": "question_id,selected_option_id,is_correct,answer_type,answer_text"},
        )
        option_status, options = await supabase_request(
            request,
            "GET",
            "/rest/v1/question_options",
            service_role=True,
            params={"question_id": f"in.({','.join(question_ids)})", "select": "id,question_id,option_key"},
        )
        if answer_status >= 400 or option_status >= 400:
            raise HTTPException(status_code=502, detail="无法读取统计")
    
    options_by_id = {option["id"]: option for option in options}
    report_questions: list[dict[str, Any]] = []
    for question in questions:
        question_answers = [answer for answer in answers if answer["question_id"] == question["id"]]
        distribution = {"A": 0, "B": 0, "C": 0, "D": 0}
        for answer in question_answers:
            if answer.get("selected_option_id"):
                key = options_by_id.get(answer["selected_option_id"], {}).get("option_key")
                if key in distribution:
                    distribution[key] += 1
        correct_count = sum(1 for answer in question_answers if answer.get("is_correct") is True)
        text_input_count = sum(1 for answer in question_answers if answer.get("answer_type") == "text_input")
        report_questions.append({
            "id": question["id"],
            "sort_order": question["sort_order"],
            "question_text": question.get("question_text"),
            "question_image_url": question.get("question_image_url"),
            "correct_option_id": question.get("correct_option_id"),
            "correct_option_key": options_by_id.get(question.get("correct_option_id"), {}).get("option_key"),
            "submitted_count": len(question_answers),
            "correct_count": correct_count,
            "text_input_count": text_input_count,
            "accuracy": round(correct_count / len(question_answers) * 100, 1) if question_answers else 0,
            "distribution": distribution,
        })
    
    participant_status, participants = await supabase_request(
        request,
        "GET",
        "/rest/v1/session_students",
        service_role=True,
        params={"session_id": f"eq.{session_id}", "select": "id"},
    )
    if participant_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取课堂人数")
    
    participant_count = len(participants)
    return {"session": session, "participant_count": participant_count, "total_submitted_count": len(answers), "questions": report_questions}


async def student_question_set(request: Request, question_set_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    set_status, sets = await supabase_request(
        request,
        "GET",
        "/rest/v1/question_sets",
        service_role=True,
        params={"id": f"eq.{question_set_id}", "status": "eq.published", "select": "id,name,grade_id,status,created_at"},
    )
    if set_status >= 400 or not sets:
        raise HTTPException(status_code=404, detail="找不到可用題目集合")
    questions = await session_questions(request, question_set_id)
    return sets[0], questions


@app.get("/api/student/grades")
async def student_grades(
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="需要學生登錄")
    
    token = authorization[7:]
    try:
        payload = decode_jwt(token)
    except HTTPException:
        raise
    
    if payload.get("role") != "student":
        raise HTTPException(status_code=401, detail="無效的令牌")
    
    status, grades = await supabase_request(
        request,
        "GET",
        "/rest/v1/grades",
        service_role=True,
        params={"is_active": "eq.true", "select": "id,code,name,sort_order", "order": "sort_order.asc"},
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取年級列表")
    set_status, sets = await supabase_request(
        request,
        "GET",
        "/rest/v1/question_sets",
        service_role=True,
        params={"status": "eq.published", "select": "id,grade_id", "order": "created_at.desc"},
    )
    if set_status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取題目集合")
    counts: dict[str, int] = {}
    for item in sets:
        if item.get("grade_id"):
            counts[item["grade_id"]] = counts.get(item["grade_id"], 0) + 1
    return [{**grade, "question_set_count": counts.get(grade["id"], 0)} for grade in grades]


Default = asgi.entrypoint(app)
