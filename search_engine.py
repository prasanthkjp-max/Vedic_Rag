import struct
import numpy as np
import logging
import re
import threading

from config import (
    DB_RAG_PATH,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    EMBED_TIMEOUT,
    get_llm_client,
    connect_db,
    ensure_fts,
)

logger = logging.getLogger("vedic.search")

class VedicSearchEngine:
    def __init__(self, db_path=DB_RAG_PATH):
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
        self._embed_cache_max = 512  # bound memory across the process lifetime
        self.load_index()
        # Build/sync the FTS5 keyword index once at startup (idempotent).
        try:
            conn = connect_db(self.db_path)
            try:
                ensure_fts(conn)
            finally:
                conn.close()
        except Exception as e:
            logger.warning("FTS index setup skipped: %s", e)
        self._probe_embedding_dim()

    def _probe_embedding_dim(self):
        """Warn loudly if the embed model's output dim != configured EMBEDDING_DIM.

        A mismatch is otherwise silent: every vector fails the len()==DIM guard
        and is dropped, so the index loads zero pages and search dies quietly.
        Best-effort — skipped if OpenRouter is unreachable/unconfigured at startup.
        """
        try:
            # Use the RAW embed call (get_embedding would filter a mismatch to
            # None, hiding the very thing we're probing for).
            client = get_llm_client()
            resp = client.with_options(timeout=EMBED_TIMEOUT).embeddings.create(
                model=EMBEDDING_MODEL, input="dimension probe"
            )
            vec = resp.data[0].embedding if resp.data else []
            if vec and len(vec) != EMBEDDING_DIM:
                logger.error(
                    "Embedding model %r returns %d dims but EMBEDDING_DIM=%d — "
                    "every embedding will be DROPPED and search will return nothing. "
                    "Set VEDIC_EMBED_DIM=%d.",
                    EMBEDDING_MODEL, len(vec), EMBEDDING_DIM, len(vec),
                )
        except Exception:
            pass  # OpenRouter down/unconfigured at startup; dim is re-checked per call.

    def _cache_embedding(self, text, embedding):
        """Insert into the query-embedding cache, evicting oldest entries when full."""
        if len(self._embed_cache) >= self._embed_cache_max:
            # dicts preserve insertion order; drop the oldest entry (approx. FIFO).
            self._embed_cache.pop(next(iter(self._embed_cache)))
        self._embed_cache[text] = embedding

    @staticmethod
    def _embed_call(inputs, timeout):
        """Call the OpenRouter embeddings endpoint (OpenAI SDK) for one string or
        a list of strings. Returns a list of vectors aligned to `inputs`, or None
        on any failure (logged) so callers can fall back to sparse search."""
        try:
            client = get_llm_client()
            resp = client.with_options(timeout=timeout).embeddings.create(
                model=EMBEDDING_MODEL, input=inputs
            )
            # OpenAI/OpenRouter may not preserve order; sort by index to be safe.
            data = sorted(resp.data, key=lambda d: d.index)
            return [d.embedding for d in data]
        except Exception as e:
            logger.warning("OpenRouter embedding error (model=%s): %s", EMBEDDING_MODEL, e)
            return None

    def get_embedding(self, text):
        """Generate a single embedding via OpenRouter.

        Returns None on failure so callers can distinguish a real vector from a
        silent all-zero fallback (which would otherwise produce garbage hits).
        """
        # Reuse the shared text->vector cache (the batch path populates it too),
        # so repeated/identical queries skip the network round trip.
        if text in self._embed_cache:
            return self._embed_cache[text]
        vectors = self._embed_call(text, EMBED_TIMEOUT)
        if not vectors:
            return None
        embedding = vectors[0]
        if embedding and len(embedding) == EMBEDDING_DIM:
            self._cache_embedding(text, embedding)
            return embedding
        # Wrong-dimension vectors are failures too, per the docstring.
        return None

    def get_embeddings_batch(self, texts):
        """
        Embed many texts in a single OpenRouter round trip. Results are cached by
        text. Returns a list aligned to `texts`, each a vector or None.
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

        # Scale the timeout with batch size, but cap it so a huge batch can't
        # block a request thread indefinitely.
        timeout = min(EMBED_TIMEOUT * max(1, len(to_embed) // 8 + 1), 120)
        embeddings = self._embed_call(to_embed, timeout)
        if embeddings:
            for j, emb in enumerate(embeddings):
                if emb and len(emb) == EMBEDDING_DIM:
                    pos = to_embed_idx[j]
                    results[pos] = emb
                    self._cache_embedding(to_embed[j], emb)
        # else: uncached entries stay None; callers fall back to sparse.
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
                mismatched_count = 0
                mismatched_dims = set()

                for row in rows:
                    book_id, page_num, raw_text, emb_blob = row

                    # Deserialization of binary float BLOB. Guard per row so one
                    # corrupt/truncated blob skips that page instead of aborting
                    # the whole index load.
                    if emb_blob:
                        try:
                            num_floats = len(emb_blob) // 4  # float is 4 bytes
                            embedding = list(struct.unpack(f"{num_floats}f", emb_blob[: num_floats * 4]))
                        except struct.error as e:
                            logger.warning("Skipping corrupt embedding (book %s, page %s): %s", book_id, page_num, e)
                            continue

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
                        else:
                            mismatched_count += 1
                            mismatched_dims.add(len(embedding))

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

                if mismatched_count > 0:
                    logger.warning(
                        "Skipped %d pages because their database embedding dimensions (%r) "
                        "did not match EMBEDDING_DIM (%d). These pages require re-embedding (repair).",
                        mismatched_count, list(mismatched_dims), EMBEDDING_DIM
                    )

                logger.info("Loaded search index: %d pages from %d books.", len(self.page_map), len(self.books))
            except Exception as e:
                logger.warning("Error loading search index: %s. Index might be empty or still ingesting.", e)
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
        query_vector = self.get_embedding(query_text)
        return self.dense_search_with_vector(query_vector, top_k=top_k, category=category)

    def dense_search_with_vector(self, query_vector, top_k=10, category=None):
        """Cosine-similarity search from a precomputed query embedding."""
        # Snapshot the index under the lock so a concurrent reload() can't swap
        # page_map out from under the similarity matrix mid-search.
        with self._lock:
            embeddings = self.embeddings
            page_map = self.page_map
        if embeddings is None or len(page_map) == 0:
            return []
        if not query_vector or len(query_vector) != EMBEDDING_DIM:
            return []

        query_np = np.array(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query_np)
        if query_norm > 0:
            query_np = query_np / query_norm

        # Calculate dot product (cosine similarity of normalized vectors)
        similarities = np.dot(embeddings, query_np)

        if category == "marriage":
            for idx, page in enumerate(page_map):
                if not page.get("is_marriage"):
                    similarities[idx] = -1.0

        # Get top-K indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if category == "marriage" and not page_map[idx].get("is_marriage"):
                continue
            page_info = page_map[idx].copy()
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
            logger.warning("Sparse (FTS) search failed: %s", e)
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
