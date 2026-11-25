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
- Seed: one school, three classes, 90 learners, and about 60 days of weekday attendance.

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
| `AT_SHORTCODE` | Optional registered SMS sender ID / shortcode | empty |
| `AT_USSD_CODE` | Code assigned to the USSD product in AT | empty |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./bakishule.db` |
| `DRY_RUN` | Log outbound SMS/Airtime/Mobile Data instead of sending | `true` |
| `DEMO_MODE` | Enables demo controls and simulated date | `true` |
| `DEMO_TEACHER_PHONE` | Seeded teacher callback identity | `+254700000001` |
| `DEMO_PARENT_PHONE` | Seeded guardian phone | `+254700000002` |
| `DEFAULT_LANGUAGE` | Guardian check-in language: `en` or `sw` | `en` |
| `AIRTIME_REWARD_KES` | Airtime amount after an eligible 4-week streak | `20` |

`.env` is ignored by git. Do not put live API keys or real student data in the repository.

## Africa's Talking sandbox setup

The official Python SDK was checked at install time (`africastalking` 2.0.3):

- `africastalking.initialize(username, api_key)`.
- SMS: `SMS.send(message, recipients, sender_id=None, enqueue=False, ...)`.
- Airtime: `Airtime.send(phone_number=..., amount=..., currency_code=...)`.
- Mobile Data: `MobileData.send(product_name, recipients, ...)`, where a recipient uses `phoneNumber`, `quantity`, `unit`, and `validity`.
- The SDK package has no Payments service export. Payments therefore use the `PaymentService` interface and `MockPaymentService`; no payment is charged.

The AT developer documentation pages returned HTTP 403 to this build environment. The USSD callback keys below are corroborated by the official SDK's USSD example. The inbound SMS handler accepts the standard form fields `from`, `to`, `text`, `date`, `id`, and `linkId`; it uses `from` and `text`. Check the current callback configuration shown in your AT console if it presents a different payload shape.

### Configure the AT console

1. Create/open a **Sandbox** app and copy its API key into `AT_API_KEY`; keep `AT_USERNAME=sandbox`.
2. Expose the local server with ngrok:

   ```bash
   ngrok http 8000
   ```

3. In the AT sandbox **USSD** product, set its callback URL to:

   ```text
   https://YOUR-NGROK-DOMAIN/ussd
   ```

   Use `POST` / form-urlencoded. The app reads `sessionId`, `serviceCode`, `phoneNumber`, and `text`, and returns a plain-text `CON ...` or `END ...` response.
4. In the sandbox **SMS inbound / callback** settings, set:

   ```text
   https://YOUR-NGROK-DOMAIN/sms/inbound
   ```

   The route reads `from` and `text`, accepts replies `1`, `2`, `3`, other text, and `STOP` / `START`, then returns HTTP 200.
5. In your app's USSD simulator, dial the code assigned by AT (`AT_USSD_CODE`), and use the exact `DEMO_TEACHER_PHONE` value as the simulated caller. Set the simulator's guardian sender to `DEMO_PARENT_PHONE` when testing inbound SMS. The seeded teacher's attendance class is `5A`; the seeded parent is attached to learner 01.

Do not set `DRY_RUN=false` until you have confirmed the Sandbox app, sender ID, simulator phone numbers, and available sandbox services. The sandbox API key remains private in `.env`.

### What's real vs mocked

- **USSD:** real HTTP callback flow when the AT product points to the ngrok URL; no USSD charge/network session is initiated by the local app.
- **SMS/Airtime:** official SDK calls are wired and will be used only when `DRY_RUN=false`. With the default `true`, requests are logged and stored as `mocked` interventions.
- **Mobile Data:** official SDK method is available and wrapped in the AT client, but there is no dashboard feature using it. Sandbox provisioning/service availability was not verifiable here.
- **Payments:** always mocked; the SDK installed has no Payments service. The sponsor button creates a demo transaction and sends simulated receipts through the SMS adapter.
- **Database/learners:** local demo seed only. No external student data is fetched.

## Three-minute demo walkthrough

1. Open the dashboard and show the seeded attendance trend, class heatmap, and risk list.
2. In the AT USSD simulator, enter the teacher number. Select **1 → class 5A → absent roll `07` → confirm 1**. Learner 07 has two seeded prior school-day absences, so this submission can push the score into `watch`; the guardian check-in is recorded as mocked with `DRY_RUN=true`.
3. Submit an inbound SMS with the guardian number and body `2` (or use the sandbox SMS simulator). The fee reply is stored, raises risk, and creates a sponsor flag. Open **Sponsor support**; names are masked until `sponsor_consent=true`.
4. Click **Sponsor KES 3,000 (demo)**. The mock payment transaction and guardian/teacher receipt interventions are recorded.
5. Return to the learner detail page or overview, choose a learner previously at `watch` or above, and click **Simulate 4-week streak**. The attendance calendar is set to present for 20 school days; the Airtime and congratulations SMS show as mocked interventions.

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
