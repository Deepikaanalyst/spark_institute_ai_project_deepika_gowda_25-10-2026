
import os
from datetime import date

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import database
from mcp_client import call_ticket_tool, call_leave_tool
from rag_service import index_uploaded_files, answer_question
from mcp_client import call_leave_tool


def get_leave_balance_answer(question, username):
    """Answer personal leave balance questions using MCP."""

    q = question.lower()
    asks_casual = "casual" in q
    asks_sick = "sick" in q

    result = call_leave_tool(
        "get_leave_balance",
        {"username": username}
    )

    if not isinstance(result, dict):
        return f"Unable to retrieve leave balance: {result}"

    if result.get("error"):
        return f"Leave balance error: {result['error']}"

    casual = result.get("casual_leave")
    sick = result.get("sick_leave")

    if asks_casual and casual is not None:
        return f"You have {casual} casual leave day(s) remaining."

    if asks_sick and sick is not None:
        return f"You have {sick} sick leave day(s) remaining."

    if casual is not None and sick is not None:
        return (
            f"Your remaining leave balance is:\n\n"
            f"- Casual leave: {casual} day(s)\n"
            f"- Sick leave: {sick} day(s)"
        )

    return "I couldn't read the leave balance returned by the leave tool."

load_dotenv()

st.set_page_config(
    page_title="PeopleDesk AI",
    page_icon="🏢",
    layout="wide",
)

database.init_db()

st.markdown("""
<style>
.stApp {
    background: #f4f7fb;
}
[data-testid="stSidebar"] {
    background: #e9eff7;
}
.block-container {
    padding-top: 1.6rem;
}
h1, h2, h3 {
    color: #173b52;
}
.stButton > button {
    border-radius: 9px;
    font-weight: 600;
}
[data-testid="stChatMessage"] {
    border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)


# ---------------- LOGIN ----------------

if "username" not in st.session_state:
    st.session_state.username = None

if not st.session_state.username:
    st.title("🏢 PeopleDesk AI")
    st.subheader("Company HR & IT Helpdesk")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button(
            "Sign in", use_container_width=True
        )

    if submitted:
        expected_user = os.getenv("APP_USERNAME", "employee1")
        expected_password = os.getenv(
            "APP_PASSWORD", "ChangeThisPassword123"
        )

        if username == expected_user and password == expected_password:
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Invalid username or password.")

    st.info(
        "Demo login uses APP_USERNAME and APP_PASSWORD from .env. "
        "Configure a proper identity provider before production use."
    )
    st.stop()


username = st.session_state.username

# Initialize chat and approval state.
if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_action" not in st.session_state:
    st.session_state.pending_action = None


# ---------------- SIDEBAR ----------------

with st.sidebar:
    st.title("PeopleDesk AI")
    st.caption("Employee Helpdesk Portal")
    st.success(f"Signed in as: {username}")

    if st.button("Log out", use_container_width=True):
        st.session_state.username = None
        st.session_state.messages = []
        st.session_state.pending_action = None
        st.rerun()

    st.divider()
    st.subheader("My Open Tickets")

    try:
        open_tickets = call_ticket_tool(
            "list_my_tickets",
            {"username": username, "open_only": True},
        )

        if isinstance(open_tickets, list) and open_tickets:
            for ticket in open_tickets:
                with st.container(border=True):
                    st.markdown(
                        f"**#{ticket.get('id')} — "
                        f"{ticket.get('title', 'Ticket')}**"
                    )
                    st.caption(
                        f"Status: {ticket.get('status', 'Unknown')}"
                    )
        elif isinstance(open_tickets, list):
            st.caption("No open tickets.")
        else:
            st.json(open_tickets)
    except Exception as exc:
        st.error(f"Could not load tickets: {exc}")


# ---------------- HEADER ----------------

st.title("Welcome to PeopleDesk AI")
st.write(
    "Ask HR policy questions, check your leave balance, "
    "submit a leave request, or raise an IT support ticket."
)

tab_chat, tab_documents, tab_leave, tab_tickets = st.tabs([
    "💬 Assistant",
    "📚 Knowledge Base",
    "🌿 Leave Management",
    "🎫 IT Helpdesk",
])


# ---------------- DOCUMENT UPLOAD ----------------

with tab_documents:
    st.subheader("Company Knowledge Base")
    st.write(
        "Upload HR policy, IT FAQ, and onboarding PDFs. "
        "The assistant uses these files to answer policy questions."
    )

    uploaded_files = st.file_uploader(
        "Upload PDF documents",
        type=["pdf"],
        accept_multiple_files=True,
        key="knowledge_pdfs",
    )

    if st.button("Index documents", key="index_documents"):
        if not uploaded_files:
            st.warning("Select at least one PDF.")
        else:
            try:
                with st.spinner("Extracting text and building FAISS index..."):
                    count = index_uploaded_files(uploaded_files)
                st.success(f"Indexed {count} text chunks successfully.")
            except Exception as exc:
                st.error(f"Indexing failed: {exc}")


# ---------------- LEAVE MANAGEMENT ----------------

with tab_leave:
    st.subheader("My Leave Balance")

    if st.button("Check my leave balance"):
        try:
            balance = call_leave_tool(
                "get_leave_balance",
                {"username": username},
            )
            st.session_state.last_balance = balance
        except Exception as exc:
            st.error(f"Leave tool error: {exc}")

    balance = st.session_state.get("last_balance")
    if isinstance(balance, dict):
        if "error" in balance:
            st.error(balance["error"])
        else:
            col1, col2 = st.columns(2)
            col1.metric(
                "Casual Leave Remaining",
                balance.get("casual_leave", "—"),
            )
            col2.metric(
                "Sick Leave Remaining",
                balance.get("sick_leave", "—"),
            )

    st.divider()
    st.subheader("Submit a Leave Request")

    with st.form("leave_request_form"):
        leave_type = st.selectbox(
            "Leave type", ["casual", "sick"]
        )
        start_date = st.date_input(
            "Start date", value=date.today()
        )
        end_date = st.date_input(
            "End date", value=date.today()
        )
        reason = st.text_area("Reason")

        confirm_leave = st.checkbox(
            "I confirm these leave details are correct."
        )
        submit_leave = st.form_submit_button(
            "Review and submit request"
        )

    if submit_leave:
        if not confirm_leave:
            st.warning("Please confirm the leave details first.")
        elif start_date < date.today():
            st.error("Select today or a future date.")
        elif end_date < start_date:
            st.error("End date must be on or after start date.")
        else:
            st.session_state.pending_action = {
                "type": "apply_leave",
                "arguments": {
                    "username": username,
                    "leave_type": leave_type,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "reason": reason,
                },
            }

    pending = st.session_state.pending_action
    if pending and pending.get("type") == "apply_leave":
        args = pending["arguments"]
        st.warning(
            f"Approval required: submit {args['leave_type']} leave "
            f"from {args['start_date']} to {args['end_date']}?"
        )

        yes, no = st.columns(2)
        if yes.button("Confirm leave request"):
            try:
                result = call_leave_tool("apply_leave", args)
                st.session_state.pending_action = None
                st.success("Leave request submitted.")
                st.json(result)
            except Exception as exc:
                st.error(f"Leave request failed: {exc}")

        if no.button("Cancel leave request"):
            st.session_state.pending_action = None
            st.rerun()


# ---------------- IT HELPDESK ----------------

with tab_tickets:
    st.subheader("Raise an IT Ticket")

    with st.form("ticket_form"):
        title = st.text_input(
            "Issue title",
            placeholder="VPN connection not working",
        )
        description = st.text_area(
            "Describe the issue",
            placeholder="Explain the error and troubleshooting tried.",
        )
        category = st.selectbox("Department", ["IT", "HR"])
        priority = st.selectbox(
            "Priority", ["Low", "Medium", "High"]
        )

        confirm_ticket = st.checkbox(
            "I confirm that I want to create this ticket."
        )
        submit_ticket = st.form_submit_button("Review ticket")

    if submit_ticket:
        if not title.strip() or not description.strip():
            st.error("Enter both a title and a description.")
        elif not confirm_ticket:
            st.warning("Confirm the ticket details first.")
        else:
            st.session_state.pending_action = {
                "type": "create_ticket",
                "arguments": {
                    "username": username,
                    "title": title.strip(),
                    "description": description.strip(),
                    "category": category,
                    "priority": priority,
                },
            }

    pending = st.session_state.pending_action
    if pending and pending.get("type") == "create_ticket":
        st.info("Review your ticket details before submitting.")
        st.json(pending["arguments"])

        yes, no = st.columns(2)
        if yes.button("Confirm and create ticket"):
            try:
                result = call_ticket_tool(
                    "create_ticket", pending["arguments"]
                )
                st.session_state.pending_action = None
                st.success("Ticket created.")
                st.json(result)
                st.rerun()
            except Exception as exc:
                st.error(f"Ticket creation failed: {exc}")

        if no.button("Cancel ticket"):
            st.session_state.pending_action = None
            st.rerun()

    st.divider()
    st.subheader("Check Ticket Status")
    ticket_id = st.number_input(
        "Ticket ID", min_value=1, step=1
    )

    if st.button("Get ticket status"):
        try:
            result = call_ticket_tool(
                "get_ticket_status",
                {
                    "username": username,
                    "ticket_id": int(ticket_id),
                },
            )
            st.json(result)
        except Exception as exc:
            st.error(f"Could not check ticket: {exc}")


# ---------------- CHAT ASSISTANT ----------------

with tab_chat:
    st.subheader("Chat with PeopleDesk")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if message.get("sources"):
                with st.expander("Sources"):
                    for source in message["sources"]:
                        st.write(
                            f"{source['source']} — page {source['page']}"
                        )

            if message.get("tools"):
                with st.expander("Tools used"):
                    for tool in message["tools"]:
                        st.write(tool)

    question = st.chat_input(
        "Ask about policies, leave balance, or IT support..."
    )

    if question:
        st.session_state.messages.append({
            "role": "user",
            "content": question,
        })

        lower = question.lower()
        tools_used = []
        sources = []

        try:
            if any(x in lower for x in [
                "how many do i have left",
                "my leave balance",
                "leaves remaining",
                "leave balance",
            ]):
                result = call_leave_tool(
                    "get_leave_balance",
                    {"username": username},
                )
                tools_used.append("Leave MCP: get_leave_balance")

                answer = (
                    f"Your current leave balance is:\n\n"
                    f"- Casual leave: {result['casual_leave']} days\n"
                    f"- Sick leave: {result['sick_leave']} days"
                )

            elif any(x in lower for x in [
                "raise a ticket",
                "create a ticket",
                "vpn",
                "not working",
                "technical issue",
                "it issue",
            ]):
                answer = (
                    "I can help raise a support ticket. Open the "
                    "**IT Helpdesk** tab, enter the issue details, "
                    "review them, and confirm creation. No ticket "
                    "has been created from this message."
                )
                tools_used.append(
                    "Ticket MCP: not called; awaiting ticket details "
                    "and confirmation"
                )

            elif any(x in lower for x in [
                "apply for leave",
                "apply leave",
                "request leave",
            ]):
                answer = (
                    "Please open **Leave Management**, choose the "
                    "leave type and dates, review the details, and "
                    "confirm the request. I will not submit leave "
                    "without your confirmation."
                )
                tools_used.append(
                    "Leave MCP: not called; awaiting details "
                    "and confirmation"
                )

            else:
                result = answer_question(question)
                answer = result["answer"]
                sources = result["sources"]
                tools_used.append("RAG: FAISS document retrieval")
                tools_used.append("Groq: policy answer generation")

        except Exception as exc:
            answer = (
                f"I couldn't complete that request: {exc}\n\n"
                "Check the MCP server, database, API key, and "
                "installed package versions."
            )
            tools_used.append("Request failed; see error above")

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "tools": tools_used,
        })
        st.rerun()
