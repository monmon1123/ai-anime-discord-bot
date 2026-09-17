# AI Anime Discord Bot 🎌

บอท Discord ที่แนะนำอนิเมะเป็นภาษาไทย โดยดึงข้อมูลจาก [MyAnimeList API v2](https://myanimelist.net/apiconfig/references/api/v2) ตัวบอทเข้าใจคำขอภาษาไทยแบบธรรมชาติ (แนว, ธีม, จำนวนตอน, คะแนน) แล้วคัดเรื่องที่ตรงที่สุดมาแนะนำแบบเพื่อนคุยกัน

## Features

- แนะนำอนิเมะจากคำค้นภาษาไทยหรืออังกฤษ เช่น `!anime ต่างโลก`, `!anime random โรแมนติก`
- เข้าใจความต้องการละเอียด เช่น "อยากได้แฟนตาซีจบไว ไม่เอาสยอง คะแนนสูง"
- ตอบกลับแบบสนทนา พร้อม embed แสดงโปสเตอร์ คะแนน จำนวนตอน สถานะ และแนว
- Retry อัตโนมัติเมื่อ MyAnimeList ตอบช้าหรือ rate-limit (429 / 5xx)
- จำกัดให้บอทตอบเฉพาะบางช่องได้ผ่าน `ALLOWED_CHANNEL_IDS`

## Requirements

- Python 3.11+
- Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications))
- MyAnimeList API Client ID ([MAL API Config](https://myanimelist.net/apiconfig))

## Setup

1. Clone repo แล้วติดตั้ง dependencies:

   ```bash
   pip install discord.py httpx python-dotenv
   ```

2. สร้างไฟล์ `.env` ในโฟลเดอร์โปรเจกต์:

   ```env
   DISCORD_BOT_TOKEN=your_discord_bot_token
   MAL_CLIENT_ID=your_mal_client_id
   ALLOWED_CHANNEL_IDS=123456789012345678,987654321098765432
   ```

   - `ALLOWED_CHANNEL_IDS` เว้นว่างได้ถ้าต้องการให้บอทตอบทุกช่อง
   - **ห้าม commit ไฟล์ `.env` ขึ้น GitHub เด็ดขาด** (ไฟล์นี้ถูกกันไว้ใน `.gitignore` แล้ว)

3. รันบอท:

   ```bash
   python bot.py
   ```

## Usage

| คำสั่ง | ตัวอย่าง | คำอธิบาย |
|---|---|---|
| `!anime <คำค้น>` | `!anime ต่างโลก` | แนะนำอนิเมะที่ตรงกับคำค้นมากที่สุด |
| `!anime random <คำค้น>` | `!anime random โรแมนติก` | สุ่มจากกลุ่มเรื่องที่น่าดูที่สุด |
| `!anime help` | — | แสดงวิธีใช้งาน |
| พิมพ์คุยธรรมดา | "ช่วยแนะนำอนิเมะแนวโรงเรียนหน่อย" | บอทตรวจจับคำว่า "แนะนำ"/"อนิเมะ" แล้วตอบให้อัตโนมัติ |

## Project Structure

```
.
├── bot.py     # Discord gateway bot (ใช้งานหลัก — ไม่ต้องมี tunnel/webhook)
├── app.py     # FastAPI webhook endpoint (ทางเลือกสำหรับ integration แบบ HTTP)
└── .env       # ค่า config ลับ (ไม่ commit)
```

## License

MIT
