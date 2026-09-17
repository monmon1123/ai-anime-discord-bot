import os
import random
import re
import asyncio

import discord
import httpx
from dotenv import load_dotenv

load_dotenv()


def parse_allowed_channels(raw: str) -> set[int]:
    if not raw.strip():
        return set()
    ids: set[int] = set()
    for piece in raw.split(","):
        piece = piece.strip()
        if piece.isdigit():
            ids.add(int(piece))
    return ids


TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
MAL_CLIENT_ID = os.getenv("MAL_CLIENT_ID", "").strip()
ALLOWED_CHANNEL_IDS = parse_allowed_channels(os.getenv("ALLOWED_CHANNEL_IDS", ""))

if not TOKEN:
    raise RuntimeError("Missing DISCORD_BOT_TOKEN in .env")
if not MAL_CLIENT_ID:
    raise RuntimeError("Missing MAL_CLIENT_ID in .env")

STOPWORDS_TH = {
    "แนะนำ",
    "ให้หน่อย",
    "หน่อย",
    "ขอ",
    "หน่อยครับ",
    "หน่อยค่ะ",
    "อนิเมะ",
    "anime",
}

TH_KEYWORDS_TO_GENRE = {
    "แฟนตาซี": "fantasy",
    "ต่างโลก": "isekai",
    "โรแมนติก": "romance",
    "รัก": "romance",
    "ฮาเร็ม": "harem",
    "คอมเมดี้": "comedy",
    "ตลก": "comedy",
    "แอคชั่น": "action",
    "ต่อสู้": "action",
    "ดราม่า": "drama",
    "สยอง": "horror",
    "ผจญภัย": "adventure",
    "โรงเรียน": "school",
    "ชีวิตประจำวัน": "slice of life",
    "ไซไฟ": "sci-fi",
    "กีฬา": "sports",
}

GENRE_SYNONYMS = {
    "action": ["action", "แอคชั่น", "ต่อสู้", "บู๊"],
    "adventure": ["adventure", "ผจญภัย"],
    "comedy": ["comedy", "คอมเมดี้", "ตลก", "ฮา"],
    "drama": ["drama", "ดราม่า"],
    "fantasy": ["fantasy", "แฟนตาซี", "เวทมนตร์", "magic"],
    "horror": ["horror", "สยอง", "หลอน", "ผี"],
    "romance": ["romance", "โรแมนติก", "รัก", "หวาน"],
    "sci-fi": ["sci-fi", "scifi", "ไซไฟ", "วิทยาศาสตร์"],
    "sports": ["sports", "กีฬา"],
    "slice of life": ["slice of life", "ชีวิตประจำวัน", "อบอุ่น", "เรื่อยๆ"],
    "mystery": ["mystery", "ลึกลับ", "สืบสวน", "ปริศนา"],
    "psychological": ["psychological", "จิตวิทยา", "mind game"],
}

THEME_SYNONYMS = {
    "school": ["school", "โรงเรียน", "มัธยม", "นักเรียน"],
    "isekai": ["isekai", "ต่างโลก", "เกิดใหม่"],
    "historical": ["historical", "ย้อนยุค", "ประวัติศาสตร์", "ยุคเก่า"],
    "music": ["music", "ดนตรี", "วงดนตรี"],
    "military": ["military", "ทหาร", "สงคราม"],
}

NEGATION_WORDS = ["ไม่", "ไม่เอา", "ไม่ชอบ", "ไม่อยาก", "เลี่ยง", "avoid", "no "]

FRIEND_OPENERS = [
    "เออ เรื่องนี้น่าจะตรงที่เธอหาอยู่เลย",
    "ถ้าถามเรา เราเชียร์เรื่องนี้นะ",
    "ลองเรื่องนี้ก่อนเลย ฟีลดีมาก",
    "อันนี้คือของดีที่อยากป้ายยา",
]

FRIEND_FOLLOWUPS = [
    "ถ้าชอบ เดี๋ยวเราหาแนวใกล้ๆ กันให้อีก",
    "ถ้าอยากได้เบาๆ กว่านี้ บอกโทนมาเพิ่มได้เลย",
    "ถ้าชอบตัวละครสายไหน เดี๋ยวเราเลือกให้เฉพาะทางได้",
    "ถ้าอยากได้แบบจบไว เดี๋ยวเราคัดเรื่องตอนน้อยให้",
]


def normalize_query(text: str) -> str:
    t = text.strip().lower()
    for w in STOPWORDS_TH:
        t = t.replace(w, " ")
    for th_word, en_word in TH_KEYWORDS_TO_GENRE.items():
        if th_word in t:
            t = t.replace(th_word, f" {en_word} ")
    t = re.sub(r"\s+", " ", t).strip()
    return t or "fantasy"


def extract_preferences(text: str) -> dict:
    low = text.lower()
    prefs = {
        "want_genres": set(),
        "avoid_genres": set(),
        "want_themes": set(),
        "avoid_themes": set(),
        "short": False,
        "long": False,
        "high_score": False,
        "newer": False,
        "completed": False,
    }

    def has_negation_near(word: str) -> bool:
        i = low.find(word)
        if i < 0:
            return False
        window = low[max(0, i - 10) : i]
        return any(neg in window for neg in NEGATION_WORDS)

    for genre, synonyms in GENRE_SYNONYMS.items():
        if any(s in low for s in synonyms):
            if any(has_negation_near(s) for s in synonyms):
                prefs["avoid_genres"].add(genre)
            else:
                prefs["want_genres"].add(genre)

    for theme, synonyms in THEME_SYNONYMS.items():
        if any(s in low for s in synonyms):
            if any(has_negation_near(s) for s in synonyms):
                prefs["avoid_themes"].add(theme)
            else:
                prefs["want_themes"].add(theme)

    if any(k in low for k in ["ตอนสั้น", "ไม่ยาว", "สั้นๆ", "ดูไว", "จบไว"]):
        prefs["short"] = True
    if any(k in low for k in ["ตอนยาว", "ยาวๆ", "หลายตอน", "ดูยาว"]):
        prefs["long"] = True
    if any(k in low for k in ["คะแนนสูง", "คุณภาพดี", "เรื่องดัง", "top"]):
        prefs["high_score"] = True
    if any(k in low for k in ["ใหม่", "ปีหลัง", "ภาพสวย", "เมะใหม่"]):
        prefs["newer"] = True
    if any(k in low for k in ["จบแล้ว", "จบสมบูรณ์", "ไม่ค้าง"]):
        prefs["completed"] = True

    return prefs


def preference_score(anime: dict, prefs: dict) -> float:
    genres = {g.get("name", "").lower() for g in anime.get("genres", [])}
    themes = {t.get("name", "").lower() for t in anime.get("themes", [])}
    status = (anime.get("status") or "").lower()
    episodes = anime.get("episodes") or 0
    year = anime.get("year") or 0
    score = anime.get("score") or 0

    value = 0.0
    value += 3.0 * len(prefs["want_genres"].intersection(genres))
    value += 2.0 * len(prefs["want_themes"].intersection(themes))
    value -= 4.0 * len(prefs["avoid_genres"].intersection(genres))
    value -= 3.0 * len(prefs["avoid_themes"].intersection(themes))

    if prefs["short"]:
        if episodes and episodes <= 24:
            value += 2.2
        elif episodes >= 36:
            value -= 1.5

    if prefs["long"]:
        if episodes >= 36:
            value += 2.2
        elif episodes and episodes <= 12:
            value -= 1.0

    if prefs["high_score"]:
        value += score / 3.0

    if prefs["newer"]:
        if year >= 2019:
            value += 2.0
        elif year and year < 2010:
            value -= 1.0

    if prefs["completed"] and "finished" in status:
        value += 1.8

    return value


def score_match(user_text: str, anime: dict) -> float:
    title = (anime.get("title") or "").lower()
    synopsis = (anime.get("synopsis") or "").lower()
    hay = f"{title}\n{synopsis}"

    u = user_text.lower()
    tokens = [x for x in re.split(r"[\s,.;:!?()\"'\\/]+", u) if len(x) >= 3]
    if not tokens:
        tokens = [u] if u else []

    text_hits = sum(1 for tok in tokens if tok in hay)
    title_hits = sum(1 for tok in tokens if tok in title)

    mal_score = anime.get("score") or 0
    popularity = anime.get("popularity") or 999999
    popularity_bonus = 1 / (1 + (popularity / 5000))

    prefs = extract_preferences(user_text)
    pref_bonus = preference_score(anime, prefs)

    return (text_hits * 2.0) + title_hits + (mal_score / 4.0) + popularity_bonus + pref_bonus


def _mal_status_to_label(status: str) -> str:
    mapping = {
        "finished_airing": "Finished Airing",
        "currently_airing": "Currently Airing",
        "not_yet_aired": "Not yet aired",
    }
    return mapping.get(status or "", status or "")


def _mal_node_to_anime(node: dict) -> dict:
    genres = [{"name": g.get("name", "")} for g in node.get("genres", []) or []]
    main_picture = node.get("main_picture") or {}
    start_season = node.get("start_season") or {}
    node_id = node.get("id")
    return {
        "title": node.get("title") or "",
        "synopsis": node.get("synopsis") or "",
        "score": node.get("mean"),
        "episodes": node.get("num_episodes") or 0,
        "year": start_season.get("year") or 0,
        "status": _mal_status_to_label(node.get("status", "")),
        "genres": genres,
        "themes": [],  # MAL API v2 ไม่มี themes แยกแบบ Jikan
        "popularity": node.get("popularity") or 999999,
        "url": f"https://myanimelist.net/anime/{node_id}" if node_id else "",
        "images": {
            "jpg": {
                "large_image_url": main_picture.get("large") or main_picture.get("medium") or ""
            }
        },
    }


MAL_FIELDS = "id,title,main_picture,synopsis,mean,popularity,num_episodes,status,genres,start_season"


async def mal_search(q: str, limit: int = 25) -> list[dict]:
    url = "https://api.myanimelist.net/v2/anime"
    params = {"q": q, "limit": limit, "fields": MAL_FIELDS}
    headers = {"X-MAL-CLIENT-ID": MAL_CLIENT_ID}

    async with httpx.AsyncClient(timeout=20) as client:
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                response = await client.get(url, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as error:
                last_error = error
                await asyncio.sleep(min(2.0 * (attempt + 1), 6.0))
                continue

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "1.5"))
                await asyncio.sleep(max(retry_after, 1.0))
                continue

            if response.status_code in (500, 502, 503, 504):
                last_error = httpx.HTTPStatusError(
                    f"Server error '{response.status_code}' for url '{response.url}'",
                    request=response.request,
                    response=response,
                )
                await asyncio.sleep(min(2.0 * (attempt + 1), 6.0))
                continue

            response.raise_for_status()
            payload = response.json().get("data", [])
            nodes = [item.get("node", {}) for item in payload if isinstance(item, dict)]
            return [_mal_node_to_anime(n) for n in nodes]

    if last_error:
        raise last_error
    return []


def build_friend_reason(req_text: str, anime: dict) -> str:
    req = req_text.lower()
    genres = [g.get("name", "").lower() for g in anime.get("genres", [])]
    themes = [t.get("name", "").lower() for t in anime.get("themes", [])]
    title = (anime.get("title") or "เรื่องนี้").strip()
    episodes = anime.get("episodes") or 0

    prefs = extract_preferences(req_text)

    want_genres = prefs["want_genres"].intersection(set(genres))
    if want_genres:
        picked = ", ".join(list(want_genres)[:2])
        return f"ตรงแนวที่เธอขอไว้เลย โดยเฉพาะ {picked}"

    want_themes = prefs["want_themes"].intersection(set(themes))
    if want_themes:
        picked = ", ".join(list(want_themes)[:2])
        return f"ธีม {picked} ค่อนข้างตรงกับที่เธอเล่าไว้"

    if prefs["short"] and episodes and episodes <= 24:
        return f"เลือก {title} เพราะเป็นเรื่องที่ดูจบได้ไม่ยาวจนเกินไป"
    if prefs["long"] and episodes >= 36:
        return f"เลือก {title} เพราะเป็นเรื่องยาว ดูต่อเนื่องได้เพลินๆ"

    matched = []
    for th_word, en_word in TH_KEYWORDS_TO_GENRE.items():
        if th_word in req and en_word in " ".join(genres):
            matched.append(th_word)

    if matched:
        picked = ", ".join(matched[:2])
        return f"เห็นว่าเธออยากได้แนว {picked} แล้วเรื่องนี้แนวค่อนข้างตรงเลย"

    score = anime.get("score")
    if score:
        return f"เลือก {title} เพราะคะแนนค่อนข้างดีและภาพรวมรีวิวโอเค"
    return f"เลือก {title} เพราะโทนเรื่องเข้ากับคำขอที่พิมพ์มา"


def build_friend_message(req_text: str, anime: dict, random_mode: bool) -> str:
    opener = random.choice(FRIEND_OPENERS)
    followup = random.choice(FRIEND_FOLLOWUPS)
    reason = build_friend_reason(req_text, anime)
    mode_line = "สุ่มให้จากกลุ่มที่น่าดูที่สุดแล้วนะ" if random_mode else "คัดให้จากที่ตรงคำขอมากที่สุดแล้ว"
    return f"{opener}\n{mode_line}\nเหตุผล: {reason}\n{followup}"


def pick_recommendations(candidates: list[dict], req_text: str, random_mode: bool, count: int = 3) -> list[dict]:
    ranked = sorted(candidates, key=lambda a: score_match(req_text, a), reverse=True)
    if not ranked:
        return []

    if random_mode:
        pool = ranked[: min(12, len(ranked))]
        size = min(count, len(pool))
        return random.sample(pool, k=size)

    return ranked[: min(count, len(ranked))]


def build_option_line(index: int, anime: dict, req_text: str) -> str:
    title = anime.get("title") or "Unknown"
    score = anime.get("score") or "-"
    eps = anime.get("episodes") or "?"
    reason = build_friend_reason(req_text, anime)
    return f"{index}. {title} (คะแนน {score}, {eps} ตอน)\n   - {reason}"


def build_chat_style_reply(req_text: str, picks: list[dict], random_mode: bool) -> str:
    if not picks:
        return "ขอเวลาแป๊บ เราหาเรื่องที่ตรงใจสุดๆ ให้ยังไม่เจอ ลองบอกเพิ่มอีกนิดได้ไหม"

    opener = random.choice(
        [
            "โอเค ได้ฟีลที่อยากดูแล้ว เราคัดให้แบบนี้นะ",
            "จัดให้แบบเพื่อนแนะนำตรงๆ เลย",
            "ถ้าถามเรา ตอนนี้ลิสต์นี้น่าลองสุด",
        ]
    )
    mode_line = "อันนี้เป็นชุดสุ่มจากตัวที่เข้าเงื่อนไขที่สุด" if random_mode else "เรียงจากที่ตรงสิ่งที่เธอเล่ามากที่สุด"

    lines = [build_option_line(i + 1, anime, req_text) for i, anime in enumerate(picks)]
    closing = "ถ้าชอบโทนของข้อไหน บอกได้เลย เดี๋ยวเราขยายลิสต์แนวนั้นให้ต่อ"
    return f"{opener}\n{mode_line}\n\n" + "\n".join(lines) + f"\n\n{closing}"


def format_anime_embed(anime: dict, req_text: str, random_mode: bool) -> discord.Embed:
    title = anime.get("title") or "Unknown"
    score = anime.get("score") or "ยังไม่มีคะแนน"
    url = anime.get("url") or ""
    image = (anime.get("images") or {}).get("jpg", {}).get("large_image_url") or ""
    synopsis = (anime.get("synopsis") or "")[:380] or "ไม่มีคำอธิบาย"
    episodes = anime.get("episodes") or "?"
    status = anime.get("status") or "Unknown"
    genres = ", ".join(g.get("name", "") for g in anime.get("genres", [])[:3]) or "-"

    description = f"{synopsis}\n\nเพื่อนขอมา: {req_text}"
    embed = discord.Embed(
        title=title,
        description=description,
        url=url,
        color=0x2ECC71 if random_mode else 0x5865F2,
    )
    embed.add_field(name="Score (MAL)", value=str(score), inline=True)
    embed.add_field(name="Episodes", value=str(episodes), inline=True)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Genres", value=genres, inline=False)
    embed.set_footer(text="อยากได้โทนไหนต่อ พิมพ์มาได้เลย เดี๋ยวคัดให้")
    if image:
        embed.set_thumbnail(url=image)
    return embed


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


async def send_recommendation(message: discord.Message, req_text: str, random_mode: bool = False):
    q = normalize_query(req_text)
    try:
        candidates = await mal_search(q, limit=25)
    except Exception as error:
        await message.reply(f"ดึงข้อมูลจาก MyAnimeList ไม่สำเร็จ: {error}")
        return

    if not candidates:
        await message.reply(
            "ไม่พบอนิเมะจากคำค้นนี้\n"
            f"คำขอ: {req_text}\n"
            f"query: {q}\n"
            "ลองคีย์เวิร์ดอังกฤษสั้นๆ เช่น fantasy / isekai / romance"
        )
        return

    prefs = extract_preferences(req_text)
    avoid_pool = prefs["avoid_genres"]
    if avoid_pool:
        filtered = []
        for item in candidates:
            gset = {g.get("name", "").lower() for g in item.get("genres", [])}
            if not avoid_pool.intersection(gset):
                filtered.append(item)
        if filtered:
            candidates = filtered

    picks = pick_recommendations(candidates, req_text, random_mode=random_mode, count=3)
    picked = picks[0]

    embed = format_anime_embed(picked, req_text, random_mode=random_mode)
    chat_reply = build_chat_style_reply(req_text, picks, random_mode)
    await message.reply(content=chat_reply, embed=embed)


@client.event
async def on_ready():
    print(f"Logged in as {client.user} (id={client.user.id})")
    if ALLOWED_CHANNEL_IDS:
        print(f"Allowed channels: {sorted(ALLOWED_CHANNEL_IDS)}")
    else:
        print("Allowed channels: ALL")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if ALLOWED_CHANNEL_IDS and message.channel.id not in ALLOWED_CHANNEL_IDS:
        return

    text = (message.content or "").strip()
    if not text:
        return

    if text.lower().startswith("!anime help"):
        await message.reply(
            "คำสั่งที่ใช้ได้:\n"
            "- !anime <แนวหรือคำค้น>\n"
            "  ตัวอย่าง: !anime ต่างโลก\n"
            "- !anime random <แนวหรือคำค้น>\n"
            "  ตัวอย่าง: !anime random โรแมนติก\n"
            "- !anime random (ไม่ใส่คำค้น จะใช้ fantasy)\n\n"
            "พิมพ์แบบละเอียดได้ด้วย เช่น:\n"
            "!anime อยากได้แฟนตาซีจบไว ไม่เอาสยอง ภาพสวย คะแนนสูง\n"
            "หรือพิมพ์แบบคุยได้เลย เช่น:\n"
            "ช่วยแนะนำอนิเมะหน่อย อยากได้แนวโรงเรียน โรแมนติก จบแล้ว"
        )
        return

    if text.lower().startswith("!anime random"):
        query = text[len("!anime random") :].strip() or "fantasy"
        await send_recommendation(message, query, random_mode=True)
        return

    if text.lower().startswith("!anime"):
        query = text[len("!anime") :].strip() or "fantasy"
        await send_recommendation(message, query, random_mode=False)
        return

    # โหมดคุยธรรมดา: ถ้าข้อความมีคำว่าแนะนำหรืออนิเมะ ให้ช่วยแนะนำทันที
    if "แนะนำ" in text or "อนิเมะ" in text.lower() or "anime" in text.lower():
        await send_recommendation(message, text, random_mode=False)


client.run(TOKEN)