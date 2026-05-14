from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import mysql.connector
from bson import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"], "allow_headers": ["Content-Type", "Authorization"]}})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# --- CONFIGURAZIONE DATABASE ---

MYSQL_CONFIG = {
    "host":     os.getenv("MYSQL_HOST"),
    "port":     int(os.getenv("MYSQL_PORT", 3306)),
    "user":     os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
}

# MongoDB — nuovo server (db.giobra.com)
MONGO_URI = os.getenv("MONGO_URI")

try:
    mongo_client   = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo_db       = mongo_client["safeclaim"]
    col_interventi = mongo_db["Proto_Intervento_SC"]   # ex Pratica
    col_documenti  = mongo_db["Proto_Documenti_SC"]    # ex Perizia
    col_sinistri   = mongo_db["Proto_Sinistro_SC"]     # ex Sinistri
    mongo_client.admin.command('ping')
    print("✅ Connessione a MongoDB (safeclaim) riuscita!")
except Exception as e:
    print(f"❌ Errore connessione MongoDB: {e}")
    col_interventi = col_documenti = col_sinistri = None

def get_mysql():
    return mysql.connector.connect(**MYSQL_CONFIG)


# ── HELPER: converte id_utente → id Perito reale ─────────────────────────────

def resolve_perito_id(id_utente):
    try:
        conn   = get_mysql()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM Perito WHERE id_utente = %s", (id_utente,))
        record = cursor.fetchone()
        cursor.close()
        conn.close()
        if record:
            return str(record['id'])
    except Exception as e:
        print(f"[resolve_perito_id] Errore lookup perito per id_utente={id_utente}: {e}")
    return id_utente


def _serializza_sinistro_embed(sinistro: dict) -> dict:
    """Serializza sinistro con alias retrocompatibilità per il frontend."""
    sinistro['_id'] = str(sinistro['_id'])
    # Alias nuovi campi → vecchi nomi usati dal frontend
    if 'data_sinistro' in sinistro:
        if isinstance(sinistro['data_sinistro'], datetime):
            sinistro['data_sinistro'] = sinistro['data_sinistro'].isoformat()
        sinistro['data_evento'] = sinistro['data_sinistro']
    if isinstance(sinistro.get('data_inserimento'), datetime):
        sinistro['data_inserimento'] = sinistro['data_inserimento'].isoformat()
    if 'descrizione_danno' in sinistro:
        sinistro['descrizione'] = sinistro['descrizione_danno']
    if 'stato_sinistro' in sinistro:
        sinistro['stato'] = sinistro['stato_sinistro']
    return sinistro


# ── GET pratica/intervento ─────────────────────────────────────────────────────

@app.route("/sinistro/<sinistro_id>/perito/<perito_id>/pratica", methods=["GET"])
def get_pratica(sinistro_id, perito_id):
    try:
        real_perito_id = resolve_perito_id(perito_id)
        query   = {"sinistro_id": sinistro_id, "perito_id": real_perito_id}
        pratica = col_interventi.find_one(query)
        if not pratica:
            return jsonify({"error": "Pratica non trovata"}), 404
        pratica["_id"]        = str(pratica["_id"])
        pratica["sinistro_id"] = str(pratica["sinistro_id"])
        return jsonify(pratica), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── GET tutte le pratiche per l'Assicurazione ─────────────────────────────────

@app.route("/pratiche_assicurazione", methods=["GET"])
def get_pratiche_assicurazione():
    try:
        pratiche_cursor = col_interventi.find()
        risultati = []
        for pratica in pratiche_cursor:
            pratica["_id"] = str(pratica["_id"])
            for campo in ("data_inserimento", "data_aggiornamento", "data_inizio", "data_fine"):
                if campo in pratica and isinstance(pratica[campo], datetime):
                    pratica[campo] = pratica[campo].isoformat()
            for key in ["sinistro_id", "perito_id"]:
                if key in pratica and pratica[key] is not None:
                    pratica[key] = str(pratica[key])
            risultati.append(pratica)
        return jsonify({"totale": len(risultati), "pratiche": risultati}), 200
    except Exception as e:
        return jsonify({"error": f"Errore nel recupero pratiche: {str(e)}"}), 500


# ── GET pratiche/interventi assegnati a un perito (con sinistro embedded) ─────

@app.route('/perito/<perito_id>/pratiche', methods=['GET'])
def get_pratiche_perito(perito_id):
    try:
        real_perito_id = resolve_perito_id(perito_id)
        pratiche = list(col_interventi.find({"perito_id": real_perito_id}))
        result = []
        for p in pratiche:
            p['_id'] = str(p['_id'])
            for key in ['sinistro_id']:
                if key in p and p[key] is not None:
                    p[key] = str(p[key])
            for key in ['data_inserimento', 'data_aggiornamento', 'data_inizio', 'data_fine']:
                if key in p and isinstance(p[key], datetime):
                    p[key] = p[key].isoformat()

            # Retrocompatibilità: tipo_intervento → tipo_danno
            p['tipo_danno'] = p.get('tipo_intervento', p.get('tipo_danno'))

            sin_id = p.get('sinistro_id')
            if sin_id:
                try:
                    sinistro = col_sinistri.find_one({"_id": ObjectId(sin_id)})
                    if sinistro:
                        sinistro = _serializza_sinistro_embed(sinistro)
                        analisi = sinistro.get('analisi_ai')
                        p['sinistro'] = {
                            '_id':                    sinistro['_id'],
                            'targa':                  sinistro.get('targa'),
                            'marca':                  sinistro.get('marca'),
                            'modello':                sinistro.get('modello_veicolo', sinistro.get('modello')),
                            'data_evento':            sinistro.get('data_sinistro', sinistro.get('data_evento')),
                            'descrizione':            sinistro.get('descrizione_danno', sinistro.get('descrizione')),
                            'luogo':                  sinistro.get('luogo'),
                            'tipo_sinistro':          sinistro.get('tipo_sinistro'),
                            'stima_danno':            sinistro.get('preventivo', {}).get('costo_totale'),
                            'stato':                  sinistro.get('stato_sinistro', sinistro.get('stato')),
                            'compagnia_assicurativa': sinistro.get('compagnia_assicurativa'),
                            'priorita':               sinistro.get('priorita'),
                            'num_immagini':           len(sinistro.get('immagini', [])),
                            'analisi_ai_stato':       analisi.get('stato') if analisi else 'non_avviata',
                        }
                except Exception as inner_err:
                    print(f"[pratiche] Errore caricamento sinistro {sin_id}: {inner_err}")
            result.append(p)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST crea pratica/intervento (con o senza perito) ─────────────────────────

@app.route('/sinistro/<id_sinistro>/pratica', methods=['POST'])
def crea_pratica(id_sinistro):
    data      = request.get_json() or {}
    perito_id = data.get("perito_id")

    if perito_id:
        try:
            conn   = get_mysql()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Perito WHERE id = %s", (perito_id,))
            perito_esiste = cursor.fetchone()
            cursor.close()
            conn.close()
            if not perito_esiste:
                return jsonify({"error": "Perito non trovato"}), 404
        except Exception:
            pass

    stato = "assegnata" if perito_id else "da_assegnare"

    # Mappa i vecchi campi ai nuovi nomi di Proto_Intervento_SC
    tipo_intervento   = data.get("tipo_intervento") or data.get("tipo_danno")
    descrizione_lavori = data.get("descrizione_lavori") or data.get("descrizione", "")
    note_tecnico       = data.get("note_tecnico") or data.get("note_tecniche")
    ricambi            = data.get("ricambi_utilizzati") or [
        {"nome": p} for p in data.get("parti_danneggiate", [])
    ]

    intervento_doc = {
        "sinistro_id":        id_sinistro,
        "perito_id":          str(perito_id) if perito_id else None,
        "officina_id":        data.get("officina_id"),
        "veicolo_targa":      data.get("veicolo_targa", data.get("veicolo", "")),
        "stato":              stato,
        "tipo_intervento":    tipo_intervento,
        "descrizione_lavori": descrizione_lavori,
        "ricambi_utilizzati": ricambi,
        "manodopera_ore":     data.get("manodopera_ore"),
        "note_tecnico":       note_tecnico,
        "foto_prima":         data.get("foto_prima", []),
        "foto_dopo":          data.get("foto_dopo", []),
        "data_inizio":        data.get("data_inizio"),
        "data_fine":          None,
        # Campi legacy mantenuti per retrocompatibilità
        "titolo":             data.get("titolo", "Intervento in attesa di assegnazione"),
        "stima_danno":        data.get("stima_danno"),
        "conclusione":        data.get("conclusione"),
        "claim_code":         data.get("claim_code"),
        "documenti":          data.get("documenti", []),
        "data_inserimento":   datetime.utcnow()
    }

    result      = col_interventi.insert_one(intervento_doc)
    pratica_id  = str(result.inserted_id)

    stato_sinistro = "in_perizia" if perito_id else "da_assegnare"
    sinistro_update = {
        "stato_sinistro":    stato_sinistro,
        "pratica_id":        pratica_id,
        "data_aggiornamento": datetime.utcnow()
    }
    if perito_id:
        sinistro_update["perito_id"] = str(perito_id)

    try:
        col_sinistri.update_one(
            {"_id": ObjectId(id_sinistro)},
            {"$set": sinistro_update}
        )
    except Exception:
        pass

    return jsonify({
        "status":     "Pratica creata",
        "id_pratica": pratica_id,
        "stato":      stato
    }), 201


# ── PUT assegna perito a pratica esistente ────────────────────────────────────

@app.route('/pratica/<pratica_id>/assegna', methods=['PUT'])
def assegna_perito_pratica(pratica_id):
    data = request.get_json()
    if not data or not data.get("perito_id"):
        return jsonify({"error": "perito_id mancante"}), 400
    if not ObjectId.is_valid(pratica_id):
        return jsonify({"error": "ID pratica non valido"}), 400

    perito_id = str(data["perito_id"])

    try:
        conn   = get_mysql()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM Perito WHERE id = %s", (perito_id,))
        perito_esiste = cursor.fetchone()
        cursor.close()
        conn.close()
        if not perito_esiste:
            return jsonify({"error": "Perito non trovato"}), 404
    except Exception:
        pass

    result = col_interventi.update_one(
        {"_id": ObjectId(pratica_id)},
        {"$set": {
            "perito_id":          perito_id,
            "stato":              "assegnata",
            "data_aggiornamento": datetime.utcnow()
        }}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Pratica non trovata"}), 404

    pratica = col_interventi.find_one({"_id": ObjectId(pratica_id)})
    if pratica and pratica.get("sinistro_id"):
        try:
            col_sinistri.update_one(
                {"_id": ObjectId(pratica["sinistro_id"])},
                {"$set": {
                    "perito_id":          perito_id,
                    "stato_sinistro":     "in_perizia",
                    "data_aggiornamento": datetime.utcnow()
                }}
            )
        except Exception:
            pass

    return jsonify({
        "status":     "Perito assegnato",
        "pratica_id": pratica_id,
        "perito_id":  perito_id
    }), 200


# ── PUT accetta / rifiuta pratica (dal perito) ────────────────────────────────

@app.route('/pratica/<pratica_id>/perito/<perito_id>', methods=['PUT'])
def aggiorna_pratica_perito(pratica_id, perito_id):
    if not ObjectId.is_valid(pratica_id):
        return jsonify({"error": "ID pratica non valido"}), 400

    real_perito_id = resolve_perito_id(perito_id)

    data         = request.get_json() or {}
    nuovo_stato  = data.get("stato", "in_perizia")
    reset_perito = data.get("_reset_perito", False)

    update_fields = {
        "stato":              nuovo_stato,
        "data_aggiornamento": datetime.utcnow()
    }
    if reset_perito:
        update_fields["perito_id"] = None

    result = col_interventi.update_one(
        {"_id": ObjectId(pratica_id), "perito_id": real_perito_id},
        {"$set": update_fields}
    )

    if result.matched_count == 0:
        result = col_interventi.update_one(
            {"_id": ObjectId(pratica_id)},
            {"$set": update_fields}
        )
        if result.matched_count == 0:
            return jsonify({"error": "Pratica non trovata"}), 404

    pratica = col_interventi.find_one({"_id": ObjectId(pratica_id)})
    if pratica and pratica.get("sinistro_id"):
        sin_id         = pratica["sinistro_id"]
        stato_sinistro = "in_perizia" if nuovo_stato == "in_perizia" else "aperto"
        sinistro_update = {
            "stato_sinistro":     stato_sinistro,
            "data_aggiornamento": datetime.utcnow()
        }
        if reset_perito:
            sinistro_update["perito_id"] = None
        try:
            col_sinistri.update_one(
                {"_id": ObjectId(str(sin_id))},
                {"$set": sinistro_update}
            )
        except Exception as e:
            print(f"[aggiorna_pratica_perito] Errore aggiornamento sinistro: {e}")

    return jsonify({
        "status":     "ok",
        "pratica_id": pratica_id,
        "stato":      nuovo_stato
    }), 200


# ── DELETE pratica ─────────────────────────────────────────────────────────────

@app.route('/pratica/<pratica_id>/perito/<perito_id>', methods=['DELETE'])
def elimina_pratica(pratica_id, perito_id):
    if not ObjectId.is_valid(pratica_id):
        return jsonify({"error": "ID pratica non valido"}), 400

    real_perito_id = resolve_perito_id(perito_id)

    try:
        result = col_interventi.delete_one({
            "_id": ObjectId(pratica_id),
            "perito_id": real_perito_id
        })
        if result.deleted_count == 0:
            result = col_interventi.delete_one({"_id": ObjectId(pratica_id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Pratica non trovata"}), 404
        return jsonify({"status": "eliminata", "pratica_id": pratica_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── PUT pratica (upsert via sinistro_id + perito_id) ─────────────────────────

@app.route("/sinistro/<sinistro_id>/perito/<perito_id>/pratica", methods=["PUT"])
def update_pratica(sinistro_id, perito_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dati mancanti"}), 400

    real_perito_id = resolve_perito_id(perito_id)

    tipo_intervento    = data.get("tipo_intervento") or data.get("tipo_danno")
    descrizione_lavori = data.get("descrizione_lavori") or data.get("descrizione")
    note_tecnico       = data.get("note_tecnico") or data.get("note_tecniche")
    ricambi            = data.get("ricambi_utilizzati") or [
        {"nome": p} for p in data.get("parti_danneggiate", [])
    ]

    query       = {"sinistro_id": sinistro_id, "perito_id": real_perito_id}
    update_data = {
        "$set": {
            "titolo":             data.get("titolo"),
            "tipo_intervento":    tipo_intervento,
            "stima_danno":        data.get("stima_danno"),
            "ricambi_utilizzati": ricambi,
            "descrizione_lavori": descrizione_lavori,
            "conclusione":        data.get("conclusione"),
            "veicolo_targa":      data.get("veicolo_targa", data.get("veicolo")),
            "claim_code":         data.get("claim_code"),
            "stato":              data.get("stato", "Bozza"),
            "note_tecnico":       note_tecnico,
            "sinistro_id":        sinistro_id,
            "perito_id":          real_perito_id,
            "data_aggiornamento": datetime.utcnow()
        }
    }
    col_interventi.update_one(query, update_data, upsert=True)
    return jsonify({"status": "success"}), 200


# ── POST rimborso ─────────────────────────────────────────────────────────────

@app.route('/sinistro/<id_sinistro>/perito/<id_perito>/pratica/<id_perizia>/rimborso', methods=['POST'])
def registra_rimborso(id_sinistro, id_perito, id_perizia):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Body JSON mancante"}), 400
    try:
        p_id = ObjectId(id_perizia)
    except Exception:
        return jsonify({"error": "Formato ID perizia non valido"}), 400

    # Aggiorna il documento in Proto_Documenti_SC
    res = col_documenti.update_one(
        {"_id": p_id},
        {"$set": {
            "stima_danno":        data.get("stima_danno"),
            "esito":              data.get("esito"),
            "stato":              "rimborso_inserito",
            "data_aggiornamento": datetime.utcnow()
        }}
    )
    if res.matched_count == 0:
        return jsonify({"error": "Documento non trovato"}), 404

    # Aggiorna il preventivo nel sinistro
    try:
        col_sinistri.update_one(
            {"_id": ObjectId(id_sinistro)},
            {"$set": {
                "stato_sinistro":              "rimborso_proposto",
                "preventivo.costo_totale":     data.get("stima_danno"),
                "preventivo.stato":            "proposto",
                "data_aggiornamento":          datetime.utcnow()
            }}
        )
    except Exception:
        pass

    return jsonify({"status": "Rimborso salvato"}), 200


# ── POST intervento officina ──────────────────────────────────────────────────

@app.route('/sinistro/<id_sinistro>/perito/<id_perito>/pratica/<id_perizia>/intervento', methods=['POST'])
def assegna_intervento(id_sinistro, id_perito, id_perizia):
    data        = request.get_json()
    id_officina = data.get("id_officina")
    if not id_officina:
        return jsonify({"error": "ID officina mancante"}), 400

    try:
        conn   = get_mysql()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM Officina WHERE id = %s", (id_officina,))
        officina_esiste = cursor.fetchone()
        cursor.close()
        conn.close()
        if not officina_esiste:
            return jsonify({"error": "Officina non trovata"}), 404
    except Exception:
        pass

    try:
        s_id = ObjectId(id_sinistro)
        p_id = ObjectId(id_perizia)
    except Exception:
        return jsonify({"error": "Formato ID non valido"}), 400

    col_sinistri.update_one(
        {"_id": s_id},
        {"$set": {
            "officina_id":        id_officina,
            "stato_sinistro":     "in_riparazione",
            "data_inizio_lavori": data.get("data_inizio_lavori"),
            "data_aggiornamento": datetime.utcnow()
        }}
    )
    col_documenti.update_one(
        {"_id": p_id},
        {"$set": {"stato": "inviata_officina", "officina_id": id_officina}}
    )
    return jsonify({"status": "Successo", "nuovo_stato": "in_riparazione"}), 200


# ── GET perizie perito ────────────────────────────────────────────────────────

@app.route('/perito/<id_utente>/perizie', methods=['GET'])
def get_perizie_perito(id_utente):
    try:
        real_perito_id = resolve_perito_id(id_utente)
        docs = list(col_documenti.find({"perito_id": real_perito_id}))

        for d in docs:
            d['_id'] = str(d['_id'])
            if 'sinistro_id' in d and isinstance(d['sinistro_id'], ObjectId):
                d['sinistro_id'] = str(d['sinistro_id'])
            for key in ['data_inserimento', 'data_aggiornamento']:
                if key in d and isinstance(d[key], datetime):
                    d[key] = d[key].isoformat()

        return jsonify(docs), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── DELETE perizia/documento ──────────────────────────────────────────────────

@app.route('/perizia/<perizia_id>', methods=['DELETE'])
def elimina_perizia(perizia_id):
    try:
        result = col_documenti.delete_one({"_id": ObjectId(perizia_id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Documento non trovato"}), 404
        return jsonify({"status": "eliminata"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET periti (da MySQL) ─────────────────────────────────────────────────────

@app.route('/periti', methods=['GET'])
def get_periti():
    try:
        conn   = get_mysql()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Perito ORDER BY id ASC")
        periti = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"totale": len(periti), "periti": periti}), 200
    except Exception as e:
        print(f"❌ Errore /periti: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
