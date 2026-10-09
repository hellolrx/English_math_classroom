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
from js import Object, Uint8Array, fetch
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
    mode: str = Field(default="teacher", pattern="^(teacher|student)$")


class CreateSessionRequest(BaseModel):
    question_set_id: str | None = None
    batch_id: str | None = None
    class_id: str = Field(min_length=1)
    session_type: str = Field(default="classroom")
    time_limit_seconds: int | None = Field(default=30, ge=0, le=600)


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


class StudentPracticeStartRequest(BaseModel):
    browser_key: str = Field(min_length=16, max_length=200)


class StudentPracticeAnswerRequest(BaseModel):
    browser_key: str = Field(min_length=16, max_length=200)
    attempt_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    selected_option_id: str = Field(min_length=1)


class StudentPracticeCompleteRequest(BaseModel):
    browser_key: str = Field(min_length=16, max_length=200)
    attempt_id: str = Field(min_length=1)


class ReviewAnswerRequest(BaseModel):
    browser_key: str = Field(min_length=16, max_length=200)
    question_id: str = Field(min_length=1)
    selected_option_id: str = Field(min_length=1)
    rating: str = Field(pattern="^(forgot|fuzzy|clear)$")


class StudentRoundStartRequest(BaseModel):
    topic_id: str | None = None
    access_code: str | None = None


class StudentRoundAnswerItem(BaseModel):
    question_id: str = Field(min_length=1)
    selected_option: str | None = None
    text_answer: str | None = None


class StudentRoundAnswerRequest(BaseModel):
    round_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    selected_option: str | None = None
    text_answer: str | None = None
    confirm: bool = False


class StudentRoundFinishRequest(BaseModel):
    round_id: str = Field(min_length=1)
    answers: list[StudentRoundAnswerItem] = Field(default_factory=list)


class ClassroomAnswerRequest(BaseModel):
    question_id: str
    selected_option: str = Field(pattern="^[ABCD]$")


class WordRatingRequest(BaseModel):
    word_id: str
    rating: str = Field(pattern="^(forgot|fuzzy|clear)$")


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


async def create_student_session(request: Request, student: dict[str, Any]) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(hours=24)
    status, result = await supabase_request(
        request,
        "POST",
        "/rest/v1/student_sessions",
        service_role=True,
        prefer_representation=True,
        body={
            "student_id": student["student_id"],
            "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "auth_version": student["auth_version"],
            "expires_at": expires_at.isoformat(),
        },
    )
    if status >= 400 or not result:
        raise HTTPException(status_code=502, detail="無法建立學生登入狀態")
    return token, expires_at


async def verify_student_token(request: Request, authorization: str | None) -> dict[str, Any]:
    token = bearer_token(authorization)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/student_sessions",
        service_role=True,
        params={
            "token_hash": f"eq.{token_hash}",
            "revoked_at": "is.null",
            "expires_at": f"gt.{utc_now().isoformat()}",
            "select": "student_id,auth_version,students(id,name,student_number,school_id,grade_id,class_id,auth_version,is_active)",
        },
    )
    if status >= 400 or not sessions:
        raise HTTPException(status_code=401, detail="學生登入狀態已失效，請重新登入")
    session = sessions[0]
    student = session.get("students")
    if not student or not student.get("is_active") or student.get("auth_version") != session.get("auth_version"):
        raise HTTPException(status_code=401, detail="學生登入狀態已失效，請重新登入")
    return student


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
            database_request = path.startswith("/rest/v1/")
            use_service_role = service_role or database_request
            request_headers = supabase_headers(
                request,
                None if use_service_role else access_token,
                service_role=use_service_role,
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
        service_role=True,
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


async def _storage_upload(request: Request, path: str, data_url: str) -> tuple[str, int]:
    import base64
    from urllib.parse import quote

    try:
        header, encoded = data_url.split(",", 1)
        mime_type = header.split(";")[0].removeprefix("data:")
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="题目图片格式无效") from exc
    if mime_type not in {"image/jpeg", "image/png", "image/webp"} or not raw or len(raw) > 1024 * 1024:
        raise HTTPException(status_code=422, detail="题目图片必须是 1MB 以内的 JPG、PNG 或 WebP")
    key = env_value(request, "SUPABASE_SECRET_KEY") or env_value(request, "SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="后端尚未设置 Supabase Service Role Key")
    js_bytes = Uint8Array.new(len(raw))
    for index, value in enumerate(raw):
        js_bytes[index] = value
    init = to_js({"method": "POST", "headers": {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": mime_type, "x-upsert": "true"}, "body": js_bytes}, dict_converter=Object.fromEntries)
    response = await fetch(f"{supabase_url(request)}/storage/v1/object/question-images-v2/{quote(path, safe='/')}", init)
    if int(response.status) >= 400:
        raise HTTPException(status_code=502, detail="题目图片上传失败")
    return path, len(raw)


async def _signed_image_url(request: Request, path: str) -> str:
    from urllib.parse import quote
    status, result = await supabase_request(request, "POST", f"/storage/v1/object/sign/question-images-v2/{quote(path, safe='/')}", service_role=True, body={"expiresIn": 3600})
    signed = result.get("signedURL") or result.get("signedUrl") if isinstance(result, dict) else None
    if status >= 400 or not signed:
        return ""
    return signed if signed.startswith("http") else f"{supabase_url(request)}{signed}"


@app.get("/api/teacher/topics")
async def teacher_topics(request: Request, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    token = bearer_token(authorization)
    teacher = await current_teacher_profile(request, token)
    status, topics = await supabase_request(request, "GET", "/rest/v1/topics", service_role=True, params={"school_id": f"eq.{teacher['school_id']}", "is_active": "eq.true", "select": "id,code,name,sort_order,math_batches(id,status,created_at,published_at,questions(count))", "order": "sort_order.asc"})
    if status >= 400:
        raise HTTPException(status_code=502, detail="无法读取主题目录")
    rows = []
    for topic in topics:
        batches = topic.pop("math_batches", [])
        published = next((batch for batch in batches if batch["status"] == "published"), None)
        rows.append({**topic, "batch_id": published["id"] if published else None, "batch_status": published["status"] if published else "empty", "question_count": (published.get("questions") or [{"count": 0}])[0].get("count", 0) if published else 0})
    return rows


@app.get("/api/teacher/topics/{topic_id}")
async def teacher_topic_detail(topic_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = bearer_token(authorization)
    teacher = await current_teacher_profile(request, token)
    status, topics = await supabase_request(request, "GET", "/rest/v1/topics", service_role=True, params={"id": f"eq.{topic_id}", "school_id": f"eq.{teacher['school_id']}", "select": "id,code,name"})
    if status >= 400 or not topics:
        raise HTTPException(status_code=404, detail="找不到主题")
    _, batches = await supabase_request(request, "GET", "/rest/v1/math_batches", service_role=True, params={"topic_id": f"eq.{topic_id}", "status": "eq.published", "select": "id,created_at,published_at,questions(id,sort_order,question_type,image_bucket,image_path,correct_option,source_reference,source_year,source_question_number,source_paper)", "order": "created_at.desc", "limit": "1"})
    batch = batches[0] if batches else None
    questions = []
    if batch:
        for q in sorted(batch.get("questions", []), key=lambda item: item["sort_order"]):
            questions.append({**q, "question_image_url": await _signed_question_image(request, q.get("image_bucket", "question-images-v2"), q["image_path"])})
    return {**topics[0], "batch": batch, "questions": questions}


@app.get("/api/teacher/questions")
async def search_teacher_questions(request: Request, year: str | None = None, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    token = bearer_token(authorization)
    teacher = await current_teacher_profile(request, token)
    params = {"source_year": f"eq.{year.strip()}", "select": "id,batch_id,sort_order,source_reference,source_year,source_question_number,source_paper,math_batches!inner(topic_id,topics!inner(code,name,school_id))", "math_batches.topics.school_id": f"eq.{teacher['school_id']}", "order": "source_year.asc,source_question_number.asc"} if year and year.strip() else {"select": "id,batch_id,sort_order,source_reference,source_year,source_question_number,source_paper,math_batches!inner(topic_id,topics!inner(code,name,school_id))", "math_batches.topics.school_id": f"eq.{teacher['school_id']}", "order": "source_year.asc,source_question_number.asc"}
    status, rows = await supabase_request(request, "GET", "/rest/v1/questions", service_role=True, params=params)
    if status >= 400:
        raise HTTPException(status_code=502, detail="无法检索题目来源")
    return rows


@app.post("/api/teacher/topics/preview")
async def preview_topic_import(request: Request, topic_id: str = Form(...), file: UploadFile = File(...), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = bearer_token(authorization)
    teacher = await current_teacher_profile(request, token)
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="只支持 .xlsx 格式的 Excel 文件")
    topic_status, topics = await supabase_request(request, "GET", "/rest/v1/topics", service_role=True, params={"id": f"eq.{topic_id}", "school_id": f"eq.{teacher['school_id']}", "select": "id"})
    if topic_status >= 400 or not topics:
        raise HTTPException(status_code=404, detail="找不到主题")
    try:
        questions = parse_question_excel(await file.read())
    except ExcelImportError as error:
        raise import_error_response(error) from error
    return {"filename": file.filename, "topic_id": topic_id, "question_count": len(questions), "questions": [{"row_number": q.row_number, "question_text": q.question_text, "question_image_url": q.question_image_url, "question_type": q.question_type, "correct_answer": q.correct_answer, "source_reference": q.source_reference, "source_year": q.source_year, "source_question_number": q.source_question_number, "source_paper": q.source_paper} for q in questions]}


@app.post("/api/teacher/topics/import")
async def import_topic(request: Request, topic_id: str = Form(...), file: UploadFile = File(...), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = bearer_token(authorization)
    teacher = await current_teacher_profile(request, token)
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="只支持 .xlsx 格式的 Excel 文件")
    topic_status, topics = await supabase_request(request, "GET", "/rest/v1/topics", service_role=True, params={"id": f"eq.{topic_id}", "school_id": f"eq.{teacher['school_id']}", "select": "id,code"})
    if topic_status >= 400 or not topics:
        raise HTTPException(status_code=404, detail="找不到主题")
    try:
        questions = parse_question_excel(await file.read())
    except ExcelImportError as error:
        raise import_error_response(error) from error
    job_id, batch_id = str(uuid4()), str(uuid4())
    status, _ = await supabase_request(request, "POST", "/rest/v1/import_jobs", service_role=True, body={"id": job_id, "created_by": teacher["user_id"], "kind": "math", "topic_id": topic_id, "filename": file.filename, "status": "preview"})
    if status >= 400:
        raise HTTPException(status_code=502, detail="无法建立导入记录")
    status, _ = await supabase_request(request, "POST", "/rest/v1/math_batches", service_role=True, body={"id": batch_id, "topic_id": topic_id, "created_by": teacher["user_id"], "import_job_id": job_id, "status": "draft"})
    if status >= 400:
        raise HTTPException(status_code=502, detail="无法建立题库批次")
    question_rows = []
    for order, q in enumerate(questions, start=1):
        if not q.question_image_url:
            await supabase_request(request, "PATCH", "/rest/v1/import_jobs", service_role=True, params={"id": f"eq.{job_id}"}, body={"status": "failed", "errors": [{"row": q.row_number, "message": "题目截图不能为空"}]})
            raise HTTPException(status_code=422, detail=f"第 {q.row_number} 行缺少题目截图")
        image_path = f"{topic_id}/{batch_id}/{order}-{secrets.token_hex(6)}.jpg"
        _, image_bytes = await _storage_upload(request, image_path, q.question_image_url)
        question_rows.append({"id": str(uuid4()), "batch_id": batch_id, "sort_order": order, "question_type": q.question_type, "image_path": image_path, "image_bytes": image_bytes, "correct_option": q.correct_answer, "source_reference": q.source_reference, "source_year": q.source_year, "source_question_number": q.source_question_number, "source_paper": q.source_paper})
    status, result = await supabase_request(request, "POST", "/rest/v1/questions", service_role=True, prefer_representation=True, body=question_rows)
    if status >= 400:
        await supabase_request(request, "PATCH", "/rest/v1/import_jobs", service_role=True, params={"id": f"eq.{job_id}"}, body={"status": "failed", "errors": [{"message": "写入题目失败"}]})
        raise HTTPException(status_code=502, detail="题目写入失败")
    status, _ = await supabase_request(request, "POST", "/rest/v1/rpc/app_publish_math_batch", service_role=True, body={"p_batch": batch_id, "p_teacher": teacher["user_id"]})
    if status >= 400:
        await supabase_request(request, "PATCH", "/rest/v1/import_jobs", service_role=True, params={"id": f"eq.{job_id}"}, body={"status": "failed", "errors": [{"message": "发布批次失败"}]})
        raise HTTPException(status_code=422, detail="题目已上传但发布失败，请联系管理员检查导入记录")
    return {"topic_id": topic_id, "batch_id": batch_id, "name": topics[0]["code"], "question_count": len(result)}


async def _classroom_payload(request: Request, session: dict[str, Any], *, include_answer: bool = False) -> dict[str, Any]:
    question = None
    if session.get("current_question_id"):
        status, rows = await supabase_request(request, "GET", "/rest/v1/questions", service_role=True, params={"id": f"eq.{session['current_question_id']}", "batch_id": f"eq.{session['batch_id']}", "select": "id,sort_order,question_type,image_bucket,image_path"})
        if rows:
            row = rows[0]
            question = {"id": row["id"], "sort_order": row["sort_order"], "question_type": row["question_type"], "image_url": await _signed_question_image(request, row["image_bucket"], row["image_path"])}
    participant_status, participants = await supabase_request(request, "GET", "/rest/v1/classroom_participants", service_role=True, params={"session_id": f"eq.{session['id']}", "select": "student_id"})
    answer_count = 0
    if question:
        _, answers = await supabase_request(request, "GET", "/rest/v1/classroom_answers", service_role=True, params={"session_id": f"eq.{session['id']}", "question_id": f"eq.{question['id']}", "select": "selected_option,is_correct"})
        answer_count = len(answers)
        if include_answer:
            question["distribution"] = {key: sum(1 for answer in answers if answer["selected_option"] == key) for key in "ABCD"}
    return {**session, "question": question, "participant_count": len(participants) if participant_status < 400 else 0, "submitted_count": answer_count}


@app.get("/api/classroom/{access_token}")
async def get_classroom(access_token: str, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    await verify_student_token(request, authorization)
    status, rows = await supabase_request(request, "GET", "/rest/v1/classroom_sessions", service_role=True, params={"access_token": f"eq.{access_token}", "select": "id,batch_id,class_id,access_token,status,current_question_id,question_status,duration_seconds,question_opened_at,deadline_at,expires_at,closed_at", "limit": "1"})
    if status >= 400 or not rows or rows[0]["status"] in {"closed", "invalidated"}:
        raise HTTPException(status_code=404, detail="课堂已结束或链接失效")
    return await _classroom_payload(request, rows[0])


@app.post("/api/classroom/{access_token}/join")
async def join_classroom(access_token: str, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    status, rows = await supabase_request(request, "GET", "/rest/v1/classroom_sessions", service_role=True, params={"access_token": f"eq.{access_token}", "select": "id,batch_id,status,expires_at"})
    if status >= 400 or not rows or rows[0]["status"] in {"closed", "invalidated"}:
        raise HTTPException(status_code=404, detail="课堂已结束或链接失效")
    session = rows[0]
    join_status, _ = await supabase_request(request, "POST", "/rest/v1/classroom_participants", service_role=True, body={"session_id": session["id"], "student_id": student["id"]})
    if join_status >= 400 and join_status != 409:
        raise HTTPException(status_code=409, detail="无法加入课堂")
    return {"joined": True}


@app.post("/api/classroom/{access_token}/answer")
async def answer_classroom(access_token: str, payload: ClassroomAnswerRequest, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    status, rows = await supabase_request(request, "GET", "/rest/v1/classroom_sessions", service_role=True, params={"access_token": f"eq.{access_token}", "select": "id,batch_id,status,current_question_id,question_status"})
    if status >= 400 or not rows or rows[0]["status"] != "active" or rows[0]["question_status"] != "open" or rows[0]["current_question_id"] != payload.question_id:
        raise HTTPException(status_code=409, detail="课堂题目已关闭")
    answer_status, result = await supabase_request(request, "POST", "/rest/v1/classroom_answers", service_role=True, prefer_representation=True, body={"session_id": rows[0]["id"], "student_id": student["id"], "question_id": payload.question_id, "selected_option": payload.selected_option, "is_correct": False})
    if answer_status >= 400:
        answer_status, result = await supabase_request(request, "PATCH", "/rest/v1/classroom_answers", service_role=True, prefer_representation=True, params={"session_id": f"eq.{rows[0]['id']}", "student_id": f"eq.{student['id']}", "question_id": f"eq.{payload.question_id}"}, body={"selected_option": payload.selected_option})
    if answer_status >= 400:
        raise HTTPException(status_code=409, detail="答案提交失败")
    return {"submitted": True}


@app.post("/api/teacher/classrooms/{session_id}/start")
async def start_new_classroom(session_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = bearer_token(authorization); teacher = await current_teacher_profile(request, token)
    status, rows = await supabase_request(request, "GET", "/rest/v1/classroom_sessions", service_role=True, params={"id": f"eq.{session_id}", "created_by": f"eq.{teacher['user_id']}", "select": "id,batch_id,status"})
    if status >= 400 or not rows: raise HTTPException(status_code=404, detail="找不到课堂")
    _, questions = await supabase_request(request, "GET", "/rest/v1/classroom_session_questions", service_role=True, params={"session_id": f"eq.{session_id}", "select": "question_id,sort_order", "order": "sort_order.asc"})
    if not questions: raise HTTPException(status_code=409, detail="课堂没有题目")
    now = utc_now(); update_status, result = await supabase_request(request, "PATCH", "/rest/v1/classroom_sessions", service_role=True, prefer_representation=True, params={"id": f"eq.{session_id}"}, body={"status": "active", "current_question_id": questions[0]["question_id"], "question_status": "open", "question_opened_at": now.isoformat(), "deadline_at": (now + timedelta(seconds=60)).isoformat()})
    if update_status >= 400: raise HTTPException(status_code=502, detail="课堂启动失败")
    return result[0]


@app.post("/api/teacher/classrooms/{session_id}/next")
async def next_new_classroom(session_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = bearer_token(authorization); teacher = await current_teacher_profile(request, token)
    status, rows = await supabase_request(request, "GET", "/rest/v1/classroom_sessions", service_role=True, params={"id": f"eq.{session_id}", "created_by": f"eq.{teacher['user_id']}", "select": "id,status,current_question_id"})
    if status >= 400 or not rows: raise HTTPException(status_code=404, detail="找不到课堂")
    session = rows[0]
    _, questions = await supabase_request(request, "GET", "/rest/v1/classroom_session_questions", service_role=True, params={"session_id": f"eq.{session_id}", "select": "question_id,sort_order", "order": "sort_order.asc"})
    index = next((i for i, q in enumerate(questions) if q["question_id"] == session.get("current_question_id")), -1)
    now = utc_now()
    if index < 0 or index + 1 >= len(questions):
        body = {"status": "closed", "question_status": "locked", "closed_at": now.isoformat(), "question_opened_at": None, "deadline_at": None}
    else:
        body = {"status": "active", "current_question_id": questions[index + 1]["question_id"], "question_status": "open", "question_opened_at": now.isoformat(), "deadline_at": (now + timedelta(seconds=60)).isoformat()}
    updated_status, result = await supabase_request(request, "PATCH", "/rest/v1/classroom_sessions", service_role=True, prefer_representation=True, params={"id": f"eq.{session_id}"}, body=body)
    if updated_status >= 400: raise HTTPException(status_code=502, detail="切换课堂题目失败")
    return result[0]


@app.get("/api/teacher/classrooms/{session_id}/stats")
async def new_classroom_stats(session_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = bearer_token(authorization); teacher = await current_teacher_profile(request, token)
    status, rows = await supabase_request(request, "GET", "/rest/v1/classroom_sessions", service_role=True, params={"id": f"eq.{session_id}", "created_by": f"eq.{teacher['user_id']}", "select": "id,status,current_question_id,question_status,duration_seconds,question_opened_at,deadline_at"})
    if status >= 400 or not rows: raise HTTPException(status_code=404, detail="找不到课堂")
    return await _classroom_payload(request, rows[0], include_answer=True)


@app.get("/api/teacher/reports")
async def teacher_report_index(request: Request, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    token = bearer_token(authorization); teacher = await current_teacher_profile(request, token)
    status, classrooms = await supabase_request(request, "GET", "/rest/v1/classroom_sessions", service_role=True, params={"created_by": f"eq.{teacher['user_id']}", "select": "id,batch_id,class_id,status,created_at,closed_at,classes(name,code),math_batches(topics(code,name))", "order": "created_at.desc"})
    practice_status, practices = await supabase_request(request, "GET", "/rest/v1/practices", service_role=True, params={"created_by": f"eq.{teacher['user_id']}", "select": "id,batch_id,access_code,status,created_at,math_batches(topics(code,name))", "order": "created_at.desc"})
    result = []
    for item in classrooms if status < 400 else []:
        topic = (item.get("math_batches") or {}).get("topics") or {}
        cls = item.get("classes") or {}
        result.append({"id": item["id"], "kind": "classroom", "status": item["status"], "title": f"{topic.get('code','')} {topic.get('name','')}", "subtitle": cls.get("name") or cls.get("code", ""), "created_at": item.get("created_at"), "closed_at": item.get("closed_at")})
    for item in practices if practice_status < 400 else []:
        topic = (item.get("math_batches") or {}).get("topics") or {}
        result.append({"id": item["id"], "kind": "practice", "status": item["status"], "title": f"{topic.get('code','')} {topic.get('name','')}", "subtitle": f"练习码 {item.get('access_code','')}", "created_at": item.get("created_at")})
    return sorted(result, key=lambda row: row.get("created_at") or "", reverse=True)


@app.get("/api/teacher/reports/practice-summary")
async def teacher_practice_summary(
    request: Request,
    class_id: str,
    batch_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    teacher = await current_teacher_profile(request, token)
    class_status, classes = await supabase_request(
        request, "GET", "/rest/v1/classes", service_role=True,
        params={"id": f"eq.{class_id}", "school_id": f"eq.{teacher['school_id']}", "is_active": "eq.true", "select": "id,code,name,grade_id,grades(code,name)"},
    )
    if class_status >= 400 or not classes:
        raise HTTPException(status_code=404, detail="找不到可用班级")
    batch_status, batches = await supabase_request(
        request, "GET", "/rest/v1/math_batches", service_role=True,
        params={"id": f"eq.{batch_id}", "status": "eq.published", "select": "id,topic_id,topics!inner(code,name,school_id)"},
    )
    if batch_status >= 400 or not batches or batches[0].get("topics", {}).get("school_id") != teacher["school_id"]:
        raise HTTPException(status_code=404, detail="找不到当前题库")
    students_status, students = await supabase_request(
        request, "GET", "/rest/v1/students", service_role=True,
        params={"class_id": f"eq.{class_id}", "is_active": "eq.true", "select": "id,name,student_number", "order": "student_number.asc"},
    )
    if students_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取班级学生")
    student_ids = [student["id"] for student in students]
    rounds: list[dict[str, Any]] = []
    if student_ids:
        round_status, rounds = await supabase_request(
            request, "GET", "/rest/v1/practice_rounds", service_role=True,
            params={"batch_id": f"eq.{batch_id}", "student_id": f"in.({','.join(student_ids)})", "status": "eq.completed", "select": "id,student_id,completed_at", "order": "completed_at.desc"},
        )
        if round_status >= 400:
            raise HTTPException(status_code=502, detail="无法读取班级答题记录")
    latest_round_ids: list[str] = []
    latest_students: set[str] = set()
    for round_row in rounds:
        student_id = round_row.get("student_id")
        if student_id and student_id not in latest_students:
            latest_students.add(student_id)
            latest_round_ids.append(round_row["id"])
    answers: list[dict[str, Any]] = []
    if latest_round_ids:
        answer_status, answers = await supabase_request(
            request, "GET", "/rest/v1/practice_answers", service_role=True,
            params={"round_id": f"in.({','.join(latest_round_ids)})", "state": "in.(confirmed,unanswered)", "select": "question_id,selected_option,is_correct,round_id"},
        )
        if answer_status >= 400:
            raise HTTPException(status_code=502, detail="无法读取题目答案")
    question_status, questions = await supabase_request(
        request, "GET", "/rest/v1/questions", service_role=True,
        params={"batch_id": f"eq.{batch_id}", "select": "id,sort_order,question_type,correct_option", "order": "sort_order.asc"},
    )
    if question_status >= 400:
        raise HTTPException(status_code=502, detail="无法读取题库题目")
    reports = []
    for question in questions:
        current = [answer for answer in answers if answer.get("question_id") == question["id"]]
        distribution = {key: sum(1 for answer in current if answer.get("selected_option") == key) for key in "ABCD"}
        correct_count = sum(1 for answer in current if answer.get("is_correct") is True)
        answered_count = sum(1 for answer in current if answer.get("selected_option") or answer.get("is_correct") is not None)
        reports.append({
            "id": question["id"], "sort_order": question["sort_order"], "question_type": question["question_type"],
            "correct_option": question.get("correct_option"), "submitted_count": answered_count,
            "unanswered_count": max(len(latest_round_ids) - answered_count, 0), "correct_count": correct_count,
            "accuracy": round(correct_count / answered_count * 100, 1) if answered_count else 0, "distribution": distribution,
        })
    topic = batches[0].get("topics") or {}
    return {
        "title": f"{topic.get('code', '')} {topic.get('name', '')}",
        "class": classes[0], "batch_id": batch_id, "student_count": len(students),
        "completed_count": len(latest_round_ids), "participant_count": len(latest_round_ids), "questions": reports,
    }


@app.get("/api/teacher/reports/{kind}/{item_id}")
async def teacher_report(kind: str, item_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = bearer_token(authorization); teacher = await current_teacher_profile(request, token)
    if kind == "classroom":
        status, sessions = await supabase_request(request, "GET", "/rest/v1/classroom_sessions", service_role=True, params={"id": f"eq.{item_id}", "created_by": f"eq.{teacher['user_id']}", "select": "id,batch_id,status,created_at,closed_at,class_id,classes(name,code)"})
        if status >= 400 or not sessions: raise HTTPException(status_code=404, detail="找不到课堂")
        session = sessions[0]; _, links = await supabase_request(request, "GET", "/rest/v1/classroom_session_questions", service_role=True, params={"session_id": f"eq.{item_id}", "select": "question_id,sort_order", "order": "sort_order.asc"})
        _, answers = await supabase_request(request, "GET", "/rest/v1/classroom_answers", service_role=True, params={"session_id": f"eq.{item_id}", "select": "question_id,selected_option,is_correct,student_id"})
        participant_status, participants = await supabase_request(request, "GET", "/rest/v1/classroom_participants", service_role=True, params={"session_id": f"eq.{item_id}", "select": "student_id"})
        title = "课堂统计"; total = len(participants) if participant_status < 400 else 0
    elif kind == "practice":
        status, practices = await supabase_request(request, "GET", "/rest/v1/practices", service_role=True, params={"id": f"eq.{item_id}", "created_by": f"eq.{teacher['user_id']}", "select": "id,batch_id,access_code,status,created_at"})
        if status >= 400 or not practices: raise HTTPException(status_code=404, detail="找不到练习")
        session = practices[0]
        _, links = await supabase_request(request, "GET", "/rest/v1/practice_questions", service_role=True, params={"practice_id": f"eq.{item_id}", "select": "question_id,sort_order", "order": "sort_order.asc"})
        round_status, rounds = await supabase_request(request, "GET", "/rest/v1/practice_rounds", service_role=True, params={"practice_id": f"eq.{item_id}", "status": "eq.completed", "select": "id,student_id,completed_at", "order": "completed_at.desc"})
        if round_status >= 400:
            raise HTTPException(status_code=502, detail="无法读取课后练习轮次")
        latest_round_ids: list[str] = []
        latest_students: set[str] = set()
        for round_row in rounds:
            student_id = round_row.get("student_id")
            if student_id and student_id not in latest_students:
                latest_students.add(student_id)
                latest_round_ids.append(round_row["id"])
        _, answers = await supabase_request(request, "GET", "/rest/v1/practice_answers", service_role=True, params={"round_id": f"in.({','.join(latest_round_ids)})", "state": "in.(confirmed,unanswered)", "select": "question_id,selected_option,is_correct,round_id"}) if latest_round_ids else (200, [])
        total = len(latest_round_ids)
        title = f"练习码 {session['access_code']}"
    else: raise HTTPException(status_code=404, detail="统计类型无效")
    question_ids = [link["question_id"] for link in links]
    _, questions = await supabase_request(request, "GET", "/rest/v1/questions", service_role=True, params={"id": f"in.({','.join(question_ids)})" if question_ids else "eq.invalid", "select": "id,sort_order,question_type,correct_option"})
    reports = []
    for question in sorted(questions, key=lambda row: row["sort_order"]):
        current = [answer for answer in answers if answer.get("question_id") == question["id"]]
        distribution = {key: sum(1 for answer in current if answer.get("selected_option") == key) for key in "ABCD"}
        correct = sum(1 for answer in current if answer.get("is_correct") is True)
        reports.append({"id": question["id"], "sort_order": question["sort_order"], "question_type": question["question_type"], "correct_option": question.get("correct_option"), "submitted_count": len(current), "correct_count": correct, "accuracy": round(correct / len(current) * 100) if current else 0, "distribution": distribution})
    return {"title": title, "session": session, "participant_count": total, "questions": reports}


@app.get("/api/student/words")
async def student_words(request: Request, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    student = await verify_student_token(request, authorization)
    status, rows = await supabase_request(request, "GET", "/rest/v1/words", service_role=True, params={"grade_id": f"eq.{student['grade_id']}", "select": "id,word,meaning,sort_order,word_batches!inner(status)", "word_batches.status": "eq.published", "order": "sort_order.asc"})
    if status >= 400: raise HTTPException(status_code=502, detail="无法读取单词")
    return rows


@app.get("/api/student/words/review")
async def student_words_review(request: Request, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    student = await verify_student_token(request, authorization)
    status, rows = await supabase_request(request, "GET", "/rest/v1/word_progress", service_role=True, params={"student_id": f"eq.{student['id']}", "due_at": f"lte.{utc_now().isoformat()}", "select": "word_id,last_rating,interval_days,due_at,words(id,word,meaning)", "order": "due_at.asc"})
    if status >= 400: raise HTTPException(status_code=502, detail="无法读取复习单词")
    return rows


@app.post("/api/student/words/rate")
async def rate_student_word(payload: WordRatingRequest, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    status, result = await supabase_request(request, "POST", "/rest/v1/rpc/app_rate_word", service_role=True, body={"p_student": student["id"], "p_word": payload.word_id, "p_rating": payload.rating})
    if status >= 400: raise HTTPException(status_code=409, detail="单词进度保存失败")
    return result


@app.get("/api/teacher/words")
async def teacher_words(request: Request, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    token = bearer_token(authorization); teacher = await current_teacher_profile(request, token)
    status, rows = await supabase_request(request, "GET", "/rest/v1/word_batches", service_role=True, params={"status": "eq.published", "select": "id,grade_id,created_at,grades(code,name),words(count)", "grades.school_id": f"eq.{teacher['school_id']}"})
    if status >= 400: raise HTTPException(status_code=502, detail="无法读取单词词库")
    return [{**row, "word_count": (row.get("words") or [{"count": 0}])[0].get("count", 0)} for row in rows]


@app.post("/api/teacher/words/import")
async def import_words(request: Request, grade_id: str = Form(...), file: UploadFile = File(...), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = bearer_token(authorization); teacher = await current_teacher_profile(request, token)
    if not file.filename or not file.filename.lower().endswith(".xlsx"): raise HTTPException(status_code=422, detail="只支持 .xlsx 格式的 Excel 文件")
    from openpyxl import load_workbook
    from io import BytesIO
    try: rows = list(load_workbook(filename=BytesIO(await file.read()), read_only=True, data_only=True).active.iter_rows(values_only=True))
    except Exception as exc: raise HTTPException(status_code=422, detail="无法读取 Excel 文件") from exc
    if not rows or len(rows[0]) < 2: raise HTTPException(status_code=422, detail="单词表必须包含单词、词义两列")
    headers = [str(value or '').strip().lower() for value in rows[0]]
    try: word_col = next(i for i, value in enumerate(headers) if value in {'单词','word'}) ; meaning_col = next(i for i, value in enumerate(headers) if value in {'词义','词意','meaning','中文'})
    except StopIteration as exc: raise HTTPException(status_code=422, detail="单词表必须包含“单词”和“词义”列") from exc
    words = []; seen = set(); errors = []
    for row_number, row in enumerate(rows[1:], start=2):
        word = str(row[word_col] or '').strip() if word_col < len(row) else ''; meaning = str(row[meaning_col] or '').strip() if meaning_col < len(row) else ''
        if not word and not meaning: continue
        normalized = word.casefold()
        if not word or not meaning: errors.append(f"第 {row_number} 行：单词和词义不能为空"); continue
        if normalized in seen: continue
        seen.add(normalized); words.append((word, meaning))
    if errors: raise HTTPException(status_code=422, detail={"message": "Excel 文件存在错误", "errors": errors})
    if not words: raise HTTPException(status_code=422, detail="没有可导入的单词")
    _, grades = await supabase_request(request, "GET", "/rest/v1/grades", service_role=True, params={"id": f"eq.{grade_id}", "school_id": f"eq.{teacher['school_id']}", "select": "id"})
    if not grades: raise HTTPException(status_code=404, detail="找不到年级")
    job_id, batch_id = str(uuid4()), str(uuid4())
    await supabase_request(request, "POST", "/rest/v1/import_jobs", service_role=True, body={"id": job_id, "created_by": teacher["user_id"], "kind": "words", "grade_id": grade_id, "filename": file.filename, "status": "preview"})
    batch_status, _ = await supabase_request(request, "POST", "/rest/v1/word_batches", service_role=True, body={"id": batch_id, "grade_id": grade_id, "created_by": teacher["user_id"], "import_job_id": job_id, "status": "draft"})
    if batch_status >= 400: raise HTTPException(status_code=502, detail="无法建立单词批次")
    word_rows = [{"batch_id": batch_id, "grade_id": grade_id, "word": word, "meaning": meaning, "sort_order": index} for index, (word, meaning) in enumerate(words, start=1)]
    write_status, _ = await supabase_request(request, "POST", "/rest/v1/words", service_role=True, body=word_rows)
    if write_status >= 400: raise HTTPException(status_code=502, detail="单词写入失败")
    publish_status, _ = await supabase_request(request, "POST", "/rest/v1/rpc/app_publish_word_batch", service_role=True, body={"p_batch": batch_id, "p_teacher": teacher["user_id"]})
    if publish_status >= 400: raise HTTPException(status_code=422, detail="单词发布失败")
    return {"batch_id": batch_id, "word_count": len(words)}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "hhx-backend"}


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, Any]:
    username = payload.username.strip()
    if payload.mode == "student":
        status, students = await supabase_request(
            request,
            "POST",
            "/rest/v1/rpc/app_authenticate_student",
            service_role=True,
            body={"p_student_number": username, "p_password": payload.password},
        )
        if status >= 400 or not students:
            raise HTTPException(status_code=401, detail="學號或密碼不正確")
        student = students[0]
        student_token, expires_at = await create_student_session(request, student)
        return {
            "mode": "student",
            "student_token": student_token,
            "expires_at": expires_at.isoformat(),
            "user": {
                "id": student["student_id"],
                "student_number": student["student_number"],
                "display_name": student["name"],
                "grade_id": student["grade_id"],
                "grade": student["grade_code"],
                "class_id": student["class_id"],
                "class_name": student["class_name"],
            },
        }

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


@app.get("/api/student/me")
async def current_student(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    grade = await _student_grade(request, student)
    class_status, classes = await supabase_request(
        request, "GET", "/rest/v1/classes", service_role=True,
        params={"id": f"eq.{student['class_id']}", "school_id": f"eq.{student['school_id']}", "select": "id,name,code"},
    )
    if class_status >= 400 or not classes:
        raise HTTPException(status_code=403, detail="學生班級資料不可用")
    return {**student, "display_name": student["name"], "grade": grade["code"], "class_name": classes[0]["name"]}


async def _student_grade(request: Request, student: dict[str, Any]) -> dict[str, Any]:
    status, grades = await supabase_request(
        request,
        "GET",
        "/rest/v1/grades",
        service_role=True,
        params={"id": f"eq.{student['grade_id']}", "school_id": f"eq.{student['school_id']}", "select": "id,code,name,is_active"},
    )
    if status >= 400 or not grades or not grades[0].get("is_active"):
        raise HTTPException(status_code=403, detail="學生年級資料不可用")
    return grades[0]


async def _published_topic(request: Request, student: dict[str, Any], topic_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    status, topics = await supabase_request(
        request,
        "GET",
        "/rest/v1/topics",
        service_role=True,
        params={"id": f"eq.{topic_id}", "school_id": f"eq.{student['school_id']}", "is_active": "eq.true", "select": "id,school_id,grade_id,code,name"},
    )
    if status >= 400 or not topics:
        raise HTTPException(status_code=404, detail="找不到可用主題")
    grade = await _student_grade(request, student)
    if grade["code"] != "S6" or topics[0]["grade_id"] != student["grade_id"]:
        raise HTTPException(status_code=403, detail="自主數學練習僅開放 S6 學生")
    batch_status, batches = await supabase_request(
        request,
        "GET",
        "/rest/v1/math_batches",
        service_role=True,
        params={"topic_id": f"eq.{topic_id}", "status": "eq.published", "select": "id,topic_id,status", "limit": "1"},
    )
    if batch_status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取主題內容")
    if not batches:
        raise HTTPException(status_code=404, detail="這個主題目前沒有題目")
    return topics[0], batches[0]


async def _question_payloads(
    request: Request,
    batch_id: str,
    answer_rows: list[dict[str, Any]] | None = None,
    *,
    practice_id: str | None = None,
) -> list[dict[str, Any]]:
    if practice_id:
        link_status, links = await supabase_request(
            request, "GET", "/rest/v1/practice_questions", service_role=True,
            params={"practice_id": f"eq.{practice_id}", "select": "question_id,sort_order", "order": "sort_order.asc"},
        )
        if link_status >= 400:
            raise HTTPException(status_code=502, detail="無法讀取練習題目清單")
        question_ids = [item["question_id"] for item in links]
        if not question_ids:
            return []
        query = {"id": f"in.({','.join(question_ids)})", "batch_id": f"eq.{batch_id}",
                 "select": "id,sort_order,question_type,image_bucket,image_path,image_bytes,correct_option", "order": "sort_order.asc"}
    else:
        query = {"batch_id": f"eq.{batch_id}",
                 "select": "id,sort_order,question_type,image_bucket,image_path,image_bytes,correct_option", "order": "sort_order.asc"}
    question_status, questions = await supabase_request(request, "GET", "/rest/v1/questions", service_role=True, params=query)
    if question_status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取題目")
    answers = {item["question_id"]: item for item in (answer_rows or [])}
    payloads = []
    for question in questions:
        answer = answers.get(question["id"])
        image_url = await _signed_question_image(request, question["image_bucket"], question["image_path"])
        result = {
            "id": question["id"], "sort_order": question["sort_order"],
            "question_type": question["question_type"], "image_url": image_url,
            "answer": ({"selected_option": answer.get("selected_option"),
                        "text_answer": answer.get("text_answer"), "state": answer["state"],
                        "is_correct": answer.get("is_correct")} if answer else None),
        }
        if answer and answer.get("state") == "confirmed":
            result["correct_option"] = question.get("correct_option")
        payloads.append(result)
    return payloads


async def _signed_question_image(request: Request, bucket: str, path: str) -> str:
    from urllib.parse import quote
    status, result = await supabase_request(
        request, "POST", f"/storage/v1/object/sign/{quote(bucket, safe='')}/{quote(path, safe='/')}",
        service_role=True, body={"expiresIn": 900},
    )
    signed_url = result.get("signedURL") or result.get("signedUrl") if isinstance(result, dict) else None
    if status >= 400 or not signed_url:
        raise HTTPException(status_code=502, detail="無法讀取題目圖片")
    if signed_url.startswith("http://") or signed_url.startswith("https://"):
        return signed_url
    return f"{supabase_url(request)}{signed_url if signed_url.startswith('/storage/v1/') else '/storage/v1' + signed_url}"


@app.get("/api/student/topics")
async def list_student_topics(request: Request, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    student = await verify_student_token(request, authorization)
    grade = await _student_grade(request, student)
    if grade["code"] != "S6":
        raise HTTPException(status_code=403, detail="自主數學練習僅開放 S6 學生；請使用老師提供的練習碼")
    status, topics = await supabase_request(
        request, "GET", "/rest/v1/topics", service_role=True,
        params={"school_id": f"eq.{student['school_id']}", "grade_id": f"eq.{student['grade_id']}",
                "is_active": "eq.true", "select": "id,code,name,sort_order", "order": "sort_order.asc"},
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取數學主題")
    if not topics:
        return []
    ids = [item["id"] for item in topics]
    batch_status, batches = await supabase_request(
        request, "GET", "/rest/v1/math_batches", service_role=True,
        params={"topic_id": f"in.({','.join(ids)})", "status": "eq.published", "select": "id,topic_id,questions(count)"},
    )
    if batch_status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取主題題目數量")
    by_topic = {}
    for batch in batches:
        counts = batch.get("questions") or [{"count": 0}]
        by_topic[batch["topic_id"]] = {"batch_id": batch["id"], "question_count": counts[0].get("count", 0)}
    return [{**topic, **by_topic.get(topic["id"], {"batch_id": None, "question_count": 0})} for topic in topics]


@app.get("/api/student/topics/{topic_id}")
async def get_student_topic(topic_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    topic, batch = await _published_topic(request, student, topic_id)
    questions = await _question_payloads(request, batch["id"])
    return {**topic, "batch_id": batch["id"], "questions": questions}


async def _student_practice_context(request: Request, student: dict[str, Any], access_code: str) -> tuple[dict[str, Any], dict[str, Any]]:
    status, practices = await supabase_request(
        request, "GET", "/rest/v1/practices", service_role=True,
        params={"access_code": f"eq.{access_code.strip().upper()}", "status": "eq.active", "select": "id,batch_id,access_code,status", "limit": "1"},
    )
    if status >= 400 or not practices:
        raise HTTPException(status_code=404, detail="練習碼無效或已失效")
    practice = practices[0]
    batch_status, batches = await supabase_request(
        request, "GET", "/rest/v1/math_batches", service_role=True,
        params={"id": f"eq.{practice['batch_id']}", "status": "eq.published", "select": "id,topic_id,status,topics(id,school_id,grade_id,code,name,is_active)"},
    )
    if batch_status >= 400 or not batches:
        raise HTTPException(status_code=404, detail="練習內容已更新或不可用")
    topic = batches[0].get("topics")
    if not topic or not topic.get("is_active") or topic["school_id"] != student["school_id"]:
        raise HTTPException(status_code=403, detail="此練習碼不可用")
    return practice, batches[0]


async def _start_student_round(request: Request, student: dict[str, Any], batch: dict[str, Any], practice_id: str | None) -> dict[str, Any]:
    params = {"student_id": f"eq.{student['id']}", "batch_id": f"eq.{batch['id']}",
              "status": "eq.in_progress", "select": "id,student_id,batch_id,practice_id,status"}
    params["practice_id"] = f"eq.{practice_id}" if practice_id else "is.null"
    status, rounds = await supabase_request(request, "GET", "/rest/v1/practice_rounds", service_role=True, params=params)
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法恢復練習進度")
    if rounds:
        return rounds[0]
    status, created = await supabase_request(
        request, "POST", "/rest/v1/practice_rounds", service_role=True, prefer_representation=True,
        body={"student_id": student["id"], "batch_id": batch["id"], "practice_id": practice_id, "status": "in_progress"},
    )
    if status >= 400 or not created:
        raise HTTPException(status_code=409, detail="無法開始練習；內容可能已更新")
    return created[0]


async def _round_payload(request: Request, round_row: dict[str, Any], practice_id: str | None) -> dict[str, Any]:
    answer_status, answers = await supabase_request(
        request, "GET", "/rest/v1/practice_answers", service_role=True,
        params={"round_id": f"eq.{round_row['id']}", "select": "question_id,selected_option,text_answer,state,is_correct,confirmed_at", "order": "updated_at.asc"},
    )
    if answer_status >= 400:
        raise HTTPException(status_code=502, detail="無法恢復答案")
    questions = await _question_payloads(request, round_row["batch_id"], answers, practice_id=practice_id)
    return {"round_id": round_row["id"], "status": round_row["status"], "questions": questions}


@app.post("/api/student/rounds/start")
async def start_student_round(payload: StudentRoundStartRequest, request: Request,
                              authorization: str | None = Header(default=None)) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    if bool(payload.topic_id) == bool(payload.access_code):
        raise HTTPException(status_code=422, detail="必須指定主題或練習碼其中一種")
    if payload.topic_id:
        _, batch = await _published_topic(request, student, payload.topic_id)
        practice_id = None
    else:
        practice, batch = await _student_practice_context(request, student, payload.access_code or "")
        practice_id = practice["id"]
    round_row = await _start_student_round(request, student, batch, practice_id)
    return await _round_payload(request, round_row, practice_id)


@app.post("/api/student/rounds/answer")
async def save_student_round_answer(payload: StudentRoundAnswerRequest, request: Request,
                                    authorization: str | None = Header(default=None)) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    status, result = await supabase_request(
        request, "POST", "/rest/v1/rpc/app_save_practice_answer", service_role=True,
        body={"p_round": payload.round_id, "p_student": student["id"], "p_question": payload.question_id,
              "p_option": payload.selected_option, "p_text": payload.text_answer, "p_confirm": payload.confirm},
    )
    if status >= 400:
        raise HTTPException(status_code=409, detail="答案保存失敗；練習可能已結束或題目已更新")
    return result if isinstance(result, dict) else {"saved": True}


@app.post("/api/student/rounds/finish")
async def finish_student_round(payload: StudentRoundFinishRequest, request: Request,
                               authorization: str | None = Header(default=None)) -> Any:
    student = await verify_student_token(request, authorization)
    status, result = await supabase_request(
        request, "POST", "/rest/v1/rpc/app_finish_round", service_role=True,
        body={"p_round": payload.round_id, "p_student": student["id"],
              "p_answers": [item.model_dump() for item in payload.answers]},
    )
    if status >= 400:
        raise HTTPException(status_code=409, detail="整份提交失敗；練習可能已結束或題目已更新")
    return {"completed": True, "answers": result}


@app.post("/api/student/logout")
async def logout_student(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    token = bearer_token(authorization)
    status, _ = await supabase_request(
        request,
        "PATCH",
        "/rest/v1/student_sessions",
        service_role=True,
        params={
            "token_hash": f"eq.{hashlib.sha256(token.encode('utf-8')).hexdigest()}",
            "revoked_at": "is.null",
        },
        body={"revoked_at": utc_now().isoformat()},
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="學生登出失敗")
    return {"logged_out": True}


@app.get("/api/auth/me")
async def current_teacher(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    profile = await current_teacher_profile(request, token)
    return profile


# Legacy question-set handlers intentionally not registered.
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
    if not payload.batch_id:
        raise HTTPException(status_code=422, detail="必须指定题库批次")
    if payload.batch_id:
        batch_status, batches = await supabase_request(request, "GET", "/rest/v1/math_batches", service_role=True, params={"id": f"eq.{payload.batch_id}", "status": "eq.published", "select": "id,topic_id,topics(school_id)"})
        if batch_status >= 400 or not batches or batches[0].get("topics", {}).get("school_id") != teacher["school_id"]:
            raise HTTPException(status_code=404, detail="找不到可用题库批次")
        question_status, questions = await supabase_request(request, "GET", "/rest/v1/questions", service_role=True, params={"batch_id": f"eq.{payload.batch_id}", "question_type": "eq.single_choice", "select": "id,sort_order", "order": "sort_order.asc"})
        if question_status >= 400 or not questions:
            raise HTTPException(status_code=409, detail="课堂没有可用的选择题")
        if payload.session_type == "homework":
            code = secrets.token_hex(4).upper()
            rpc_status, practice_id = await supabase_request(request, "POST", "/rest/v1/rpc/app_create_practice", service_role=True, body={"p_batch": payload.batch_id, "p_teacher": teacher["user_id"], "p_code": code})
            if rpc_status >= 400:
                raise HTTPException(status_code=502, detail="创建练习码失败")
            return {"id": practice_id, "practice_code": code, "question_count": len(questions), "join_url": f"{env_value(request, 'PUBLIC_APP_URL', 'http://localhost:5173').rstrip('/')}/student/practice/{code}"}
        if not payload.class_id:
            raise HTTPException(status_code=422, detail="课堂必须选择班级")
        session_status, created = await supabase_request(request, "POST", "/rest/v1/classroom_sessions", service_role=True, prefer_representation=True, body={"batch_id": payload.batch_id, "class_id": payload.class_id, "created_by": teacher["user_id"], "duration_seconds": int(payload.time_limit_seconds or 30)})
        if session_status >= 400 or not created:
            raise HTTPException(status_code=502, detail="创建课堂失败")
        session = created[0]
        links = [{"session_id": session["id"], "batch_id": payload.batch_id, "question_id": q["id"], "sort_order": q["sort_order"]} for q in questions]
        link_status, _ = await supabase_request(request, "POST", "/rest/v1/classroom_session_questions", service_role=True, body=links)
        if link_status >= 400:
            raise HTTPException(status_code=502, detail="写入课堂题目失败")
        app_url = env_value(request, "PUBLIC_APP_URL", "http://localhost:5173").rstrip("/")
        return {**session, "join_url": f"{app_url}/student/session/{session['access_token']}", "question_count": len(questions)}


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
    return {"session_id": session_id, "status": session["status"], "current_question_status": session["current_question_status"], "current_question_id": session.get("current_question_id"), "time_limit_seconds": int(session.get("time_limit_seconds") or 0), "question_started_at": session.get("question_started_at"), "participant_count": len(participants), "submitted_count": len(answers), "distribution": distribution}


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
            "question_image_url": question.get("question_image_url"),
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


async def public_session(access_token: str, request: Request) -> dict[str, Any]:
    session = await find_session_by_token(request, access_token)
    session = await advance_expired_session(request, session)
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


async def submit_public_answer(access_token: str, payload: AnswerRequest, request: Request) -> dict[str, Any]:
    session = await find_session_by_token(request, access_token)
    session = await advance_expired_session(request, session)
    if session.get("session_type") != "classroom" or session.get("status") != "active" or session.get("current_question_status") != "open":
        raise HTTPException(status_code=409, detail="当前题目已结束，答案未提交")
    if session.get("current_question_id") != payload.question_id:
        raise HTTPException(status_code=409, detail="当前题目已切换，答案未提交")
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


async def student_grades(
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    student = await verify_student_token(request, authorization)
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


async def student_question_sets(
    request: Request,
    grade_id: str | None = None,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    student = await verify_student_token(request, authorization)
    params = {
        "status": "eq.published",
        "select": "id,name,grade_id,created_at,questions(count)",
        "order": "created_at.desc",
    }
    if grade_id:
        params["grade_id"] = f"eq.{grade_id}"
    status, sets = await supabase_request(request, "GET", "/rest/v1/question_sets", service_role=True, params=params)
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取題目集合")
    result = []
    for item in sets:
        counts = item.pop("questions", [{"count": 0}])
        result.append({**item, "question_count": (counts[0] or {}).get("count", 0)})
    return result


async def student_question_set_detail(
    question_set_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    question_set, questions = await student_question_set(request, question_set_id)
    return {
        **question_set,
        "questions": [public_question(question, await question_options(request, question["id"])) for question in questions],
    }


async def start_student_practice(
    question_set_id: str,
    payload: StudentPracticeStartRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    await student_question_set(request, question_set_id)
    device_id = await ensure_anonymous_device(request, payload.browser_key)
    status, created = await supabase_request(
        request,
        "POST",
        "/rest/v1/student_practice_attempts",
        service_role=True,
        prefer_representation=True,
        body={"question_set_id": question_set_id, "anonymous_device_id": device_id},
    )
    if status >= 400 or not created:
        raise HTTPException(status_code=502, detail="無法開始練習")
    return {"attempt_id": created[0]["id"]}


async def answer_student_practice(
    question_set_id: str,
    payload: StudentPracticeAnswerRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    await student_question_set(request, question_set_id)
    device_id = await ensure_anonymous_device(request, payload.browser_key)
    attempt_status, attempts = await supabase_request(request, "GET", "/rest/v1/student_practice_attempts", service_role=True, params={"id": f"eq.{payload.attempt_id}", "question_set_id": f"eq.{question_set_id}", "anonymous_device_id": f"eq.{device_id}", "select": "id"})
    if attempt_status >= 400 or not attempts:
        raise HTTPException(status_code=409, detail="練習輪次已失效")
    q_status, questions = await supabase_request(request, "GET", "/rest/v1/questions", service_role=True, params={"id": f"eq.{payload.question_id}", "question_set_id": f"eq.{question_set_id}", "select": "id,correct_option_id"})
    if q_status >= 400 or not questions:
        raise HTTPException(status_code=404, detail="找不到題目")
    is_correct = questions[0].get("correct_option_id") == payload.selected_option_id
    existing_status, existing = await supabase_request(request, "GET", "/rest/v1/student_practice_answers", service_role=True, params={"attempt_id": f"eq.{payload.attempt_id}", "question_id": f"eq.{payload.question_id}", "select": "id"})
    body = {"attempt_id": payload.attempt_id, "question_id": payload.question_id, "selected_option_id": payload.selected_option_id, "is_correct": is_correct}
    if existing_status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取作答")
    if existing:
        write_status, _ = await supabase_request(request, "PATCH", "/rest/v1/student_practice_answers", service_role=True, prefer_representation=True, params={"id": f"eq.{existing[0]['id']}"}, body=body)
    else:
        write_status, _ = await supabase_request(request, "POST", "/rest/v1/student_practice_answers", service_role=True, prefer_representation=True, body=body)
    if write_status >= 400:
        raise HTTPException(status_code=409, detail="答案提交失敗")
    return {"submitted": True, "is_correct": is_correct}


async def complete_student_practice(
    question_set_id: str,
    payload: StudentPracticeCompleteRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    await student_question_set(request, question_set_id)
    device_id = await ensure_anonymous_device(request, payload.browser_key)
    status, updated = await supabase_request(request, "PATCH", "/rest/v1/student_practice_attempts", service_role=True, prefer_representation=True, params={"id": f"eq.{payload.attempt_id}", "question_set_id": f"eq.{question_set_id}", "anonymous_device_id": f"eq.{device_id}"}, body={"completed_at": utc_now().isoformat()})
    if status >= 400 or not updated:
        raise HTTPException(status_code=409, detail="練習完成狀態更新失敗")
    answer_status, answers = await supabase_request(request, "GET", "/rest/v1/student_practice_answers", service_role=True, params={"attempt_id": f"eq.{payload.attempt_id}", "select": "question_id,is_correct,selected_option_id"})
    if answer_status >= 400:
        raise HTTPException(status_code=502, detail="結果讀取失敗")
    return {"completed": True, "answers": answers}


REVIEW_INTERVAL_DAYS = [0, 1, 3, 7, 14, 30, 60]


async def get_student_review(
    request: Request,
    grade_id: str | None = None,
    browser_key: str = "",
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    if len(browser_key) < 16:
        raise HTTPException(status_code=422, detail="匿名設備識別碼無效")
    device_id = await ensure_anonymous_device(request, browser_key)
    params = {"status": "eq.published", "select": "id", "order": "created_at.desc"}
    if grade_id:
        params["grade_id"] = f"eq.{grade_id}"
    set_status, sets = await supabase_request(request, "GET", "/rest/v1/question_sets", service_role=True, params=params)
    if set_status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取複習題目")
    set_ids = [item["id"] for item in sets]
    if not set_ids:
        return {"questions": []}
    q_status, questions = await supabase_request(request, "GET", "/rest/v1/questions", service_role=True, params={"question_set_id": f"in.({','.join(set_ids)})", "select": "id,question_set_id,sort_order,question_text,question_image_url,explanation,question_type,content_type,language,correct_option_id", "order": "sort_order.asc"})
    if q_status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取複習題目")
    p_status, progress = await supabase_request(request, "GET", "/rest/v1/review_progress", service_role=True, params={"anonymous_device_id": f"eq.{device_id}", "select": "question_id,interval_level,due_at,last_rating,review_count"})
    if p_status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取複習進度")
    progress_by_question = {item["question_id"]: item for item in progress}
    now = utc_now()
    due = [question for question in questions if not progress_by_question.get(question["id"]) or datetime.fromisoformat(progress_by_question[question["id"]]["due_at"].replace("Z", "+00:00")) <= now]
    due.sort(key=lambda item: progress_by_question.get(item["id"], {}).get("due_at", ""))
    return {"questions": [{**public_question(question, await question_options(request, question["id"])), "review": progress_by_question.get(question["id"], {"interval_level": 0, "last_rating": None, "review_count": 0})} for question in due[:20]]}


async def answer_student_review(
    payload: ReviewAnswerRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    device_id = await ensure_anonymous_device(request, payload.browser_key)
    q_status, questions = await supabase_request(request, "GET", "/rest/v1/questions", service_role=True, params={"id": f"eq.{payload.question_id}", "select": "id,correct_option_id,explanation"})
    if q_status >= 400 or not questions:
        raise HTTPException(status_code=404, detail="找不到題目")
    is_correct = questions[0].get("correct_option_id") == payload.selected_option_id
    p_status, progress = await supabase_request(request, "GET", "/rest/v1/review_progress", service_role=True, params={"anonymous_device_id": f"eq.{device_id}", "question_id": f"eq.{payload.question_id}", "select": "id,interval_level,review_count"})
    if p_status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取複習進度")
    previous_level = int(progress[0].get("interval_level", 0)) if progress else 0
    if payload.rating == "forgot":
        level = 0
        due_at = utc_now() + timedelta(minutes=10)
    elif payload.rating == "fuzzy":
        level = max(1, min(previous_level, 5))
        due_at = utc_now() + timedelta(days=REVIEW_INTERVAL_DAYS[level])
    else:
        level = min(previous_level + 1, 6)
        due_at = utc_now() + timedelta(days=REVIEW_INTERVAL_DAYS[level])
    body = {"anonymous_device_id": device_id, "question_id": payload.question_id, "interval_level": level, "due_at": due_at.isoformat(), "last_rating": payload.rating, "review_count": (int(progress[0].get("review_count", 0)) + 1 if progress else 1), "last_selected_option_id": payload.selected_option_id, "last_is_correct": is_correct}
    if progress:
        write_status, _ = await supabase_request(request, "PATCH", "/rest/v1/review_progress", service_role=True, prefer_representation=True, params={"id": f"eq.{progress[0]['id']}"}, body=body)
    else:
        write_status, _ = await supabase_request(request, "POST", "/rest/v1/review_progress", service_role=True, prefer_representation=True, body=body)
    if write_status >= 400:
        raise HTTPException(status_code=502, detail="複習進度儲存失敗")
    return {"submitted": True, "is_correct": is_correct, "correct_option_id": questions[0].get("correct_option_id"), "explanation": questions[0].get("explanation"), "next_due_at": due_at.isoformat()}


async def check_student_review_answer(
    payload: ReviewAnswerRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_token(request, authorization)
    status, questions = await supabase_request(request, "GET", "/rest/v1/questions", service_role=True, params={"id": f"eq.{payload.question_id}", "select": "id,correct_option_id,explanation"})
    if status >= 400 or not questions:
        raise HTTPException(status_code=404, detail="找不到題目")
    return {"is_correct": questions[0].get("correct_option_id") == payload.selected_option_id, "correct_option_id": questions[0].get("correct_option_id"), "explanation": questions[0].get("explanation")}


Default = asgi.entrypoint(app)
