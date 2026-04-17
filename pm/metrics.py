"""
Daily/weekly rental car metrics vs. historical benchmarks.

On weekdays: yesterday vs. the prior 4 same-weekdays.
On Sunday/Monday: last complete week vs. the prior 4 weeks.

Schema discovery runs once on first use and caches to data/metrics_schema.json.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"
_SCHEMA_CACHE = _DATA_DIR / "metrics_schema.json"

# Candidates in priority order
_DATE_CANDIDATES = [
    "BOOKING_DATE", "CREATED_AT", "BOOKING_CREATED_AT",
    "BOOKING_CREATED_DATE", "CHECKOUT_DATE", "RESERVATION_DATE",
]
_GBV_CANDIDATES = [
    "GBV", "CAR_GBV", "GBV_USD", "TOTAL_GBV",
    "BOOKING_VALUE_USD", "TOTAL_BOOKING_VALUE_USD", "AMOUNT_USD",
    "BOOKING_VALUE", "TOTAL_AMOUNT",
]
_HOTEL_DATE_CANDIDATES = [
    "CREATED_AT", "BOOKING_DATE", "BOOKING_CREATED_AT",
    "BOOKING_CREATED_DATE", "CHECK_IN_DATE",
]
_HOTEL_GBV_CANDIDATES = [
    "GBV", "GBV_USD", "TOTAL_GBV", "BOOKING_VALUE_USD",
    "TOTAL_BOOKING_VALUE_USD", "AMOUNT_USD",
]


def _pick(columns_set, candidates):
    for c in candidates:
        if c in columns_set:
            return c
    return None


def _discover_schema(run_query):
    """Query INFORMATION_SCHEMA to find usable columns, then cache."""

    def get_cols(table):
        try:
            _, rows = run_query(f"""
                SELECT COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = 'PUBLIC'
                  AND TABLE_NAME   = '{table}'
                ORDER BY ORDINAL_POSITION
            """)
            return {r[0]: r[1] for r in rows}
        except Exception:
            return {}

    car_cols  = get_cols("FCT_RENTAL_CAR_BOOKINGS")
    hotel_cols = get_cols("FCT_BOOKINGS") or get_cols("FCT_HOTEL_BOOKINGS")

    # Also check for status column options in hotel table
    hotel_status_col  = "STATUS"
    hotel_status_val  = "'confirmed'"
    if "BOOKING_STATUS_CODE" in hotel_cols:
        hotel_status_col = "BOOKING_STATUS_CODE"
        hotel_status_val = "'BOOKING_STATUS_CONFIRMED'"

    schema = {
        "car_date_col":   _pick(car_cols,   _DATE_CANDIDATES),
        "car_gbv_col":    _pick(car_cols,   _GBV_CANDIDATES),
        "hotel_date_col": _pick(hotel_cols, _HOTEL_DATE_CANDIDATES),
        "hotel_gbv_col":  _pick(hotel_cols, _HOTEL_GBV_CANDIDATES),
        "hotel_table":    "FCT_BOOKINGS" if hotel_cols else None,
        "hotel_status_col": hotel_status_col,
        "hotel_status_val": hotel_status_val,
        "car_columns":    list(car_cols.keys()),
        "hotel_columns":  list(hotel_cols.keys()),
    }
    _DATA_DIR.mkdir(exist_ok=True)
    _SCHEMA_CACHE.write_text(json.dumps(schema, indent=2))
    return schema


def _get_schema(run_query):
    if _SCHEMA_CACHE.exists():
        return json.loads(_SCHEMA_CACHE.read_text())
    return _discover_schema(run_query)


def _daily_query(schema):
    dc  = schema["car_date_col"]
    gc  = schema["car_gbv_col"]
    hd  = schema["hotel_date_col"]
    ht  = schema["hotel_table"]
    hsc = schema["hotel_status_col"]
    hsv = schema["hotel_status_val"]

    car_gbv_expr  = f"SUM(NULLIF({gc}, 0))" if gc else "NULL"
    h_filter = f"{hsc} {hsv}" if hsv.strip().upper().startswith("IN") else f"{hsc} = {hsv}"
    hotel_part    = f"""
    hotel_daily AS (
        SELECT
            {hd}::DATE AS booking_date,
            COUNT(*) AS hotel_bookings
        FROM ANALYTICS.{ht}
        WHERE {h_filter}
          AND {hd}::DATE >= DATEADD('day', -35, CURRENT_DATE)
          AND {hd}::DATE <  CURRENT_DATE
        GROUP BY 1
    ),""" if (ht and hd) else "hotel_daily AS (SELECT NULL::DATE AS booking_date, NULL::INT AS hotel_bookings WHERE FALSE),"

    return f"""
WITH car_daily AS (
    SELECT
        {dc}::DATE AS booking_date,
        COUNT(*) AS car_bookings,
        {car_gbv_expr} AS car_gbv
    FROM ANALYTICS.FCT_RENTAL_CAR_BOOKINGS
    WHERE BOOKING_STATUS_CODE = 'CAR_BOOKING_STATUS_CONFIRMED'
      AND {dc}::DATE >= DATEADD('day', -35, CURRENT_DATE)
      AND {dc}::DATE <  CURRENT_DATE
    GROUP BY 1
),
{hotel_part}
combined AS (
    SELECT
        c.booking_date,
        c.car_bookings,
        ROUND(COALESCE(c.car_gbv, 0)) AS car_gbv,
        COALESCE(h.hotel_bookings, 0) AS hotel_bookings,
        CASE WHEN COALESCE(h.hotel_bookings, 0) > 0
             THEN ROUND(c.car_bookings * 100.0 / h.hotel_bookings, 2)
             ELSE NULL END AS attach_rate_pct
    FROM car_daily c
    LEFT JOIN hotel_daily h ON c.booking_date = h.booking_date
)
SELECT * FROM combined
WHERE DAYOFWEEK(booking_date) = DAYOFWEEK(DATEADD('day', -1, CURRENT_DATE))
ORDER BY booking_date DESC
LIMIT 5
"""


def _weekly_query(schema):
    dc  = schema["car_date_col"]
    gc  = schema["car_gbv_col"]
    hd  = schema["hotel_date_col"]
    ht  = schema["hotel_table"]
    hsc = schema["hotel_status_col"]
    hsv = schema["hotel_status_val"]

    car_gbv_expr = f"SUM(NULLIF({gc}, 0))" if gc else "NULL"
    h_filter = f"{hsc} {hsv}" if hsv.strip().upper().startswith("IN") else f"{hsc} = {hsv}"
    hotel_part   = f"""
    hotel_weekly AS (
        SELECT
            DATE_TRUNC('week', {hd}) AS week_start,
            COUNT(*) AS hotel_bookings
        FROM ANALYTICS.{ht}
        WHERE {h_filter}
          AND {hd} >= DATEADD('week', -6, DATE_TRUNC('week', CURRENT_DATE))
          AND {hd} <  CURRENT_DATE
        GROUP BY 1
    ),""" if (ht and hd) else "hotel_weekly AS (SELECT NULL::DATE AS week_start, NULL::INT AS hotel_bookings WHERE FALSE),"

    return f"""
WITH car_weekly AS (
    SELECT
        DATE_TRUNC('week', {dc}::DATE) AS week_start,
        COUNT(*) AS car_bookings,
        {car_gbv_expr} AS car_gbv,
        -- days of data in this week (0–6), used to flag partial weeks
        DATEDIFF('day', DATE_TRUNC('week', {dc}::DATE), MAX({dc}::DATE)) AS days_of_data
    FROM ANALYTICS.FCT_RENTAL_CAR_BOOKINGS
    WHERE BOOKING_STATUS_CODE = 'CAR_BOOKING_STATUS_CONFIRMED'
      AND {dc} >= DATEADD('week', -6, DATE_TRUNC('week', CURRENT_DATE))
      AND {dc} <  CURRENT_DATE
    GROUP BY 1
),
{hotel_part}
combined AS (
    SELECT
        c.week_start,
        c.car_bookings,
        ROUND(COALESCE(c.car_gbv, 0)) AS car_gbv,
        COALESCE(h.hotel_bookings, 0) AS hotel_bookings,
        CASE WHEN COALESCE(h.hotel_bookings, 0) > 0
             THEN ROUND(c.car_bookings * 100.0 / h.hotel_bookings, 2)
             ELSE NULL END AS attach_rate_pct,
        c.days_of_data
    FROM car_weekly c
    LEFT JOIN hotel_weekly h ON c.week_start::DATE = h.week_start::DATE
)
SELECT * FROM combined
ORDER BY week_start DESC
LIMIT 6
"""


def _fmt_delta(val, baseline, higher_is_better=True):
    """Return colored delta string. val vs baseline (both floats)."""
    if not baseline or baseline == 0:
        return ""
    pct = (val - baseline) / baseline * 100
    better = pct >= 0 if higher_is_better else pct <= 0
    abs_pct = abs(pct)
    sign = "+" if pct >= 0 else "-"
    if abs_pct >= 10:
        color = "\033[92m" if better else "\033[91m"   # green / red
        flag = "" if better else "  🚨"
    elif abs_pct >= 5:
        color = "\033[92m" if better else "\033[93m"   # green / yellow
        flag = "" if better else "  ⚠️"
    else:
        color = "\033[92m" if better else "\033[2m"
        flag = ""
    RESET = "\033[0m"
    return f"{color}{sign}{abs_pct:.1f}%{RESET}{flag}"


def _fmt_gbv(v):
    if v is None:
        return "—"
    v = float(v)
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    return f"${v/1_000:.1f}K"


def get_daily_metrics(run_query):
    """
    Return formatted output lines for yesterday vs. prior same-weekday average.
    Returns [] if Snowflake is unavailable or schema can't be resolved.
    """
    try:
        schema = _get_schema(run_query)
        if not schema.get("car_date_col"):
            return ["  (Could not resolve FCT_RENTAL_CAR_BOOKINGS schema)"]

        _, rows = run_query(_daily_query(schema))
        if not rows:
            return ["  No data returned."]

        yesterday_row = rows[0]    # most recent = yesterday
        prior_rows    = rows[1:]   # same weekday in prior weeks

        yday_bookings   = float(yesterday_row[1] or 0)
        yday_gbv        = float(yesterday_row[2] or 0)
        yday_hotel      = float(yesterday_row[3] or 0)
        yday_attach     = float(yesterday_row[4] or 0) if yesterday_row[4] is not None else None

        if prior_rows:
            avg_bookings = sum(float(r[1] or 0) for r in prior_rows) / len(prior_rows)
            avg_gbv      = sum(float(r[2] or 0) for r in prior_rows) / len(prior_rows)
            avg_attach   = None
            attach_vals  = [float(r[4]) for r in prior_rows if r[4] is not None]
            if attach_vals:
                avg_attach = sum(attach_vals) / len(attach_vals)
        else:
            avg_bookings = avg_gbv = avg_attach = None

        yesterday = date.today() - timedelta(days=1)
        weekday   = yesterday.strftime("%A")
        lines = [
            f"  Yesterday ({weekday} {yesterday.strftime('%-m/%-d')})  |  4-week {weekday} avg",
            f"  {'─'*56}",
        ]

        d_b = _fmt_delta(yday_bookings, avg_bookings)
        d_g = _fmt_delta(yday_gbv, avg_gbv)
        lines.append(
            f"  Bookings     {int(yday_bookings):>6}   avg {int(avg_bookings or 0):>6}   {d_b}"
        )
        lines.append(
            f"  Car GBV    {_fmt_gbv(yday_gbv):>7}   avg {_fmt_gbv(avg_gbv):>7}   {d_g}"
        )
        if yday_attach is not None:
            d_a = _fmt_delta(yday_attach, avg_attach)
            lines.append(
                f"  Attach       {yday_attach:.2f}%   avg {(avg_attach or 0):.2f}%     {d_a}"
            )

        return lines

    except Exception as e:
        return [f"  Snowflake error: {e}"]


def get_weekly_metrics(run_query):
    """
    Return formatted output lines comparing weeks.
    The most recent row may be a partial current week — labeled accordingly.
    Deltas are always computed against complete weeks only (days_of_data == 6).
    """
    try:
        schema = _get_schema(run_query)
        if not schema.get("car_date_col"):
            return ["  (Could not resolve schema)"]

        _, rows = run_query(_weekly_query(schema))
        if not rows:
            return ["  No data returned."]

        # rows cols: week_start, car_bookings, car_gbv, hotel_bookings, attach_rate_pct, days_of_data
        current_week_start = date.today() - timedelta(days=date.today().weekday())

        # Separate partial vs complete rows
        complete_rows = [r for r in rows if int(r[5] or 0) >= 6]
        partial_rows  = [r for r in rows if int(r[5] or 0) < 6]

        # Use the most recent complete week for the headline comparison
        if not complete_rows:
            return ["  Not enough complete week data yet."]

        last_complete = complete_rows[0]
        prior_rows    = complete_rows[1:5]   # up to 4 prior complete weeks for avg

        lw_bookings = float(last_complete[1] or 0)
        lw_gbv      = float(last_complete[2] or 0)
        lw_attach   = float(last_complete[4]) if last_complete[4] is not None else None

        if prior_rows:
            avg_b = sum(float(r[1] or 0) for r in prior_rows) / len(prior_rows)
            avg_g = sum(float(r[2] or 0) for r in prior_rows) / len(prior_rows)
            av    = [float(r[4]) for r in prior_rows if r[4] is not None]
            avg_a = sum(av) / len(av) if av else None
        else:
            avg_b = avg_g = avg_a = None

        lines = [
            f"  {'Week':<14} {'Bookings':>9} {'Car GBV':>10} {'Attach':>8}",
            f"  {'─'*48}",
        ]

        # Print partial week first (if any) with clear label
        for r in partial_rows:
            days = int(r[5] or 0)
            w   = date.fromisoformat(str(r[0])[:10]).strftime("%-m/%-d")
            bk  = int(r[1] or 0)
            gbv = _fmt_gbv(r[2])
            att = f"{float(r[4]):.2f}%" if r[4] is not None else "—"
            lines.append(f"  {w} (thru yest){'':<1} {bk:>9,} {gbv:>10} {att:>8}  ← this week ({days}/7 days)")

        # Print complete weeks
        for i, r in enumerate(complete_rows[:5]):
            w     = date.fromisoformat(str(r[0])[:10]).strftime("%-m/%-d")
            bk    = int(r[1] or 0)
            gbv   = _fmt_gbv(r[2])
            att   = f"{float(r[4]):.2f}%" if r[4] is not None else "—"
            label = " ← last week" if i == 0 else ""
            lines.append(f"  {w:<14} {bk:>9,} {gbv:>10} {att:>8}{label}")

        # Deltas vs avg (complete weeks only)
        if avg_b:
            lines.append(f"  {'─'*48}")
            d_b = _fmt_delta(lw_bookings, avg_b)
            d_g = _fmt_delta(lw_gbv, avg_g)
            lines.append(f"  Last complete week vs. 4-wk avg:  bookings {d_b}   GBV {d_g}")
            if lw_attach is not None and avg_a:
                d_a = _fmt_delta(lw_attach, avg_a)
                lines.append(f"                                    attach {d_a}")

        return lines

    except Exception as e:
        return [f"  Snowflake error: {e}"]
