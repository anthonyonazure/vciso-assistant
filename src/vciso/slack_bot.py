"""Slack bot endpoint — interactive vCISO Q&A.

Receives Slack Events API events at /slack/events. On app_mention or DM,
runs answer_question() and replies in-thread. Signature is verified via
the Slack signing secret.

Run:  vciso slack-bot
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Request

from vciso.qa import answer_question

log = structlog.get_logger()
app = FastAPI(title="vCISO Slack endpoint", version="0.1.0")


def _verify_signature(body: bytes, ts: str, sig: str) -> bool:
    secret = os.environ.get("VCISO_SLACK_SIGNING_SECRET", "")
    if not secret:
        log.warning("vciso.slack.no_signing_secret")
        return False
    # Drop replay attempts (>5 min)
    try:
        if abs(int(ts) - int(time.time())) > 300:
            return False
    except ValueError:
        return False
    base = f"v0:{ts}:".encode() + body
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


async def _post(channel: str, thread_ts: str | None, text: str) -> None:
    token = os.environ.get("VCISO_SLACK_BOT_TOKEN", "")
    if not token:
        log.warning("vciso.slack.no_bot_token")
        return
    body = {"channel": channel, "text": text}
    if thread_ts:
        body["thread_ts"] = thread_ts
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    log.info("vciso.slack.posted", channel=channel, ok=r.json().get("ok"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/slack/events")
async def events(req: Request):
    body = await req.body()
    ts = req.headers.get("X-Slack-Request-Timestamp", "")
    sig = req.headers.get("X-Slack-Signature", "")
    # Allow unsigned in dev (token absent); reject in prod
    if os.environ.get("VCISO_SLACK_SIGNING_SECRET") and not _verify_signature(
        body, ts, sig
    ):
        raise HTTPException(401, "bad signature")

    payload = await req.json()
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    event = payload.get("event") or {}
    if (
        event.get("type") in ("app_mention", "message")
        and event.get("user")
        and event.get("bot_id") is None
    ):
        text = event.get("text", "")
        # Strip leading mention if present
        if "<@" in text:
            text = text.split(">", 1)[-1].strip()
        ans = await answer_question(text)
        formatted = (
            f"{ans['answer']}\n\n"
            f"_Citations: {', '.join(ans.get('kb_citations', []) or ['(none)'])}_"
            + (
                f"  ·  open risks: {', '.join(ans['risk_citations'])}"
                if ans.get("risk_citations")
                else ""
            )
            + (
                f"\n_Confidence: {ans['confidence']:.2f}_"
                if "confidence" in ans
                else ""
            )
        )
        await _post(event["channel"], event.get("ts"), formatted)
    return {"ok": True}
