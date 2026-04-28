"""Synthetic Italian-flavored seed data for the helpdesk demo.

Domain: public water utility, Lombardy. ~30 customers, mix of B2C/B2B,
~80 invoices, ~15 switches, ~25 tickets (mix of open/closed),
~6 KB articles, ~3 outages.

Run:  python -m app.seed
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from app.db import init_db, conn_ctx, now_iso

random.seed(42)

ZONES = [
    "Milano-Centro", "Milano-Sud", "Milano-Nord",
    "Bergamo", "Brescia", "Como", "Pavia",
    "Mantova", "Cremona", "Lecco", "Lodi",
]

B2C_NAMES = [
    "Marco Rossi", "Giulia Bianchi", "Andrea Romano", "Francesca Russo",
    "Luca Ferrari", "Chiara Esposito", "Matteo Conti", "Sara Greco",
    "Davide Marino", "Elena Ricci", "Giovanni Lombardi", "Alessia Bruno",
    "Stefano Galli", "Martina Costa", "Federico Moretti", "Valentina De Luca",
    "Roberto Barbieri", "Anna Mancini", "Paolo Villa", "Silvia Fontana",
]

B2B_NAMES = [
    ("Trattoria da Gianni SRL", "IT01234567890"),
    ("Hotel Excelsior SPA", "IT09876543210"),
    ("Pasticceria Lombarda SAS", "IT11122233344"),
    ("Lavanderia Industriale Po SRL", "IT55566677788"),
    ("Centro Sportivo Aquatica SSD", "IT99988877766"),
    ("Ristorante Il Navigliante SRL", "IT44455566677"),
    ("Azienda Agricola Verdi SS", "IT33344455566"),
    ("Officina Meccanica Brescia SRL", "IT22233344455"),
    ("Stabilimento Tessile Como SPA", "IT66677788899"),
    ("Pizzeria Margherita SNC", "IT77788899900"),
]

KB = [
    ("Come leggere il contatore dell'acqua",
     "Il contatore mostra i metri cubi consumati. Per l'autolettura, fotografa il numero nero (escludi i decimali rossi) e invialo dall'area clienti o tramite chatbot. La lettura va effettuata almeno una volta a trimestre per evitare conguagli.",
     "contatore,lettura,autolettura"),
    ("Cosa fare se non ricevo la bolletta",
     "Se la bolletta non arriva entro 5 giorni dalla data prevista, verifica: (1) email/spam per la versione digitale, (2) indirizzo di recapito aggiornato in area clienti, (3) eventuali sospensioni del servizio postale nella tua zona. È sempre possibile scaricare la bolletta dall'area clienti senza aspettare il recapito.",
     "bolletta,recapito,fattura"),
    ("Procedura di voltura",
     "La voltura trasferisce il contratto a un nuovo intestatario senza interruzione del servizio. Servono: documento d'identità del nuovo intestatario, codice fiscale, lettura del contatore al momento della voltura, e per i B2B la visura camerale. Tempistica standard: 7 giorni lavorativi.",
     "voltura,subentro,cambio intestatario"),
    ("Switch fornitore: tempistiche e blocchi",
     "Lo switch verso un nuovo fornitore richiede tipicamente 21 giorni. Cause comuni di blocco: morosità (debito non saldato), contratto a termine ancora attivo, indirizzo di fornitura non corrispondente. In caso di blocco viene inviata comunicazione formale entro 3 giorni.",
     "switch,cambio fornitore,morosità"),
    ("Segnalazione perdite e disservizi",
     "Per perdite visibili (rotture, fughe, allagamenti) chiamare il pronto intervento 800-XXX-XXX attivo 24/7. Per cali di pressione o discontinuità verificare prima sul sito gli avvisi di disservizio nella tua zona; se non presenti, apri ticket dall'area clienti o chatbot.",
     "perdita,rottura,disservizio,pressione"),
    ("Rateizzazione e piani di pagamento",
     "Per importi superiori a 100€ è possibile richiedere la rateizzazione fino a 12 mensilità senza interessi (24 con interessi convenzionati). La domanda va presentata entro la scadenza della bolletta. I clienti vulnerabili (legge 4/2022) hanno priorità e condizioni agevolate.",
     "rateizzazione,piano pagamento,vulnerabili"),
]

OUTAGES = [
    ("Bergamo", -2, None, "high",
     "Rottura condotta principale via Roma; squadre al lavoro, ripristino previsto in giornata."),
    ("Como", -9, -8, "medium",
     "Manutenzione programmata rete idrica zona lago, servizio ripristinato."),
    ("Milano-Sud", -1, None, "low",
     "Cali di pressione localizzati per lavori di pulizia tubazioni; nessuna sospensione prevista."),
]

# Ticket templates — (subject, body, true_category, channel)
TICKET_TEMPLATES = [
    ("Bolletta marzo non ricevuta",
     "Buongiorno, non ho ancora ricevuto la bolletta del trimestre scorso. Il pagamento mi risulta in scadenza ma non ho il documento. Potete inviarmela?",
     "billing", "email"),
    ("Importo bolletta errato",
     "La mia ultima bolletta è di 312€ ma il consumo medio è sempre stato sotto i 90€. Credo ci sia un errore di lettura. Chiedo verifica.",
     "billing", "web"),
    ("Voltura non andata a buon fine",
     "Ho richiesto la voltura del contratto a nome di mia moglie il mese scorso ma il contatore risulta ancora a mio nome e ho ricevuto bolletta intestata a me. Cosa è successo?",
     "switching", "email"),
    ("Switch a nuovo gestore bloccato",
     "Ho richiesto il passaggio ad altro fornitore ma è bloccato da settimane. Non ho debiti aperti, vorrei capire il motivo.",
     "switching", "phone"),
    ("Pressione acqua bassissima zona Centro",
     "Da due giorni in via Garibaldi la pressione è praticamente nulla, riusciamo a malapena a riempire un bicchiere. Tutto il palazzo segnala lo stesso.",
     "outage", "chat"),
    ("Perdita su strada via Manzoni",
     "Segnalo grossa perdita d'acqua dal manto stradale all'incrocio Manzoni/Verdi, sta allagando la carreggiata.",
     "outage", "phone"),
    ("Lettura contatore non corrispondente",
     "La bolletta riporta una lettura di 1840 m³ ma il mio contatore segna 1612 m³. Allego foto. Vorrei rettifica.",
     "billing", "web"),
    ("Richiesta rateizzazione bolletta conguaglio",
     "Ho ricevuto un conguaglio annuale di 480€, non riesco a pagarlo in un'unica soluzione. Posso rateizzare?",
     "billing", "email"),
    ("Errore IVA bolletta B2B",
     "Sono titolare di Trattoria da Gianni SRL, l'ultima bolletta riporta IVA al 22% ma per uso commerciale alimentare dovrebbe essere al 10%. Chiedo nota di credito.",
     "billing", "email"),
    ("Disservizio acqua zona Bergamo",
     "Da stamattina manca completamente l'acqua a Bergamo zona via Roma. Quando torna?",
     "outage", "chat"),
    ("Cambio indirizzo recapito bolletta",
     "Ho cambiato casa, vorrei ricevere le bollette al nuovo indirizzo. Come faccio?",
     "general", "web"),
    ("Voltura per decesso intestatario",
     "Mio padre è venuto a mancare, devo intestare il contratto a mio nome. Quali documenti servono?",
     "switching", "email"),
    ("Bolletta doppia stesso periodo",
     "Ho ricevuto due bollette per lo stesso trimestre, importi diversi. Una è giusta o sbagliate entrambe?",
     "billing", "email"),
    ("Sospensione fornitura ingiustificata",
     "Mi è stata sospesa la fornitura ma ho pagato tutto regolarmente, ho la ricevuta. Riattivate subito.",
     "billing", "phone"),
    ("Acqua torbida dal rubinetto",
     "Da ieri esce acqua marrone dai rubinetti di tutta casa. È pericolosa? Cosa devo fare?",
     "outage", "chat"),
    ("Richiesta autolettura contatore",
     "Vorrei comunicare la lettura del contatore: 2156 m³ al 28/04. Codice cliente: vedere intestazione.",
     "general", "web"),
    ("Switch annullato senza motivo",
     "Ho richiesto switch a un altro gestore, mi avete scritto che è annullato ma senza spiegare perché.",
     "switching", "email"),
    ("Bolletta arrivata in ritardo, chiedo proroga",
     "La bolletta mi è arrivata con 10 giorni di ritardo, non riesco a pagarla entro la scadenza. Posso avere proroga?",
     "billing", "web"),
    ("Contatore bloccato non gira",
     "Il contatore non scatta più da due settimane ma noi consumiamo regolarmente. Sostituire?",
     "general", "phone"),
    ("Allacciamento nuovo locale commerciale",
     "Apriamo nuova pizzeria in via Dante 12 Milano, abbiamo bisogno di nuovo allacciamento idrico per uso commerciale.",
     "general", "email"),
]


def days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).isoformat(timespec="seconds")


def seed() -> None:
    init_db(force=True)
    with conn_ctx() as c:
        # Customers
        cust_ids: list[int] = []
        for i, name in enumerate(B2C_NAMES):
            cur = c.execute(
                "INSERT INTO customers (type,name,address,zone,email,phone,vulnerable) VALUES ('B2C',?,?,?,?,?,?)",
                (
                    name,
                    f"Via {random.choice(['Roma','Garibaldi','Manzoni','Dante','Verdi'])} {random.randint(1,120)}",
                    random.choice(ZONES),
                    f"{name.split()[0].lower()}.{name.split()[1].lower()}@example.it",
                    f"+39 3{random.randint(10,99)} {random.randint(1000000,9999999)}",
                    1 if random.random() < 0.10 else 0,
                ),
            )
            cust_ids.append(cur.lastrowid)
        for name, vat in B2B_NAMES:
            cur = c.execute(
                "INSERT INTO customers (type,name,address,zone,vat_id,email,phone) VALUES ('B2B',?,?,?,?,?,?)",
                (
                    name,
                    f"Via {random.choice(['Industria','Commercio','Lavoro','Mercato'])} {random.randint(1,80)}",
                    random.choice(ZONES),
                    vat,
                    f"amministrazione@{name.split()[0].lower()}.it",
                    f"+39 0{random.randint(10,99)} {random.randint(1000000,9999999)}",
                ),
            )
            cust_ids.append(cur.lastrowid)

        # Invoices: 3-5 per customer
        for cid in cust_ids:
            for q, period in enumerate(["2025-Q3", "2025-Q4", "2026-Q1"]):
                amount = round(random.uniform(40, 280) if cid <= 20 else random.uniform(180, 1200), 2)
                status = random.choices(
                    ["paid", "pending", "overdue", "disputed"],
                    weights=[0.65, 0.20, 0.10, 0.05],
                )[0]
                issued = days_ago(90 - q * 30)
                due = days_ago(60 - q * 30)
                c.execute(
                    "INSERT INTO invoices (customer_id,period,amount_eur,status,issued_date,due_date) VALUES (?,?,?,?,?,?)",
                    (cid, period, amount, status, issued, due),
                )

        # Switches
        for cid in random.sample(cust_ids, 15):
            status = random.choices(
                ["requested", "in_progress", "completed", "failed", "blocked"],
                weights=[0.15, 0.25, 0.30, 0.15, 0.15],
            )[0]
            blocker = None
            if status == "blocked":
                blocker = random.choice(["unpaid_balance", "contract_lock", "address_mismatch"])
            elif status == "failed":
                blocker = "provider_rejected"
            c.execute(
                "INSERT INTO switches (customer_id,target_provider,status,blocker,opened_at,closed_at) VALUES (?,?,?,?,?,?)",
                (
                    cid,
                    random.choice(["AcquaSrl", "IdroPlus SPA", "BlueWater Italia", "EcoIdrica"]),
                    status,
                    blocker,
                    days_ago(random.randint(5, 60)),
                    days_ago(random.randint(0, 4)) if status in ("completed", "failed") else None,
                ),
            )

        # KB articles
        for title, body, tags in KB:
            c.execute("INSERT INTO kb_articles (title,body,tags) VALUES (?,?,?)", (title, body, tags))

        # Outages
        for zone, start_off, end_off, sev, desc in OUTAGES:
            c.execute(
                "INSERT INTO outages (zone,started_at,ended_at,severity,description) VALUES (?,?,?,?,?)",
                (
                    zone,
                    days_ago(-start_off),
                    days_ago(-end_off) if end_off is not None else None,
                    sev,
                    desc,
                ),
            )

        # Tickets — mix of recent open and historical closed
        n_tickets = 80
        for i in range(n_tickets):
            tpl = random.choice(TICKET_TEMPLATES)
            subject, body, true_cat, channel = tpl
            cid = random.choice(cust_ids)
            opened_at = days_ago(random.randint(0, 90))
            # ~60% are historical/resolved, 40% are open/in-flight (so dashboard has both)
            if random.random() < 0.60:
                status = random.choice(["resolved", "closed"])
                closed_at = days_ago(random.randint(0, 89))
                agent_handled = 1 if random.random() < 0.70 else 0
                confidence = round(random.uniform(0.72, 0.98), 2)
                resolution = "Risolto via auto-agente." if agent_handled else "Risolto da operatore umano."
                escalation = None if agent_handled else random.choice(
                    ["low_confidence", "high_amount", "vulnerable_customer", "policy_exception"]
                )
            else:
                status = "open"
                closed_at = None
                agent_handled = 0
                confidence = None
                resolution = None
                escalation = None
            c.execute(
                "INSERT INTO tickets "
                "(customer_id,channel,category,subject,body,status,priority,opened_at,closed_at,"
                " agent_handled,confidence,escalation_reason,resolution_summary) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cid, channel, true_cat if status != "open" else None,
                    subject, body, status,
                    random.choice(["low", "medium", "medium", "high", "urgent"]),
                    opened_at, closed_at, agent_handled, confidence, escalation, resolution,
                ),
            )

        print(f"[seed] inserted {len(cust_ids)} customers, {n_tickets} tickets, {len(KB)} KB articles, {len(OUTAGES)} outages")


if __name__ == "__main__":
    seed()
