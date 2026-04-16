"""
Alert Service
--------------
Sends notifications via email (SMTP) and Telegram when trading events
occur, such as trade executions, drawdown breaches, or profit targets.
"""

import json
import logging
import smtplib
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Database helpers for alert config
# ──────────────────────────────────────────────

_CREATE_ALERT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS alert_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    channel         TEXT NOT NULL,
    enabled         INTEGER NOT NULL DEFAULT 1,
    threshold_json  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""


def _init_alert_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_CREATE_ALERT_TABLE_SQL)
    conn.commit()
    conn.close()


def _load_alert_configs(
    db_path: str, event_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Load alert configurations from the database.

    Parameters
    ----------
    db_path:
        Path to the SQLite database.
    event_type:
        If provided, only return configs matching this event type.

    Returns
    -------
    list[dict]
        Each dict has keys: ``id``, ``event_type``, ``channel``,
        ``enabled``, ``thresholds``.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if event_type:
        rows = conn.execute(
            "SELECT * FROM alert_config WHERE event_type = ? AND enabled = 1",
            (event_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM alert_config WHERE enabled = 1"
        ).fetchall()
    conn.close()

    configs = []
    for row in rows:
        d = dict(row)
        thresholds = {}
        if d.get("threshold_json"):
            try:
                thresholds = json.loads(d["threshold_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        d["thresholds"] = thresholds
        configs.append(d)
    return configs


# ──────────────────────────────────────────────
#  Alert Service
# ──────────────────────────────────────────────

class AlertService:
    """Sends alerts via email and Telegram based on trading events.

    Parameters
    ----------
    db_path:
        SQLite database path for reading ``alert_config`` rows.
    smtp_host, smtp_port, smtp_user, smtp_password, email_from:
        SMTP server settings for email delivery.
    telegram_bot_token, telegram_chat_id:
        Telegram Bot API credentials.
    """

    def __init__(
        self,
        db_path: str = "./data/trading.db",
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        email_from: str = "",
        telegram_bot_token: str = "",
        telegram_chat_id: str = "",
    ) -> None:
        self.db_path = db_path
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.email_from = email_from
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id

        _init_alert_db(db_path)

    # -- Email ------------------------------------------------------------

    def send_email(
        self,
        subject: str,
        body: str,
        to_address: str,
        html: bool = False,
    ) -> bool:
        """Send an email via SMTP.

        Parameters
        ----------
        subject:
            Email subject line.
        body:
            Plain-text (or HTML if *html* is True) email body.
        to_address:
            Recipient email address.
        html:
            If ``True`` the body is sent as ``text/html``.

        Returns
        -------
        bool
            ``True`` if the email was sent successfully.
        """
        if not self.smtp_host or not to_address:
            logger.warning("Email not configured; skipping send.")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.email_from or self.smtp_user
            msg["To"] = to_address

            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(
                    msg["From"], [to_address], msg.as_string()
                )

            logger.info("Email sent to %s: %s", to_address, subject)
            return True

        except Exception:
            logger.exception("Failed to send email to %s", to_address)
            return False

    # -- Telegram ---------------------------------------------------------

    def send_telegram(
        self,
        message: str,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> bool:
        """Send a message via the Telegram Bot API.

        Parameters
        ----------
        message:
            The text to send (supports Telegram MarkdownV2).
        bot_token:
            Override the instance-level token.
        chat_id:
            Override the instance-level chat ID.

        Returns
        -------
        bool
            ``True`` if the message was sent successfully.
        """
        token = bot_token or self.telegram_bot_token
        cid = chat_id or self.telegram_chat_id

        if not token or not cid:
            logger.warning("Telegram not configured; skipping send.")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": cid,
            "text": message,
            "parse_mode": "HTML",
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram message sent to chat %s", cid)
                return True
            else:
                logger.warning(
                    "Telegram API returned %s: %s",
                    resp.status_code,
                    resp.text,
                )
                return False
        except Exception:
            logger.exception("Failed to send Telegram message")
            return False

    # -- Event-driven alerting --------------------------------------------

    def check_and_alert(
        self,
        event_type: str,
        data: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Check whether an event should trigger alerts and send them.

        Parameters
        ----------
        event_type:
            One of ``"trade_executed"``, ``"drawdown_exceeded"``,
            ``"profit_target_reached"``.
        data:
            Event payload (e.g. trade details, drawdown percentage).
        config:
            Optional override config dict with keys ``email_to``,
            ``telegram_bot_token``, ``telegram_chat_id``.  If ``None``
            alert configs are loaded from the database.

        Returns
        -------
        list[str]
            Channels that were successfully notified.
        """
        notified: List[str] = []

        # Build the alert message
        subject, body = self._format_alert(event_type, data)
        if not subject:
            return notified

        # Determine which channels to use
        channels = self._resolve_channels(event_type, data, config)

        for channel_info in channels:
            channel = channel_info.get("channel", "")

            if channel == "email":
                to_addr = channel_info.get(
                    "email_to", config.get("email_to", "") if config else ""
                )
                if self.send_email(subject, body, to_addr):
                    notified.append("email")

            elif channel == "telegram":
                token = channel_info.get(
                    "telegram_bot_token",
                    config.get("telegram_bot_token", "") if config else "",
                )
                cid = channel_info.get(
                    "telegram_chat_id",
                    config.get("telegram_chat_id", "") if config else "",
                )
                if self.send_telegram(body, bot_token=token, chat_id=cid):
                    notified.append("telegram")

        return notified

    # -- Internal helpers -------------------------------------------------

    def _format_alert(
        self, event_type: str, data: Dict[str, Any]
    ) -> Tuple[str, str]:
        """Return (subject, body) for the given event."""

        if event_type == "trade_executed":
            trade = data.get("trade", data)
            side = trade.get("side", "?").upper()
            symbol = data.get("symbol", data.get("bot_id", ""))
            price = trade.get("price", 0)
            amount = trade.get("amount", 0)
            profit = trade.get("profit")

            subject = f"Trade Executed: {side} {symbol}"
            lines = [
                f"<b>Trade Executed</b>",
                f"Bot: {data.get('bot_id', 'N/A')}",
                f"Side: {side}",
                f"Price: {price:.4f}",
                f"Amount: {amount:.6f}",
            ]
            if profit is not None:
                lines.append(f"Profit: ${profit:.4f}")
            body = "\n".join(lines)
            return subject, body

        elif event_type == "drawdown_exceeded":
            dd_pct = data.get("drawdown_pct", 0)
            threshold = data.get("threshold_pct", 0)
            bot_id = data.get("bot_id", "N/A")

            subject = f"Drawdown Alert: {dd_pct:.2f}% on {bot_id}"
            body = (
                f"<b>Drawdown Exceeded</b>\n"
                f"Bot: {bot_id}\n"
                f"Current drawdown: {dd_pct:.2f}%\n"
                f"Threshold: {threshold:.2f}%"
            )
            return subject, body

        elif event_type == "profit_target_reached":
            profit_pct = data.get("profit_pct", 0)
            target_pct = data.get("target_pct", 0)
            bot_id = data.get("bot_id", "N/A")

            subject = f"Profit Target Reached: {profit_pct:.2f}% on {bot_id}"
            body = (
                f"<b>Profit Target Reached</b>\n"
                f"Bot: {bot_id}\n"
                f"Current profit: {profit_pct:.2f}%\n"
                f"Target: {target_pct:.2f}%"
            )
            return subject, body

        else:
            logger.warning("Unknown event type: %s", event_type)
            return "", ""

    def _resolve_channels(
        self,
        event_type: str,
        data: Dict[str, Any],
        config: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Determine which channels should be alerted.

        If an explicit *config* is provided, use it directly.
        Otherwise load enabled alert configs from the database and
        evaluate any threshold conditions.
        """
        if config is not None:
            # Caller provided explicit config
            channels = []
            if config.get("email_to"):
                channels.append({"channel": "email", "email_to": config["email_to"]})
            if config.get("telegram_bot_token") or self.telegram_bot_token:
                channels.append({
                    "channel": "telegram",
                    "telegram_bot_token": config.get(
                        "telegram_bot_token", self.telegram_bot_token
                    ),
                    "telegram_chat_id": config.get(
                        "telegram_chat_id", self.telegram_chat_id
                    ),
                })
            return channels

        # Load from DB
        db_configs = _load_alert_configs(self.db_path, event_type)
        channels = []

        for cfg in db_configs:
            thresholds = cfg.get("thresholds", {})

            # Evaluate thresholds
            if event_type == "drawdown_exceeded":
                min_dd = thresholds.get("min_drawdown_pct", 0)
                if data.get("drawdown_pct", 0) < min_dd:
                    continue

            elif event_type == "profit_target_reached":
                min_profit = thresholds.get("min_profit_pct", 0)
                if data.get("profit_pct", 0) < min_profit:
                    continue

            channel = cfg.get("channel", "")
            entry: Dict[str, Any] = {"channel": channel}

            if channel == "email":
                entry["email_to"] = thresholds.get("email_to", "")
            elif channel == "telegram":
                entry["telegram_bot_token"] = thresholds.get(
                    "telegram_bot_token", self.telegram_bot_token
                )
                entry["telegram_chat_id"] = thresholds.get(
                    "telegram_chat_id", self.telegram_chat_id
                )

            channels.append(entry)

        return channels
