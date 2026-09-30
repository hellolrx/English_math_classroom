"""Classroom session API endpoints using student authentication."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field

from services.auth import decode_jwt

router = APIRouter(prefix="/api/public/sessions", tags=["sessions"])


async def supabase_request(
    request: Request,
    method: str,
    path: str,
    params: dict[str, str] | None = None,
    body: dict | None = None,
    access_token: str | None = None,
) -> tuple[int, Any]:
    """Make a request to Supabase REST API."""
    env = request.scope.get("env", {})
    supabase_url = env.get("SUPABASE_URL", "")
    anon_key = env.get("SUPABASE_ANON_KEY", "")
    
    from pyodide.ffi import to_js
    from js import Object
    
    headers = Object()
    headers["apikey"] = anon_key
    headers["Content-Type"] = "application/json"
    headers["Authorization"] = f"Bearer {access_token or anon_key}"
    
    if params:
        for k, v in params.items():
            if "?" in path:
                path += f"&{k}={v}"
            else:
                path += f"?{k}={v}"
    
    url = f"{supabase_url}{path}"
    
    fetch_options = Object()
    fetch_options["method"] = method
    fetch_options["headers"] = headers
    if body:
        fetch_options["body"] = to_js(json.dumps(body))
    
    result = await fetch(url, fetch_options)
    status = result.status
    
    if status >= 400:
        error_text = await result.text()
        return status, error_text
    
    content_type = result.headers.get("content-type", "")
    if "application/json" in content_type:
        return status, await result.json()
    else:
        return status, await result.text()


class StudentJoinRequest(BaseModel):
    student_id: str = Field(min_length=1)


class StudentAnswerRequest(BaseModel):
    question_id: str = Field(min_length=1)
    answer_type: str = Field(pattern="^(single_choice|text_input)$")
    selected_option_id: str | None = None
    answer_text: str | None = Field(default=None, max_length=5000)


async def get_student_from_token(authorization: str | None) -> dict[str, Any]:
    """Get student info from JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="需要學生登錄")
    
    token = authorization[7:]
    try:
        payload = decode_jwt(token)
    except HTTPException:
        raise
    
    if payload.get("role") != "student":
        raise HTTPException(status_code=401, detail="無效的令牌")
    
    return payload


@router.get("/{access_token}")
async def get_session(
    access_token: str,
    request: Request,
) -> dict[str, Any]:
    """Get session info (public, no auth required)."""
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        params={
            "select": "id,access_token,session_type,status,current_question_id,current_question_status,started_at,expires_at",
            "access_token": f"eq.{access_token}",
            "limit": "1",
        },
    )
    
    if status >= 400 or not isinstance(sessions, list) or not sessions:
        raise HTTPException(status_code=404, detail="課堂不存在")
    
    return sessions[0]


@router.post("/{access_token}/join")
async def join_session(
    access_token: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Join a session as a student."""
    student = await get_student_from_token(authorization)
    student_id = student.get("student_id")
    
    # Get session
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        params={
            "select": "id,status",
            "access_token": f"eq.{access_token}",
            "limit": "1",
        },
    )
    
    if status >= 400 or not isinstance(sessions, list) or not sessions:
        raise HTTPException(status_code=404, detail="課堂不存在")
    
    session = sessions[0]
    if session["status"] != "active":
        raise HTTPException(status_code=410, detail="課堂未開始或已結束")
    
    # Check if already joined
    status, existing = await supabase_request(
        request,
        "GET",
        "/rest/v1/session_students",
        params={
            "select": "id",
            "session_id": f"eq.{session['id']}",
            "student_id": f"eq.{student_id}",
            "limit": "1",
        },
    )
    
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法加入課堂")
    
    if not isinstance(existing, list) or not existing:
        # Join session
        status, _ = await supabase_request(
            request,
            "POST",
            "/rest/v1/session_students",
            body={
                "session_id": session["id"],
                "student_id": student_id,
            },
            access_token=student.get("sub"),
        )
        
        if status >= 400:
            raise HTTPException(status_code=502, detail="無法加入課堂")
    
    # Get participant count
    count_status, count_rows = await supabase_request(
        request,
        "GET",
        "/rest/v1/session_students",
        params={"session_id": f"eq.{session['id']}", "select": "id"},
    )
    
    return {
        "joined": True,
        "session_id": session["id"],
        "status": session["status"],
        "participant_count": len(count_rows) if count_status < 400 else 0,
    }


@router.post("/{access_token}/answers")
async def submit_answer(
    access_token: str,
    payload: StudentAnswerRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Submit an answer as a student."""
    student = await get_student_from_token(authorization)
    student_id = student.get("student_id")
    
    # Get session
    status, sessions = await supabase_request(
        request,
        "GET",
        "/rest/v1/sessions",
        params={
            "select": "id,status,current_question_id,current_question_status",
            "access_token": f"eq.{access_token}",
            "limit": "1",
        },
    )
    
    if status >= 400 or not isinstance(sessions, list) or not sessions:
        raise HTTPException(status_code=404, detail="課堂不存在")
    
    session = sessions[0]
    
    if session["status"] != "active" or session["current_question_status"] != "open":
        raise HTTPException(status_code=409, detail="當前題目已結束")
    
    if session["current_question_id"] != payload.question_id:
        raise HTTPException(status_code=409, detail="當前題目已切換")
    
    # Check if already submitted
    existing_status, existing = await supabase_request(
        request,
        "GET",
        "/rest/v1/student_answers",
        params={
            "select": "id,is_correct",
            "session_id": f"eq.{session['id']}",
            "student_id": f"eq.{student_id}",
            "question_id": f"eq.{payload.question_id}",
            "limit": "1",
        },
    )
    
    if existing_status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取已有答案")
    
    # Get question to check correctness
    question_status, question = await supabase_request(
        request,
        "GET",
        f"/rest/v1/questions",
        params={
            "select": "id,question_type,question_options(option_key,is_correct)",
            "id": f"eq.{payload.question_id}",
            "limit": "1",
        },
    )
    
    is_correct = None
    if question_status < 400 and isinstance(question, list) and question:
        question_data = question[0]
        if payload.answer_type == "single_choice":
            options = question_data.get("question_options", [])
            for opt in options:
                if opt.get("option_key") == payload.selected_option_id:
                    is_correct = opt.get("is_correct", False)
                    break
    
    # Save the answer
    answer_body = {
        "session_id": session["id"],
        "student_id": student_id,
        "question_id": payload.question_id,
        "answer_type": payload.answer_type,
        "selected_option_id": payload.selected_option_id,
        "answer_text": payload.answer_text,
        "is_correct": is_correct,
    }
    
    if isinstance(existing, list) and existing:
        status, _ = await supabase_request(
            request,
            "PATCH",
            f"/rest/v1/student_answers",
            params={"id": f"eq.{existing[0]['id']}"},
            body=answer_body,
            access_token=student.get("sub"),
        )
    else:
        status, _ = await supabase_request(
            request,
            "POST",
            f"/rest/v1/student_answers",
            body=answer_body,
            access_token=student.get("sub"),
        )
    
    if status >= 400:
        raise HTTPException(status_code=409, detail="答案提交失敗")
    
    return {
        "submitted": True,
        "question_id": payload.question_id,
        "is_correct": is_correct,
    }
