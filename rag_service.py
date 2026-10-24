
import os
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
INDEX_DIR = BASE_DIR / "data" / "faiss_index"

_embeddings = None
_vector_store = None


def get_embeddings():
    """Create the embedding model once and reuse it."""
    global _embeddings

    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

    return _embeddings


def index_uploaded_files(uploaded_files):
    """Extract PDF text, create chunks, and save a FAISS index."""
    global _vector_store

    documents = []

    for uploaded_file in uploaded_files:
        try:
            pdf_bytes = uploaded_file.getvalue()
            reader = PdfReader(BytesIO(pdf_bytes))

            for page_number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""

                if page_text.strip():
                    documents.append(
                        Document(
                            page_content=page_text,
                            metadata={
                                "source": uploaded_file.name,
                                "page": page_number,
                            },
                        )
                    )

        except Exception as exc:
            raise ValueError(
                f"Could not read {uploaded_file.name}: {exc}"
            ) from exc

    if not documents:
        raise ValueError(
            "No readable text was found in the uploaded PDFs. "
            "Please upload PDFs containing selectable text."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
    )

    chunks = splitter.split_documents(documents)

    if not chunks:
        raise ValueError("No document chunks were created.")

    embeddings = get_embeddings()

    _vector_store = FAISS.from_documents(
        documents=chunks,
        embedding=embeddings,
    )

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    _vector_store.save_local(str(INDEX_DIR))

    return len(chunks)


def load_index():
    """Load an existing index, if available."""
    global _vector_store

    if _vector_store is not None:
        return _vector_store

    index_file = INDEX_DIR / "index.faiss"
    metadata_file = INDEX_DIR / "index.pkl"

    if not index_file.exists() or not metadata_file.exists():
        return None

    # Only load the pickle file if this is your own trusted,
    # locally generated FAISS index.
    _vector_store = FAISS.load_local(
        str(INDEX_DIR),
        get_embeddings(),
        allow_dangerous_deserialization=True,
    )

    return _vector_store


def retrieve_context(question, k=3):
    """Retrieve the most relevant document chunks."""
    store = load_index()

    if store is None:
        return []

    return store.similarity_search(question, k=k)


def answer_question(question):
    """Answer a policy question using retrieved PDF content."""
    if not question or not question.strip():
        return {
            "answer": "Please enter a question.",
            "sources": [],
        }

    documents = retrieve_context(question)

    if not documents:
        return {
            "answer": (
                "I couldn't find relevant information in the indexed "
                "documents. Please upload and index the applicable "
                "HR policy, IT FAQ, or onboarding PDF."
            ),
            "sources": [],
        }

    context_parts = []
    sources = []
    seen_sources = set()

    for document in documents:
        source = document.metadata.get("source", "Unknown")
        page = document.metadata.get("page", "?")

        context_parts.append(
            f"[Source: {source}, page {page}]\n"
            f"{document.page_content}"
        )

        source_key = (source, page)

        if source_key not in seen_sources:
            sources.append({
                "source": source,
                "page": page,
            })
            seen_sources.add(source_key)

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing from your .env file."
        )

    model_name = os.getenv(
        "GROQ_MODEL",
        "llama-3.3-70b-versatile",
    )

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a company HR and IT helpdesk assistant. "
            "Answer using only the supplied document context. "
            "Do not invent company policies or facts. "
            "If the context does not answer the question, clearly "
            "say that the information was not found. "
            "Cite supporting sources by filename and page number.\n\n"
            "DOCUMENT CONTEXT:\n{context}",
        ),
        ("human", "{question}"),
    ])

    llm = ChatGroq(
        model=model_name,
        temperature=0,
        api_key=api_key,
        max_tokens=500,
    )

    chain = prompt | llm

    response = chain.invoke({
        "context": "\n\n".join(context_parts),
        "question": question,
    })

    return {
        "answer": response.content,
        "sources": sources,
    }
