import struct
import numpy as np
import json
import urllib.request
import re
import threading

from config import (
    DB_PATH,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    OLLAMA_EMBED_URL,
    OLLAMA_EMBED_BATCH_URL,
    EMBED_TIMEOUT,
    connect_db,
    ensure_fts,
)

class VedicSearchEngine:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.books = {}      # book_id -> book_metadata
        self.page_map = []   # List of dicts with page metadata: {book_id, page_num, raw_text}
        self.embeddings = None # NumPy matrix [N, EMBEDDING_DIM]
        self.last_page_count = -1 # Cache count to avoid redundant reads
        # Guards index mutation: FastAPI runs sync endpoints in a threadpool, so
        # concurrent reload()/search calls would otherwise race on the arrays.
        self._lock = threading.Lock()
        # Caches query-text -> embedding. Embedding on the Pi CPU is ~3s each, so
        # caching makes repeated/identical queries (common across predictions)
        # effectively free.
        self._embed_cache = {}
        self.load_index()
        # Build/sync the FTS5 keyword index once at startup (idempotent).
        try:
            conn = connect_db(self.db_path)
            try:
                ensure_fts(conn)
            finally:
                conn.close()
        except Exception as e:
            print(f"FTS index setup skipped: {e}")

    def get_ollama_embedding(self, text):
        """Generate an embedding using the local Ollama instance.

        Returns None on failure so callers can distinguish a real vector from a
        silent all-zero fallback (which would otherwise produce garbage hits).
        """
        data = {
            "model": EMBEDDING_MODEL,
            "prompt": text
        }
        req = urllib.request.Request(
            OLLAMA_EMBED_URL,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                embedding = res_data.get("embedding", [])
                return embedding if embedding else None
        except Exception as e:
            print(f"Error generating embedding in search engine: {e}")
            return None

    def get_ollama_embeddings_batch(self, texts):
        """
        Embed many texts in a single /api/embed round trip (the Pi computes them
        serially, but one HTTP call avoids per-request overhead). Results are
        cached by text. Returns a list aligned to `texts`, each a vector or None.
        """
        results = [None] * len(texts)
        to_embed = []      # texts needing a fresh embedding
        to_embed_idx = []  # their positions in `texts`

        for i, t in enumerate(texts):
            if t in self._embed_cache:
                results[i] = self._embed_cache[t]
            else:
                to_embed.append(t)
                to_embed_idx.append(i)

        if not to_embed:
            return results

        data = {"model": EMBEDDING_MODEL, "input": to_embed}
        req = urllib.request.Request(
            OLLAMA_EMBED_BATCH_URL,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            # Scale the timeout with batch size (serial CPU embedding).
            timeout = EMBED_TIMEOUT * max(1, len(to_embed))
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                embeddings = res_data.get("embeddings", []) or []
            for j, emb in enumerate(embeddings):
                if emb and len(emb) == EMBEDDING_DIM:
                    pos = to_embed_idx[j]
                    results[pos] = emb
                    self._embed_cache[to_embed[j]] = emb
        except Exception as e:
            print(f"Error generating batch embeddings: {e}")
            # Leave the uncached entries as None; callers fall back to sparse.
        return results

    def load_index(self):
        """Load books and page embeddings from the SQLite database into memory"""
        with self._lock:
            conn = None
            try:
                conn = connect_db(self.db_path)
                cursor = conn.cursor()

                # Fast count check for caching
                cursor.execute("SELECT count(*) FROM pages")
                page_count = cursor.fetchone()[0]

                # Check if tables exist and have entries. If matches cache, return immediately!
                if page_count == self.last_page_count and page_count > 0:
                    return

                # Load books
                books = {}
                cursor.execute("SELECT id, filename, title, total_pages FROM books")
                for row in cursor.fetchall():
                    books[row[0]] = {
                        "id": row[0],
                        "filename": row[1],
                        "title": row[2],
                        "total_pages": row[3]
                    }

                # Load pages
                cursor.execute("SELECT book_id, page_num, raw_text, embedding FROM pages")
                rows = cursor.fetchall()

                page_map = []
                emb_list = []

                for row in rows:
                    book_id, page_num, raw_text, emb_blob = row

                    # Deserialization of binary float BLOB
                    if emb_blob:
                        num_floats = len(emb_blob) // 4  # float is 4 bytes
                        embedding = list(struct.unpack(f"{num_floats}f", emb_blob))

                        # Ensure embedding has the expected dimensions
                        if len(embedding) == EMBEDDING_DIM:
                            text_lower = (raw_text or "").lower()
                            is_marriage = any(kw in text_lower for kw in [
                                "marriage", "spouse", "husband", "wife", "marital",
                                "vivaha", "koota", "porutham", "compatibility",
                                "agreement", "congenial", "7th house", "seventh house",
                                "7th bhava", "seventh bhava", "7th lord", "seventh lord",
                                "navamsha", "navamsa"
                            ])
                            page_map.append({
                                "book_id": book_id,
                                "page_num": page_num,
                                "raw_text": raw_text,
                                "is_marriage": is_marriage,
                                "book_title": books[book_id]["title"] if book_id in books else "Unknown Book"
                            })
                            emb_list.append(embedding)

                embeddings = None
                if emb_list:
                    embeddings = np.array(emb_list, dtype=np.float32)
                    # L2 normalize embeddings for fast cosine similarity via dot product
                    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                    # Avoid division by zero
                    norms[norms == 0] = 1.0
                    embeddings = embeddings / norms

                # Atomically swap in the freshly built index
                self.books = books
                self.page_map = page_map
                self.embeddings = embeddings
                self.last_page_count = page_count

                print(f"Loaded search index: {len(self.page_map)} pages from {len(self.books)} books.")
            except Exception as e:
                print(f"Error loading search index: {e}. Index might be empty or still ingesting.")
                # Preserve any previously loaded index rather than wiping it on a
                # transient read error.
            finally:
                if conn is not None:
                    conn.close()

    def reload(self):
        """Reload the search index to include newly ingested pages"""
        self.load_index()

    def dense_search(self, query_text, top_k=10, category=None):
        """Perform semantic cosine similarity search (embeds the query first)."""
        # Get query embedding. None / wrong-dim means the embedding service
        # failed; return nothing so hybrid_search falls back to sparse instead
        # of fabricating zero-score "matches".
        query_vector = self.get_ollama_embedding(query_text)
        return self.dense_search_with_vector(query_vector, top_k=top_k, category=category)

    def dense_search_with_vector(self, query_vector, top_k=10, category=None):
        """Cosine-similarity search from a precomputed query embedding."""
        if self.embeddings is None or len(self.page_map) == 0:
            return []
        if not query_vector or len(query_vector) != EMBEDDING_DIM:
            return []

        query_np = np.array(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query_np)
        if query_norm > 0:
            query_np = query_np / query_norm

        # Calculate dot product (cosine similarity of normalized vectors)
        similarities = np.dot(self.embeddings, query_np)

        if category == "marriage":
            for idx, page in enumerate(self.page_map):
                if not page.get("is_marriage"):
                    similarities[idx] = -1.0

        # Get top-K indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if category == "marriage" and not self.page_map[idx].get("is_marriage"):
                continue
            page_info = self.page_map[idx].copy()
            page_info["score"] = score
            page_info["type"] = "dense"
            results.append(page_info)

        return results

    def sparse_search(self, query_text, top_k=10, category=None):
        """
        BM25-ranked keyword search via the FTS5 index (pages_fts).
        Supports category-based filtering for faster, contextual subsets.
        """
        # \w (unicode) keeps Indic OCR terms; dedupe preserves first-seen order.
        words = re.findall(r"\w{3,}", query_text.lower())
        if not words:
            return []
        match_expr = " OR ".join(f'"{w}"' for w in dict.fromkeys(words))

        conn = None
        try:
            conn = connect_db(self.db_path)
            cursor = conn.cursor()
            
            sql = """
                SELECT p.book_id, p.page_num, p.raw_text, bm25(pages_fts) AS rank
                FROM pages_fts JOIN pages p ON p.id = pages_fts.rowid
                WHERE pages_fts MATCH ?
            """
            params = [match_expr]
            
            if category == "marriage":
                sql += """
                    AND (p.raw_text LIKE '%marriage%' OR p.raw_text LIKE '%wife%' OR p.raw_text LIKE '%husband%' 
                         OR p.raw_text LIKE '%spouse%' OR p.raw_text LIKE '%koota%' OR p.raw_text LIKE '%vivaha%' 
                         OR p.raw_text LIKE '%7th house%' OR p.raw_text LIKE '%seventh house%' OR p.raw_text LIKE '%7th lord%' 
                         OR p.raw_text LIKE '%seventh lord%' OR p.raw_text LIKE '%navamsha%' OR p.raw_text LIKE '%navamsa%' 
                         OR p.raw_text LIKE '%compatibility%' OR p.raw_text LIKE '%agreement%')
                """
                
            sql += """
                ORDER BY rank
                LIMIT ?
            """
            params.append(top_k)
            
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
        except Exception as e:
            print(f"Sparse (FTS) search failed: {e}")
            return []
        finally:
            if conn is not None:
                conn.close()

        results = []
        for book_id, page_num, raw_text, rank in rows:
            book_meta = self.books.get(book_id) if self.books else None
            results.append({
                "book_id": book_id,
                "page_num": page_num,
                "raw_text": raw_text,
                "book_title": book_meta["title"] if book_meta else "Unknown Book",
                # Flip BM25 cost into a positive relevance score for consistency.
                "score": -float(rank),
                "type": "sparse",
            })
        return results

    def hybrid_search(self, query_text, top_k=5, category=None):
        """
        Combine Dense (Semantic) and Sparse (Keyword) search results 
        using Reciprocal Rank Fusion (RRF) with optional category filtering
        """
        dense_results = self.dense_search(query_text, top_k=30, category=category)
        sparse_results = self.sparse_search(query_text, top_k=30, category=category)
        
        if not dense_results and not sparse_results:
            return []
            
        # Reciprocal Rank Fusion (RRF) scoring
        rrf_scores = {}  # key: (book_id, page_num) -> float
        metadata = {}    # key: (book_id, page_num) -> dict
        
        # Dense ranking
        for rank, res in enumerate(dense_results):
            key = (res["book_id"], res["page_num"])
            # Constant 60 is typical in RRF
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (60.0 + rank))
            if key not in metadata:
                metadata[key] = res
                
        # Sparse ranking
        for rank, res in enumerate(sparse_results):
            key = (res["book_id"], res["page_num"])
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (60.0 + rank))
            if key not in metadata:
                metadata[key] = res
                
        # Sort by RRF score descending
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        
        final_results = []
        for key in sorted_keys[:top_k]:
            res = metadata[key].copy()
            res["rrf_score"] = rrf_scores[key]
            # Include original dense similarity if available
            dense_match = next((d for d in dense_results if d["book_id"] == key[0] and d["page_num"] == key[1]), None)
            res["dense_score"] = dense_match["score"] if dense_match else 0.0
            final_results.append(res)
            
        return final_results
