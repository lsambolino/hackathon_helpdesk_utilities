// Helpdesk Utilities — shared frontend logic.
// Vanilla JS, no framework. Page dispatch driven by <body data-page="...">.

(function () {
  "use strict";

  // ---------- fetch helpers ----------
  async function apiGet(path) {
    const res = await fetch(path, { headers: { "Accept": "application/json" } });
    if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
    return res.json();
  }
  async function apiPost(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
    return res.json();
  }

  // ---------- HTML helpers ----------
  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  function el(id) { return document.getElementById(id); }
  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" }) +
           " " + d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  }
  function fmtPct(v) {
    if (v === null || v === undefined) return "—";
    return (v * 100).toFixed(0) + "%";
  }
  function badge(text, cls) {
    return `<span class="badge ${cls || ""}">${escapeHtml(text)}</span>`;
  }

  // ---------- Tickets page ----------
  let selectedTicketId = null;

  async function loadTickets() {
    const tbody = el("tickets-tbody");
    tbody.innerHTML = `<tr><td colspan="9" class="empty">Caricamento ticket...</td></tr>`;
    try {
      const data = await apiGet("/api/tickets");
      renderTicketTable(data);
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="9" class="error">Errore nel caricamento: ${escapeHtml(e.message)}</td></tr>`;
    }
  }

  function renderTicketTable(tickets) {
    const tbody = el("tickets-tbody");
    if (!tickets || tickets.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="empty">Nessun ticket trovato.</td></tr>`;
      return;
    }
    tbody.innerHTML = tickets.map(t => `
      <tr data-id="${t.id}" class="${t.id === selectedTicketId ? "selected" : ""}">
        <td>#${t.id}</td>
        <td>${escapeHtml(t.customer_name || ("Cliente " + t.customer_id))}</td>
        <td>${escapeHtml(t.category || "—")}</td>
        <td>${escapeHtml(t.subject)}</td>
        <td>${badge(t.status, "status-" + t.status)}</td>
        <td>${badge(t.priority, "priority-" + t.priority)}</td>
        <td>${fmtDate(t.opened_at)}</td>
        <td>${t.agent_handled ? badge("agente", "agent") : ""}</td>
        <td>${t.confidence !== null && t.confidence !== undefined ? fmtPct(t.confidence) : "—"}</td>
      </tr>
    `).join("");
    Array.from(tbody.querySelectorAll("tr[data-id]")).forEach(tr => {
      tr.addEventListener("click", () => selectTicket(parseInt(tr.dataset.id, 10)));
    });
  }

  async function selectTicket(id) {
    selectedTicketId = id;
    Array.from(document.querySelectorAll("#tickets-tbody tr")).forEach(tr => {
      tr.classList.toggle("selected", parseInt(tr.dataset.id, 10) === id);
    });
    const pane = el("ticket-detail");
    pane.innerHTML = `<div class="empty">Caricamento dettaglio...</div>`;
    try {
      const t = await apiGet(`/api/tickets/${id}`);
      renderTicketDetail(t);
    } catch (e) {
      pane.innerHTML = `<div class="error">Errore: ${escapeHtml(e.message)}</div>`;
    }
  }

  function renderTicketDetail(t) {
    const pane = el("ticket-detail");
    const comments = (t.comments || []).map(c => `
      <div class="entry">
        <span class="who">${escapeHtml(c.author)}</span>
        <span class="when">${fmtDate(c.created_at)}</span>
        <div class="what">${escapeHtml(c.body)}</div>
      </div>
    `).join("") || `<div class="empty">Nessun commento.</div>`;

    const audit = (t.audit_log || []).map(a => `
      <div class="entry">
        <span class="who">${escapeHtml(a.actor)}</span>
        <span class="when">${fmtDate(a.ts)}</span>
        <div class="what">${escapeHtml(a.action)}${a.detail ? " — " + escapeHtml(a.detail) : ""}</div>
      </div>
    `).join("") || `<div class="empty">Nessuna azione registrata.</div>`;

    pane.innerHTML = `
      <div class="detail">
        <h3>#${t.id} — ${escapeHtml(t.subject)}</h3>
        <div class="meta">
          ${badge(t.status, "status-" + t.status)}
          ${badge(t.priority, "priority-" + t.priority)}
          ${t.agent_handled ? badge("gestito da agente", "agent") : ""}
          ${t.confidence !== null && t.confidence !== undefined ? badge("confidenza " + fmtPct(t.confidence)) : ""}
        </div>
        <div class="meta">
          <strong>Cliente:</strong> ${escapeHtml(t.customer_name || ("#" + t.customer_id))}
          &nbsp;·&nbsp; <strong>Categoria:</strong> ${escapeHtml(t.category || "non classificato")}
          &nbsp;·&nbsp; <strong>Canale:</strong> ${escapeHtml(t.channel)}
          &nbsp;·&nbsp; <strong>Aperto:</strong> ${fmtDate(t.opened_at)}
        </div>
        <div class="body">${escapeHtml(t.body)}</div>

        <div style="margin-top: 16px;">
          <button class="btn" id="btn-triage">Esegui agente sul ticket</button>
          <span id="triage-result" style="margin-left: 12px; font-size: 12px; color: var(--muted);"></span>
        </div>

        <div class="timeline">
          <h4>Commenti</h4>
          ${comments}
          <h4>Audit log</h4>
          ${audit}
        </div>
      </div>
    `;
    el("btn-triage").addEventListener("click", () => runTriage(t.id));
  }

  async function runTriage(id) {
    const btn = el("btn-triage");
    const out = el("triage-result");
    btn.disabled = true;
    out.textContent = "Esecuzione agente in corso...";
    try {
      const r = await apiPost(`/api/tickets/${id}/triage`, {});
      out.innerHTML = `Azione: <strong>${escapeHtml(r.action || "—")}</strong> · ` +
                      `Categoria: <strong>${escapeHtml(r.category || "—")}</strong> · ` +
                      `Confidenza: <strong>${fmtPct(r.confidence)}</strong>` +
                      (r.escalated ? ` · ${badge("escalation", "status-escalated")}` : "");
      // Refresh detail and list
      await selectTicket(id);
      await loadTickets();
    } catch (e) {
      out.innerHTML = `<span class="error">Errore: ${escapeHtml(e.message)}</span>`;
    } finally {
      btn.disabled = false;
    }
  }

  function initTicketsPage() {
    loadTickets();
  }

  // ---------- Chat page ----------
  let chatSessionId = null;
  const chatHistory = [];

  function renderChat() {
    const box = el("chat-history");
    box.innerHTML = chatHistory.map(m => {
      const ticketNote = m.ticket_id
        ? `<span class="ticket-note">Ticket #${m.ticket_id} aperto</span>`
        : "";
      return `<div class="chat-bubble ${m.role}">${escapeHtml(m.text)}${ticketNote}</div>`;
    }).join("");
    box.scrollTop = box.scrollHeight;
  }

  async function sendChat() {
    const input = el("chat-input-field");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    chatHistory.push({ role: "user", text });
    renderChat();

    const btn = el("chat-send");
    btn.disabled = true;
    try {
      const payload = { message: text };
      if (chatSessionId) payload.session_id = chatSessionId;
      const r = await apiPost("/api/chat", payload);
      if (r.session_id) chatSessionId = r.session_id;
      chatHistory.push({ role: "bot", text: r.reply || "(nessuna risposta)", ticket_id: r.ticket_id });
      renderChat();
    } catch (e) {
      chatHistory.push({ role: "bot", text: "Errore di comunicazione: " + e.message });
      renderChat();
    } finally {
      btn.disabled = false;
      input.focus();
    }
  }

  function initChatPage() {
    chatHistory.push({
      role: "bot",
      text: "Buongiorno, sono l'assistente virtuale del servizio idrico. Come posso aiutarla?"
    });
    renderChat();
    el("chat-send").addEventListener("click", sendChat);
    el("chat-input-field").addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); sendChat(); }
    });
    el("chat-input-field").focus();
  }

  // ---------- Dashboard page ----------
  async function initDashPage() {
    const root = el("dash-root");
    try {
      const d = await apiGet("/api/dashboard");
      renderDash(d);
    } catch (e) {
      root.innerHTML = `<div class="error">Errore nel caricamento dashboard: ${escapeHtml(e.message)}</div>`;
    }
  }

  function renderDash(d) {
    const k = d.kpis || {};
    const s = d.savings || {};
    const h = d.historical_insights || {};

    const kpiHtml = `
      <div class="kpi-grid">
        <div class="card kpi">
          <div class="label">Tasso auto-risoluzione</div>
          <div class="value">${k.auto_resolution_rate_pct !== undefined ? k.auto_resolution_rate_pct + "%" : "—"}</div>
          <div class="sub">ticket chiusi senza intervento umano</div>
        </div>
        <div class="card kpi">
          <div class="label">Tempo medio gestione</div>
          <div class="value">${k.avg_agent_handle_min !== undefined ? k.avg_agent_handle_min + "'" : "—"}</div>
          <div class="sub">vs ${k.avg_human_handle_min || "—"}' umano · −${k.handle_time_reduction_pct || 0}%</div>
        </div>
        <div class="card kpi">
          <div class="label">Escalation</div>
          <div class="value">${k.escalation_rate_pct !== undefined ? k.escalation_rate_pct + "%" : "—"}</div>
          <div class="sub">ticket inoltrati a operatore</div>
        </div>
        <div class="card kpi">
          <div class="label">Ticket ultimi 7 giorni</div>
          <div class="value">${k.tickets_last_7d !== undefined ? k.tickets_last_7d : "—"}</div>
          <div class="sub">volume settimanale</div>
        </div>
      </div>
    `;

    const savingsHtml = s.annual_saving_eur !== undefined ? `
      <div class="card" style="margin-top: 16px; background: #e7f6f3;">
        <h3 style="margin: 0 0 8px; font-size: 14px; color: #0f766e;">Risparmio annuo stimato</h3>
        <div style="font-size: 32px; font-weight: 700; color: #0f766e;">${escapeHtml(s.annual_saving_eur_human_readable || "")}</div>
        <div style="font-size: 13px; color: var(--muted); margin-top: 6px;">
          ${s.annual_tickets_assumed?.toLocaleString("it-IT")} ticket/anno × €${s.saving_per_ticket_eur} risparmiato per ticket
          (umano €${s.cost_per_ticket_human_eur} → agentico €${s.cost_per_ticket_agent_eur})
        </div>
      </div>
    ` : "";

    const cats = d.by_category || [];
    const maxCount = cats.reduce((m, c) => Math.max(m, c.n || 0), 1);
    const barsHtml = cats.length === 0
      ? `<div class="empty">Nessun dato disponibile.</div>`
      : cats.map(c => `
          <div class="bar-row">
            <div class="label">${escapeHtml(c.category || "—")}</div>
            <div class="bar"><div class="fill" style="width: ${(100 * (c.n || 0) / maxCount).toFixed(1)}%"></div></div>
            <div class="count">${c.n || 0}</div>
          </div>
        `).join("");

    const zones = d.spike_forecast || [];
    const zonesHtml = zones.length === 0
      ? `<div class="empty">Nessuna previsione disponibile.</div>`
      : `<div class="zone-list">` + zones.map(z => `
          <div class="zone-card risk-${escapeHtml(z.risk || "low")}">
            <div class="zone-name">${escapeHtml(z.zone)}</div>
            <div class="zone-meta">Rischio: ${escapeHtml(z.risk || "—")} · ${z.recent_count || 0} recenti vs ${z.prior_count || 0} prima</div>
            <div class="zone-meta">Crescita: ${z.growth_pct !== undefined ? z.growth_pct + "%" : "—"}</div>
          </div>
        `).join("") + `</div>`;

    let historicalHtml = "";
    if (h && h.available) {
      const topCatsHtml = (h.top_categories || []).slice(0, 5).map(c =>
        `<div class="bar-row">
           <div class="label">${escapeHtml(c.category)}</div>
           <div class="count">${c.count}</div>
         </div>`
      ).join("");
      historicalHtml = `
        <div class="card" style="margin-top: 24px;">
          <h3 style="margin: 0 0 12px; font-size: 14px;">Backlog storico — 1.000 reclami chiusi</h3>
          <div class="kpi-grid" style="margin-bottom: 12px;">
            <div class="card kpi"><div class="label">Tempo medio risoluzione</div><div class="value">${h.avg_resolution_days || "—"} <small style="font-size:14px;color:var(--muted);">giorni</small></div><div class="sub">baseline storico</div></div>
            <div class="card kpi"><div class="label">CSAT medio</div><div class="value">${h.avg_csat_score || "—"} <small style="font-size:14px;color:var(--muted);">/5</small></div><div class="sub">soddisfazione cliente</div></div>
            <div class="card kpi"><div class="label">Importo contestato</div><div class="value">€${(h.disputed_amount_eur_total || 0).toLocaleString("it-IT", {maximumFractionDigits: 0})}</div><div class="sub">su ${h.total_complaints} reclami</div></div>
            <div class="card kpi"><div class="label">Reclami totali</div><div class="value">${h.total_complaints}</div><div class="sub">categorie: 14</div></div>
          </div>
          <h4 style="margin: 12px 0 6px; font-size: 13px; color: var(--muted);">Top 5 categorie storiche</h4>
          ${topCatsHtml}
        </div>
      `;
    }

    el("dash-root").innerHTML = `
      ${kpiHtml}
      ${savingsHtml}
      <div class="split">
        <div class="card">
          <h3 style="margin: 0 0 12px; font-size: 14px;">Ticket per categoria (ultimi 30 giorni)</h3>
          ${barsHtml}
        </div>
        <div class="card">
          <h3 style="margin: 0 0 12px; font-size: 14px;">Previsione disservizi</h3>
          ${zonesHtml}
        </div>
      </div>
      ${historicalHtml}
    `;
  }

  // ---------- dispatcher ----------
  document.addEventListener("DOMContentLoaded", () => {
    const page = document.body.dataset.page;
    if (page === "tickets") initTicketsPage();
    else if (page === "chat") initChatPage();
    else if (page === "dash") initDashPage();
  });

  // expose for debugging
  window.HD = { apiGet, apiPost };
})();
