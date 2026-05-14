"""
seed_mongodb.py — Migrazione e popolamento MongoDB SafeClaim
Elimina le vecchie collezioni e crea Proto_Sinistro_SC,
Proto_Intervento_SC, Proto_Documenti_SC con dati coerenti al MySQL.
Proto_Knowledge_SC viene lasciata intatta.
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = client["safeclaim"]

UTC = timezone.utc

# ─────────────────────────────────────────────
#  1. ELIMINA VECCHIE COLLEZIONI
# ─────────────────────────────────────────────

VECCHIE = [
    "Guidatore", "Officina", "Perizia", "Pratica",
    "Preventivo", "Sinistri", "sinistri", "Soccorso",
    "log_ricerche", "token_blacklist",
]

print("\n=== ELIMINAZIONE VECCHIE COLLEZIONI ===")
collezioni_esistenti = db.list_collection_names()
for nome in VECCHIE:
    if nome in collezioni_esistenti:
        db.drop_collection(nome)
        print(f"  [✓] Eliminata: {nome}")
    else:
        print(f"  [–] Non esisteva: {nome}")

# ─────────────────────────────────────────────
#  2. PROTO_SINISTRO_SC
# ─────────────────────────────────────────────
# Dati coerenti con MySQL:
#   automobilista_id → Automobilista.id
#   targa            → Veicolo.targa (stessa riga)
#   officina_id      → Utente.id con ruolo officina (7=Autofficina Rossi, 8=Carrozzeria Blu)

sinistri_col = db["Proto_Sinistro_SC"]
sinistri_col.drop()

sinistri_docs = [
    {
        "automobilista_id":    1,
        "targa":               "AB123CD",
        "modello_veicolo":     "Volkswagen Golf 2020",
        "telaio":              "WVWZZZ3CZWE123456",
        "cliente":             "Mario Rossi",
        "contatto_cliente":    {"telefono": None, "email": "mario.rossi@email.com"},
        "compagnia_assicurativa": "UnipolSai",
        "numero_sinistro":     "SIN-2026-10001",
        "data_sinistro":       datetime(2026, 2, 10, 14, 30, tzinfo=UTC),
        "descrizione_danno":   "Urto posteriore con danni al paraurti, fanali e portellone. Necessaria sostituzione paraurti e verniciatura portellone.",
        "stato_sinistro":      "assegnato",
        "attivo":              True,
        "priorita":            "urgente",
        "officina_id":         7,
        "note":                "Cliente disponibile dal lunedì al venerdì dalle 9 alle 18.",
        "preventivo": {
            "data":            None,
            "costo_totale":    None,
            "ore_manodopera":  None,
            "giorni_previsti": None,
            "stato":           "da_creare",
            "dettaglio_voci":  [],
            "fattura":         None,
        },
        "immagini":            [],
        "analisi_ai":          None,
        "data_inserimento":    datetime(2026, 2, 10, 15, 0, tzinfo=UTC),
        "data_aggiornamento":  datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        "data_assegnazione":   datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
    },
    {
        "automobilista_id":    2,
        "targa":               "EF456GH",
        "modello_veicolo":     "Fiat 500 2022",
        "telaio":              "TMBJF25J6E1234567",
        "cliente":             "Giulia Ferrari",
        "contatto_cliente":    {"telefono": None, "email": "giulia.ferrari@email.com"},
        "compagnia_assicurativa": "Generali",
        "numero_sinistro":     "SIN-2026-10002",
        "data_sinistro":       datetime(2026, 3, 5, 9, 15, tzinfo=UTC),
        "descrizione_danno":   "Collisione laterale sinistra: portiera anteriore deformata e cristallo rotto.",
        "stato_sinistro":      "aperto",
        "attivo":              True,
        "priorita":            "normale",
        "officina_id":         None,
        "note":                "Cliente richiede riparazione rapida, ha bisogno del veicolo per lavoro.",
        "preventivo": {
            "data":            None,
            "costo_totale":    None,
            "ore_manodopera":  None,
            "giorni_previsti": None,
            "stato":           "da_creare",
            "dettaglio_voci":  [],
            "fattura":         None,
        },
        "immagini":            [],
        "analisi_ai":          None,
        "data_inserimento":    datetime(2026, 3, 5, 10, 0, tzinfo=UTC),
        "data_aggiornamento":  None,
        "data_assegnazione":   None,
    },
    {
        "automobilista_id":    3,
        "targa":               "IJ789KL",
        "modello_veicolo":     "BMW Serie 3 2021",
        "telaio":              "WBAPH5C55BA123456",
        "cliente":             "Luca Esposito",
        "contatto_cliente":    {"telefono": None, "email": "luca.esposito@email.com"},
        "compagnia_assicurativa": "UnipolSai",
        "numero_sinistro":     "SIN-2026-10003",
        "data_sinistro":       datetime(2026, 1, 20, 18, 45, tzinfo=UTC),
        "descrizione_danno":   "Danni al cofano anteriore e parafango dx per urto con animale selvatico.",
        "stato_sinistro":      "in_perizia",
        "attivo":              True,
        "priorita":            "normale",
        "officina_id":         8,
        "note":                "Perizia richiesta dalla compagnia prima di procedere con la riparazione.",
        "perito_id":           "1",
        "preventivo": {
            "data":            None,
            "costo_totale":    None,
            "ore_manodopera":  None,
            "giorni_previsti": None,
            "stato":           "in_valutazione",
            "dettaglio_voci":  [],
            "fattura":         None,
        },
        "immagini":            [],
        "analisi_ai":          None,
        "data_inserimento":    datetime(2026, 1, 21, 8, 0, tzinfo=UTC),
        "data_aggiornamento":  datetime(2026, 2, 5, 11, 0, tzinfo=UTC),
        "data_assegnazione":   datetime(2026, 2, 5, 11, 0, tzinfo=UTC),
    },
    {
        "automobilista_id":    37,
        "targa":               "GP765DM",
        "modello_veicolo":     "FIAT PANDA 2025",
        "telaio":              "HAGAVAT000001",
        "cliente":             "Gino Paoli",
        "contatto_cliente":    {"telefono": "+39 456 5678995", "email": "paoligino@mail.com"},
        "compagnia_assicurativa": "Generali",
        "numero_sinistro":     "SIN-2026-10004",
        "data_sinistro":       datetime(2026, 4, 12, 11, 0, tzinfo=UTC),
        "descrizione_danno":   "Graffio profondo su tutta la fiancata sinistra, probabile atto vandalico.",
        "stato_sinistro":      "in_riparazione",
        "attivo":              True,
        "priorita":            "normale",
        "officina_id":         7,
        "note":                "Riparazione avviata il 20/04/2026.",
        "preventivo": {
            "data":            datetime(2026, 4, 18, tzinfo=UTC).isoformat(),
            "costo_totale":    850.0,
            "ore_manodopera":  8,
            "giorni_previsti": 3,
            "stato":           "approvato",
            "dettaglio_voci":  [
                {"voce": "Verniciatura fiancata sx", "costo": 600.0},
                {"voce": "Stucco e preparazione", "costo": 250.0},
            ],
            "fattura":         None,
        },
        "immagini":            [],
        "analisi_ai":          None,
        "data_inserimento":    datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
        "data_aggiornamento":  datetime(2026, 4, 18, 10, 0, tzinfo=UTC),
        "data_assegnazione":   datetime(2026, 4, 15, 9, 0, tzinfo=UTC),
    },
    {
        "automobilista_id":    38,
        "targa":               "AF241GE",
        "modello_veicolo":     "Lancia Delta 2005",
        "telaio":              "GAFADSCA00006",
        "cliente":             "Giovanni Verga",
        "contatto_cliente":    {"telefono": "+39 3498765341", "email": "giovanni.verga@test.it"},
        "compagnia_assicurativa": "Generali",
        "numero_sinistro":     "SIN-2026-10005",
        "data_sinistro":       datetime(2025, 12, 3, 16, 20, tzinfo=UTC),
        "descrizione_danno":   "Tamponamento in autostrada: danni strutturali al retrotreno, cinture da sostituire.",
        "stato_sinistro":      "chiuso",
        "attivo":              False,
        "priorita":            "urgente",
        "officina_id":         8,
        "note":                "Sinistro chiuso. Rimborso erogato il 15/01/2026.",
        "preventivo": {
            "data":            datetime(2025, 12, 15, tzinfo=UTC).isoformat(),
            "costo_totale":    3200.0,
            "ore_manodopera":  20,
            "giorni_previsti": 10,
            "stato":           "pagato",
            "dettaglio_voci":  [
                {"voce": "Riparazione retrotreno",   "costo": 1800.0},
                {"voce": "Sostituzione cinture (2)", "costo": 400.0},
                {"voce": "Verniciatura paraurti",    "costo": 600.0},
                {"voce": "Manodopera",               "costo": 400.0},
            ],
            "fattura":         "FAT-2026-0042",
        },
        "immagini":            [],
        "analisi_ai":          {"stato": "non_avviata"},
        "data_inserimento":    datetime(2025, 12, 3, 17, 0, tzinfo=UTC),
        "data_aggiornamento":  datetime(2026, 1, 15, 14, 0, tzinfo=UTC),
        "data_assegnazione":   datetime(2025, 12, 5, 10, 0, tzinfo=UTC),
    },
]

result = sinistri_col.insert_many(sinistri_docs)
sin_ids = result.inserted_ids
print(f"\n=== PROTO_SINISTRO_SC: {len(sin_ids)} documenti inseriti ===")
for i, oid in enumerate(sin_ids):
    print(f"  [{i+1}] {sinistri_docs[i]['numero_sinistro']} → {oid}")

# ─────────────────────────────────────────────
#  3. PROTO_INTERVENTO_SC
# ─────────────────────────────────────────────

interventi_col = db["Proto_Intervento_SC"]
interventi_col.drop()

interventi_docs = [
    {
        "sinistro_id":        str(sin_ids[0]),
        "officina_id":        7,
        "veicolo_targa":      "AB123CD",
        "data_inizio":        datetime(2026, 3, 3, 8, 0, tzinfo=UTC),
        "data_fine":          None,
        "tipo_intervento":    "carrozzeria",
        "descrizione_lavori": "Sostituzione paraurti posteriore, verniciatura portellone e sostituzione fanali posteriori.",
        "ricambi_utilizzati": [
            {"nome": "Paraurti posteriore", "codice": "PB-VW-GOLF-001", "costo": 480.0},
            {"nome": "Fanale posteriore sx", "codice": "FL-VW-GOLF-002", "costo": 220.0},
            {"nome": "Fanale posteriore dx", "codice": "FL-VW-GOLF-003", "costo": 220.0},
        ],
        "manodopera_ore":     10,
        "foto_prima":         [],
        "foto_dopo":          [],
        "note_tecnico":       "In attesa di conferma arrivo paraurti dal fornitore.",
        "stato":              "in_corso",
        "perito_id":          None,
        "titolo":             "Riparazione danni posteriori Volkswagen Golf",
        "stima_danno":        None,
        "conclusione":        None,
        "documenti":          [],
        "data_inserimento":   datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
    },
    {
        "sinistro_id":        str(sin_ids[2]),
        "officina_id":        8,
        "veicolo_targa":      "IJ789KL",
        "data_inizio":        datetime(2026, 2, 10, 9, 0, tzinfo=UTC),
        "data_fine":          datetime(2026, 2, 15, 17, 0, tzinfo=UTC),
        "tipo_intervento":    "carrozzeria",
        "descrizione_lavori": "Sostituzione cofano anteriore e parafango destro. Verniciatura e trattamento antiruggine.",
        "ricambi_utilizzati": [
            {"nome": "Cofano anteriore", "codice": "COF-BMW-S3-001", "costo": 890.0},
            {"nome": "Parafango dx",     "codice": "PFG-BMW-S3-002", "costo": 340.0},
        ],
        "manodopera_ore":     14,
        "foto_prima":         [],
        "foto_dopo":          [],
        "note_tecnico":       "Intervento completato. Colore verificato con targa BMW.",
        "stato":              "completato",
        "perito_id":          "1",
        "titolo":             "Riparazione danni cofano BMW Serie 3",
        "stima_danno":        1850.0,
        "conclusione":        "Veicolo riparato e riconsegnato al cliente il 15/02/2026.",
        "documenti":          [],
        "data_inserimento":   datetime(2026, 2, 5, 12, 0, tzinfo=UTC),
        "data_aggiornamento": datetime(2026, 2, 15, 17, 0, tzinfo=UTC),
    },
    {
        "sinistro_id":        str(sin_ids[3]),
        "officina_id":        7,
        "veicolo_targa":      "GP765DM",
        "data_inizio":        datetime(2026, 4, 20, 8, 0, tzinfo=UTC),
        "data_fine":          datetime(2026, 4, 23, 17, 0, tzinfo=UTC),
        "tipo_intervento":    "carrozzeria",
        "descrizione_lavori": "Lucidatura e verniciatura fiancata sinistra. Stucco e preparazione superfici danneggiate.",
        "ricambi_utilizzati": [
            {"nome": "Vernice base metallizzata", "codice": "VRN-FIAT-001", "costo": 120.0},
            {"nome": "Stucco poliestere",         "codice": "STU-GEN-002",  "costo": 45.0},
        ],
        "manodopera_ore":     8,
        "foto_prima":         [],
        "foto_dopo":          [],
        "note_tecnico":       "Verniciatura completata. Cliente soddisfatto.",
        "stato":              "completato",
        "perito_id":          None,
        "titolo":             "Verniciatura fiancata FIAT PANDA",
        "stima_danno":        850.0,
        "conclusione":        "Veicolo riconsegnato il 23/04/2026.",
        "documenti":          [],
        "data_inserimento":   datetime(2026, 4, 15, 9, 0, tzinfo=UTC),
        "data_aggiornamento": datetime(2026, 4, 23, 17, 0, tzinfo=UTC),
    },
    {
        "sinistro_id":        str(sin_ids[4]),
        "officina_id":        8,
        "veicolo_targa":      "AF241GE",
        "data_inizio":        datetime(2025, 12, 8, 8, 0, tzinfo=UTC),
        "data_fine":          datetime(2025, 12, 18, 17, 0, tzinfo=UTC),
        "tipo_intervento":    "meccanica",
        "descrizione_lavori": "Riparazione retrotreno: sostituzione longheroni, traversa e cinture di sicurezza. Verniciatura paraurti.",
        "ricambi_utilizzati": [
            {"nome": "Longherone sx",          "codice": "LNG-LNC-001", "costo": 580.0},
            {"nome": "Longherone dx",          "codice": "LNG-LNC-002", "costo": 580.0},
            {"nome": "Traversa posteriore",    "codice": "TRV-LNC-003", "costo": 240.0},
            {"nome": "Cintura sicurezza (x2)", "codice": "CIN-LNC-004", "costo": 400.0},
        ],
        "manodopera_ore":     20,
        "foto_prima":         [],
        "foto_dopo":          [],
        "note_tecnico":       "Intervento completato con esito positivo. Collaudo superato.",
        "stato":              "completato",
        "perito_id":          "2",
        "titolo":             "Riparazione retrotreno Lancia Delta",
        "stima_danno":        3200.0,
        "conclusione":        "Veicolo riparato e riconsegnato il 18/12/2025. Rimborso approvato.",
        "documenti":          [],
        "data_inserimento":   datetime(2025, 12, 5, 10, 0, tzinfo=UTC),
        "data_aggiornamento": datetime(2025, 12, 18, 17, 0, tzinfo=UTC),
    },
]

result_int = interventi_col.insert_many(interventi_docs)
int_ids = result_int.inserted_ids
print(f"\n=== PROTO_INTERVENTO_SC: {len(int_ids)} documenti inseriti ===")
for i, oid in enumerate(int_ids):
    print(f"  [{i+1}] {interventi_docs[i]['veicolo_targa']} → {oid}")

# ─────────────────────────────────────────────
#  4. PROTO_DOCUMENTI_SC
# ─────────────────────────────────────────────
# Collezione per perizie e documenti allegati ai sinistri.
# Schema: sinistro_id, perito_id, tipo_documento, descrizione,
#         stima_danno, esito, stato, officina_id, allegati, note, date

documenti_col = db["Proto_Documenti_SC"]
documenti_col.drop()

documenti_docs = [
    {
        "sinistro_id":        str(sin_ids[2]),
        "perito_id":          "1",
        "officina_id":        8,
        "tipo_documento":     "perizia",
        "titolo":             "Perizia danni cofano BMW Serie 3",
        "descrizione":        "Perizia tecnica sui danni al cofano anteriore e parafango destro causati da urto con animale selvatico.",
        "stima_danno":        1850.0,
        "esito":              "approvato",
        "stato":              "inviata_officina",
        "note":               "Danni coerenti con la dinamica dichiarata. Approvato rimborso.",
        "allegati":           [],
        "data_inserimento":   datetime(2026, 2, 5, 11, 30, tzinfo=UTC),
        "data_aggiornamento": datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
    },
    {
        "sinistro_id":        str(sin_ids[4]),
        "perito_id":          "2",
        "officina_id":        8,
        "tipo_documento":     "perizia",
        "titolo":             "Perizia danni retrotreno Lancia Delta",
        "descrizione":        "Perizia strutturale per danni da tamponamento ad alta velocità. Verificata integrità telaiistica.",
        "stima_danno":        3200.0,
        "esito":              "approvato",
        "stato":              "rimborso_inserito",
        "note":               "Danni strutturali confermati. Rimborso integrale approvato.",
        "allegati":           [],
        "data_inserimento":   datetime(2025, 12, 5, 10, 30, tzinfo=UTC),
        "data_aggiornamento": datetime(2025, 12, 10, 14, 0, tzinfo=UTC),
    },
    {
        "sinistro_id":        str(sin_ids[0]),
        "perito_id":          None,
        "officina_id":        7,
        "tipo_documento":     "preventivo_officina",
        "titolo":             "Preventivo riparazione Volkswagen Golf",
        "descrizione":        "Preventivo per sostituzione paraurti posteriore, fanali e verniciatura portellone.",
        "stima_danno":        1320.0,
        "esito":              "in_valutazione",
        "stato":              "bozza",
        "note":               "In attesa di approvazione dalla compagnia UnipolSai.",
        "allegati":           [],
        "data_inserimento":   datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        "data_aggiornamento": None,
    },
    {
        "sinistro_id":        str(sin_ids[3]),
        "perito_id":          None,
        "officina_id":        7,
        "tipo_documento":     "fattura",
        "titolo":             "Fattura riparazione FIAT PANDA",
        "descrizione":        "Fattura finale per verniciatura fiancata sinistra FIAT PANDA.",
        "stima_danno":        850.0,
        "esito":              "approvato",
        "stato":              "chiusa",
        "note":               "Pagamento ricevuto. Pratica chiusa.",
        "allegati":           [],
        "data_inserimento":   datetime(2026, 4, 24, 10, 0, tzinfo=UTC),
        "data_aggiornamento": datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
    },
]

result_doc = documenti_col.insert_many(documenti_docs)
doc_ids = result_doc.inserted_ids
print(f"\n=== PROTO_DOCUMENTI_SC: {len(doc_ids)} documenti inseriti ===")
for i, oid in enumerate(doc_ids):
    print(f"  [{i+1}] {documenti_docs[i]['tipo_documento']} — {documenti_docs[i]['titolo'][:50]} → {oid}")

# ─────────────────────────────────────────────
#  5. AGGIORNA PRATICA_ID NEI SINISTRI
# ─────────────────────────────────────────────
# Collega sinistro → intervento (pratica_id)

sinistri_col.update_one(
    {"_id": sin_ids[0]},
    {"$set": {"pratica_id": str(int_ids[0])}}
)
sinistri_col.update_one(
    {"_id": sin_ids[2]},
    {"$set": {"pratica_id": str(int_ids[1])}}
)
sinistri_col.update_one(
    {"_id": sin_ids[3]},
    {"$set": {"pratica_id": str(int_ids[2])}}
)
sinistri_col.update_one(
    {"_id": sin_ids[4]},
    {"$set": {"pratica_id": str(int_ids[3])}}
)
print("\n=== PRATICA_ID collegati ai sinistri ===")

# ─────────────────────────────────────────────
#  6. RIEPILOGO
# ─────────────────────────────────────────────

print("\n" + "="*50)
print(" MIGRAZIONE COMPLETATA")
print("="*50)
for nome, col in [
    ("Proto_Sinistro_SC",   sinistri_col),
    ("Proto_Intervento_SC", interventi_col),
    ("Proto_Documenti_SC",  documenti_col),
]:
    print(f"  {nome}: {col.count_documents({})} documenti")

knowledge = db["Proto_Knowledge_SC"]
print(f"  Proto_Knowledge_SC: {knowledge.count_documents({})} documenti (invariata)")
print()
client.close()
