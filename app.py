import os
import re
import math
import httpx
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

load_dotenv()
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
API_TOKEN = os.environ["API_TOKEN"]

app = FastAPI()

STOPWORDS_TH = {"แนะนำ", "ให้หน่อย", "หน่อย", "ขอ", "หน่อยครับ", "หน่อยค่ะ"}

def normalize_query(text: str) -> str:
    t = text.strip()
    for w in STOPWORDS_TH:
        t = t.replace(w, " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t or text.strip()

def score_match(user_text: str, title: str, synopsis: str) -> float:
    u = user_text.lower()
    hay = f"{title}\n{synopsis}".lower()
    tokens = [x for x in re.split(r"[\s,.;:!?()\"'\\/]+", u) if len(x) >= 3]
    if not tokens:
        tokens = [u] if u else []
    hits = sum(1 for tok in tokens if tok in hay)
    title_hits = sum(1 for tok in tokens if tok in (title or "").lower())
    return hits + 0.5 * title_hits

async def jikan_search(q: str, limit: int = 25) -> list[dict]:
    url = "https://api.jikan.moe/v4/anime"
    params = {"q": q, "limit": limit}
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 (anime-bot)"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        data = r.json().get("data", [])
        return data if isinstance(data, list) else []

async def discord_send(content: str):
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(DISCORD_WEBHOOK_URL, json={"content": content})

def require_token(req: Request):
    auth = req.headers.get("authorization") or ""
    # Expect: Authorization: Bearer <token>
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth.removeprefix("Bearer ").strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

@app.post("/discord-anime")
async def discord_anime(req: Request):
    require_token(req)

    body = await req.json()
    message = (body.get("content") or "").strip() or "แนะนำอนิเมะแนวแฟนตาซีให้หน่อย"
    q = normalize_query(message)

    try:
        candidates = await jikan_search(q, limit=25)
    except Exception as e:
        await discord_send(f"ดึงข้อมูลจาก Jikan ไม่สำเร็จ: {e}")
        return {"ok": False}

    if not candidates:
        await discord_send(
            "ไม่พบอนิเมะจากคำค้นนี้\n"
            f"คำขอ: {message}\n"
            f"query: {q}\n"
            "ลองใช้คีย์เวิร์ดสั้นๆ/อังกฤษ เช่น fantasy, isekai, romance, school"
        )
        return {"ok": True}

    best = max(
        candidates,
        key=lambda a: score_match(message, a.get("title") or "", a.get("synopsis") or "")
    )

    title = best.get("title") or "Unknown"
    score = best.get("score") or "ยังไม่มีคะแนน"
    url = best.get("url") or ""
    image = (best.get("images") or {}).get("jpg", {}).get("large_image_url") or ""
    synopsis = (best.get("synopsis") or "")[:300]

    reply = (
        f"✨ **คำแนะนำ:** {title}\n"
        f"💡 **เหตุผล:** เลือกจากความตรงกับคำขอ (matching keywords) มากกว่าคะแนน\n\n"
        f"📊 **MAL คะแนน:** {score}\n"
        f"🔗 {url}\n"
        f"🖼️ {image}\n\n"
        f"📝 {synopsis}"
    )
    await discord_send(reply)
    return {"ok": True}