
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastmcp import FastMCP
import database

mcp = FastMCP("Company Ticketing Server")


@mcp.tool()
def create_ticket(username: str, title: str, description: str,
                  category: str = "IT",
                  priority: str = "Medium") -> dict:
    """Create an IT or HR support ticket for an employee."""
    if category.upper() not in ("IT", "HR"):
        raise ValueError("Category must be IT or HR")

    if priority.title() not in ("Low", "Medium", "High"):
        raise ValueError("Priority must be Low, Medium or High")

    return database.create_ticket(
        username, title, description,
        category.upper(), priority.title()
    )


@mcp.tool()
def get_ticket_status(username: str, ticket_id: int) -> dict:
    """Get a ticket's status if it belongs to this employee."""
    ticket = database.get_ticket_status(username, ticket_id)
    return ticket or {"error": "Ticket not found"}


@mcp.tool()
def list_my_tickets(username: str, open_only: bool = False) -> list:
    """List an employee's tickets, optionally only open tickets."""
    return database.list_my_tickets(username, open_only)


if __name__ == "__main__":
    database.init_db()
    mcp.run()
