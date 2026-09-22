from __future__ import annotations

import json
import hashlib
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


app = FastAPI(title="HHX English Math Classroom API", version="0.1.0")


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


class CreateSessionRequest(BaseModel):
    question_set_id: str = Field(min_length=1)
    class_id: str = Field(min_length=1)
    session_type: str = Field(default="classroom")


class AnswerRequest(BaseModel):
    question_id: str = Field(min_length=1)
    selected_option_id: str = Field(min_length=1)
    browser_key: str = Field(min_length=16, max_length=200)


class JoinRequest(BaseModel):
    browser_key: str = Field(min_length=16, max_length=200)


class PracticeStartRequest(BaseModel):
    browser_key: str = Field(min_length=16, max_length=200)


class PracticeAnswerRequest(BaseModel):
    browser_key: str = Field(min_length=16, max_length=200)
    attempt_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    selected_option_id: str = Field(min_length=1)


class PracticeCompleteRequest(BaseModel):
    browser_key: str = Field(min_length=16, max_length=200)
    attempt_id: str = Field(min_length=1)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def browser_key_hash(browser_key: str) -> str:
    return hashlib.sha256(browser_key.encode("utf-8")).hexdigest()


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
            "select": "id,name,source_filename,status,version,created_at,updated_at,archived_at,questions(count)",
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
        params={"id": f"eq.{question_set_id}", "select": "id,name,source_filename,status,version,created_at,updated_at,archived_at"},
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
                "options": question.options,
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
        questions = parse_question_excel(await file.read())
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
            "explanation": question.explanation,
            "question_type": "single_choice",
            "content_type": "text",
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
                    "content_type": "text",
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
    except Exception as exc:
        await cleanup_question_set(request, question_set_id, question_ids)
        raise HTTPException(status_code=502, detail="题目导入失败，未保留不完整数据") from exc

    return {
        "id": question_set_id,
        "name": clean_name,
        "status": "draft",
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
            "select": "id,created_by,question_set_id,class_id,session_type,access_token,status,current_question_id,current_question_status,starts_at,expires_at,closed_at",
        },
    )
    if status >= 400 or not sessions:
        raise HTTPException(status_code=404, detail="找不到课堂场次或二维码已失效")
    session = sessions[0]
    if session["expires_at"] <= utc_now().isoformat():
        raise HTTPException(status_code=410, detail="二维码已过期")
    return session


async def ensure_anonymous_device(request: Request, browser_key: str) -> str:
    device_hash = browser_key_hash(browser_key)
    device_status, devices = await supabase_request(
        request,
        "GET",
        "/rest/v1/anonymous_devices",
        service_role=True,
        params={"browser_key_hash": f"eq.{device_hash}", "select": "id"},
    )
    if device_status >= 400:
        raise HTTPException(status_code=502, detail="无法建立匿名设备")
    if devices:
        return devices[0]["id"]
    create_status, created = await supabase_request(
        request,
        "POST",
        "/rest/v1/anonymous_devices",
        service_role=True,
        prefer_representation=True,
        body={"browser_key_hash": device_hash},
    )
    if create_status >= 400 or not created:
        raise HTTPException(status_code=502, detail="无法建立匿名设备")
    return created[0]["id"]


async def join_anonymous_session(request: Request, session_id: str, device_id: str) -> None:
    participant_status, participants = await supabase_request(
        request,
        "GET",
        "/rest/v1/session_participants",
        service_role=True,
        params={"session_id": f"eq.{session_id}", "anonymous_device_id": f"eq.{device_id}", "select": "id"},
    )
    if participant_status >= 400:
        raise HTTPException(status_code=502, detail="无法加入练习")
    if not participants:
        join_status, _ = await supabase_request(
            request,
            "POST",
            "/rest/v1/session_participants",
            service_role=True,
            prefer_representation=True,
            body={"session_id": session_id, "anonymous_device_id": device_id},
        )
        if join_status >= 400:
            raise HTTPException(status_code=502, detail="无法加入练习")


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
            "select": "id,question_set_id,class_id,session_type,access_token,status,current_question_id,current_question_status,starts_at,expires_at,closed_at,archived_at,created_at,classes(code,name),question_sets(name)",
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
        params={"id": f"eq.{session_id}", "select": "id,question_set_id,status"},
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
        body={"status": "active", "current_question_id": questions[0]["id"], "current_question_status": "open", "starts_at": utc_now().isoformat()},
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
        params={"id": f"eq.{session_id}", "select": "id,question_set_id,current_question_id,status"},
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
            body={"status": "closed", "current_question_status": "locked", "closed_at": utc_now().isoformat()},
        )
    else:
        update_status, result = await supabase_request(
            request,
            "PATCH",
            "/rest/v1/sessions",
            service_role=True,
            prefer_representation=True,
            params={"id": f"eq.{session_id}"},
            body={"status": "active", "current_question_id": questions[current_index + 1]["id"], "current_question_status": "open"},
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
        params={"id": f"eq.{session_id}", "select": "id,question_set_id,current_question_id,status"},
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
        body={"current_question_id": questions[current_index - 1]["id"], "current_question_status": "open"},
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
        params={"id": f"eq.{session_id}", "select": "id,current_question_id,status,current_question_status"},
    )
    if status >= 400 or not sessions:
        raise HTTPException(status_code=404, detail="找不到课堂场次")
    session = sessions[0]
    participant_status, participants = await supabase_request(
        request,
        "GET",
        "/rest/v1/session_participants",
        access_token=token,
        params={"session_id": f"eq.{session_id}", "select": "id"},
    )
    answers: list[dict[str, Any]] = []
    answer_status = 200
    if session.get("current_question_id"):
        answer_status, answers = await supabase_request(
            request,
            "GET",
            "/rest/v1/answers",
            access_token=token,
            params={"session_id": f"eq.{session_id}", "question_id": f"eq.{session['current_question_id']}", "practice_attempt_id": "is.null", "select": "selected_option_id"},
        )
    if participant_status >= 400 or answer_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取课堂统计")
    distribution: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    if answers:
        option_status, options = await supabase_request(
            request,
            "GET",
            "/rest/v1/question_options",
            access_token=token,
            params={"id": f"in.({','.join(answer['selected_option_id'] for answer in answers)})", "select": "id,option_key"},
        )
        if option_status >= 400:
            raise HTTPException(status_code=502, detail="无法读取选项统计")
        option_keys = {option["id"]: option["option_key"] for option in options}
        for answer in answers:
            key = option_keys.get(answer["selected_option_id"])
            if key in distribution:
                distribution[key] += 1
    return {"session_id": session_id, "status": session["status"], "current_question_status": session["current_question_status"], "current_question_id": session.get("current_question_id"), "participant_count": len(participants), "submitted_count": len(answers), "distribution": distribution}


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
        params={"id": f"eq.{session_id}", "select": "id,status,session_type,created_at,closed_at,question_set_id,class_id,classes(code,name),question_sets(name)"},
    )
    if session_status >= 400 or not sessions:
        raise HTTPException(status_code=404, detail="找不到课堂场次")
    session = sessions[0]
    questions = await session_questions(request, session["question_set_id"])
    question_ids = [question["id"] for question in questions]
    answers: list[dict[str, Any]] = []
    completed_attempt_count = 0
    options: list[dict[str, Any]] = []
    if question_ids:
        if session.get("session_type") == "homework":
            attempt_status, attempts = await supabase_request(
                request,
                "GET",
                "/rest/v1/practice_attempts",
                service_role=True,
                params={"session_id": f"eq.{session_id}", "status": "eq.completed", "select": "id,anonymous_device_id,completed_at", "order": "completed_at.desc"},
            )
            if attempt_status >= 400:
                raise HTTPException(status_code=502, detail="无法读取课后练习统计")
            completed_attempt_count = len(attempts)
            latest_attempt_ids: list[str] = []
            latest_devices: set[str] = set()
            for attempt in attempts:
                device_id = attempt.get("anonymous_device_id")
                if device_id and device_id not in latest_devices:
                    latest_devices.add(device_id)
                    latest_attempt_ids.append(attempt["id"])
            if latest_attempt_ids:
                answer_status, answers = await supabase_request(
                    request,
                    "GET",
                    "/rest/v1/answers",
                    service_role=True,
                    params={"session_id": f"eq.{session_id}", "question_id": f"in.({','.join(question_ids)})", "practice_attempt_id": f"in.({','.join(latest_attempt_ids)})", "select": "question_id,selected_option_id,is_correct,practice_attempt_id"},
                )
            else:
                answer_status = 200
        else:
            answer_status, answers = await supabase_request(
                request,
                "GET",
                "/rest/v1/answers",
                service_role=True,
                params={"session_id": f"eq.{session_id}", "question_id": f"in.({','.join(question_ids)})", "practice_attempt_id": "is.null", "select": "question_id,selected_option_id,is_correct"},
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
            key = options_by_id.get(answer["selected_option_id"], {}).get("option_key")
            if key in distribution:
                distribution[key] += 1
        correct_count = sum(1 for answer in question_answers if answer.get("is_correct") is True)
        report_questions.append({
            "id": question["id"],
            "sort_order": question["sort_order"],
            "question_text": question.get("question_text"),
            "correct_option_id": question.get("correct_option_id"),
            "correct_option_key": options_by_id.get(question.get("correct_option_id"), {}).get("option_key"),
            "submitted_count": len(question_answers),
            "correct_count": correct_count,
            "accuracy": round(correct_count / len(question_answers) * 100, 1) if question_answers else 0,
            "distribution": distribution,
        })
    participant_status, participants = await supabase_request(
        request,
        "GET",
        "/rest/v1/session_participants",
        service_role=True,
        params={"session_id": f"eq.{session_id}", "select": "id"},
    )
    if participant_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取课堂人数")
    participant_count = len(participants) if session.get("session_type") != "homework" else len({answer.get("practice_attempt_id") for answer in answers if answer.get("practice_attempt_id")})
    return {"session": session, "participant_count": participant_count, "completed_attempt_count": completed_attempt_count, "total_submitted_count": len(answers), "questions": report_questions}


@app.get("/api/public/practice/{access_token}")
async def public_practice(access_token: str, request: Request) -> dict[str, Any]:
    session = await find_session_by_token(request, access_token)
    if session["session_type"] != "homework":
        raise HTTPException(status_code=422, detail="这不是课后练习码")
    if session["status"] != "active":
        raise HTTPException(status_code=410, detail="练习已结束")
    questions = await session_questions(request, session["question_set_id"])
    payload_questions = []
    for question in questions:
        payload_questions.append(public_question(question, await question_options(request, question["id"])))
    return {
        "id": session["id"],
        "session_type": "homework",
        "status": session["status"],
        "expires_at": session.get("expires_at"),
        "question_count": len(payload_questions),
        "questions": payload_questions,
    }


@app.post("/api/public/practice/{access_token}/start")
async def start_public_practice(access_token: str, payload: PracticeStartRequest, request: Request) -> dict[str, Any]:
    session = await find_session_by_token(request, access_token)
    if session["session_type"] != "homework" or session["status"] != "active":
        raise HTTPException(status_code=410, detail="练习已结束")
    device_id = await ensure_anonymous_device(request, payload.browser_key)
    await join_anonymous_session(request, session["id"], device_id)

    draft_status, drafts = await supabase_request(
        request,
        "GET",
        "/rest/v1/practice_attempts",
        service_role=True,
        params={"session_id": f"eq.{session['id']}", "anonymous_device_id": f"eq.{device_id}", "status": "eq.draft", "select": "id"},
    )
    if draft_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取未完成练习")
    # 首版不支持续做，开始新练习时清理同一设备留下的未完成轮次。
    for draft in drafts:
        await supabase_request(
            request,
            "DELETE",
            "/rest/v1/answers",
            service_role=True,
            params={"practice_attempt_id": f"eq.{draft['id']}"},
        )
        await supabase_request(
            request,
            "DELETE",
            "/rest/v1/practice_attempts",
            service_role=True,
            params={"id": f"eq.{draft['id']}"},
        )
    create_status, attempts = await supabase_request(
        request,
        "POST",
        "/rest/v1/practice_attempts",
        service_role=True,
        prefer_representation=True,
        body={"session_id": session["id"], "anonymous_device_id": device_id, "status": "draft"},
    )
    if create_status >= 400 or not attempts:
        raise HTTPException(status_code=502, detail="无法开始练习")
    return {"attempt_id": attempts[0]["id"], "session_id": session["id"]}


@app.post("/api/public/practice/{access_token}/answers")
async def submit_practice_answer(access_token: str, payload: PracticeAnswerRequest, request: Request) -> dict[str, Any]:
    session = await find_session_by_token(request, access_token)
    if session["session_type"] != "homework" or session["status"] != "active":
        raise HTTPException(status_code=410, detail="练习已结束")
    device_id = await ensure_anonymous_device(request, payload.browser_key)
    attempt_status, attempts = await supabase_request(
        request,
        "GET",
        "/rest/v1/practice_attempts",
        service_role=True,
        params={"id": f"eq.{payload.attempt_id}", "session_id": f"eq.{session['id']}", "anonymous_device_id": f"eq.{device_id}", "status": "eq.draft", "select": "id"},
    )
    if attempt_status >= 400 or not attempts:
        raise HTTPException(status_code=409, detail="练习轮次已失效，请重新输入练习码")
    existing_status, existing = await supabase_request(
        request,
        "GET",
        "/rest/v1/answers",
        service_role=True,
        params={"practice_attempt_id": f"eq.{payload.attempt_id}", "question_id": f"eq.{payload.question_id}", "select": "id"},
    )
    if existing_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取已有答案")
    body = {"session_id": session["id"], "question_id": payload.question_id, "selected_option_id": payload.selected_option_id, "practice_attempt_id": payload.attempt_id}
    if existing:
        write_status, _ = await supabase_request(request, "PATCH", "/rest/v1/answers", service_role=True, prefer_representation=True, params={"id": f"eq.{existing[0]['id']}"}, body={"selected_option_id": payload.selected_option_id})
    else:
        write_status, _ = await supabase_request(request, "POST", "/rest/v1/answers", service_role=True, prefer_representation=True, body=body)
    if write_status >= 400:
        raise HTTPException(status_code=409, detail="答案提交失败，请重新尝试")
    return {"submitted": True, "question_id": payload.question_id}


@app.post("/api/public/practice/{access_token}/complete")
async def complete_public_practice(access_token: str, payload: PracticeCompleteRequest, request: Request) -> dict[str, Any]:
    session = await find_session_by_token(request, access_token)
    if session["session_type"] != "homework" or session["status"] != "active":
        raise HTTPException(status_code=410, detail="练习已结束")
    device_id = await ensure_anonymous_device(request, payload.browser_key)
    attempt_status, attempts = await supabase_request(request, "GET", "/rest/v1/practice_attempts", service_role=True, params={"id": f"eq.{payload.attempt_id}", "session_id": f"eq.{session['id']}", "anonymous_device_id": f"eq.{device_id}", "status": "eq.draft", "select": "id"})
    if attempt_status >= 400 or not attempts:
        raise HTTPException(status_code=409, detail="练习轮次已失效，请重新输入练习码")
    update_status, updated = await supabase_request(request, "PATCH", "/rest/v1/practice_attempts", service_role=True, prefer_representation=True, params={"id": f"eq.{payload.attempt_id}"}, body={"status": "completed", "completed_at": utc_now().isoformat()})
    if update_status >= 400 or not updated:
        message = updated.get("message", "练习尚未完成，请完成全部题目") if isinstance(updated, dict) else "练习尚未完成，请完成全部题目"
        raise HTTPException(status_code=409, detail=message)
    answer_status, answers = await supabase_request(request, "GET", "/rest/v1/answers", service_role=True, params={"practice_attempt_id": f"eq.{payload.attempt_id}", "select": "question_id,selected_option_id,is_correct"})
    if answer_status >= 400:
        raise HTTPException(status_code=502, detail="练习已完成，但结果读取失败")
    return {"completed": True, "attempt_id": payload.attempt_id, "answers": answers}


@app.get("/api/public/sessions/{access_token}")
async def public_session(access_token: str, request: Request) -> dict[str, Any]:
    session = await find_session_by_token(request, access_token)
    participant_status, participants = await supabase_request(
        request,
        "GET",
        "/rest/v1/session_participants",
        service_role=True,
        params={"session_id": f"eq.{session['id']}", "select": "id"},
    )
    if participant_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取课堂人数")
    question = None
    options: list[dict[str, Any]] = []
    if session["status"] == "active" and session.get("current_question_id"):
        questions = await session_questions(request, session["question_set_id"])
        question = next((item for item in questions if item["id"] == session["current_question_id"]), None)
        if question:
            options = await question_options(request, question["id"])
    return session_public_payload(session, question, options, len(participants))


@app.post("/api/public/sessions/{access_token}/join")
async def join_public_session(access_token: str, payload: JoinRequest, request: Request) -> dict[str, Any]:
    session = await find_session_by_token(request, access_token)
    device_hash = browser_key_hash(payload.browser_key)
    device_status, devices = await supabase_request(
        request,
        "GET",
        "/rest/v1/anonymous_devices",
        service_role=True,
        params={"browser_key_hash": f"eq.{device_hash}", "select": "id"},
    )
    if device_status >= 400:
        raise HTTPException(status_code=502, detail="无法建立匿名设备")
    if devices:
        device_id = devices[0]["id"]
    else:
        create_status, created = await supabase_request(
            request,
            "POST",
            "/rest/v1/anonymous_devices",
            service_role=True,
            prefer_representation=True,
            body={"browser_key_hash": device_hash},
        )
        if create_status >= 400 or not created:
            raise HTTPException(status_code=502, detail="无法建立匿名设备")
        device_id = created[0]["id"]
    participant_status, participants = await supabase_request(
        request,
        "GET",
        "/rest/v1/session_participants",
        service_role=True,
        params={"session_id": f"eq.{session['id']}", "anonymous_device_id": f"eq.{device_id}", "select": "id"},
    )
    if participant_status >= 400:
        raise HTTPException(status_code=502, detail="无法加入课堂")
    if not participants:
        join_status, _ = await supabase_request(
            request,
            "POST",
            "/rest/v1/session_participants",
            service_role=True,
            prefer_representation=True,
            body={"session_id": session["id"], "anonymous_device_id": device_id},
        )
        if join_status >= 400:
            raise HTTPException(status_code=502, detail="无法加入课堂")
    count_status, count_rows = await supabase_request(
        request,
        "GET",
        "/rest/v1/session_participants",
        service_role=True,
        params={"session_id": f"eq.{session['id']}", "select": "id"},
    )
    return {"joined": True, "session_id": session["id"], "status": session["status"], "participant_count": len(count_rows) if count_status < 400 else 0}


@app.post("/api/public/sessions/{access_token}/answers")
async def submit_public_answer(access_token: str, payload: AnswerRequest, request: Request) -> dict[str, Any]:
    session = await find_session_by_token(request, access_token)
    device_hash = browser_key_hash(payload.browser_key)
    device_status, devices = await supabase_request(
        request,
        "GET",
        "/rest/v1/anonymous_devices",
        service_role=True,
        params={"browser_key_hash": f"eq.{device_hash}", "select": "id"},
    )
    if device_status >= 400 or not devices:
        raise HTTPException(status_code=403, detail="请先加入课堂")
    device_id = devices[0]["id"]
    existing_status, existing = await supabase_request(
        request,
        "GET",
        "/rest/v1/answers",
        service_role=True,
        params={"session_id": f"eq.{session['id']}", "question_id": f"eq.{payload.question_id}", "anonymous_device_id": f"eq.{device_id}", "practice_attempt_id": "is.null", "select": "id"},
    )
    if existing_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取已有答案")
    answer_body = {"session_id": session["id"], "question_id": payload.question_id, "selected_option_id": payload.selected_option_id, "anonymous_device_id": device_id}
    if existing:
        write_method = "PATCH"
        write_path = "/rest/v1/answers"
        write_params = {"id": f"eq.{existing[0]['id']}"}
    else:
        write_method = "POST"
        write_path = "/rest/v1/answers"
        write_params = None
    write_status, _ = await supabase_request(
        request,
        write_method,
        write_path,
        service_role=True,
        prefer_representation=True,
        params=write_params,
        body=answer_body,
    )
    if write_status >= 400:
        raise HTTPException(status_code=409, detail="当前题目不能提交答案，请确认课堂仍在进行")
    return {"submitted": True, "question_id": payload.question_id}


Default = asgi.entrypoint(app)
