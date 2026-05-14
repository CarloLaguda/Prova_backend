"""
endpoint_5F_Sinistri_User.py — Branch main
Gestione sinistri, soccorso e veicoli.
Le immagini vengono salvate su Cloudinary tramite Storage.py,
poi analizzate in modo asincrono da Gemini Vision (Google).

Collezioni MongoDB (nuovo server):
  Proto_Sinistro_SC   — sinistri
  Proto_Intervento_SC — interventi/pratiche
  Proto_Documenti_SC  — documenti/perizie
  Soccorso            — richieste soccorso (mirror di MySQL)
"""

from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
from datetime import datetime, UTC, timezone
import threading
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types
    _GENAI_IMPORTATO = True
except Exception as _e:
    print(f"⚠️  Impossibile importare google-genai: {_e}")
    _GENAI_IMPORTATO = False

try:
    from Storage import carica_immagine
    _STORAGE_DISPONIBILE = True
except Exception as _e:
    print(f"⚠️  Impossibile importare Storage.py: {_e}")
    _STORAGE_DISPONIBILE = False

app = Flask(__name__)

# ─────────────────────────────────────────────
#  CORS — configurazione esplicita per Codespaces
#  flask-cors gestisce il preflight OPTIONS e
#  aggiunge gli header su ogni risposta.
# ─────────────────────────────────────────────

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    supports_credentials=False,
    max_age=600,
)


# Fallback: intercetta ogni OPTIONS e restituisce 200 anche se flask-cors
# non lo cattura (può succedere su alcuni reverse-proxy di Codespaces).
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        resp = make_response("", 200)
        resp.headers["Access-Control-Allow-Origin"]  = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
        resp.headers["Access-Control-Max-Age"]       = "600"
        return resp


# Aggiunge gli header CORS su ogni risposta (doppio livello di sicurezza).
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
    return response


# ─────────────────────────────────────────────
#  CONFIGURAZIONE MYSQL
# ─────────────────────────────────────────────

MYSQL_CONFIG = {
    "host":     os.getenv("MYSQL_HOST"),
    "port":     int(os.getenv("MYSQL_PORT", 3306)),
    "user":     os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
}

def get_mysql():
    try:
        return mysql.connector.connect(**MYSQL_CONFIG)
    except Exception as e:
        print(f"❌ Errore connessione MySQL: {e}")
        raise

# ─────────────────────────────────────────────
#  CONFIGURAZIONE MONGODB — nuovo server
# ─────────────────────────────────────────────

col_interventi = None   # Proto_Intervento_SC  (ex Pratica)
col_documenti  = None   # Proto_Documenti_SC    (ex Perizia)
col_sinistri   = None   # Proto_Sinistro_SC     (ex Sinistri)
soccorso_col   = None   # Soccorso
_MONGO_DISPONIBILE = False

try:
    MONGO_URI    = os.getenv("MONGO_URI")
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo_db     = mongo_client["safeclaim"]
    col_interventi = mongo_db["Proto_Intervento_SC"]
    col_documenti  = mongo_db["Proto_Documenti_SC"]
    col_sinistri   = mongo_db["Proto_Sinistro_SC"]
    soccorso_col   = mongo_db["Soccorso"]
    mongo_client.admin.command("ping")
    _MONGO_DISPONIBILE = True
    print("✅ Connessione a MongoDB (safeclaim) riuscita!")
except Exception as e:
    print(f"❌ Errore connessione MongoDB: {e} — le rotte MongoDB risponderanno con 503.")

# ─────────────────────────────────────────────
#  CONFIGURAZIONE GEMINI VISION
# ─────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = "gemini-2.5-flash"

gemini_client      = None
gemini_disponibile = False

if _GENAI_IMPORTATO:
    try:
        gemini_client      = genai.Client(api_key=GEMINI_API_KEY)
        gemini_disponibile = True
        print("✅ Gemini Vision inizializzato correttamente.")
    except Exception as e:
        print(f"⚠️  Gemini Vision non disponibile: {e}")
else:
    print("⚠️  Gemini Vision non disponibile (libreria non importata).")

PROMPT_PERITO = (
    "Agisci come un perito assicurativo esperto. Analizza l'immagine e descrivi l'incidente "
    "identificando: 1. Punto d'impatto principale. 2. Componenti danneggiati (es. paraurti, "
    "gruppi ottici, cristalli). 3. Entità del danno (graffio, ammaccatura, deformazione strutturale). "
    "Usa un linguaggio tecnico."
)

# ─────────────────────────────────────────────
#  HELPER
# ─────────────────────────────────────────────

def _richiedi_mongo():
    if not _MONGO_DISPONIBILE:
        return jsonify({"error": "Database MongoDB non disponibile. Riprova più tardi."}), 503
    return None


def _serializza_sinistro(s: dict) -> dict:
    """Serializza un documento Proto_Sinistro_SC aggiungendo alias per compatibilità frontend."""
    s["_id"] = str(s["_id"])
    if "data_sinistro" in s:
        if isinstance(s["data_sinistro"], datetime):
            s["data_sinistro"] = s["data_sinistro"].isoformat()
        s["data_evento"] = s["data_sinistro"]
    if "descrizione_danno" in s:
        s["descrizione"] = s["descrizione_danno"]
    if "stato_sinistro" in s:
        s["stato"] = s["stato_sinistro"]
    for campo in ("data_inserimento", "data_aggiornamento", "data_assegnazione"):
        if isinstance(s.get(campo), datetime):
            s[campo] = s[campo].isoformat()
    analisi = s.get("analisi_ai")
    if analisi and isinstance(analisi.get("data_analisi"), datetime):
        analisi["data_analisi"] = analisi["data_analisi"].isoformat()
    if not analisi:
        s["analisi_ai"] = {"stato": "non_avviata"}
    if "immagini" not in s or s["immagini"] is None:
        s["immagini"] = []
    return s

# ─────────────────────────────────────────────
#  ANALISI AI IN BACKGROUND
# ─────────────────────────────────────────────

def analizza_immagine_ai(sinistro_id: str, image_url: str):
    import time

    if not gemini_disponibile:
        print(f"[AI] Gemini non disponibile — sinistro {sinistro_id} non analizzato.")
        try:
            col_sinistri.update_one(
                {"_id": ObjectId(sinistro_id)},
                {"$set": {"analisi_ai": {
                    "stato":        "non_disponibile",
                    "errore":       "Gemini API non configurata o chiave non valida.",
                    "data_analisi": datetime.now(UTC)
                }}}
            )
        except Exception as mongo_err:
            print(f"[AI] Impossibile aggiornare MongoDB: {mongo_err}")
        return

    MAX_TENTATIVI = 3
    ATTESA_BASE   = 15

    for tentativo in range(1, MAX_TENTATIVI + 1):
        try:
            print(f"[AI] Tentativo {tentativo}/{MAX_TENTATIVI} per sinistro {sinistro_id}...")
            import requests as http_requests
            risposta_http = http_requests.get(image_url, timeout=15)
            risposta_http.raise_for_status()

            risposta = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    PROMPT_PERITO,
                    types.Part.from_bytes(
                        data=risposta_http.content,
                        mime_type="image/jpeg"
                    )
                ]
            )
            risultato_ai = risposta.text.strip()
            print(f"✅ [AI] Analisi completata per sinistro {sinistro_id}")

            col_sinistri.update_one(
                {"_id": ObjectId(sinistro_id)},
                {"$set": {"analisi_ai": {
                    "testo":        risultato_ai,
                    "modello":      GEMINI_MODEL,
                    "data_analisi": datetime.now(UTC),
                    "stato":        "completata"
                }}}
            )
            return

        except Exception as e:
            print(f"[AI] Errore tentativo {tentativo}/{MAX_TENTATIVI}: {e}")
            if tentativo < MAX_TENTATIVI:
                attesa = ATTESA_BASE * tentativo
                print(f"[AI] Attendo {attesa}s prima di ritentare...")
                time.sleep(attesa)
            else:
                try:
                    col_sinistri.update_one(
                        {"_id": ObjectId(sinistro_id)},
                        {"$set": {"analisi_ai": {
                            "stato":        "errore",
                            "errore":       str(e),
                            "data_analisi": datetime.now(UTC)
                        }}}
                    )
                except Exception as mongo_err:
                    print(f"[AI] Impossibile aggiornare MongoDB dopo errore: {mongo_err}")

# ─────────────────────────────────────────────
#  ROTTE — SINISTRI
# ─────────────────────────────────────────────

@app.route("/sinistro", methods=["POST"])
def apri_sinistro():
    err = _richiedi_mongo()
    if err:
        return err

    data = request.json
    required = ["automobilista_id", "targa"]
    if not any(k in data for k in ("data_evento", "data_sinistro")):
        return jsonify({"error": "Campo obbligatorio mancante: data_evento o data_sinistro"}), 400
    if not any(k in data for k in ("descrizione", "descrizione_danno")):
        return jsonify({"error": "Campo obbligatorio mancante: descrizione o descrizione_danno"}), 400
    if not all(k in data for k in required):
        return jsonify({"error": "Campi obbligatori mancanti: automobilista_id, targa"}), 400

    posizione = None
    geo = data.get("geolocalizzazione")
    if isinstance(geo, dict):
        lat = geo.get("latitudine", geo.get("lat"))
        lng = geo.get("longitudine", geo.get("lng"))
    else:
        lat = data.get("latitudine", data.get("lat"))
        lng = data.get("longitudine", data.get("lng"))

    if lat is not None and lng is not None:
        try:
            posizione = {"latitudine": float(lat), "longitudine": float(lng)}
        except (TypeError, ValueError):
            return jsonify({"error": "Dati di geolocalizzazione non validi"}), 400

    data_raw = data.get("data_sinistro") or data.get("data_evento")
    try:
        data_sinistro_dt = datetime.fromisoformat(data_raw).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return jsonify({"error": "Formato data non valido. Usa ISO 8601."}), 400

    descrizione_danno = data.get("descrizione_danno") or data.get("descrizione", "")

    try:
        nuovo_sinistro = {
            "automobilista_id":       data["automobilista_id"],
            "targa":                  data["targa"],
            "modello_veicolo":        data.get("modello_veicolo", ""),
            "data_sinistro":          data_sinistro_dt,
            "descrizione_danno":      descrizione_danno,
            "stato_sinistro":         "APERTO",
            "attivo":                 True,
            "priorita":               data.get("priorita", "normale"),
            "officina_id":            data.get("officina_id"),
            "compagnia_assicurativa": data.get("compagnia_assicurativa", ""),
            "numero_sinistro":        data.get("numero_sinistro", ""),
            "telaio":                 data.get("telaio", ""),
            "cliente":                data.get("cliente", ""),
            "note":                   data.get("note", ""),
            "contatto_cliente":       data.get("contatto_cliente", {}),
            "preventivo": {
                "data":            None,
                "costo_totale":    None,
                "ore_manodopera":  None,
                "giorni_previsti": None,
                "stato":           "da_creare",
                "dettaglio_voci":  [],
                "fattura":         None
            },
            "data_inserimento": datetime.now(UTC),
            "immagini":         [],
            "analisi_ai":       None,
        }
        if posizione is not None:
            nuovo_sinistro["geolocalizzazione"] = posizione

        result = col_sinistri.insert_one(nuovo_sinistro)
        return jsonify({"status": "success", "mongo_id": str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sinistro/<sinistro_id>", methods=["PUT"])
def aggiorna_sinistro(sinistro_id):
    err = _richiedi_mongo()
    if err:
        return err

    if not ObjectId.is_valid(sinistro_id):
        return jsonify({"error": "ID non valido"}), 400
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dati mancanti"}), 400

    update_fields = {"data_aggiornamento": datetime.now(UTC)}

    if "descrizione_danno" in data:
        update_fields["descrizione_danno"] = data["descrizione_danno"]
    elif "descrizione" in data:
        update_fields["descrizione_danno"] = data["descrizione"]

    if "stato_sinistro" in data:
        update_fields["stato_sinistro"] = data["stato_sinistro"]
    elif "stato" in data:
        update_fields["stato_sinistro"] = data["stato"]

    for campo in ("priorita", "officina_id", "note", "contatto_cliente",
                  "compagnia_assicurativa", "numero_sinistro"):
        if campo in data:
            update_fields[campo] = data[campo]

    if "preventivo" in data:
        for k, v in data["preventivo"].items():
            update_fields[f"preventivo.{k}"] = v

    try:
        col_sinistri.update_one(
            {"_id": ObjectId(sinistro_id)},
            {"$set": update_fields}
        )
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sinistri", methods=["GET"])
def get_tutti_sinistri():
    err = _richiedi_mongo()
    if err:
        return err

    try:
        filtro = {}
        automobilista_id = request.args.get("automobilista_id")
        if automobilista_id:
            filtro["automobilista_id"] = int(automobilista_id)

        sinistri = list(col_sinistri.find(filtro).sort("data_inserimento", DESCENDING))
        return jsonify([_serializza_sinistro(s) for s in sinistri]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sinistro/<sinistro_id>", methods=["GET"])
def get_sinistro_by_id(sinistro_id):
    err = _richiedi_mongo()
    if err:
        return err

    if not ObjectId.is_valid(sinistro_id):
        return jsonify({"error": "ID sinistro non valido"}), 400
    try:
        s = col_sinistri.find_one({"_id": ObjectId(sinistro_id)})
        if not s:
            return jsonify({"error": "Sinistro non trovato"}), 404
        return jsonify(_serializza_sinistro(s)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sinistro/<sinistro_id>", methods=["DELETE"])
def elimina_sinistro(sinistro_id):
    err = _richiedi_mongo()
    if err:
        return err

    if not ObjectId.is_valid(sinistro_id):
        return jsonify({"error": "ID sinistro non valido"}), 400
    try:
        result = col_sinistri.delete_one({"_id": ObjectId(sinistro_id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Sinistro non trovato"}), 404
        interventi_eliminati = col_interventi.delete_many({"sinistro_id": sinistro_id})
        return jsonify({
            "status":               "eliminato",
            "id":                   sinistro_id,
            "interventi_eliminati": interventi_eliminati.deleted_count
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
#  ROTTE — UPLOAD IMMAGINI + ANALISI AI
# ─────────────────────────────────────────────

@app.route("/sinistro/<sinistro_id>/immagini", methods=["POST"])
def aggiungi_immagine(sinistro_id):
    err = _richiedi_mongo()
    if err:
        return err

    if not ObjectId.is_valid(sinistro_id):
        return jsonify({"error": "ID sinistro non valido"}), 400

    if not _STORAGE_DISPONIBILE:
        return jsonify({"error": "Storage Cloudinary non disponibile."}), 503

    if "immagini" not in request.files and "immagine" not in request.files:
        return jsonify({"error": "Dati immagine mancanti"}), 400

    files = request.files.getlist("immagini") or [request.files.get("immagine")]

    try:
        sinistro = col_sinistri.find_one({"_id": ObjectId(sinistro_id)})
        if not sinistro:
            return jsonify({"error": "Sinistro non trovato"}), 404

        immagini_caricate = []
        for file in files:
            print(f"☁️  Caricamento immagine su Cloudinary per sinistro {sinistro_id}...")
            info_cloudinary = carica_immagine(file.read(), sinistro_id)
            print(f"✅ Immagine caricata: {info_cloudinary['secure_url']}")
            immagini_caricate.append({
                "url":       info_cloudinary["secure_url"],
                "public_id": info_cloudinary["public_id"]
            })
            if gemini_disponibile:
                thread = threading.Thread(
                    target=analizza_immagine_ai,
                    args=(sinistro_id, info_cloudinary["secure_url"]),
                    daemon=True
                )
                thread.start()

        stato_analisi = "in_elaborazione" if gemini_disponibile else "non_disponibile"

        col_sinistri.update_one(
            {"_id": ObjectId(sinistro_id)},
            {
                "$push": {"immagini": {"$each": immagini_caricate}},
                "$set":  {"analisi_ai": {
                    "stato":      stato_analisi,
                    "data_avvio": datetime.now(UTC)
                }}
            }
        )

        return jsonify({
            "status":           "accepted",
            "id_sinistro":      sinistro_id,
            "immagini":         [i["url"] for i in immagini_caricate],
            "messaggio":        f"{len(immagini_caricate)} immagini salvate."
                                + (" Analisi AI avviata in background." if gemini_disponibile
                                   else " Analisi AI non disponibile."),
            "analisi_ai_stato": stato_analisi
        }), 202

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sinistro/<sinistro_id>/analisi", methods=["GET"])
def get_analisi_ai(sinistro_id):
    err = _richiedi_mongo()
    if err:
        return err

    if not ObjectId.is_valid(sinistro_id):
        return jsonify({"error": "ID non valido"}), 400
    try:
        sinistro = col_sinistri.find_one(
            {"_id": ObjectId(sinistro_id)},
            {"analisi_ai": 1}
        )
        if not sinistro:
            return jsonify({"error": "Sinistro non trovato"}), 404
        analisi = sinistro.get("analisi_ai")
        if not analisi:
            return jsonify({"stato": "non_avviata"}), 200
        return jsonify(analisi), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
#  ROTTE — SOCCORSO
# ─────────────────────────────────────────────

@app.route("/soccorso", methods=["POST"])
def crea_richiesta_soccorso():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Body JSON mancante o malformato"}), 400

    targa           = data.get("targa")
    id_sinistro     = data.get("id_sinistro")
    id_officina     = data.get("id_officina")
    lat             = data.get("lat")
    lon             = data.get("lon")
    via             = data.get("via")
    orario_arrivo   = data.get("orario_arrivo")
    durata_soccorso = data.get("durata_soccorso")

    if not targa:
        return jsonify({"error": "Targa obbligatoria"}), 400

    conn = None
    try:
        conn   = get_mysql()
        cursor = conn.cursor(dictionary=True)

        # 1. Recuperiamo i dati del veicolo e dell'automobilista tramite la targa
        cursor.execute("""
            SELECT v.id AS veicolo_id, a.id AS automobilista_id
            FROM Veicolo v
            JOIN Automobilista a ON v.automobilista_id = a.id
            WHERE v.targa = %s
        """, (targa,))

        veicolo = cursor.fetchone()
        if veicolo is None:
            return jsonify({"error": f"Veicolo con targa '{targa}' non trovato"}), 404

        now_utc = datetime.now(timezone.utc)

        # 2. INSERIMENTO SU MYSQL
        # IMPORTANTE: id_veicolo_soccorso è impostato a None (NULL) perché al momento della 
        # richiesta il carroattrezzi non è ancora stato assegnato. Passare l'ID del veicolo
        # privato qui causava l'errore 1452 di integrità referenziale.
        cursor.execute("""
            INSERT INTO Richiesta_Soccorso
            (id_sinistro, id_automobilista, id_officina, id_veicolo_soccorso,
             data_richiesta, orario_arrivo, durata_soccorso, stato)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            id_sinistro,
            veicolo["automobilista_id"],
            id_officina,
            None,  # Risolto: rimosso veicolo["veicolo_id"] che causava il crash
            now_utc,
            orario_arrivo,
            durata_soccorso,
            "in_attesa",
        ))

        richiesta_id = cursor.lastrowid
        conn.commit()

        # Gestione posizione per MongoDB
        posizione = None
        if lat is not None and lon is not None:
            posizione = {"tipo": "gps", "lat": lat, "lon": lon}
        elif via:
            posizione = {"tipo": "indirizzo", "via": via}

        # 3. INSERIMENTO SU MONGODB
        # Qui manteniamo l'ID del veicolo dell'utente (veicolo["veicolo_id"]) perché 
        # è utile per lo storico e non ha vincoli di foreign key.
        mongo_id = None
        if _MONGO_DISPONIBILE and soccorso_col is not None:
            res = soccorso_col.insert_one({
                "richiesta_mysql_id": richiesta_id,
                "id_sinistro":        id_sinistro,
                "id_automobilista":   veicolo["automobilista_id"],
                "id_officina":        id_officina,
                "id_veicolo_utente":  veicolo["veicolo_id"], # Chiave rinominata per chiarezza
                "targa":              targa,
                "posizione":          posizione,
                "orario_arrivo":      orario_arrivo,
                "durata_soccorso":    durata_soccorso,
                "stato":              "in_attesa",
                "data_richiesta":     now_utc,
            })
            mongo_id = str(res.inserted_id)

        return jsonify({
            "success":          True,
            "richiesta_id":     richiesta_id,
            "mongo_id":         mongo_id,
            "id_sinistro":      id_sinistro,
            "id_automobilista": veicolo["automobilista_id"],
            "id_officina":      id_officina,
            "id_veicolo_utente":veicolo["veicolo_id"],
            "posizione":        posizione,
            "orario_arrivo":    orario_arrivo,
            "durata_soccorso":  durata_soccorso,
            "stato":            "in_attesa",
            "message":          "Richiesta di soccorso inviata con successo",
        }), 201

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ [soccorso] Errore: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route("/soccorso/utente/<int:automobilista_id>", methods=["GET"])
def get_soccorsi_utente(automobilista_id):
    conn = None
    try:
        conn   = get_mysql()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT rs.id, rs.id_automobilista, rs.data_richiesta, rs.stato
            FROM Richiesta_Soccorso rs
            WHERE rs.id_automobilista = (
                SELECT id FROM Automobilista WHERE id_utente = %s
            )
            ORDER BY rs.data_richiesta DESC
        """, (automobilista_id,))
        richieste = cursor.fetchall()
        for r in richieste:
            if isinstance(r.get("data_richiesta"), datetime):
                r["data_richiesta"] = r["data_richiesta"].isoformat()
        return jsonify(richieste), 200
    except Exception as e:
        print(f"❌ [soccorso/utente] Errore: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# ─────────────────────────────────────────────
#  ROTTE — VEICOLI
# ─────────────────────────────────────────────

@app.route("/veicoli-utente/<int:user_id>", methods=["GET"])
def get_veicoli_utente(user_id):
    conn = None
    try:
        conn   = get_mysql()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT v.id, v.targa, v.marca, v.modello, v.anno_immatricolazione,
                   a.nome AS nome_proprietario, a.cognome AS cognome_proprietario
            FROM Veicolo v
            JOIN Automobilista a ON v.automobilista_id = a.id
            WHERE a.id_utente = %s
        """, (user_id,))
        return jsonify(cursor.fetchall()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/veicolo/user/<int:user_id>", methods=["POST"])
def crea_veicolo_utente(user_id):
    data = request.get_json()
    if not data or "targa" not in data:
        return jsonify({"error": "Campo obbligatorio mancante: targa"}), 400

    conn = None
    try:
        conn   = get_mysql()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM Automobilista WHERE id_utente = %s", (user_id,))
        auto = cursor.fetchone()
        if not auto:
            return jsonify({"error": f"Automobilista con id_utente={user_id} non trovato"}), 404
        automobilista_id = auto["id"]

        cursor.execute(
            "INSERT INTO Veicolo (targa, n_telaio, marca, modello, anno_immatricolazione, automobilista_id) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (data.get("targa"), data.get("n_telaio"), data.get("marca"),
             data.get("modello"), data.get("anno_immatricolazione"), automobilista_id)
        )
        conn.commit()
        return jsonify({
            "status":           "success",
            "message":          "Veicolo creato con successo",
            "veicolo_id":       cursor.lastrowid,
            "automobilista_id": automobilista_id,
        }), 201

    except mysql.connector.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"error": "Targa o numero telaio già esistente"}), 409
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# ─────────────────────────────────────────────
#  AVVIO
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n📋 Stato sottosistemi all'avvio:")
    print(f"   MongoDB  : {'✅ disponibile' if _MONGO_DISPONIBILE  else '❌ non disponibile'}")
    print(f"   Gemini   : {'✅ disponibile' if gemini_disponibile  else '⚠️  non disponibile'}")
    print(f"   Storage  : {'✅ disponibile' if _STORAGE_DISPONIBILE else '❌ non disponibile'}\n")
    app.run(debug=True, host="0.0.0.0", port=7000)