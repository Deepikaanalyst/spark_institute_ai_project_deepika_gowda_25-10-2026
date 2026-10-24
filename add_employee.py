
from database import connect

def main():
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO employees
                (username, full_name, casual_leave, sick_leave)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            ("deepika", "Deepika", 12, 10),
        )

        rows = conn.execute(
            """
            SELECT username, full_name, casual_leave, sick_leave
            FROM employees
            WHERE username = %s
            """,
            ("deepika",),
        ).fetchall()

        print("Employee record:", rows)

if __name__ == "__main__":
    main()
