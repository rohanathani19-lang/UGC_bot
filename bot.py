import os
import logging
import asyncio
import aiohttp
import base64
import json
import re
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from PIL import Image, ImageDraw, ImageFont
import requests

# ─────────────────────────────────────────
# CONFIG — paste your real keys here
# ─────────────────────────────────────────
TELEGRAM_TOKEN    = "YOUR_TELEGRAM_BOT_TOKEN"
OPENAI_API_KEY    = "YOUR_OPENAI_API_KEY"       # platform.openai.com
REPLICATE_API_KEY = "YOUR_REPLICATE_API_KEY"

# Your AI Influencer images (upload to any public URL like imgbb.com or use file_id)
INFLUENCER_CASUAL_URL   = "YOUR_INFLUENCER_CASUAL_IMAGE_URL"   # café photo
INFLUENCER_SAREE_URL    = "YOUR_INFLUENCER_SAREE_IMAGE_URL"    # temple photo

# Instagram (optional - skip for now)
INSTAGRAM_ACCESS_TOKEN   = ""
INSTAGRAM_BUSINESS_ID    = ""

# ─────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Session storage per user
user_sessions = {}

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def get_session(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "image_url": None,
            "image_b64": None,
            "command": None,
            "content_type": None,
            "generated": {}
        }
    return user_sessions[user_id]

async def image_to_base64(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            data = await r.read()
            return base64.b64encode(data).decode("utf-8")

async def telegram_photo_to_base64(file) -> tuple:
    """Download telegram photo and return (base64, bytes)"""
    buf = BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)
    raw = buf.read()
    return base64.b64encode(raw).decode("utf-8"), raw

# ─────────────────────────────────────────
# OPENAI GPT-4o — Brain of the bot
# ─────────────────────────────────────────

async def ask_gpt(prompt: str, image_b64: str = None, system: str = None) -> str:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    messages = []

    # System message
    if system:
        messages.append({"role": "system", "content": system})

    # User message — with or without image
    if image_b64:
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}",
                        "detail": "high"
                    }
                },
                {"type": "text", "text": prompt}
            ]
        })
    else:
        messages.append({"role": "user", "content": prompt})

    body = {
        "model": "gpt-4o",
        "max_tokens": 2000,
        "messages": messages
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=body
        ) as r:
            data = await r.json()
            if "error" in data:
                raise Exception(f"OpenAI error: {data['error']['message']}")
            return data["choices"][0]["message"]["content"]

# ─────────────────────────────────────────
# REPLICATE — Image Generation
# ─────────────────────────────────────────

async def generate_image_replicate(prompt: str, influencer_b64: str = None) -> bytes:
    """Generate image using Replicate SDXL or img2img with influencer"""
    headers = {
        "Authorization": f"Token {REPLICATE_API_KEY}",
        "Content-Type": "application/json"
    }

    if influencer_b64:
        # Use img2img to keep influencer likeness
        input_data = {
            "prompt": prompt,
            "image": f"data:image/jpeg;base64,{influencer_b64}",
            "prompt_strength": 0.6,
            "num_inference_steps": 30,
            "guidance_scale": 7.5
        }
        model = "stability-ai/sdxl:39ed52f2319f9b1e7a0d4f4a84cc0e5b3c4e04b7a2c5f6d8e9f0a1b2c3d4e5f6"
    else:
        input_data = {
            "prompt": prompt,
            "num_inference_steps": 30,
            "guidance_scale": 7.5,
            "width": 1024,
            "height": 1024
        }
        model = "stability-ai/sdxl:39ed52f2319f9b1e7a0d4f4a84cc0e5b3c4e04b7a2c5f6d8e9f0a1b2c3d4e5f6"

    # Start prediction
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"https://api.replicate.com/v1/predictions",
            headers=headers,
            json={"version": model.split(":")[1], "input": input_data}
        ) as r:
            pred = await r.json()
            pred_id = pred.get("id")

        # Poll for result
        for _ in range(60):
            await asyncio.sleep(3)
            async with session.get(
                f"https://api.replicate.com/v1/predictions/{pred_id}",
                headers=headers
            ) as r:
                result = await r.json()
                if result["status"] == "succeeded":
                    img_url = result["output"][0] if isinstance(result["output"], list) else result["output"]
                    async with session.get(img_url) as img_r:
                        return await img_r.read()
                elif result["status"] == "failed":
                    raise Exception(f"Replicate failed: {result.get('error')}")

    raise Exception("Replicate timed out")

# ─────────────────────────────────────────
# BANNER GENERATOR (PIL fallback)
# ─────────────────────────────────────────

async def create_banner_with_influencer(
    influencer_bytes: bytes,
    headline: str,
    subtext: str,
    cta: str,
    color_scheme: str = "luxury"
) -> bytes:
    """Composite influencer photo into a professional banner"""

    # Color schemes
    schemes = {
        "luxury":    {"bg": (15, 10, 35),    "accent": (212, 175, 55),  "text": (255, 255, 255)},
        "real_estate": {"bg": (10, 30, 20),  "accent": (0, 180, 100),   "text": (255, 255, 255)},
        "fashion":   {"bg": (240, 230, 220),  "accent": (180, 50, 80),   "text": (20, 20, 20)},
        "wellness":  {"bg": (245, 240, 230),  "accent": (100, 160, 120), "text": (30, 30, 30)},
        "tech":      {"bg": (5, 5, 20),       "accent": (0, 200, 255),   "text": (255, 255, 255)},
    }
    colors = schemes.get(color_scheme, schemes["luxury"])

    W, H = 1080, 1080
    banner = Image.new("RGB", (W, H), colors["bg"])
    draw = ImageDraw.Draw(banner)

    # Background gradient effect
    for i in range(H):
        alpha = int(30 * (1 - i/H))
        draw.line([(0, i), (W, i)], fill=tuple(min(255, c+alpha) for c in colors["bg"]))

    # Place influencer image (right side)
    try:
        inf_img = Image.open(BytesIO(influencer_bytes)).convert("RGBA")
        # Resize to fit right 55% of banner
        inf_w = int(W * 0.58)
        inf_h = H
        inf_img = inf_img.resize((inf_w, inf_h), Image.LANCZOS)
        # Fade left edge of influencer image
        fade_mask = Image.new("L", (inf_w, inf_h), 255)
        fade_draw = ImageDraw.Draw(fade_mask)
        fade_width = 120
        for x in range(fade_width):
            alpha = int(255 * (x / fade_width))
            fade_draw.line([(x, 0), (x, inf_h)], fill=alpha)
        inf_rgba = inf_img.copy()
        inf_rgba.putalpha(fade_mask)
        banner.paste(inf_img, (W - inf_w, 0), inf_rgba)
    except Exception as e:
        logger.warning(f"Could not paste influencer: {e}")

    # Text area (left side)
    text_x = 60
    y = 120

    # Accent line
    draw.rectangle([(text_x, y), (text_x + 50, y + 4)], fill=colors["accent"])
    y += 30

    # Try to load fonts, fallback to default
    try:
        font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 64)
        font_med   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_cta   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    except:
        font_big = font_med = font_small = font_cta = ImageFont.load_default()

    # Headline — wrap text
    words = headline.upper().split()
    lines = []
    line = ""
    for word in words:
        test = (line + " " + word).strip()
        bbox = draw.textbbox((0,0), test, font=font_big)
        if bbox[2] - bbox[0] < W * 0.48:
            line = test
        else:
            if line: lines.append(line)
            line = word
    if line: lines.append(line)

    for l in lines[:3]:
        draw.text((text_x, y), l, font=font_big, fill=colors["text"])
        y += 70

    y += 16
    # Subtext — wrap
    sub_words = subtext.split()
    sub_lines = []
    line = ""
    for word in sub_words:
        test = (line + " " + word).strip()
        bbox = draw.textbbox((0,0), test, font=font_med)
        if bbox[2] - bbox[0] < W * 0.44:
            line = test
        else:
            if line: sub_lines.append(line)
            line = word
    if line: sub_lines.append(line)

    for l in sub_lines[:4]:
        draw.text((text_x, y), l, font=font_med, fill=(*colors["text"][:3],) if len(colors["text"])>3 else colors["text"])
        y += 36

    y += 30
    # CTA button
    cta_bbox = draw.textbbox((0,0), cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0] + 50
    cta_h = 52
    draw.rounded_rectangle(
        [(text_x, y), (text_x + cta_w, y + cta_h)],
        radius=10, fill=colors["accent"]
    )
    draw.text((text_x + 25, y + 12), cta, font=font_cta,
              fill=(20, 20, 20) if colors["accent"][0] > 150 else (255, 255, 255))

    # Bottom accent
    draw.rectangle([(0, H-4), (W, H)], fill=colors["accent"])

    buf = BytesIO()
    banner.save(buf, format="PNG", quality=95)
    buf.seek(0)
    return buf.read()

# ─────────────────────────────────────────
# RESEARCH ENGINE
# ─────────────────────────────────────────

async def research_and_generate(session_data: dict, content_type: str, user_command: str) -> dict:
    """Main AI brain — research + generate everything"""

    image_b64 = session_data.get("image_b64")

    system_prompt = """You are an elite UGC content strategist, creative director, and social media expert.
You think like a human — with cultural intuition, trend awareness, and deep platform knowledge.
You understand Indian audiences, Instagram trends, and what drives engagement.
Always respond in valid JSON only. No markdown. No extra text."""

    prompt = f"""
Analyze this content request and generate a complete UGC content package.

USER COMMAND: {user_command}
CONTENT TYPE: {content_type}
INFLUENCER: Indian female, authentic, relatable, works across lifestyle/beauty/real estate niches

Think deeply. Research what's trending. Generate:

{{
  "product_analysis": "What this product/service is and who buys it",
  "target_audience": "Specific audience description",
  "color_scheme": "one of: luxury, real_estate, fashion, wellness, tech",
  "banner": {{
    "headline": "Powerful 4-6 word headline",
    "subtext": "2-3 line compelling description",
    "cta": "Call to action button text"
  }},
  "hooks": [
    "Hook 1 — first 3 seconds of video",
    "Hook 2 — alternate hook",
    "Hook 3 — curiosity-based hook"
  ],
  "video_script": {{
    "hook": "Exact words for first 3 seconds",
    "main": "Core content 10-25 seconds with actions",
    "cta": "Last 5 seconds exact words",
    "visual_direction": "What influencer should do/wear/show"
  }},
  "caption": "Full Instagram caption with emojis, line breaks, storytelling opener",
  "hashtags": ["list", "of", "20", "strategic", "hashtags"],
  "trending_audio": ["3 trending song/audio suggestions for this content"],
  "posting_time": "Best day and time to post",
  "story_ideas": ["2-3 Instagram story ideas to support this post"],
  "human_insight": "One deep insight about why this will work for Indian audience"
}}
"""

    result_text = await ask_gpt(prompt, image_b64=image_b64, system=system_prompt)

    # Clean and parse JSON
    clean = result_text.strip()
    clean = re.sub(r'^```json\s*', '', clean)
    clean = re.sub(r'\s*```$', '', clean)

    return json.loads(clean)

# ─────────────────────────────────────────
# BOT HANDLERS
# ─────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📸 Upload Image + Command", callback_data="guide_upload")],
        [InlineKeyboardButton("ℹ️ How to use", callback_data="guide_how")]
    ]
    await update.message.reply_text(
        f"👋 Hey {user.first_name}!\n\n"
        "🤖 *UGC AI Agent* is ready.\n\n"
        "Just send me:\n"
        "📸 *An image* (product, property, anything)\n"
        "✍️ *Tell me what to create* — banner, UGC post, reel script\n\n"
        "Examples:\n"
        "• _'Banner for real estate plot in Hyderabad'_\n"
        "• _'UGC content for skincare serum'_\n"
        "• _'Instagram reel script for fashion brand'_\n\n"
        "I'll research, generate, and give you everything! 🚀",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User sends a photo"""
    user_id = update.effective_user.id
    session = get_session(user_id)

    msg = await update.message.reply_text("📥 Got your image! Analyzing...")

    # Download photo
    photo = update.message.photo[-1]  # Largest size
    file = await context.bot.get_file(photo.file_id)
    b64, raw = await telegram_photo_to_base64(file)

    session["image_b64"] = b64
    session["image_raw"] = raw

    # Get caption if any
    caption = update.message.caption or ""

    if caption.strip():
        # They sent image + command together
        session["command"] = caption
        await msg.edit_text("🔍 Analyzing your image and command...")
        await process_request(update, context, session, caption)
    else:
        # Ask what they want
        keyboard = [
            [InlineKeyboardButton("🖼 Banner / Flyer", callback_data="ct_banner")],
            [InlineKeyboardButton("🎬 UGC Reel Content", callback_data="ct_ugc")],
            [InlineKeyboardButton("📱 Instagram Post", callback_data="ct_post")],
            [InlineKeyboardButton("🏠 Real Estate Ad", callback_data="ct_realestate")],
            [InlineKeyboardButton("💄 Beauty/Fashion UGC", callback_data="ct_beauty")],
        ]
        await msg.edit_text(
            "✅ Image received! What do you want me to create?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User sends text command"""
    user_id = update.effective_user.id
    session = get_session(user_id)
    text = update.message.text.strip()

    # Check for upload approval
    if text.lower() in ["upload", "yes upload", "post it", "upload it", "akri", "ok upload"]:
        if session.get("generated"):
            await handle_upload_approval(update, context, session)
        else:
            await update.message.reply_text("No content ready yet. Send me an image first! 📸")
        return

    if session.get("image_b64"):
        session["command"] = text
        await process_request(update, context, session, text)
    else:
        await update.message.reply_text(
            "📸 Please send me an image first, then I'll create content based on your command!\n\n"
            "Example: Send a product photo and write *'UGC content for skincare'*",
            parse_mode="Markdown"
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session = get_session(user_id)
    data = query.data

    content_map = {
        "ct_banner": ("banner", "🖼 Banner/Flyer"),
        "ct_ugc": ("ugc", "🎬 UGC Reel"),
        "ct_post": ("post", "📱 Instagram Post"),
        "ct_realestate": ("real_estate", "🏠 Real Estate Ad"),
        "ct_beauty": ("beauty", "💄 Beauty UGC"),
    }

    if data in content_map:
        ct, label = content_map[data]
        await query.edit_message_text(f"{label} selected! What's this for? (e.g. 'luxury villa in Mumbai', 'glow serum launch')")
        session["content_type"] = ct

    elif data == "guide_how":
        await query.edit_message_text(
            "📖 *How to use UGC Agent:*\n\n"
            "1️⃣ Send me any image\n"
            "2️⃣ Tell me what to create\n"
            "3️⃣ I research + generate everything\n"
            "4️⃣ Review what I send back\n"
            "5️⃣ Say *'upload'* to post to Instagram\n\n"
            "That's it! 🎯",
            parse_mode="Markdown"
        )

    elif data.startswith("approve_"):
        await handle_upload_approval(update, context, session)

    elif data == "regenerate":
        if session.get("command"):
            await process_request(update, context, session, session["command"], edit_msg=query.message)

async def process_request(update, context, session, command, edit_msg=None):
    """Main processing pipeline"""
    user_id = update.effective_user.id if update.effective_user else None

    # Send thinking message
    if edit_msg:
        thinking_msg = edit_msg
        await thinking_msg.edit_text(
            "🧠 Agent is thinking...\n\n"
            "🔍 Researching trends...\n"
            "✍️ Writing copy...\n"
            "🎨 Designing banner...\n\n"
            "_This takes 20-30 seconds_",
            parse_mode="Markdown"
        )
    else:
        thinking_msg = await update.message.reply_text(
            "🧠 Agent is thinking...\n\n"
            "🔍 Researching trends...\n"
            "✍️ Writing copy...\n"
            "🎨 Designing banner...\n\n"
            "_This takes 20-30 seconds_",
            parse_mode="Markdown"
        )

    content_type = session.get("content_type", "ugc")

    try:
        # Step 1: Research + Generate copy
        await thinking_msg.edit_text("🔍 Researching your niche and audience...", parse_mode="Markdown")
        data = await research_and_generate(session, content_type, command)
        session["generated"] = data

        # Step 2: Create banner with influencer
        await thinking_msg.edit_text("🎨 Creating banner with your influencer model...", parse_mode="Markdown")

        influencer_bytes = session.get("image_raw")
        banner_data = data.get("banner", {})

        banner_img = await create_banner_with_influencer(
            influencer_bytes=influencer_bytes,
            headline=banner_data.get("headline", "Premium Quality"),
            subtext=banner_data.get("subtext", "Discover the difference"),
            cta=banner_data.get("cta", "Learn More"),
            color_scheme=data.get("color_scheme", "luxury")
        )

        await thinking_msg.delete()

        # Step 3: Send banner
        chat_id = update.effective_chat.id
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=BytesIO(banner_img),
            caption=f"🖼 *Banner Ready!*\n\n_{data.get('product_analysis', '')}..._",
            parse_mode="Markdown"
        )

        # Step 4: Send content package
        hooks_text = "\n".join([f"  {i+1}. {h}" for i, h in enumerate(data.get("hooks", []))])
        script = data.get("video_script", {})
        hashtags = " ".join([f"#{h.replace('#','').strip()}" for h in data.get("hashtags", [])[:15]])
        audio = "\n".join([f"  🎵 {a}" for a in data.get("trending_audio", [])])

        msg1 = (
            f"⚡ *HOOKS (First 3 seconds)*\n{hooks_text}\n\n"
            f"🎬 *VIDEO SCRIPT*\n"
            f"🔴 Hook: {script.get('hook','')}\n"
            f"📹 Main: {script.get('main','')}\n"
            f"✅ CTA: {script.get('cta','')}\n"
            f"🎭 Visual: _{script.get('visual_direction','')}_"
        )
        await context.bot.send_message(chat_id=chat_id, text=msg1, parse_mode="Markdown")

        msg2 = (
            f"✍️ *CAPTION*\n\n{data.get('caption','')}\n\n"
            f"🏷 *HASHTAGS*\n{hashtags}"
        )
        await context.bot.send_message(chat_id=chat_id, text=msg2, parse_mode="Markdown")

        msg3 = (
            f"🎵 *TRENDING AUDIO*\n{audio}\n\n"
            f"⏰ *BEST TIME TO POST*\n{data.get('posting_time','')}\n\n"
            f"📱 *STORY IDEAS*\n" +
            "\n".join([f"  • {s}" for s in data.get("story_ideas", [])]) +
            f"\n\n💡 *HUMAN INSIGHT*\n_{data.get('human_insight','')}_"
        )
        await context.bot.send_message(chat_id=chat_id, text=msg3, parse_mode="Markdown")

        # Step 5: Approval buttons
        keyboard = [
            [InlineKeyboardButton("✅ Upload to Instagram", callback_data="approve_upload")],
            [InlineKeyboardButton("🔄 Regenerate", callback_data="regenerate")],
            [InlineKeyboardButton("✏️ Edit Caption", callback_data="edit_caption")]
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="👆 Everything ready! Say *'upload'* or tap button to post to Instagram 🚀",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except json.JSONDecodeError as e:
        await thinking_msg.edit_text(f"⚠️ AI response parsing error. Try again!\nError: {str(e)[:100]}")
    except Exception as e:
        logger.error(f"Processing error: {e}", exc_info=True)
        await thinking_msg.edit_text(
            f"❌ Something went wrong: {str(e)[:200]}\n\nTry again or rephrase your command."
        )

async def handle_upload_approval(update, context, session):
    """Post to Instagram"""
    chat_id = update.effective_chat.id
    generated = session.get("generated", {})

    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_BUSINESS_ID:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📋 *Instagram posting not configured yet.*\n\nHere's your final content to post manually:\n\n" +
                 generated.get("caption", "") + "\n\n" +
                 " ".join([f"#{h}" for h in generated.get("hashtags", [])[:20]]),
            parse_mode="Markdown"
        )
        return

    await context.bot.send_message(chat_id=chat_id, text="📤 Uploading to Instagram...")

    try:
        # Instagram Graph API posting
        caption_full = generated.get("caption","") + "\n\n" + " ".join([f"#{h}" for h in generated.get("hashtags",[])])

        # Note: For full Instagram auto-posting you need a public image URL
        # This is the basic structure
        async with aiohttp.ClientSession() as http:
            # Create media container
            async with http.post(
                f"https://graph.facebook.com/v18.0/{INSTAGRAM_BUSINESS_ID}/media",
                params={
                    "image_url": session.get("image_url", ""),
                    "caption": caption_full[:2200],
                    "access_token": INSTAGRAM_ACCESS_TOKEN
                }
            ) as r:
                media_data = await r.json()
                container_id = media_data.get("id")

            if container_id:
                # Publish
                async with http.post(
                    f"https://graph.facebook.com/v18.0/{INSTAGRAM_BUSINESS_ID}/media_publish",
                    params={"creation_id": container_id, "access_token": INSTAGRAM_ACCESS_TOKEN}
                ) as r:
                    pub_data = await r.json()
                    if pub_data.get("id"):
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="✅ *Posted to Instagram successfully!* 🎉\n\nPost ID: " + pub_data["id"],
                            parse_mode="Markdown"
                        )
                    else:
                        raise Exception(str(pub_data))
            else:
                raise Exception(str(media_data))

    except Exception as e:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ Instagram posting error: {str(e)[:200]}\n\nContent is ready — post manually."
        )

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("🤖 UGC Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
