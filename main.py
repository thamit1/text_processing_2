import os
import sqlite3
import faiss
import numpy as np
from typing import List

from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from atlassian import Jira, Confluence
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer

# ─── Configuration ───────────────────────────────────────────
JIRA_URL = os.getenv("JIRA_URL")
JIRA_USER = os.getenv("JIRA_USER")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")
CONF_URL = os.getenv("CONFLUENCE_URL")
CONF_USER = os.getenv("CONFLUENCE_USER")
CONF_TOKEN = os.getenv("CONFLUENCE_TOKEN")

JIRA_JQL = "project = MYPROJECT"
CONF_SPACE = "MYSPACE"

DB_PATH = "docs.db"
EMB_DIM = 768  # MPNet embedding size
TOP_K = 5  # Default search results

# ─── Initialize Clients ──────────────────────────────────────
jira = Jira(url=JIRA_URL, username=JIRA_USER, password=JIRA_TOKEN)
confluence = Confluence(url=CONF_URL, username=CONF_USER, password=CONF_TOKEN)

# Load cached MPNet model
embedder = SentenceTransformer("mpnet_cached")

# ─── Faiss Index Initialization ──────────────────────────────
faiss_index = faiss.IndexFlatL2(EMB_DIM)
vectors = []   # Stores document embeddings
metadata = []  # Stores metadata (source, doc_id, chunk text)

# ─── FastAPI App ─────────────────────────────────────────────
app = FastAPI()


# ─── Pydantic Models ─────────────────────────────────────────
class QueryIn(BaseModel):
    query: str
    top_k: int = TOP_K

class Hit(BaseModel):
    source_id: str
    snippet: str
    score: float

class QueryOut(BaseModel):
    hits: List[Hit]


# ─── Data Processing Helpers ─────────────────────────────────
def html_to_text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(separator="\n")

def chunk_text(text: str, max_words=300, overlap=50):
    words = text.split()
    step = max_words - overlap
    for i in range(0, len(words), step):
        yield " ".join(words[i : i + max_words])


# ─── Ingestion / Indexing ────────────────────────────────────
def ingest_data():
    global vectors, metadata
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Create SQLite FTS5 Table
    c.execute("DROP TABLE IF EXISTS docs")
    c.execute("""
        CREATE VIRTUAL TABLE docs USING fts5(
          content, source UNINDEXED, doc_id UNINDEXED, tokenize='unicode61'
        )
    """)

    # Jira Issues
    issues = jira.jql(JIRA_JQL, limit=100)["issues"]
    for issue in issues:
        key = issue["key"]
        desc = html_to_text(issue["fields"].get("description", ""))
        for chunk in chunk_text(desc):
            vec = embedder.encode(chunk)
            vectors.append(vec)
            metadata.append({"source": "jira", "id": key, "text": chunk})
            c.execute("INSERT INTO docs(content, source, doc_id) VALUES (?, ?, ?)", (chunk, "jira", key))

    # Confluence Pages
    pages = confluence.get_all_pages_from_space(CONF_SPACE, limit=100)
    for page in pages:
        page_id = page["id"]
        html = confluence.get_page_by_id(page_id, expand="body.storage")["body"]["storage"]["value"]
        text = html_to_text(html)
        for chunk in chunk_text(text):
            vec = embedder.encode(chunk)
            vectors.append(vec)
            metadata.append({"source": "confluence", "id": page_id, "text": chunk})
            c.execute("INSERT INTO docs(content, source, doc_id) VALUES (?, ?, ?)", (chunk, "confluence", page_id))

    conn.commit()
    conn.close()

    # Convert vectors to NumPy for Faiss indexing
    vectors_np = np.array(vectors, dtype=np.float32)
    faiss_index.add(vectors_np)


# ─── Search / Query ──────────────────────────────────────────
def perform_ftss_match(query: str, top_k: int) -> List[Hit]:
    """Keyword-based search using SQLite FTS5"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = """
      SELECT doc_id, source, snippet(docs, -1, '[', ']', '...', 5) AS snippet, bm25(docs) AS rank
      FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?
    """
    cur = conn.execute(sql, (query, top_k))
    
    results = []
    for row in cur:
        results.append(Hit(
            source_id=f"{row['source']}:{row['doc_id']}",
            snippet=row["snippet"],
            score=-row["rank"]
        ))

    conn.close()
    return results


def perform_faiss_search(query: str, initial_results: List[Hit], top_k: int) -> List[Hit]:
    """Semantic search using Faiss on initial keyword-based results"""
    q_vec = embedder.encode(query).astype(np.float32)
    distances, indices = faiss_index.search(np.array([q_vec]), top_k)

    final_results = []
    for i, idx in enumerate(indices[0]):
        doc = metadata[idx]
        final_results.append(Hit(
            source_id=f"{doc['source']}:{doc['id']}",
            snippet=doc["text"],
            score=distances[0][i]
        ))

    return final_results + initial_results[:top_k]  # Combine with initial keyword search


def hybrid_search(query: str, top_k: int) -> List[Hit]:
    """Runs FTS5 keyword match first, then refines with Faiss"""
    initial_results = perform_ftss_match(query, top_k * 2)  # Get more to refine
    final_results = perform_faiss_search(query, initial_results, top_k)
    return sorted(final_results, key=lambda x: x.score, reverse=True)[:top_k]


# ─── FastAPI Endpoints ───────────────────────────────────────
@app.post("/ingest")
def ingest(background: BackgroundTasks):
    """Triggers background ingestion & indexing"""
    background.add_task(ingest_data)
    return {"status": "indexing started"}

@app.post("/query", response_model=QueryOut)
def query(q: QueryIn):
    """Runs hybrid search (FTS5 + Faiss)"""
    hits = hybrid_search(q.query, q.top_k)
    return QueryOut(hits=hits)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
