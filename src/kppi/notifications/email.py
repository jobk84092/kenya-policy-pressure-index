"""
Email notification for KPPI weekly summaries.

Sends an HTML email via SMTP (default: Gmail SMTP with STARTTLS).

Configuration (via .env or environment variables)
--------------------------------------------------
  EMAIL_ENABLED=true
  EMAIL_TO=you@gmail.com
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=your-gmail@gmail.com
  SMTP_PASSWORD=your-app-password   # Gmail App Password, not login password

Gmail App Password setup
------------------------
  1. Go to https://myaccount.google.com/security
  2. Enable 2-Step Verification (required)
  3. Go to https://myaccount.google.com/apppasswords
  4. Create an app password for "Mail" and paste it as SMTP_PASSWORD
"""
from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from loguru import logger

from kppi.config import settings
from kppi.index.calculator import KPPIResult

# ── Tier colour map (HTML) ────────────────────────────────────────────────────

_TIER_COLOURS = {
    "Low":      "#2e7d32",   # dark green
    "Moderate": "#f57f17",   # amber
    "High":     "#e65100",   # deep orange
    "Severe":   "#b71c1c",   # dark red
    "Crisis":   "#880e4f",   # deep purple/red
}

_TIER_BG = {
    "Low":      "#e8f5e9",
    "Moderate": "#fff8e1",
    "High":     "#fbe9e7",
    "Severe":   "#ffebee",
    "Crisis":   "#fce4ec",
}


# ── HTML template ─────────────────────────────────────────────────────────────

def _build_html(result: KPPIResult) -> str:
    tier_colour = _TIER_COLOURS.get(result.tier, "#333333")
    tier_bg     = _TIER_BG.get(result.tier, "#f5f5f5")
    now_str     = datetime.now(timezone.utc).strftime("%A, %d %B %Y")

    def score_bar(score: float) -> str:
        """Tiny inline progress bar."""
        pct = min(100, max(0, score))
        colour = "#2e7d32" if pct < 30 else "#f57f17" if pct < 50 else "#e65100" if pct < 70 else "#b71c1c"
        return (
            f'<div style="background:#e0e0e0;border-radius:4px;height:8px;width:160px;display:inline-block;vertical-align:middle;">'
            f'<div style="background:{colour};width:{pct:.0f}%;height:8px;border-radius:4px;"></div></div>'
            f' <span style="font-size:12px;color:#555;">{score:.1f}</span>'
        )

    rows = [
        ("Inflation",             result.components.inflation,       result.raw_inflation,       "%",      "World Bank"),
        ("FX Rate (KES/USD)",     result.components.fx_rate,         result.raw_fx_rate,         "KES/USD","ExchangeRate API"),
        ("Bond Yield (91d)",      result.components.bond_yield,      result.raw_bond_yield,      "%",      "CBK"),
        ("Market Stress (NASI)",  result.components.market_stress,   result.raw_market_stress,   "pts",    "nseinsider.co.ke"),
        ("Political (live)",      result.components.political,       result.raw_political,       "score",  "Google News RSS"),
        ("Forex Reserves",        result.components.forex_reserves,  result.raw_forex_reserves,  "mo impt","CBK"),
        ("Eurobond Spread",       result.components.eurobond_spread, result.raw_eurobond_spread, "pp",     "US Treasury + WGB"),
        ("M-Pesa Volume (YoY)",   result.components.mpesa_volume,    result.raw_mpesa_volume,    "% YoY",  "CBK Payments"),
    ]

    # Add 4-week smoothed political row when available
    pol_smoothed_row = ""
    if result.political_smoothed is not None:
        from kppi.index.normalizer import normalise_political
        smooth_score = normalise_political(result.political_smoothed)
        pol_smoothed_row = f"""
        <tr style="border-bottom:1px solid #eeeeee;background:#fafafa;">
          <td style="padding:10px 12px;font-size:14px;color:#333;">&#8627; Political (4-wk avg)</td>
          <td style="padding:10px 12px;">{score_bar(smooth_score)}</td>
          <td style="padding:10px 12px;font-size:13px;color:#888;">{result.political_smoothed:.1f} score</td>
          <td style="padding:10px 12px;font-size:12px;color:#999;">4-week MA</td>
        </tr>"""

    table_rows = ""
    for label, score, raw, unit, source in rows:
        raw_str = f"{raw:.2f} {unit}" if raw is not None else "n/a"
        table_rows += f"""
        <tr style="border-bottom:1px solid #eeeeee;">
          <td style="padding:10px 12px;font-size:14px;color:#333;">{label}</td>
          <td style="padding:10px 12px;">{score_bar(score)}</td>
          <td style="padding:10px 12px;font-size:13px;color:#666;">{raw_str}</td>
          <td style="padding:10px 12px;font-size:12px;color:#999;">{source}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:#1a237e;padding:28px 32px;">
            <p style="margin:0;font-size:11px;color:#9fa8da;letter-spacing:2px;text-transform:uppercase;">Weekly Report &bull; {now_str}</p>
            <h1 style="margin:6px 0 0;font-size:22px;color:#ffffff;font-weight:700;">
              Kenya Policy Pressure Index
            </h1>
          </td>
        </tr>

        <!-- Score banner -->
        <tr>
          <td style="background:{tier_bg};padding:24px 32px;text-align:center;border-bottom:3px solid {tier_colour};">
            <p style="margin:0;font-size:48px;font-weight:800;color:{tier_colour};line-height:1;">
              {result.composite_score:.1f}
              <span style="font-size:20px;font-weight:400;color:#666;">&thinsp;/ 100</span>
            </p>
            <p style="margin:10px 0 0;font-size:18px;font-weight:600;color:{tier_colour};">
              {result.tier_emoji}&ensp;{result.tier}
            </p>
            <p style="margin:6px 0 0;font-size:14px;color:#555;">{result.tier_description}</p>
            <p style="margin:10px 0 0;font-size:13px;color:#333;">
              Data confidence: <strong>{result.confidence_score:.0f}% ({result.confidence_label})</strong>
            </p>
            <p style="margin:4px 0 0;font-size:12px;color:#777;">{result.confidence_notes}</p>
          </td>
        </tr>

        <!-- Component table -->
        <tr>
          <td style="padding:24px 32px 8px;">
            <h2 style="margin:0 0 14px;font-size:14px;font-weight:700;color:#333;text-transform:uppercase;letter-spacing:1px;">Component Breakdown</h2>
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
              <thead>
                <tr style="background:#f5f5f5;">
                  <th style="padding:8px 12px;text-align:left;font-size:12px;color:#777;font-weight:600;">Indicator</th>
                  <th style="padding:8px 12px;text-align:left;font-size:12px;color:#777;font-weight:600;">Pressure Score</th>
                  <th style="padding:8px 12px;text-align:left;font-size:12px;color:#777;font-weight:600;">Raw Value</th>
                  <th style="padding:8px 12px;text-align:left;font-size:12px;color:#777;font-weight:600;">Source</th>
                </tr>
              </thead>
              <tbody>{table_rows}
              {pol_smoothed_row}
              </tbody>
            </table>
          </td>
        </tr>

        <!-- Scale legend -->
        <tr>
          <td style="padding:16px 32px 24px;">
            <p style="margin:0 0 8px;font-size:12px;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:1px;">Pressure Scale</p>
            <table cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:3px 10px 3px 0;font-size:12px;color:#2e7d32;">&#9632; 0–30 Low</td>
                <td style="padding:3px 10px 3px 0;font-size:12px;color:#f57f17;">&#9632; 30–50 Moderate</td>
                <td style="padding:3px 10px 3px 0;font-size:12px;color:#e65100;">&#9632; 50–70 High</td>
                <td style="padding:3px 10px 3px 0;font-size:12px;color:#b71c1c;">&#9632; 70–85 Severe</td>
                <td style="padding:3px 0;font-size:12px;color:#880e4f;">&#9632; 85+ Crisis</td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f5f5f5;padding:16px 32px;border-top:1px solid #e0e0e0;">
            <p style="margin:0;font-size:11px;color:#aaa;">
              Generated by KPPI v2 &bull; Data sources: World Bank, CBK, ExchangeRate API, NSE Insider, GDELT
              &bull; Scores indicate pressure (0 = calm, 100 = crisis)
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ── Plain-text fallback ───────────────────────────────────────────────────────

def _build_text(result: KPPIResult) -> str:
    now_str = datetime.now(timezone.utc).strftime("%A, %d %B %Y")
    return f"""Kenya Policy Pressure Index (KPPI) – Weekly Report
{now_str}
{'=' * 50}

Composite Score : {result.composite_score:.1f} / 100
Tier            : {result.tier_emoji} {result.tier}
                  {result.tier_description}
Confidence      : {result.confidence_score:.0f}% ({result.confidence_label})
                  {result.confidence_notes}

Component Scores (0 = calm, 100 = crisis)
------------------------------------------
  Inflation          : {result.components.inflation:.1f}  (raw: {f"{result.raw_inflation:.2f}%" if result.raw_inflation is not None else "n/a"})
  FX Rate (KES/USD)  : {result.components.fx_rate:.1f}  (raw: {f"{result.raw_fx_rate:.2f}" if result.raw_fx_rate is not None else "n/a"})
  Bond Yield (91d)   : {result.components.bond_yield:.1f}  (raw: {f"{result.raw_bond_yield:.2f}%" if result.raw_bond_yield is not None else "n/a"})
  Market Stress NASI : {result.components.market_stress:.1f}  (raw: {f"{result.raw_market_stress:.2f} pts" if result.raw_market_stress is not None else "n/a"})
  Political (live)   : {result.components.political:.1f}  (raw: {f"{result.raw_political:.2f} score" if result.raw_political is not None else "n/a"})
{f'  Political (4-wk MA): {result.political_smoothed:.1f}' if result.political_smoothed is not None else ''}\
  Forex Reserves     : {result.components.forex_reserves:.1f}  (raw: {f"{result.raw_forex_reserves:.2f} months import cover" if result.raw_forex_reserves is not None else "n/a"})
  Eurobond Spread    : {result.components.eurobond_spread:.1f}  (raw: {f"{result.raw_eurobond_spread:.2f} pp vs US 10yr" if result.raw_eurobond_spread is not None else "n/a"})
  M-Pesa Vol (YoY)   : {result.components.mpesa_volume:.1f}  (raw: {f"{result.raw_mpesa_volume:+.1f}% YoY" if result.raw_mpesa_volume is not None else "n/a"})

Scale: 0–30 Low | 30–50 Moderate | 50–70 High | 70–85 Severe | 85+ Crisis

Generated by KPPI v2
"""


# ── Public send function ──────────────────────────────────────────────────────

def send_kppi_email(result: KPPIResult) -> None:
    """
    Send an HTML weekly summary email for `result`.

    Does nothing (and logs a debug message) if EMAIL_ENABLED is False
    or SMTP credentials are not configured.
    """
    if not settings.email_enabled:
        logger.debug("Email notifications disabled (EMAIL_ENABLED=false)")
        return

    missing = [
        name for name, val in (
            ("EMAIL_TO",       settings.email_to),
            ("SMTP_USER",      settings.smtp_user),
            ("SMTP_PASSWORD",  settings.smtp_password),
        )
        if not val
    ]
    if missing:
        logger.warning("Email skipped – missing config: {}", ", ".join(missing))
        return

    subject = (
        f"KPPI Weekly: {result.tier_emoji} {result.tier} "
        f"({result.composite_score:.1f}/100) – "
        f"{datetime.now(timezone.utc).strftime('%d %b %Y')}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"KPPI Monitor <{settings.smtp_user}>"
    msg["To"]      = settings.email_to

    msg.attach(MIMEText(_build_text(result), "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(result), "html",  "utf-8"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_user, settings.email_to, msg.as_bytes())
        logger.success("KPPI email sent to {}", settings.email_to)
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "SMTP auth failed for {}. "
            "Make sure SMTP_PASSWORD is a Gmail App Password, not your login password. "
            "See: https://myaccount.google.com/apppasswords",
            settings.smtp_user,
        )
    except Exception as exc:
        logger.error("Failed to send KPPI email: {}", exc)
