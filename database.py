
import os
from datetime import date

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()


def connect():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is missing from .env")
    return psycopg.connect(url, row_factory=dict_row)


def init_db():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                username TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                casual_leave INTEGER NOT NULL DEFAULT 12,
                sick_leave INTEGER NOT NULL DEFAULT 10
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS leave_requests (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL REFERENCES employees(username),
                leave_type TEXT NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                reason TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL REFERENCES employees(username),
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'IT',
                priority TEXT NOT NULL DEFAULT 'Medium',
                status TEXT NOT NULL DEFAULT 'Open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            INSERT INTO employees
                (username, full_name, casual_leave, sick_leave)
            VALUES ('employee1', 'Demo Employee', 12, 10)
            ON CONFLICT (username) DO NOTHING
        """)


def get_leave_balance(username):
    with connect() as conn:
        row = conn.execute("""
            SELECT casual_leave, sick_leave
            FROM employees WHERE username = %s
        """, (username,)).fetchone()

    if not row:
        raise ValueError("Employee not found")

    return {
        "username": username,
        "casual_leave": row["casual_leave"],
        "sick_leave": row["sick_leave"],
    }



def apply_leave(username, leave_type, start_date, end_date, reason=""):
    from datetime import date

    leave_type = leave_type.strip().lower()

    if leave_type not in ("casual", "sick"):
        raise ValueError("Leave type must be casual or sick")

    start = date.fromisoformat(str(start_date))
    end = date.fromisoformat(str(end_date))

    if end < start:
        raise ValueError("End date cannot be before start date")

    if start < date.today():
        raise ValueError("Leave cannot start in the past")

    days = (end - start).days + 1

    # Choose the correct database column.
    column = (
        "casual_leave"
        if leave_type == "casual"
        else "sick_leave"
    )

    # Both the request and balance update happen
    # within one database transaction.
    with connect() as conn:
        employee = conn.execute(
            f"""
            SELECT {column} AS balance
            FROM employees
            WHERE username = %s
            FOR UPDATE
            """,
            (username,)
        ).fetchone()

        if not employee:
            raise ValueError("Employee not found")

        if employee["balance"] < days:
            raise ValueError(
                f"Insufficient {leave_type} leave balance. "
                f"Available: {employee['balance']} days."
            )

        # Create the leave request.
        request = conn.execute(
            """
            INSERT INTO leave_requests
                (username, leave_type, start_date,
                 end_date, reason, status)
            VALUES (%s, %s, %s, %s, %s, 'Pending')
            RETURNING id, username, leave_type,
                      start_date, end_date, reason, status
            """,
            (username, leave_type, start, end, reason)
        ).fetchone()

        # Deduct the requested days immediately.
        balance_row = conn.execute(
            f"""
            UPDATE employees
            SET {column} = {column} - %s
            WHERE username = %s
            RETURNING {column} AS remaining_balance
            """,
            (days, username)
        ).fetchone()

        result = dict(request)
        result["days_deducted"] = days
        result["remaining_balance"] = (
            balance_row["remaining_balance"]
        )

    return result



def list_my_tickets(username, open_only=False):
    sql = """
        SELECT id, title, description, category, priority,
               status, created_at
        FROM tickets WHERE username = %s
    """
    params = [username]

    if open_only:
        sql += " AND status NOT IN ('Resolved', 'Cancelled')"

    sql += " ORDER BY created_at DESC"

    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


def create_ticket(username, title, description,
                  category="IT", priority="Medium"):
    with connect() as conn:
        row = conn.execute("""
            INSERT INTO tickets
                (username, title, description, category, priority)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, username, title, description,
                      category, priority, status, created_at
        """, (username, title, description, category, priority)
        ).fetchone()

    return dict(row)


def get_ticket_status(username, ticket_id):
    with connect() as conn:
        row = conn.execute("""
            SELECT id, title, description, category,
                   priority, status, created_at
            FROM tickets
            WHERE id = %s AND username = %s
        """, (ticket_id, username)).fetchone()

    return dict(row) if row else None


def resolve_ticket(username, ticket_id):
    with connect() as conn:
        row = conn.execute("""
            UPDATE tickets
            SET status = 'Resolved'
            WHERE id = %s AND username = %s
            RETURNING id, title, status
        """, (ticket_id, username)).fetchone()

    return dict(row) if row else None


if __name__ == "__main__":
    init_db()
    print("Database tables initialized successfully.")
