# BakiShule

BakiShule is a school attendance early-warning MVP for a hackathon demo. Teachers mark attendance from a basic-phone USSD menu; a rule-based score highlights learners who may need support; parents and school staff can be contacted by SMS. The dashboard is server-rendered and updates its key panels with HTMX.

> **Demo safety:** this is a local MVP, not a production student-record system. It has no login or role-based access control. Keep it on localhost or a trusted demo network. `DRY_RUN=true` is the default and prevents outbound SMS and Airtime calls.

## What is implemented

- FastAPI + SQLAlchemy + SQLite; Jinja2 dashboard, HTMX polling, Chart.js.
- USSD callback at `POST /ussd`, SMS inbound callback at `POST /sms/inbound`.
- Attendance is class-wide: learners not listed absent are marked present. Submitting again for the same date overwrites the first submission.
- Explainable risk scores (0–100) for absence streaks, recent attendance drops, weekday patterns, recurring monthly clusters, same-day sibling absences, and parent “2 / Fees” replies.
- Tiered interventions: guardian check-in for watch, teacher/head-teacher alerts at at-risk, sponsor flag at critical, and airtime after an eligible four-week full-attendance streak.
- Sponsor profiles hide the learner's full name until guardian consent is true.
- Demo-only advance-day, streak-simulation, recompute, and reset controls.
- Seed: one school, five classes, 150 learners, about 60 days of weekday attendance, behaviour notes, and a hashed demo PIN for every guardian.
- Parent SMS/USSD queries (STATUS, ATT, BEHAVIOUR, REPORT in English and Swahili), teacher behaviour logging over USSD, and a Friday weekly report.

## Setup

Python 3.11+ is required. From the project root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Set AT_API_KEY and the demo phones in .env; keep DRY_RUN=true for the first run.
.venv/bin/python -m scripts.seed --reset
.venv/bin/python -m uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). API health check: `/health`.

To recompute risk snapshots outside the dashboard:

```bash
.venv/bin/python -m scripts.recompute_risk
```

Run the tests:

```bash
.venv/bin/pytest -q
```

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `AT_USERNAME` | Africa's Talking app username; use `sandbox` for sandbox | `sandbox` |
| `AT_API_KEY` | Sandbox API key from the AT app dashboard | empty |
| `AT_SENDER_ID` | SMS sender. Leave empty in sandbox (`AFTKNG` is rejected as `InvalidSenderId`); set to your shortcode for two-way SMS. `AT_SHORTCODE` is read as a fallback | empty |
| `AT_USSD_CODE` | Code assigned to the USSD product in AT | empty |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./bakishule.db` |
| `DRY_RUN` | Log outbound SMS/Airtime/Mobile Data instead of sending | `true` |
| `DEMO_MODE` | Enables demo controls and simulated date | `true` |
| `DEMO_TEACHER_PHONE` | Seeded teacher callback identity | `+254700000001` |
| `DEMO_PARENT_PHONE` | Seeded guardian phone | `+254700000002` |
| `DEFAULT_LANGUAGE` | Language used when a person hasn't chosen one | `en` |
| `AIRTIME_REWARD_KES` | Airtime amount after an eligible 4-week streak | `20` |
| `DEMO_GUARDIAN_PIN` | PIN given to every seeded guardian (stored hashed) | `1234` |
| `PARENT_DAILY_QUERY_LIMIT` | Parent SMS/USSD queries allowed per number per day | `10` |
| `TIMEZONE` | Used for the daily limit and the weekly report schedule | `Africa/Nairobi` |
| `ENABLE_SCHEDULER` | Send the weekly REPORT every Friday 16:00 | `true` |
| `ANTHROPIC_API_KEY` | Anthropic API key for AI chat replies (keep it only in `.env`) | empty |
| `AI_CHAT_ENABLED` | Answer free-text parent SMS with Claude (off = forward to teacher) | `true` |
| `AI_MODEL` | Claude model for AI chat | `claude-opus-5-5` |
| `SMS_USE_EMOJI` | Use ⭐ ⚠️ ✅ ⬇️ 🟡 in SMS (plain fallback when over 2 segments) | `true` |

`.env` is ignored by git. Do not put live API keys or real student data in the repository.

## Africa's Talking sandbox setup

The official Python SDK was checked at install time (`africastalking` 2.0.3):

- `africastalking.initialize(username, api_key)`.
- SMS: `SMS.send(message, recipients, sender_id=None, enqueue=False, ...)` — note the keyword is `sender_id`, not `sender`. Errors raise `africastalking.Service.AfricasTalkingException`; the adapter catches it (and network/invalid-number errors) and returns `{"status": "failed", "error": ..., "details": ...}`.
- Phone numbers are normalized to E.164 (`0707…`, `254707…`, `00254707…` → `+254707…`) before sending and on inbound USSD/SMS lookups (`app/services/phone.py`).
- Airtime: `Airtime.send(phone_number=..., amount=..., currency_code=...)`.
- Mobile Data: `MobileData.send(product_name, recipients, ...)`, where a recipient uses `phoneNumber`, `quantity`, `unit`, and `validity`.
- The SDK package has no Payments service export. Payments therefore use the `PaymentService` interface and `MockPaymentService`; no payment is charged.

The AT developer documentation pages returned HTTP 403 to this build environment. The USSD callback keys below are corroborated by the official SDK's USSD example. The inbound SMS handler accepts the standard form fields `from`, `to`, `text`, `date`, `id`, and `linkId`; it uses `from` and `text`. Check the current callback configuration shown in your AT console if it presents a different payload shape.

### Configure the AT console

1. Create/open a **Sandbox** app and copy its API key into `AT_API_KEY`; keep `AT_USERNAME=sandbox` and leave `AT_SENDER_ID` empty.
2. Check SMS credentials (set `DRY_RUN=false` first; add the recipient to the sandbox simulator so you can see the message):

   ```bash
   .venv/bin/python -m scripts.send_test_sms 0707274525 "Hello from BakiShule"
   ```

   Prints the AT JSON response, or `{"status": "failed", ...}` with details (e.g. invalid key, blacklisted number).
3. Expose the local server with ngrok, copy the HTTPS URL, and **open it once in your browser** (ngrok free tier shows an interstitial page that can otherwise block AT callbacks):

   ```bash
   ngrok http 8000
   ```

4. In the AT sandbox **USSD** product (USSD → Create channel), set its callback URL to the exact path — **no trailing slash**:

   ```text
   https://YOUR-NGROK-DOMAIN/ussd
   ```

   Use `POST` / form-urlencoded. The app reads `sessionId`, `serviceCode`, `phoneNumber`, and `text`, and returns a plain-text `CON ...` (continue) or `END ...` (finish) response. Responses must come back within ~3 seconds or the sandbox drops the session. Put the assigned code in `AT_USSD_CODE`.

   Test it through ngrok before using the simulator:

   ```bash
   curl -X POST https://YOUR-NGROK-DOMAIN/ussd \
     -d "sessionId=12345" -d "serviceCode=*384#" \
     -d "phoneNumber=+254700000001" -d "text="
   # → CON BakiShule
   #   1. Mark attendance ...
   ```
5. In the sandbox **SMS inbound / callback** settings, set:

   ```text
   https://YOUR-NGROK-DOMAIN/sms/inbound
   ```

   Parents reply to a **shortcode**: create one under **SMS → Shortcodes** in the sandbox, then set `AT_SENDER_ID` to it so check-ins come from a number parents can reply to.

   Also set **SMS → SMS Callback URLs → Delivery Reports** to `https://YOUR-NGROK-DOMAIN/sms/delivery`. Each SMS intervention stores AT's `messageId`; the delivery report updates its status to `delivered` or `failed` (with the reason).

   The route reads `from` and `text`, accepts replies `1`, `2`, `3`, other text, and `STOP` / `START`, then returns HTTP 200.
6. In your app's USSD simulator, dial the code assigned by AT (`AT_USSD_CODE`), and use the exact `DEMO_TEACHER_PHONE` value as the simulated caller. Set the simulator's guardian sender to `DEMO_PARENT_PHONE` when testing inbound SMS. The seeded teacher's attendance class is `5A`; the seeded parent is attached to learner 01.

Do not set `DRY_RUN=false` until you have confirmed the Sandbox app, sender ID, simulator phone numbers, and available sandbox services. The sandbox API key remains private in `.env`.

### What's real vs mocked

- **USSD:** real HTTP callback flow when the AT product points to the ngrok URL; no USSD charge/network session is initiated by the local app.
- **SMS/Airtime:** official SDK calls are wired and will be used only when `DRY_RUN=false`. With the default `true`, requests are logged and stored as `mocked` interventions.
- **Mobile Data:** official SDK method is available and wrapped in the AT client, but there is no dashboard feature using it. Sandbox provisioning/service availability was not verifiable here.
- **Payments:** always mocked; the SDK installed has no Payments service. The sponsor button creates a demo transaction and sends simulated receipts through the SMS adapter.
- **Database/learners:** local demo seed only. No external student data is fetched.

## English and Kiswahili

Every USSD screen and SMS is available in English and Kiswahili. All wording lives in [`app/messages.py`](app/messages.py) (one dictionary per language with identical keys and placeholders; a test enforces this) and is read through `t(key, lang, **params)`. [`TRANSLATIONS.md`](TRANSLATIONS.md) lists every string side by side for a native speaker to review; regenerate it with `python -m scripts.export_translations` after editing.

- **Language preference** is stored per guardian and per teacher (`en`, `sw`, or empty until chosen). Change it on the learner page (guardian) or **Teachers** page, by USSD, or by SMS.
- **First-time USSD users** (no language yet), teachers and parents alike, see:
  ```
  Karibu BakiShule / Welcome
  Chagua lugha / Choose language:
  1. English
  2. Kiswahili
  ```
- **Everything outgoing** (check-ins, teacher/head-teacher alerts, sponsor receipts, airtime messages, weekly reports, USSD screens) uses the recipient's saved language, defaulting to English.

### Kiswahili USSD menus

| Teacher (`BakiShule - Mwalimu`) | Parent (`BakiShule - {jina}`) |
|---|---|
| 1. Andika mahudhurio | 1. Hali ya leo |
| 2. Muhtasari wa darasa | 2. Mahudhurio |
| 3. Wanafunzi walio hatarini | 3. Tabia *(PIN)* |
| 4. Andika tabia | 4. Ripoti ya wiki *(PIN)* |
| 5. Tafuta mwanafunzi | 5. Wasiliana na shule |
| 6. Badilisha lugha | 6. Badilisha lugha |

A teacher who is also a parent gets **6. Menyu ya mzazi** and **7. Badilisha lugha**. Navigation: `0. Rudi` (back), `00. Menyu kuu` (main menu). Behaviour codes: 1 Alishiriki vizuri ⭐, 2 Hakufanya kazi ya nyumbani ⚠️, 3 Alichelewa darasani ⚠️, 4 Alisumbua darasani ⚠️, 5 Aliwasaidia wenzake ⭐, 6 Alama bora mtihanini ⭐.

## Parent SMS commands

Parents text the shortcode; every reply is generated from system data (teachers never answer by hand). Commands are case-insensitive.

| English | Kiswahili | PIN? | Reply |
|---|---|---|---|
| `MENU` / `HELP` | `MSAADA` | no | List of commands |
| `STATUS` | `HALI` | no | Today's attendance + latest behaviour note |
| `ATT` | `MAHUDHURIO` | no | Days attended / missed this week, term %, class average |
| `BEHAVIOUR <PIN>` | `TABIA <PIN>` | yes | Last 5 behaviour notes with ⭐/⚠️ and term totals |
| `REPORT <PIN>` | `RIPOTI <PIN>` | yes | Weekly summary: attendance % and change, behaviour, status, a tip |
| `ENGLISH`, `LANG EN` | `KISWAHILI`, `LUGHA SW` | no | Saves the language and replies with the menu in it |
| `STOP` / `START` | `ACHA` / `ANZA` | no | Opt out / back in |
| `1` / `2` / `3` | `1` / `2` / `3` | no | Check-in replies: sick / fees (karo) / other |

**Ask in your own words (AI chat).** Anything that isn't a command (for example *"Mtoto wangu anaendelea vipi?"* or *"How is my child doing?"*) is answered by Claude like a chat, in the language the parent wrote in, using only that parent's children's real data and the last few messages. The reply stays within 2 SMS. Claude also recognises intent: *"Baraka ni mgonjwa leo"* (sick), *"no money for fees"* (fees) or *"ask the teacher to call me"* trigger the same actions as replies 1 / 2 / 3, and the teacher is told. Behaviour history and risk status need the parent's PIN typed in the message (*"Tabia ya Amani iko aje? 1234"*); the PIN is masked before anything is sent. The school records attendance and behaviour notes, not exam marks, and the assistant says so. If the AI call fails or `AI_CHAT_ENABLED=false`, free text is forwarded to the teacher with a thank-you as before. Chat messages count toward the daily limit. See [PRIVACY.md](PRIVACY.md) for what is sent to Anthropic.

**Which language the reply uses:** a Kiswahili command word (HALI, MAHUDHURIO, TABIA, RIPOTI, MSAADA, ACHA, ANZA) gets a Kiswahili reply; an English one gets English; language-neutral input (1/2/3, a PIN on its own, other text) uses the saved preference, defaulting to English. Command words never change the saved preference; only the language commands do. The first SMS from a guardian with no language also gets *"Karibu BakiShule! Tuma KISWAHILI au ENGLISH kuchagua lugha. / Reply ENGLISH or KISWAHILI to choose your language."* (once), and their command is still answered.

Example Kiswahili reply (`HALI`): *Amani (5B) - Jumatano 25 Nov: ✅ Yuko shuleni leo. Mwisho: ⭐ Alishiriki vizuri (Mwl. Otieno). Tuma MAHUDHURIO, TABIA au RIPOTI kwa zaidi.*

- **Several children:** `STATUS` and `ATT` return a short combined summary; add the child number for details (`HALI 2`, `RIPOTI 2 1234`).
- **Security:** the guardian is identified by phone number; unknown numbers only get a bilingual "not registered". `BEHAVIOUR`/`REPORT` need the 4-digit PIN (hashed in the database); 5 wrong PINs lock the number for 1 hour. PINs are masked in all logs, and a PIN sent on its own is never forwarded to a teacher.
- **Rate limit:** 10 queries per number per day, then one polite limit message and silence until midnight (Nairobi).
- **Length:** every reply stays within 2 SMS segments. Emojis force UCS-2 encoding (134 characters for 2 segments instead of 306), so when a reply would be longer the emoji-free fallback is sent (⭐→`*`, ⚠️→`!`, ✅→`OK`, ⬇️/⬆️→`down`/`up` or `chini`/`juu`, 🟢🟡🟠🔴 removed). Set `SMS_USE_EMOJI=false` to always send the plain version.
- **Parent USSD:** see the menus above (PIN for Behaviour and Weekly report). **Wasiliana na shule / Contact school** forwards a typed message to the class teacher.
- **Weekly report:** sent automatically every Friday at 16:00 Nairobi time to guardians who haven't opted out (respects `DRY_RUN`), each in their own language, or on demand with **Send weekly reports now** in the demo controls.
- **Dashboard:** the **Live parent messages** panel (overview and `/parent-queries`) shows incoming commands and auto-replies live with an EN/SW badge; behaviour notes appear on each learner's timeline.
- Teachers log behaviour from the USSD menu: **4 → class → roll → code → subject (optional)**. Codes, subjects, and the behaviour risk signal (3+ concerns in 14 days, +8) are configured in `app/school_config.py`.

To add these features to an existing demo database without resetting it (adds new tables/columns, behaviour notes, guardian PINs and demo languages):

```bash
.venv/bin/python -m scripts.seed --upgrade
```

## Three-minute demo walkthrough

1. Open the dashboard and show the seeded attendance trend, class heatmap, and risk list.
2. In the AT USSD simulator, enter the teacher number. Select **1 → class 5A → absent roll `07` → confirm 1**. Learner 07 has two seeded prior school-day absences, so this submission can push the score into `watch`; the guardian check-in is recorded as mocked with `DRY_RUN=true`.
3. Submit an inbound SMS with the guardian number and body `2` (or use the sandbox SMS simulator). The fee reply is stored, raises risk, and creates a sponsor flag. Open **Sponsor support**; names are masked until `sponsor_consent=true`.
4. Click **Sponsor KES 3,000 (demo)**. The mock payment transaction and guardian/teacher receipt interventions are recorded.
5. Return to the learner detail page or overview, choose a learner previously at `watch` or above, and click **Simulate 4-week streak**. The attendance calendar is set to present for 20 school days; the Airtime and congratulations SMS show as mocked interventions.
6. **Kiswahili, live.** Click **Reset language for demo guardian** in the demo controls, and put **Live parent messages** (`/parent-queries`) on the projector.
   1. The demo guardian dials the USSD code: the **Karibu BakiShule / Welcome** language screen appears. Choose **2. Kiswahili**: the menu is now in Kiswahili (the demo number is also a teacher, so choose **6. Menyu ya mzazi** for the parent menu, then **1. Hali ya leo**).
   2. The parent texts **`HALI`** to the shortcode: the reply comes back in Kiswahili (a combined summary for both children; `HALI 1` for one child, `RIPOTI 1 1234` for the weekly report).
   3. The parent texts **`ENGLISH`**: the English menu arrives and from now on every reply, check-in and USSD screen for that number is in English. Text `STATUS` or dial again to show it.
   4. The parent texts a normal question, **`Mtoto wangu anaendelea vipi?`** or **`How is my child doing?`**: an AI reply built from the child's real attendance arrives in the same language. Try **`Learner 91 ni mgonjwa leo`**: the reply says the teacher has been told, and the teacher gets a sick alert.
   Each message and automatic reply appears in the panel within 3 seconds with an EN/SW badge and the PIN masked.

## Callback/reference shapes

USSD requests are form fields:

```text
sessionId, serviceCode, phoneNumber, text
```

Inbound SMS callback fields consumed by this MVP:

```text
from, to, text, date, id, linkId
```

Only `from` and `text` are required for reply matching. `to`, `date`, `id`, and `linkId` are ignored, as AT can include them as delivery metadata.
