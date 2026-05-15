"""
endpoint_5F_RAG_Assistente.py — Porta 12000
Assistente virtuale SafeClaim — KB da MongoDB (Proto_Knowledge_SC)
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from google import genai
from pymongo import MongoClient
import numpy as np
import os
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────
#  GEMINI
# ─────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = "gemini-2.5-flash"
_gemini_client = None

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client

# ─────────────────────────────────────────────
#  MONGODB
# ─────────────────────────────────────────────

MONGO_URI     = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "safeclaim")
COLLECTION_KB = "Proto_Knowledge_SC"
_mongo_client = None

def get_db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI)
    return _mongo_client[MONGO_DB_NAME]

# ─────────────────────────────────────────────
#  KNOWLEDGE BASE — stato globale
# ─────────────────────────────────────────────

knowledge_base: list[dict] = []
vectorizer                 = None
tfidf_matrix               = None


def _testo_retrieval(doc: dict) -> str:
    """Testo usato per il calcolo TF-IDF (titolo + contenuto + tags + FAQ)."""
    parti = []
    if doc.get("titolo"):    parti.append(doc["titolo"])
    if doc.get("contenuto"): parti.append(doc["contenuto"])
    if doc.get("tags"):      parti.append(" ".join(doc["tags"]))
    for faq in doc.get("faq", []):
        if faq.get("domanda"):  parti.append(faq["domanda"])
        if faq.get("risposta"): parti.append(faq["risposta"])
    return " ".join(parti)


def _testo_contesto(doc: dict) -> str:
    """Testo formattato passato a Gemini come contesto."""
    parti = [f"[{doc.get('titolo', '')}]"]
    if doc.get("contenuto"):
        parti.append(doc["contenuto"])
    for faq in doc.get("faq", []):
        d, r = faq.get("domanda", ""), faq.get("risposta", "")
        if d and r:
            parti.append(f"D: {d}\nR: {r}")
    return "\n".join(parti)


def carica_knowledge_base() -> int:
    global knowledge_base, vectorizer, tfidf_matrix

    try:
        docs = list(
            get_db()[COLLECTION_KB].find({"pubblicato": True, "attivo": True})
        )

        if not docs:
            print("[KB] Nessun documento trovato in Proto_Knowledge_SC")
            knowledge_base = []
            return 0

        knowledge_base = [
            {
                "_id":             str(doc["_id"]),
                "titolo":          doc.get("titolo", ""),
                "categoria":       doc.get("categoria", ""),
                "testo_retrieval": _testo_retrieval(doc),
                "testo_contesto":  _testo_contesto(doc),
            }
            for doc in docs
        ]

        corpus = [c["testo_retrieval"] for c in knowledge_base]
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), min_df=1,
            strip_accents="unicode", lowercase=True,
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)

        print(f"[KB] {len(knowledge_base)} documenti — {tfidf_matrix.shape[1]} termini TF-IDF")
        return len(knowledge_base)

    except Exception as e:
        print(f"[KB][ERRORE] {e}")
        knowledge_base = []
        return 0


print("Caricamento Knowledge Base da MongoDB...")
carica_knowledge_base()

# ─────────────────────────────────────────────
#  RETRIEVAL
# ─────────────────────────────────────────────

def recupera_chunk_rilevanti(domanda: str, top_k: int = 3) -> list[dict]:
    if vectorizer is None or tfidf_matrix is None or not knowledge_base:
        return []

    query_vec  = vectorizer.transform([domanda])
    similarita = cosine_similarity(query_vec, tfidf_matrix).flatten()
    indici_top = np.argsort(similarita)[::-1][:top_k]

    return [
        {
            "titolo":         knowledge_base[i]["titolo"],
            "testo_contesto": knowledge_base[i]["testo_contesto"],
            "score":          round(float(similarita[i]), 4),
        }
        for i in indici_top
        if similarita[i] > 0.01
    ]

# ─────────────────────────────────────────────
#  GEMINI — generazione risposta
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Sei SafeBot, l'assistente virtuale di SafeClaim, piattaforma italiana
di gestione sinistri assicurativi. Aiuta gli automobilisti a usare il sito.
Rispondi in italiano, in modo chiaro e professionale.
Usa solo le informazioni nel contesto fornito.
Se non le trovi, dì che non lo sai e suggerisci il supporto SafeClaim.
Non inventare mai. Massimo 150 parole."""


def genera_risposta_gemini(domanda: str, chunk_rilevanti: list[dict]) -> str:
    if not chunk_rilevanti:
        contesto = "Nessuna informazione specifica trovata nella Knowledge Base."
    else:
        contesto = "\n\n".join(
            f"Informazione {i} — {c['titolo']}:\n{c['testo_contesto']}"
            for i, c in enumerate(chunk_rilevanti, 1)
        )

    prompt = f"""{SYSTEM_PROMPT}

CONTESTO:
{contesto}

DOMANDA:
{domanda}

RISPOSTA:"""

    for tentativo in range(1, 4):
        try:
            return get_gemini_client().models.generate_content(
                model=GEMINI_MODEL, contents=prompt
            ).text.strip()
        except Exception as e:
            print(f"[GEMINI] Tentativo {tentativo}/3: {e}")
            if tentativo < 3:
                time.sleep(5 * tentativo)

    return "Errore nella generazione. Contatta il supporto SafeClaim."

# ─────────────────────────────────────────────
#  ENDPOINT
# ─────────────────────────────────────────────

@app.route("/assistente/chat", methods=["POST"])
def chat_assistente():
    data    = request.get_json()
    domanda = (data or {}).get("domanda", "").strip()

    if not domanda:
        return jsonify({"error": "Campo 'domanda' obbligatorio"}), 400
    if len(domanda) > 500:
        return jsonify({"error": "Domanda troppo lunga (max 500 caratteri)"}), 400

    chunk    = recupera_chunk_rilevanti(domanda, top_k=3)
    risposta = genera_risposta_gemini(domanda, chunk)

    return jsonify({
        "risposta":    risposta,
        "chunk_usati": [{"titolo": c["titolo"], "score": c["score"]} for c in chunk],
        "status":      "ok",
    }), 200


@app.route("/assistente/reload", methods=["POST"])
def reload_kb():
    """Ricarica la KB da MongoDB senza riavviare."""
    n = carica_knowledge_base()
    return jsonify({"status": "ok", "documenti": n}), 200


@app.route("/assistente/health", methods=["GET"])
def health_check():
    return jsonify({
        "status":        "online",
        "modello":       GEMINI_MODEL,
        "kb_chunks":     len(knowledge_base),
        "tfidf_termini": tfidf_matrix.shape[1] if tfidf_matrix is not None else 0,
        "fonte":         f"MongoDB/{COLLECTION_KB}",
    }), 200


@app.route("/assistente/argomenti", methods=["GET"])
def lista_argomenti():
    return jsonify({
        "argomenti": [c["titolo"] for c in knowledge_base],
        "totale":    len(knowledge_base),
    }), 200


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=12000)