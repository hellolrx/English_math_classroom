"""Vocabulary import API endpoints for teachers."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Header, UploadFile, File, Form
from pydantic import BaseModel, Field

from services.vocabulary_parser import parse_vocabulary_excel, VocabularyImportError

router = APIRouter(prefix="/api/vocabulary", tags=["vocabulary"])


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


async def get_teacher_token(authorization: str | None) -> str:
    """Get teacher token from authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="需要老師登錄")
    return authorization[7:]


class VocabularyPreviewRequest(BaseModel):
    grade_id: str = Field(min_length=1, max_length=20)


@router.post("/preview")
async def preview_vocabulary(
    file: UploadFile = File(...),
    request: Request = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Preview vocabulary Excel file without importing."""
    await get_teacher_token(authorization)
    
    content = await file.read()
    
    try:
        words = parse_vocabulary_excel(content)
    except VocabularyImportError as exc:
        return {
            "status": "error",
            "errors": exc.errors,
            "count": 0,
        }
    
    # Return first 100 words for preview
    preview = [{"row_number": w.row_number, "word": w.word, "meaning": w.meaning} for w in words[:100]]
    
    return {
        "status": "preview",
        "count": len(words),
        "words": preview,
    }


@router.post("/import")
async def import_vocabulary(
    file: UploadFile = File(...),
    grade_id: str = Form(...),
    request: Request = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Import vocabulary Excel file."""
    token = await get_teacher_token(authorization)
    
    content = await file.read()
    
    try:
        words = parse_vocabulary_excel(content)
    except VocabularyImportError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors})
    
    # Insert words into database
    inserted_count = 0
    errors: list[str] = []
    
    for index, word in enumerate(words):
        status, result = await supabase_request(
            request,
            "POST",
            "/rest/v1/vocabulary_words",
            body={
                "grade_id": grade_id,
                "word": word.word,
                "meaning": word.meaning,
                "sort_order": index + 1,
                "is_active": True,
            },
            access_token=token,
        )
        
        if status >= 400:
            error_msg = result if isinstance(result, str) else str(result)
            errors.append(f"行 {word.row_number}: {error_msg}")
        else:
            inserted_count += 1
    
    return {
        "status": "imported",
        "imported_count": inserted_count,
        "total_count": len(words),
        "errors": errors if errors else None,
        "grade_id": grade_id,
    }


@router.get("/{grade_id}")
async def get_vocabulary_by_grade(
    grade_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    """Get vocabulary words for a grade."""
    token = await get_teacher_token(authorization)
    
    status, result = await supabase_request(
        request,
        "GET",
        "/rest/v1/vocabulary_words",
        params={
            "select": "id,word,meaning,sort_order,is_active,created_at,updated_at",
            "grade_id": f"eq.{grade_id}",
            "is_active": "eq:true",
            "order": "sort_order.asc",
        },
        access_token=token,
    )
    
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取單詞")
    
    return result if isinstance(result, list) else []
