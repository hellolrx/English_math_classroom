"""Topics API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Header

router = APIRouter(prefix="/api/topics", tags=["topics"])


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
        import json
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


@router.get("")
async def list_topics(
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    """List all topics (teacher only)."""
    token = await get_teacher_token(authorization)
    
    status, result = await supabase_request(
        request,
        "GET",
        "/rest/v1/topics",
        params={
            "select": "id,code,name,created_at,updated_at",
            "order": "code.asc",
        },
        access_token=token,
    )
    
    if status >= 400:
        raise HTTPException(status_code=502, detail="無法讀取主題")
    
    return result if isinstance(result, list) else []
