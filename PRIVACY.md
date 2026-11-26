# Privacy notes

BakiShule handles learner names, attendance dates, guardian contact details, parent replies, and risk explanations. The hackathon seed uses generated records and placeholder phone numbers by default; replace them only with numbers that you control for the simulator.

## Who sees what

- **Teacher/head teacher:** the dashboard is currently unauthenticated, so anyone who can reach it can see full seeded learner names, attendance, risk reasons, and replies. The dashboard must remain local/trusted for the demo. Production use requires authentication and school/class-level authorization.
- **Sponsor view:** unconsented learner names are reduced to a first initial plus class and county. The profile shows the stated support need and risk score, not guardian name or phone. The name is shown only when `sponsor_consent` is true.
- **Guardian:** SMS prompts request only a short coded reply (`1` sick, `2` fees, `3` other); free-text replies are stored for teacher follow-up.
- **External providers:** if `DRY_RUN=false`, guardian/staff phone numbers and SMS content are sent through Africa's Talking. Sandbox calls are not production privacy controls.
- **AI chat (Anthropic):** when `AI_CHAT_ENABLED=true` and `ANTHROPIC_API_KEY` is set, a parent's free-text SMS (e.g. "How is my child doing?") is sent to the Anthropic API together with facts about that parent's own children: name, class, teacher surname, today's and this week's attendance, term and class-average attendance, and the latest teacher note. Behaviour history and risk status are included only when the parent typed their correct PIN in the message. Phone numbers, guardian names and PINs are never sent (PINs are masked as `****` before the call and in all logs), and recent exchanges from the last 24 hours are included so follow-up questions make sense. Anthropic's API data-retention terms apply. Set `AI_CHAT_ENABLED=false` to keep all parent data local; free text is then forwarded to the teacher as before.

## Consent and opt-out

`sponsor_consent` gates full-name display in the sponsor view. The app does not expose a consent collection workflow; staff must set consent only after obtaining it through an approved process. A guardian reply of `STOP` marks all learners sharing that guardian phone as opted out of outgoing guardian SMS and Airtime. `START` clears the local SMS opt-out flag. Replies and opt-out state remain in the local database for the demo.

## Data minimisation and retention

Risk reasons are stored as short strings and parent replies are retained as received for the intervention timeline. Use generated data for demos; do not enter sensitive medical details or unnecessary family information. The demo reset drops and reseeds the local SQLite database. No retention schedule, encryption at rest, access audit, or production deletion process is implemented.
