# 🤖 UGC AI Agent — Complete Setup Guide

## YOUR FLOW
1. Send image to Telegram bot
2. Tell bot what to create (banner, UGC, reel)
3. Bot researches + generates EVERYTHING
4. Bot sends back: Banner with your influencer + Hooks + Script + Caption + Hashtags + Audio suggestions
5. You say "upload" → auto posts to Instagram

---

## STEP 1 — Get Your API Keys

### A) Telegram Bot Token (FREE)
1. Open Telegram → search @BotFather
2. Send: /newbot
3. Choose a name (e.g. "My UGC Agent")
4. Copy the token — looks like: 1234567890:ABCdef...
5. Paste it in bot.py → TELEGRAM_TOKEN = "paste here"

### B) Anthropic Claude API (FREE CREDITS TO START)
1. Go to: https://console.anthropic.com
2. Sign up with email
3. Go to API Keys → Create Key
4. Copy and paste in bot.py → ANTHROPIC_API_KEY = "paste here"

### C) Replicate API (FREE CREDITS)
1. Go to: https://replicate.com
2. Sign up
3. Go to: https://replicate.com/account/api-tokens
4. Create token
5. Paste in bot.py → REPLICATE_API_KEY = "paste here"

### D) Your Influencer Images
- Upload your 2 influencer photos to: https://imgbb.com (free)
- Copy the direct image URLs
- Paste in bot.py:
  INFLUENCER_CASUAL_URL = "https://i.ibb.co/..."
  INFLUENCER_SAREE_URL = "https://i.ibb.co/..."

---

## STEP 2 — Upload to GitHub (FREE)

1. Go to: https://github.com
2. Create account if you don't have one
3. Click "New Repository"
4. Name it: ugc-bot
5. Upload these 3 files:
   - bot.py
   - requirements.txt
   - railway.toml

---

## STEP 3 — Deploy on Railway (FREE)

1. Go to: https://railway.app
2. Sign up with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your ugc-bot repository
5. Railway will auto-detect and deploy!

### Add Environment Variables on Railway:
Go to your project → Variables → Add these:
- TELEGRAM_TOKEN = your token
- ANTHROPIC_API_KEY = your key
- REPLICATE_API_KEY = your key

(Don't put real keys in bot.py — use Railway variables for security!)

---

## STEP 4 — Test Your Bot

1. Open Telegram
2. Find your bot by its name
3. Send /start
4. Send a photo with caption: "banner for real estate villa"
5. Watch the magic! ✨

---

## COMMANDS YOUR BOT UNDERSTANDS

Send image + any of these:
- "banner for [product]"
- "UGC content for [product]"  
- "Instagram reel for [product]"
- "real estate ad for [property]"
- "beauty UGC for [product]"

After receiving content:
- Say "upload" → posts to Instagram
- Say "regenerate" → creates new version

---

## WHAT BOT SENDS BACK

1. 🖼 Banner/Flyer with your influencer composited in
2. ⚡ 3 Hooks (first 3 seconds of video)
3. 🎬 Full Video Script (hook + main + CTA + visual direction)
4. ✍️ Instagram Caption (ready to copy)
5. 🏷 20 Strategic Hashtags
6. 🎵 Trending Audio Suggestions
7. ⏰ Best Time to Post
8. 📱 Story Ideas

---

## COST BREAKDOWN

| Service | Cost |
|---------|------|
| Telegram Bot | FREE forever |
| Railway Hosting | FREE tier (500 hours/month) |
| Anthropic Claude | ~$0.01 per request |
| Replicate | Free credits, then ~$0.002/image |
| Instagram API | FREE |

**Estimated monthly cost: $2-5 for heavy use**

---

## NEED HELP?

If anything doesn't work, open the bot conversation and share the error message.
