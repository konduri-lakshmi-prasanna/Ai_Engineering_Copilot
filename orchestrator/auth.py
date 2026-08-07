import os
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
FRONTEND_URL = "http://localhost:3000"


@router.get("/auth/login")
def login():
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&scope=repo"
        f"&redirect_uri=http://localhost:8000/auth/callback"
    )
    return RedirectResponse(github_auth_url)


@router.get("/auth/callback")
async def callback(code: str):
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
            },
        )

    token_data = token_response.json()
    access_token = token_data.get("access_token")

    if not access_token:
        raise HTTPException(status_code=400, detail="GitHub OAuth failed")

    # Redirect back to frontend, passing the token in the URL
    # (fine for a student project demo; production would use a secure session/cookie instead)
    return RedirectResponse(f"{FRONTEND_URL}?token={access_token}")


@router.get("/auth/repos")
async def get_repos(token: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            headers={"Authorization": f"token {token}"},
            params={"sort": "updated", "per_page": 30},
        )

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch repos")

    repos = response.json()
    return [{"full_name": r["full_name"]} for r in repos]