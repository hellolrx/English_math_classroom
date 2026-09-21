from __future__ import annotations

import json
from uuid import uuid4
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
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
    with httpx.Client(timeout=12.0) as client:
        response = client.request(
            method,
            f"{supabase_url(request)}{path}",
            headers=supabase_headers(
                request,
                access_token,
                service_role=service_role,
                prefer_representation=prefer_representation,
            ),
            json=body,
            params=params,
        )
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"message": response.text[:300]}
    return response.status_code, payload


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


Default = asgi.entrypoint(app)
