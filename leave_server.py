
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastmcp import FastMCP
import database

mcp = FastMCP("Company Leave Server")


@mcp.tool()
def get_leave_balance(username: str) -> dict:
    """Get an employee's remaining casual and sick leave balance."""
    return database.get_leave_balance(username)


@mcp.tool()
def apply_leave(
    username: str,
    leave_type: str,
    start_date: str,
    end_date: str,
    reason: str = ""
) -> dict:
    """Submit a leave request after the employee confirms it."""
    return database.apply_leave(
        username, leave_type, start_date, end_date, reason
    )


if __name__ == "__main__":
    database.init_db()
    mcp.run()
