# Gorzdrav SPb Referral Booking Bot

Telegram bot for monitoring Gorzdrav SPb referral appointments and booking selected or automatically matched slots.

## Features

- Stores all user medical settings in PostgreSQL.
- Supports multiple referrals per Telegram user.
- Selects doctors only from the referral data returned by Gorzdrav.
- Booking modes:
  - `notify_only`: notify and let the user choose a slot.
  - `auto_first`: book the first available slot.
  - `auto_window`: book the first slot inside a daily or exact date/time window.
- Appointment creation retries transient Gorzdrav failures up to 6 total attempts.

## Run

```bash
cp .env.example .env
# edit BOT_TOKEN and POSTGRES_PASSWORD
docker compose up --build
```

## Bot Commands

- `/start` - create a profile.
- `/set_referral` - add referral number and last name.
- `/booking_mode` - choose booking mode for a referral.
- `/time_window` - set or clear a window for `auto_window`.
- `/referral_status` or `/status` - show current referrals.
- `/on` / `/off` - enable or disable monitoring for a referral.
- `/delete` - delete profile and referrals.

## Tests

```bash
python -m pytest
```
