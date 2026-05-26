# Referral Auto Booking Bot Design

## Context

The current repository is empty except for the initial git metadata. The bot will be based on `cucumberian/gorzdrav_spb_checkbot`, updated for the current Gorzdrav SPb API behavior and extended with referral-based booking.

The Gorzdrav public frontend currently uses these API routes:

- `GET /_api/api/v2/referral/{referralId}?lastName={lastName}` to load referral data, patient data, specialities, doctors, and available appointments.
- `POST /_api/api/v2/appointment/create` to create an appointment.
- Existing free-schedule monitoring still uses `/v2/schedule/lpu/{lpuId}/speciality/{specialtyId}/doctors` and `/v2/schedule/lpu/{lpuId}/doctor/{doctorId}/appointments`.

## Goals

Build a Telegram bot that:

- Monitors appointments for a selected doctor.
- Lets the user enter all medical and booking information inside Telegram.
- Supports referral booking by referral number and last name.
- Can either notify only, book the user-selected appointment, or auto-book according to user settings.
- Runs through Docker Compose with PostgreSQL.

## Configuration

The `.env` file is only for infrastructure and secrets:

- `BOT_TOKEN`
- PostgreSQL connection settings, either as `DATABASE_URL` or `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.
- Optional operational defaults such as poll interval and log level may have built-in code defaults and should not require user setup.

The user enters referral number, last name, doctor choice, booking mode, and time window in the bot. These values are stored in PostgreSQL.

## User Flows

### Profile

The user starts the bot with `/start`. The bot creates or loads a profile and guides the user through:

- Selecting a doctor for monitoring, using the district -> LPU -> speciality -> doctor flow from the original bot.
- Adding referral booking data: referral number and last name.
- Choosing booking mode.

### Booking Modes

The user can choose one of three modes:

1. `notify_only`
   - The bot always monitors.
   - When appointments appear, it sends a Telegram message with available slots.
   - Each slot has an inline button.
   - The bot books only after the user selects a specific slot.

2. `auto_first`
   - The bot always monitors.
   - When appointments appear, it immediately attempts to book the first available appointment for the configured doctor and referral.
   - After successful booking, monitoring for that referral is disabled.

3. `auto_window`
   - The bot always monitors.
   - The user sets a time window, for example `19:00-21:00`.
   - When appointments appear, the bot ignores slots outside the window and books the earliest slot inside the window.
   - If slots are available but none match the window, the bot notifies the user and continues monitoring.
   - After successful booking, monitoring for that referral is disabled.

### Retry Behavior

Gorzdrav often returns transient errors during high load. Booking attempts must be resilient:

- One booking operation performs up to 6 total attempts: the first attempt plus 5 retries.
- Retries happen only for transient failures: HTTP 429, 5xx, timeouts, connection errors, or Gorzdrav responses that look like temporary backend/MIS failures.
- Retries use short delays with jitter, for example 1s, 2s, 3s, 5s, 8s.
- Non-retryable failures stop immediately: invalid referral, no matching patient/referral, already booked, appointment already taken, or validation errors.
- Every attempt is logged and the final outcome is sent to the user.

## Gorzdrav API Layer

Create a dedicated API client with:

- Request timeout.
- Shared headers.
- Structured parsing of `success`, `errorCode`, `message`, and `result`.
- Typed methods for districts, LPUs, specialities, doctors, appointments, referral lookup, and appointment creation.
- Explicit exception classes for transient, validation, not found, and conflict cases.

The referral lookup result is the source of truth for referral-specific booking. It contains LPU, patient, speciality, doctor, and appointments. The bot should prefer this data for referral booking instead of mixing unrelated free-schedule data.

## Data Model

PostgreSQL stores:

- Telegram users.
- Selected monitoring doctor.
- Referral settings:
  - referral number normalized without hyphens;
  - last name;
  - booking mode;
  - optional start/end time window;
  - active flag;
  - last known status;
  - created/updated timestamps.
- Appointment candidates already notified to avoid duplicate spam.
- Booking attempts:
  - user id;
  - referral id;
  - appointment id;
  - attempt number;
  - status;
  - error code/message;
  - timestamp.

The schema should be migration-friendly. If the existing project does not have migrations, add a small startup migrator that creates required tables idempotently.

## Scheduler

The scheduler periodically loads active referral monitors and checks Gorzdrav.

For each active referral monitor:

1. Fetch referral info by referral number and last name.
2. Find the configured doctor in the referral's doctors list.
3. Collect appointment candidates for that doctor.
4. Apply mode:
   - `notify_only`: send available slots with inline booking buttons.
   - `auto_first`: choose the earliest candidate.
   - `auto_window`: choose the earliest candidate inside the time window.
5. If a slot is selected for booking, call appointment create with retry behavior.
6. On success, notify the user and deactivate the monitor.
7. On retryable failure after all attempts, notify the user and keep monitoring.
8. On permanent failure, notify the user and deactivate or pause the monitor depending on the error.

## Telegram Commands

Keep and update existing commands:

- `/start`
- `/help`
- `/status`
- `/on`
- `/off`
- `/set_doctor`
- `/delete`

Add:

- `/set_referral` to enter referral number and last name.
- `/booking_mode` to choose `notify_only`, `auto_first`, or `auto_window`.
- `/time_window` to set or clear the booking window.
- `/referral_status` to show current referral settings and last check result.

Inline buttons are used for selecting booking mode, selecting appointments, confirming manual booking, and canceling a monitor.

## Safety Rules

- Auto-booking must only happen when the user explicitly selected an auto mode.
- The bot must show the active mode in `/status` and after every mode change.
- A successful booking disables further auto-booking for that referral.
- Manual booking buttons must include enough context to avoid booking the wrong slot: date, time, doctor, room if available.
- The bot must not store Telegram messages containing secrets.

## Docker

Provide:

- `Dockerfile` for the bot.
- `docker-compose.yml` with bot and PostgreSQL services.
- `.env.example` with bot token and PostgreSQL variables.

The bot service waits for PostgreSQL readiness before startup or handles startup retries internally.

## Testing

Use test-first implementation for new behavior:

- Endpoint construction tests.
- API parsing tests for referral lookup and appointment creation.
- Retry policy tests: success after retry, permanent error stops, six attempts max.
- Slot-selection tests for `notify_only`, `auto_first`, and `auto_window`.
- PostgreSQL repository tests, preferably with a test database or isolated container.
- Telegram handler tests for state transitions where practical.

Network calls to Gorzdrav must not run in unit tests. Use fixtures based on observed response shapes.

## Non-Goals

- No ESIA authentication flow.
- No storage of full medical documents.
- No automatic booking for any doctor other than the configured doctor/referral combination.
- No web UI.
