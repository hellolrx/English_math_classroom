"""Student API endpoints for practice, vocabulary, and profile."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field

from services.auth import (
    ChangePasswordRequest,
    StudentLoginRequest,
    create_student_token,
    decode_jwt,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/student", tags=["student"])


class StudentAnswerRequest(BaseModel):
    question_id: str = Field(min_length=1)
    answer_type: str = Field(pattern="^(single_choice|text_input)$")
    selected_option_id: str | None = None
    answer_text: str | None = Field(default=None, max_length=5000)


class VocabularyRateRequest(BaseModel):
    word_id: str = Field(min_length=1)
    rating: str = Field(pattern="^(forgot|fuzzy|clear)$")


async def get_student_from_token(request: Request, authorization: str | None) -> dict[str, Any]:
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


@router.get("/topics")
async def get_student_topics(
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    """Get topics available for the student (only S6 can access math topics)."""
    student = await get_student_from_token(request, authorization)
    grade_id = student.get("grade_id")
    
    # Only S6 can access math topics
    if grade_id != "S6":
        return []
    
    status, result = await supabase_request(
        request,
        "GET",
        "/rest/v1/topics",
        params={
            "select": "id,code,name",
            "order": "code.asc",
        },
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取主題")
    return result


@router.get("/topics/{topic_id}/questions")
async def get_topic_questions(
    topic_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    """Get questions for a topic (without correct answers)."""
    student = await get_student_from_token(request, authorization)
    grade_id = student.get("grade_id")
    
    # Only S6 can access math topics
    if grade_id != "S6":
        raise HTTPException(status_code=403, detail="沒有權限訪問此主題")
    
    status, result = await supabase_request(
        request,
        "GET",
        f"/rest/v1/questions",
        params={
            "select": "id,question_set_id,question_order,question_type,question_image_url,question_options(option_key)",
            "topic_id": f"eq.{topic_id}",
            "order": "question_order.asc",
        },
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取題目")
    return result


@router.get("/practice/{topic_id}/progress")
async def get_practice_progress(
    topic_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Get practice progress for a student on a topic."""
    student = await get_student_from_token(request, authorization)
    student_id = student.get("student_id")
    
    status, result = await supabase_request(
        request,
        "GET",
        f"/rest/v1/practice_progress",
        params={
            "select": "*",
            "student_id": f"eq.{student_id}",
            "topic_id": f"eq.{topic_id}",
            "limit": "1",
        },
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取進度")
    
    if isinstance(result, list) and result:
        return result[0]
    return {"topic_id": topic_id, "current_question_order": 1, "answered_count": 0, "status": "not_started"}


@router.post("/practice/{topic_id}/answer")
async def submit_answer(
    topic_id: str,
    payload: StudentAnswerRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Submit an answer for a question."""
    student = await get_student_from_token(request, authorization)
    student_id = student.get("student_id")
    
    # Get the question to check correctness
    status, question = await supabase_request(
        request,
        "GET",
        f"/rest/v1/questions",
        params={
            "select": "id,question_set_id,question_type,question_options(option_key,is_correct)",
            "id": f"eq.{payload.question_id}",
            "limit": "1",
        },
    )
    if status >= 400 or not question:
        raise HTTPException(status_code=404, detail="題目不存在")
    
    question_data = question[0] if isinstance(question, list) else question
    is_correct = None
    
    if payload.answer_type == "single_choice":
        # Check if the selected option is correct
        options = question_data.get("question_options", [])
        for opt in options:
            if opt.get("option_key") == payload.selected_option_id:
                is_correct = opt.get("is_correct", False)
                break
    
    # Save the answer
    status, _ = await supabase_request(
        request,
        "POST",
        f"/rest/v1/student_answers",
        body={
            "student_id": student_id,
            "topic_id": topic_id,
            "question_id": payload.question_id,
            "answer_type": payload.answer_type,
            "selected_option_id": payload.selected_option_id,
            "answer_text": payload.answer_text,
            "is_correct": is_correct,
        },
        access_token=student.get("sub"),
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="保存答案失敗")
    
    # Update practice progress
    status, progress = await supabase_request(
        request,
        "GET",
        f"/rest/v1/practice_progress",
        params={
            "select": "id,answered_count,current_question_order",
            "student_id": f"eq.{student_id}",
            "topic_id": f"eq.{topic_id}",
            "limit": "1",
        },
    )
    
    if isinstance(progress, list) and progress:
        progress_data = progress[0]
        new_answered_count = progress_data.get("answered_count", 0) + 1
        status, _ = await supabase_request(
            request,
            "PATCH",
            f"/rest/v1/practice_progress",
            params={"id": f"eq.{progress_data['id']}"},
            body={
                "answered_count": new_answered_count,
                "current_question_order": progress_data.get("current_question_order", 1) + 1,
            },
            access_token=student.get("sub"),
        )
    else:
        status, _ = await supabase_request(
            request,
            "POST",
            f"/rest/v1/practice_progress",
            body={
                "student_id": student_id,
                "topic_id": topic_id,
                "current_question_order": 2,
                "answered_count": 1,
                "status": "in_progress",
            },
            access_token=student.get("sub"),
        )
    
    return {
        "status": "saved",
        "is_correct": is_correct,
        "question_type": question_data.get("question_type"),
    }


@router.get("/vocabulary")
async def get_vocabulary(
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    """Get vocabulary words for the student's grade."""
    student = await get_student_from_token(request, authorization)
    grade_id = student.get("grade_id")
    
    status, result = await supabase_request(
        request,
        "GET",
        f"/rest/v1/vocabulary_words",
        params={
            "select": "id,word,meaning,sort_order,is_active",
            "grade_id": f"eq.{grade_id}",
            "is_active": "eq.true",
            "order": "sort_order.asc",
        },
    )
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取單詞")
    return result


@router.get("/vocabulary/review")
async def get_review_words(
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    """Get words due for review (due now or in the future for learning)."""
    student = await get_student_from_token(request, authorization)
    student_id = student.get("student_id")
    grade_id = student.get("grade_id")
    
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    
    # Get words that are due for review (next_review_at <= now)
    status, due_words = await supabase_request(
        request,
        "GET",
        f"/rest/v1/student_word_progress",
        params={
            "select": "id,word_id,familiarity_level,next_review_at,last_rating",
            "student_id": f"eq.{student_id}",
            "next_review_at": f"lte.{now}",
            "order": "next_review_at.asc",
        },
    )
    
    # Get words not yet started (new words for learning)
    status2, progress_ids = await supabase_request(
        request,
        "GET",
        f"/rest/v1/student_word_progress",
        params={
            "select": "word_id",
            "student_id": f"eq.{student_id}",
        },
    )
    
    progress_word_ids = set()
    if isinstance(progress_ids, list):
        progress_word_ids = {p["word_id"] for p in progress_ids}
    
    status3, all_words = await supabase_request(
        request,
        "GET",
        f"/rest/v1/vocabulary_words",
        params={
            "select": "id,word,meaning,sort_order",
            "grade_id": f"eq.{grade_id}",
            "is_active": "eq.true",
            "order": "sort_order.asc",
        },
    )
    
    result = []
    if isinstance(due_words, list):
        result.extend(due_words)
    
    if isinstance(all_words, list):
        for word in all_words:
            if word["id"] not in progress_word_ids:
                result.append({
                    "word_id": word["id"],
                    "word": word["word"],
                    "meaning": word["meaning"],
                    "familiarity_level": 1,
                    "next_review_at": None,
                    "last_rating": None,
                })
    
    return result


@router.post("/vocabulary/rate")
async def rate_word(
    payload: VocabularyRateRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Rate a word and update review schedule."""
    student = await get_student_from_token(request, authorization)
    student_id = student.get("student_id")
    
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    
    # Get existing progress
    status, progress = await supabase_request(
        request,
        "GET",
        f"/rest/v1/student_word_progress",
        params={
            "select": "*",
            "student_id": f"eq.{student_id}",
            "word_id": f"eq.{payload.word_id}",
            "limit": "1",
        },
    )
    
    # Simple spaced repetition algorithm
    rating_map = {
        "forgot": {"delta": -2, "interval_hours": 1},
        "fuzzy": {"delta": 1, "interval_hours": 24},
        "clear": {"delta": 2, "interval_hours": 72},
    }
    
    config = rating_map[payload.rating]
    
    if isinstance(progress, list) and progress:
        progress_data = progress[0]
        current_level = progress_data.get("familiarity_level", 1)
        new_level = max(1, min(10, current_level + config["delta"]))
        next_review = now + timedelta(hours=config["interval_hours"])
        
        status, _ = await supabase_request(
            request,
            "PATCH",
            f"/rest/v1/student_word_progress",
            params={"id": f"eq.{progress_data['id']}"},
            body={
                "familiarity_level": new_level,
                "next_review_at": next_review.isoformat(),
                "last_rating": payload.rating,
                "reviewed_at": now.isoformat(),
            },
            access_token=student.get("sub"),
        )
    else:
        new_level = 1 + config["delta"]
        new_level = max(1, min(10, new_level))
        next_review = now + timedelta(hours=config["interval_hours"])
        
        status, _ = await supabase_request(
            request,
            "POST",
            f"/rest/v1/student_word_progress",
            body={
                "student_id": student_id,
                "word_id": payload.word_id,
                "familiarity_level": new_level,
                "next_review_at": next_review.isoformat(),
                "last_rating": payload.rating,
                "reviewed_at": now.isoformat(),
            },
            access_token=student.get("sub"),
        )
    
    return {"status": "saved", "rating": payload.rating}


@router.post("/password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Change student password."""
    student = await get_student_from_token(request, authorization)
    student_id = student.get("student_id")
    
    # Get current student record
    status, student_record = await supabase_request(
        request,
        "GET",
        f"/rest/v1/students",
        params={
            "select": "id,password_hash",
            "id": f"eq.{student_id}",
            "limit": "1",
        },
    )
    
    if status >= 400 or not student_record:
        raise HTTPException(status_code=404, detail="學生不存在")
    
    student_data = student_record[0] if isinstance(student_record, list) else student_record
    current_hash = student_data.get("password_hash", "")
    
    # Verify current password
    if not verify_password(payload.current_password, current_hash):
        raise HTTPException(status_code=401, detail="當前密碼不正確")
    
    # Hash new password
    new_hash = hash_password(payload.new_password)
    
    # Update password
    status, _ = await supabase_request(
        request,
        "PATCH",
        f"/rest/v1/students",
        params={"id": f"eq.{student_id}"},
        body={
            "password_hash": new_hash,
            "must_change_password": False,
        },
        access_token=student.get("sub"),
    )
    
    if status >= 400:
        raise HTTPException(status_code=502, detail="修改密碼失敗")
    
    return {"status": "success"}
