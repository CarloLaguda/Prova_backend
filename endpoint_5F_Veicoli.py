from flask import Flask, request, jsonify
from datetime import datetime, UTC
import mysql.connector
import pymongo
from bson.objectid import ObjectId
from flask_cors import CORS
import os
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app)

# ── Configurazione MySQL ────────────────────────────────────────────────────
load_dotenv()
MYSQL_CONFIG = {
    "host":     os.getenv("MYSQL_HOST"),
    "port":     int(os.getenv("MYSQL_PORT", 3306)),
    "user":     os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
}

def get_db_connection():
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
_MONGO_DISPONIBILE = False

try:
    MONGO_URI    = os.getenv("MONGO_URI")
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo_db     = mongo_client["safeclaim"]
    col_interventi = mongo_db["Proto_Intervento_SC"]
    col_documenti  = mongo_db["Proto_Documenti_SC"]
    col_sinistri   = mongo_db["Proto_Sinistro_SC"]
    mongo_client.admin.command("ping")
    _MONGO_DISPONIBILE = True
    print("✅ Connessione a MongoDB (safeclaim) riuscita!")
except Exception as e:
    print(f"❌ Errore connessione MongoDB: {e} — le rotte MongoDB risponderanno con 503.")
# ── Veicoli ──────────────────────────────────────────────────────────────────

@app.route('/veicoli', methods=['GET'])
@app.route('/veicoli/<int:id>', methods=['GET'])
def get_veicoli(id=None):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if id:
            cursor.execute("SELECT * FROM Veicolo WHERE id = %s", (id,))
            veicolo = cursor.fetchone()
            if not veicolo:
                return jsonify({"error": "Veicolo non trovato"}), 404
            return jsonify(veicolo), 200
        else:
            cursor.execute("SELECT * FROM Veicolo")
            return jsonify(cursor.fetchall()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# Nel nuovo schema Automobilista non ha più email/psw propri:
# si cerca per id_utente tramite Utente → Automobilista.
@app.route('/veicoli-utente/<int:user_id>', methods=['GET'])
def get_veicoli_utente(user_id):
    """Recupera i veicoli dell'automobilista associato all'utente (id_utente)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT v.id, v.targa, v.n_telaio, v.marca, v.modello, v.anno_immatricolazione,
                   a.nome AS nome_proprietario, a.cognome AS cognome_proprietario
            FROM Veicolo v
            JOIN Automobilista a ON v.automobilista_id = a.id
            WHERE a.id_utente = %s
        """
        cursor.execute(query, (user_id,))
        return jsonify(cursor.fetchall()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/veicolo/user/<int:user_id>', methods=['POST'])
def crea_veicolo_utente(user_id):
    """Crea un veicolo per l'automobilista associato all'utente (id_utente)."""
    data = request.get_json()
    if not data or not data.get('targa'):
        return jsonify({"error": "Campo obbligatorio mancante: targa"}), 400

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Trova il record Automobilista tramite id_utente
        cursor.execute("SELECT id FROM Automobilista WHERE id_utente = %s", (user_id,))
        automobilista = cursor.fetchone()
        if not automobilista:
            return jsonify({"error": f"Automobilista con id_utente={user_id} non trovato"}), 404

        automobilista_id = automobilista['id']

        cursor.execute(
            "INSERT INTO Veicolo (targa, n_telaio, marca, modello, anno_immatricolazione, automobilista_id) VALUES (%s,%s,%s,%s,%s,%s)",
            (data.get('targa'), data.get('n_telaio'), data.get('marca'),
             data.get('modello'), data.get('anno_immatricolazione'), automobilista_id)
        )
        conn.commit()
        return jsonify({"status": "success", "veicolo_id": cursor.lastrowid,
                        "automobilista_id": automobilista_id}), 201

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

@app.route('/veicoli-utente/<int:user_id>/<string:targa>', methods=['DELETE'])
def elimina_veicolo_utente(user_id, targa):
    """Elimina un veicolo dell'automobilista associato all'utente."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM Automobilista WHERE id_utente = %s", (user_id,))
        automobilista = cursor.fetchone()
        if not automobilista:
            return jsonify({"error": "Automobilista non trovato"}), 404

        cursor.execute(
            "SELECT id FROM Veicolo WHERE targa = %s AND automobilista_id = %s",
            (targa, automobilista['id'])
        )
        if not cursor.fetchone():
            return jsonify({"error": "Veicolo non trovato o non appartenente a questo utente"}), 404

        cursor.execute(
            "DELETE FROM Veicolo WHERE targa = %s AND automobilista_id = %s",
            (targa, automobilista['id'])
        )
        conn.commit()
        return jsonify({"status": "success", "message": f"Veicolo {targa} rimosso con successo"}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)
