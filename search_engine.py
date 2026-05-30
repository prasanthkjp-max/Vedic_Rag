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
    EMBED_TIMEOUT,
    connect_db,
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
        self.load_index()

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
                            page_map.append({
                                "book_id": book_id,
                                "page_num": page_num,
                                "raw_text": raw_text,
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

    def dense_search(self, query_text, top_k=10):
        """Perform semantic cosine similarity search"""
        if self.embeddings is None or len(self.page_map) == 0:
            return []
            
        # Get query embedding. None / wrong-dim means the embedding service
        # failed; return nothing so hybrid_search falls back to sparse instead
        # of fabricating zero-score "matches".
        query_vector = self.get_ollama_embedding(query_text)
        if not query_vector or len(query_vector) != EMBEDDING_DIM:
            return []
            
        query_np = np.array(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query_np)
        if query_norm > 0:
            query_np = query_np / query_norm
            
        # Calculate dot product (cosine similarity of normalized vectors)
        similarities = np.dot(self.embeddings, query_np)
        
        # Get top-K indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            page_info = self.page_map[idx].copy()
            page_info["score"] = score
            page_info["type"] = "dense"
            results.append(page_info)
            
        return results

    def sparse_search(self, query_text, top_k=10):
        """Perform simple keyword occurrence matching across the raw text"""
        if not self.page_map:
            return []
            
        # Tokenize and clean query into words (case insensitive, ignoring very short words)
        words = re.findall(r"\b\w{3,}\b", query_text.lower())
        if not words:
            return []
            
        scored_results = []
        for page in self.page_map:
            text_lower = page["raw_text"].lower()
            score = 0
            
            # Simple TF-like score based on keyword match frequencies
            for word in words:
                matches = len(re.findall(re.escape(word), text_lower))
                if matches > 0:
                    score += matches * 1.5  # weigh exact matches
                    
            if score > 0:
                page_info = page.copy()
                page_info["score"] = score
                page_info["type"] = "sparse"
                scored_results.append(page_info)
                
        # Sort by score descending
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:top_k]

    def hybrid_search(self, query_text, top_k=5):
        """
        Combine Dense (Semantic) and Sparse (Keyword) search results 
        using Reciprocal Rank Fusion (RRF)
        """
        dense_results = self.dense_search(query_text, top_k=30)
        sparse_results = self.sparse_search(query_text, top_k=30)
        
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
