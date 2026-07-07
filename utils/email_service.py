"""
Email Service - transaction alert mails over SMTP.

Sends a real email to the user's registered address whenever money moves
on their account (debit or credit). Sending happens on a daemon thread so
a slow SMTP server can never delay or fail a transaction — email is a
notification, not part of the transaction itself.

Configuration lives in config.py (SMTP_* values, read from .env).
"""

import smtplib
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config
from utils.logger import logger


def _format_inr(amount: float) -> str:
    return f"₹{amount:,.2f}"


def _build_transaction_html(name: str, txn_type: str, direction: str,
                            amount: float, balance: float,
                            account_number: str, category: str,
                            counterparty: str = None) -> str:
    """Dark-themed HTML matching the SmartBank web app styling."""
    is_credit = direction == "credit"
    color = "#00D4AA" if is_credit else "#FF5470"
    sign = "+" if is_credit else "−"
    verb = "credited to" if is_credit else "debited from"
    masked = f"XXXX XXXX {account_number[-4:]}" if account_number else "your account"
    when = datetime.now().strftime("%d %b %Y, %I:%M %p")
    counterparty_row = ""
    if counterparty:
        counterparty_row = f"""
            <tr>
              <td style="padding:6px 0;color:#8A94A8;">Counterparty</td>
              <td style="padding:6px 0;color:#E8EDF4;text-align:right;">A/c ending {counterparty[-4:]}</td>
            </tr>"""

    return f"""
    <div style="background:#0B1020;padding:32px 16px;font-family:'Segoe UI',Arial,sans-serif;">
      <div style="max-width:520px;margin:0 auto;background:#161C30;border:1px solid #2A3A5C;
                  border-radius:14px;overflow:hidden;">
        <div style="padding:20px 28px;border-bottom:1px solid #2A3A5C;">
          <span style="font-size:19px;font-weight:800;color:#00D4AA;">&#127974; SmartBank</span>
        </div>
        <div style="padding:28px;">
          <p style="color:#E8EDF4;margin:0 0 6px;">Hi {name},</p>
          <p style="color:#8A94A8;margin:0 0 22px;font-size:14px;">
            {_format_inr(amount)} was {verb} account {masked}.
          </p>
          <div style="text-align:center;padding:18px;background:#0B1020;border-radius:10px;
                      margin-bottom:22px;">
            <div style="font-size:32px;font-weight:800;color:{color};">
              {sign} {_format_inr(amount)}
            </div>
            <div style="color:#8A94A8;font-size:12px;text-transform:uppercase;
                        letter-spacing:1px;margin-top:4px;">{txn_type.replace('_', ' ')}</div>
          </div>
          <table style="width:100%;font-size:13px;border-collapse:collapse;">
            <tr>
              <td style="padding:6px 0;color:#8A94A8;">Account</td>
              <td style="padding:6px 0;color:#E8EDF4;text-align:right;">{masked}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#8A94A8;">Category</td>
              <td style="padding:6px 0;color:#E8EDF4;text-align:right;">{category}</td>
            </tr>{counterparty_row}
            <tr>
              <td style="padding:6px 0;color:#8A94A8;">Date &amp; Time</td>
              <td style="padding:6px 0;color:#E8EDF4;text-align:right;">{when}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#8A94A8;border-top:1px solid #2A3A5C;">Available Balance</td>
              <td style="padding:6px 0;color:#00D4AA;font-weight:700;text-align:right;
                         border-top:1px solid #2A3A5C;">{_format_inr(balance)}</td>
            </tr>
          </table>
        </div>
        <div style="padding:16px 28px;border-top:1px solid #2A3A5C;">
          <p style="color:#8A94A8;font-size:11px;margin:0;">
            If you did not authorize this transaction, contact SmartBank support immediately.
            This is an automated alert &mdash; please do not reply.
          </p>
        </div>
      </div>
    </div>"""


def _send(to_address: str, subject: str, html_body: str):
    """Blocking SMTP send — always called from a daemon thread."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config.EMAIL_FROM_NAME} <{config.SMTP_USER}>"
        msg["To"] = to_address
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, [to_address], msg.as_string())
        logger.success(f"Transaction email sent to {to_address}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_address}: {e}")


def send_transaction_email(user: dict, txn_type: str, direction: str,
                           amount: float, balance: float,
                           account_number: str, category: str = "Other",
                           counterparty: str = None):
    """
    Fire-and-forget transaction alert.

    Args:
        user: user record (needs `name` and `email`)
        txn_type: deposit / withdraw / transfer_out / transfer_in
        direction: "credit" or "debit" (decides color and +/- sign)
        amount, balance: transaction amount and post-transaction balance
        account_number: user's own account number (masked in the mail)
        category: transaction category label
        counterparty: other account number for transfers (optional)
    """
    if not config.EMAIL_ENABLED:
        return
    email = (user or {}).get("email")
    if not email:
        logger.info(f"No email on file for {(user or {}).get('user_id', '?')} — alert skipped")
        return
    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        logger.warning("SMTP_USER/SMTP_PASSWORD not configured — "
                       f"email to {email} skipped (set them in .env)")
        return

    action = "credited" if direction == "credit" else "debited"
    subject = f"SmartBank Alert: {_format_inr(amount)} {action}"
    html = _build_transaction_html(
        user.get("name", "Customer"), txn_type, direction, amount,
        balance, account_number, category, counterparty
    )
    threading.Thread(
        target=_send, args=(email, subject, html),
        daemon=True, name="txn-email"
    ).start()
