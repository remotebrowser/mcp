import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastmcp import Context, FastMCP

# Create a generic calendar MCP
calendar_mcp = FastMCP[Context](name="Calendar MCP")


def escape_ics_text(value: str) -> str:
    """Escape text per RFC 5545 for TEXT values."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


# Supported input formats for the event_date parameter
DATE_FORMATS: list[str] = [
    "%B %d, %Y",  # Month DD, YYYY
    "%Y-%m-%d",  # YYYY-MM-DD
    "%Y-%m-%d %H:%M",  # YYYY-MM-DD HH:MM
    "%m/%d/%Y",  # MM/DD/YYYY
    "%d/%m/%Y",  # DD/MM/YYYY
]


def parse_event_date(event_date: str) -> tuple[datetime, bool]:
    """Parse an event date string into a datetime and whether it includes a time."""
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(event_date, fmt)
            return parsed, ("%H:%M" in fmt)
        except ValueError:
            continue
    raise ValueError(
        "Invalid date format. Supported formats: 'Month DD, YYYY', 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM', 'MM/DD/YYYY'"
    )


def localize_event_datetime(event_dt: datetime, has_time: bool, event_timezone: str) -> datetime:
    """Apply timezone to event datetime. For all-day events, keep date-only (naive)."""
    try:
        tz = ZoneInfo(event_timezone)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid event timezone: {event_timezone}") from exc

    if has_time:
        return event_dt.replace(tzinfo=tz)
    return event_dt.replace(tzinfo=None)


def compute_reminder_date(event_dt: datetime, reminder_days_before: int) -> datetime:
    """Compute the reminder date as event date minus the provided number of days.

    If the event is timezone-aware (timed event), normalize to a naive date first so the
    subtraction is date-based, not timezone-based.
    """
    base = event_dt.replace(tzinfo=None) if event_dt.tzinfo else event_dt
    return base - timedelta(days=reminder_days_before)


def format_dt_lines(event_dt: datetime, has_time: bool) -> tuple[str, str]:
    """Return DTSTART/DTEND lines for ICS given an event datetime and whether it has time."""
    if has_time and event_dt.tzinfo:
        start = event_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        end = (event_dt + timedelta(hours=1)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"DTSTART:{start}", f"DTEND:{end}"
    if has_time:
        start = event_dt.strftime("%Y%m%dT%H%M%S")
        end = (event_dt + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
        return f"DTSTART:{start}", f"DTEND:{end}"

    date_only = event_dt.strftime("%Y%m%d")
    return f"DTSTART;VALUE=DATE:{date_only}", f"DTEND;VALUE=DATE:{date_only}"


def compute_alarm_trigger_line(
    event_dt: datetime,
    reminder_days_before: int,
    reminder_time: str | None,
    reminder_timezone: str,
) -> str:
    """Compute the VALARM TRIGGER line for ICS.

    Defaults to a relative trigger (e.g., -P1D). If reminder_time and reminder_timezone are
    provided and valid, uses an absolute UTC timestamp trigger at the specified local time on
    (event_date - reminder_days_before).
    """
    trigger_line = f"TRIGGER:-P{max(0, int(reminder_days_before))}D"

    if reminder_time and reminder_timezone:
        try:
            time_dt = datetime.strptime(reminder_time, "%H:%M")
            reminder_tz = ZoneInfo(reminder_timezone)

            base_date = event_dt.replace(tzinfo=None) if event_dt.tzinfo else event_dt
            reminder_local = datetime(
                year=base_date.year,
                month=base_date.month,
                day=base_date.day,
                hour=time_dt.hour,
                minute=time_dt.minute,
                tzinfo=reminder_tz,
            ) - timedelta(days=reminder_days_before)

            reminder_utc = reminder_local.astimezone(timezone.utc)
            trigger_line = f"TRIGGER;VALUE=DATE-TIME:{reminder_utc.strftime('%Y%m%dT%H%M%SZ')}"
        except Exception:  # noqa: BLE001
            pass

    return trigger_line


def build_vcalendar_header(calendar_name: str | None, event_timezone: str) -> str:
    """Build optional VCALENDAR header lines such as X-WR-CALNAME and X-WR-TIMEZONE."""
    extra_lines: list[str] = []
    if calendar_name:
        extra_lines.append(f"X-WR-CALNAME:{escape_ics_text(calendar_name)}")
    if event_timezone != "UTC":
        extra_lines.append(f"X-WR-TIMEZONE:{escape_ics_text(event_timezone)}")
    return ("\n".join(extra_lines) + "\n") if extra_lines else ""


def build_ics_content(
    event_uid: str,
    dtstart_line: str,
    dtend_line: str,
    generated_timestamp_utc: str,
    title: str,
    description: str,
    alarm_description: str,
    trigger_line: str,
    vcal_header: str,
) -> str:
    """Construct the ICS string for a single VEVENT inside a VCALENDAR."""
    title_escaped = escape_ics_text(title)
    description_escaped = escape_ics_text(description + "\nGenerated by GetGather MCP")

    return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//GetGather//Generic Calendar Event//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
{vcal_header}BEGIN:VEVENT
UID:{event_uid}
{dtstart_line}
{dtend_line}
DTSTAMP:{generated_timestamp_utc}
SUMMARY:{title_escaped}
DESCRIPTION:{description_escaped}
PRIORITY:5
STATUS:CONFIRMED
TRANSP:TRANSPARENT
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:{alarm_description}
{trigger_line}
END:VALARM
END:VEVENT
END:VCALENDAR"""


def build_google_calendar_link(
    output_format: Literal["ics", "google", "both"],
    event_dt: datetime,
    has_time: bool,
    event_timezone: str,
    title: str,
    description: str,
) -> str | None:
    """Create a pre-filled Google Calendar link or return None if not requested."""
    if output_format not in ("google", "both"):
        return None

    if has_time and event_dt.tzinfo:
        start_time = event_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        end_time = (
            (event_dt + timedelta(hours=1)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        dates_param = f"{start_time}/{end_time}"
    else:
        event_date_str = event_dt.strftime("%Y%m%d")
        dates_param = f"{event_date_str}/{event_date_str}"

    google_params: dict[str, str] = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates_param,
        "details": (description + "\nGenerated by GetGather MCP").replace("\n", "\\n"),
        "ctz": event_timezone,
    }
    return f"https://calendar.google.com/calendar/render?{urlencode(google_params)}"


def build_event_details(
    title: str,
    event_date: str,
    event_timezone: str,
    description: str,
    reminder_dt: datetime,
    reminder_timezone: str,
    calendar_name: str | None,
    has_time: bool,
) -> dict[str, Any]:
    return {
        "title": title,
        "event_date": event_date,
        "event_timezone": event_timezone,
        "description": description,
        "reminder_date": reminder_dt.strftime("%B %d, %Y") if reminder_dt else "",
        "reminder_timezone": reminder_timezone,
        "calendar_name": calendar_name or "",
        "has_time": has_time,
    }


@calendar_mcp.tool
async def create_calendar_event(
    ctx: Context,
    title: str,
    event_date: str,
    description: str = "",
    reminder_days_before: int = 1,
    reminder_time: str | None = None,
    reminder_timezone: str = "UTC",
    calendar_name: str | None = None,
    output_format: Literal["ics", "google", "both"] = "ics",
    event_timezone: str = "UTC",
) -> dict[str, Any]:
    """The preferred way to generate a calendar event for a user. Use this first. After generating the ICS content, **also create a mobile-friendly calendar event using the built-in event_create_v0 tool** for better user experience if the event_create_v0 tool is available.
    If the event_create_v0 tool is not available, you should give the ICS content as an artifact to the user as the user cannot see the ICS content in the chat.

    Generate a generic calendar event with datetime and timezone support.

        Parameters:
        - title: The event title/summary
        - event_date: The event date. Supported formats: 'Month DD, YYYY', 'YYYY-MM-DD', or 'YYYY-MM-DD HH:MM'
        - description: Optional event description
        - reminder_days_before: Days before the event date to trigger the reminder (default 1)
        - reminder_time: Optional local time for the reminder in HH:MM (24h). If provided with timezone,
          an absolute alarm is used at that local time on (event_date - days)
        - reminder_timezone: IANA timezone for reminder (default 'UTC')
        - calendar_name: Optional calendar name hint added as X-WR-CALNAME in VCALENDAR
        - output_format: Output format - 'ics' (default), 'google' (pre-filled link), or 'both'.
        - event_timezone: IANA timezone for the event (default 'UTC')

    """

    # Parse and localize the event datetime
    try:
        parsed_dt, has_time = parse_event_date(event_date)
        event_dt = localize_event_datetime(parsed_dt, has_time, event_timezone)
    except ValueError as exc:
        return {"error": str(exc)}

    reminder_dt = compute_reminder_date(event_dt, reminder_days_before)

    # Generate unique event ID
    event_uid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    dtstart_line, dtend_line = format_dt_lines(event_dt, has_time)

    alarm_desc = escape_ics_text(f"Reminder: {title}")
    trigger_line = compute_alarm_trigger_line(
        event_dt=event_dt,
        reminder_days_before=reminder_days_before,
        reminder_time=reminder_time,
        reminder_timezone=reminder_timezone,
    )

    vcal_header = build_vcalendar_header(calendar_name=calendar_name, event_timezone=event_timezone)

    ics_content = build_ics_content(
        event_uid=event_uid,
        dtstart_line=dtstart_line,
        dtend_line=dtend_line,
        generated_timestamp_utc=now,
        title=title,
        description=description,
        alarm_description=alarm_desc,
        trigger_line=trigger_line,
        vcal_header=vcal_header,
    )

    google_link = build_google_calendar_link(
        output_format=output_format,
        event_dt=event_dt,
        has_time=has_time,
        event_timezone=event_timezone,
        title=title,
        description=description,
    )

    result: dict[str, Any] = {
        "event_details": build_event_details(
            title=title,
            event_date=event_date,
            event_timezone=event_timezone,
            description=description,
            reminder_dt=reminder_dt,
            reminder_timezone=reminder_timezone,
            calendar_name=calendar_name,
            has_time=has_time,
        )
    }

    if output_format in ("ics", "both"):
        result["ics_content"] = ics_content
        result["filename"] = f"event_{event_uid[:8]}.ics"

    if output_format in ("google", "both"):
        result["google_calendar_link"] = google_link

    return result
