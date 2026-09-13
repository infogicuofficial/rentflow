/* RentFlow payment portal — post-paid billing logic (client side) */
(function () {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const el = {
    building: $("#sel-building"),
    flat: $("#sel-flat"),
    steps: [null, $("#step-1"), $("#step-2"), $("#step-3"), $("#step-4"), $("#step-5")],
    occFields: $("#occ-fields"),
    occSkel: $("#occ-skeletons"),
    vacantNote: $("#vacant-note"),
    monthList: $("#month-list"),
    dueAlert: $("#due-alert"),
    upcomingNote: $("#upcoming-note"),
    amountField: $("#amount-field"),
    amount: $("#f-amount"),
    summary: $("#summary-body"),
    verifyOut: $("#verify-out"),
    btnVerify: $("#btn-verify"),
    btnPreview: $("#btn-preview"),
    btnGenerate: $("#btn-generate"),
    depositCard: $("#deposit-card"),
    depositInfo: $("#deposit-info"),
    topupBlock: $("#topup-block"),
    topupAmount: $("#topup-amount"),
    topupMethod: $("#topup-method"),
  };

  let ctx = null;       // flat context from server
  let verified = false;

  function unlock(n) { el.steps[n]?.classList.remove("locked"); }
  function lockFrom(n) {
    for (let i = n; i <= 5; i++) el.steps[i]?.classList.add("locked");
    verified = false;
    el.btnPreview.hidden = true;
    el.verifyOut.innerHTML = "";
  }
  function markDone(n, done) {
    el.steps[n]?.classList.toggle("done", done);
  }

  // ---- Step 1: building → flats ------------------------------------------
  el.building.addEventListener("change", async () => {
    lockFrom(2);
    el.flat.innerHTML = "<option>Loading…</option>";
    el.flat.disabled = true;
    if (!el.building.value) return;
    const r = await fetch(`/payments/api/flats/?building=${el.building.value}`);
    const d = await r.json();
    el.flat.innerHTML = '<option value="">— Select flat —</option>' +
      d.flats.map((f) => `<option value="${f.id}">${f.label}</option>`).join("");
    el.flat.disabled = false;
  });

  el.flat.addEventListener("change", loadFlatContext);

  async function loadFlatContext() {
    lockFrom(3);
    if (!el.flat.value) { lockFrom(2); return; }
    unlock(2);
    el.occFields.hidden = true;
    el.vacantNote.hidden = true;
    el.occSkel.hidden = false;

    const r = await fetch(`/payments/api/flat-context/?flat=${el.flat.value}`);
    ctx = await r.json();
    el.occSkel.hidden = true;

    if (!ctx.occupied) {
      el.vacantNote.hidden = false;
      renderSummary();
      return;
    }
    $("#f-name").value = ctx.occupant.name;
    $("#f-id").value = `${ctx.occupant.occupant_id}${ctx.occupant.nid ? " / " + ctx.occupant.nid : ""}`;
    $("#f-email").value = ctx.occupant.email;
    $("#f-phone").value = ctx.occupant.phone;
    $("#f-rent").value = rfMoney(ctx.current_rent);
    $("#tenancy-note").textContent =
      `Tenancy started ${ctx.start_date}. ${ctx.billing_note}`;
    el.occFields.hidden = false;
    markDone(1, true); markDone(2, true);
    unlock(3);
    renderMonths();
    renderDepositCard();
    renderSummary();
  }

  // ---- Step 3: due months --------------------------------------------------
  function renderMonths() {
    const payable = ctx.months.filter((m) => m.status !== "upcoming");
    const overdue = payable.filter((m) => m.status === "overdue");
    const upcoming = ctx.months.find((m) => m.status === "upcoming");

    el.dueAlert.innerHTML = "";
    if (overdue.length) {
      el.dueAlert.innerHTML = `
        <div class="alert alert-red">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.8 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.8a2 2 0 0 0-3.4 0z"/></svg>
          <div><b>${overdue.map((m) => m.label).join(" and ")} rent ${overdue.length > 1 ? "are" : "is"} OVERDUE — collect now.</b>
          Rent is due by the 20th of the following month.</div>
        </div>`;
    } else if (payable.length) {
      el.dueAlert.innerHTML = `
        <div class="alert alert-amber">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>
          <div><b>${payable.map((m) => m.label).join(", ")} rent is now payable.</b>
          Due by ${payable[payable.length - 1].due_date}.</div>
        </div>`;
    } else {
      el.dueAlert.innerHTML = `
        <div class="alert alert-green">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg>
          <div><b>All finished months are fully paid.</b> Nothing is payable right now — the current month is billed next month.</div>
        </div>`;
    }

    el.monthList.innerHTML = payable.map((m) => `
      <label class="check-row month-check">
        <input type="checkbox" value="${m.key}" data-rent="${m.rent}">
        <div class="meta">
          <div style="font-weight:700;">${m.label} rent</div>
          <div class="small muted">
            payable from 1st of following month · due ${m.due_date}
            ${m.status === "overdue" ? `· <b style="color:var(--red-600)">${m.days_overdue} days overdue</b>` : ""}
          </div>
          ${Number(m.increase) > 0 ? `<div class="inc">includes rent increase of ${rfMoney(m.increase)} over the original contract</div>` : ""}
        </div>
        <div class="rent">${rfMoney(m.rent)}</div>
      </label>`).join("");

    el.upcomingNote.innerHTML = upcoming ? `
      <div class="small muted" style="margin-top:10px; padding:10px 13px; border:1px dashed var(--gray-300); border-radius:6px;">
        <b>${upcoming.label}</b> (current month) is not billable yet — it becomes payable
        on the 1st of next month and due by ${upcoming.due_date}. Post-paid billing never charges the running month.
      </div>` : "";

    el.monthList.querySelectorAll("input").forEach((cb) =>
      cb.addEventListener("change", onMonthsChanged));
  }

  function selectedMonths() {
    return [...el.monthList.querySelectorAll("input:checked")].map((cb) => ({
      key: cb.value, rent: Number(cb.dataset.rent),
    }));
  }

  function onMonthsChanged() {
    lockFrom(5);
    const sel = selectedMonths();
    if (sel.length) {
      unlock(4);
      markDone(3, true);
      const total = sel.reduce((a, m) => a + m.rent, 0);
      el.amount.value = total.toFixed(2);
    } else {
      lockFrom(4);
      markDone(3, false);
    }
    updateDepositUI();
    renderSummary();
  }

  // ---- Step 4: methods -----------------------------------------------------
  const methodFields = { cash: "#mf-cash", bank: "#mf-bank", bkash: "#mf-bkash", deposit: "#mf-deposit" };
  document.querySelectorAll('input[name="method"]').forEach((r) =>
    r.addEventListener("change", () => {
      lockFrom(5);
      Object.values(methodFields).forEach((s) => ($(s).hidden = true));
      $(methodFields[r.value]).hidden = false;
      el.amountField.hidden = r.value === "deposit";
      if (r.value === "deposit") updateDepositUI();
      unlock(5);
      markDone(4, true);
      renderSummary();
    }));

  function currentMethod() {
    return document.querySelector('input[name="method"]:checked')?.value || "";
  }

  function renderDepositCard() {
    const d = ctx.deposit;
    const input = el.depositCard.querySelector("input");
    if (!d.can_use) {
      input.disabled = true;
      el.depositCard.style.opacity = 0.55;
      el.depositCard.querySelector(".d").textContent = d.notice_given
        ? "Deposit balance exhausted"
        : "Locked — only available once the occupant has given notice to leave";
    } else {
      input.disabled = false;
      el.depositCard.style.opacity = 1;
      el.depositCard.querySelector(".d").textContent =
        `Balance available: ${rfMoney(d.balance)}`;
    }
  }

  function updateDepositUI() {
    if (currentMethod() !== "deposit" || !ctx) return;
    const sel = selectedMonths();
    const chosen = ctx.months.filter((m) => sel.some((s) => s.key === m.key));
    const basePart = chosen.reduce((a, m) => a + Math.min(Number(m.rent), Number(m.base_rent)), 0);
    const topup = chosen.reduce((a, m) => a + Math.max(Number(m.increase), 0), 0);
    const bal = Number(ctx.deposit.balance);

    el.depositInfo.innerHTML = `
      Security deposit balance: <b>${rfMoney(bal)}</b><br>
      Base rent to settle from deposit: <b>${rfMoney(basePart)}</b> →
      remaining after this payment: <b>${rfMoney(bal - basePart)}</b>
      ${bal < basePart ? '<br><span style="color:var(--red-600); font-weight:700;">Insufficient deposit balance for the selected months.</span>' : ""}
      <br><span class="small">Note: if the rent has increased, the deposit only covers the original
      contract rent — the increase is charged separately below.</span>`;

    el.topupBlock.hidden = topup <= 0;
    if (topup > 0) el.topupAmount.textContent = rfMoney(topup);
  }

  el.topupMethod?.addEventListener("change", () => {
    ["cash", "bank", "bkash"].forEach((m) =>
      ($(`#tf-${m}`).hidden = el.topupMethod.value !== m));
  });

  // ---- summary rail ---------------------------------------------------------
  function renderSummary() {
    if (!ctx || !ctx.occupied) {
      el.summary.innerHTML = '<div class="empty" style="padding:28px 10px;">Select an occupied flat to begin.</div>';
      return;
    }
    const sel = selectedMonths();
    const chosen = ctx.months.filter((m) => sel.some((s) => s.key === m.key));
    const total = chosen.reduce((a, m) => a + Number(m.rent), 0);
    const method = currentMethod();
    const rows = chosen.map((m) => `
      <div class="row"><span>${m.label}</span><span class="mono">${rfMoney(m.rent)}</span></div>`).join("");
    el.summary.innerHTML = `
      <div class="row"><span class="muted">Occupant</span><span style="font-weight:700;">${ctx.occupant.name}</span></div>
      <div class="row"><span class="muted">Method</span><span style="font-weight:700;">${method ? { cash: "Cash", bank: "Bank transfer", bkash: "Bkash", deposit: "Security deposit" }[method] : "—"}</span></div>
      ${rows || '<div class="row"><span class="muted">Months</span><span>—</span></div>'}
      <div class="total"><span>Total</span><span class="amt">${rfMoney(total)}</span></div>`;
  }

  // ---- collect payload -------------------------------------------------------
  function collectDetails(scope, attr) {
    const out = {};
    document.querySelectorAll(`${scope} [${attr}]`).forEach((i) => {
      out[i.getAttribute(attr)] = i.value.trim();
    });
    return out;
  }

  function buildPayload() {
    const method = currentMethod();
    const payload = {
      occupancy_id: ctx.occupancy_id,
      months: selectedMonths().map((m) => m.key),
      method,
      details: method && method !== "deposit" ? collectDetails(methodFields[method], "data-det") : {},
      amount: el.amount.value || "0",
      payment_date: $("#f-date").value,
    };
    if (method === "deposit") {
      payload.topup_method = el.topupMethod.value || "";
      payload.topup_details = payload.topup_method
        ? collectDetails(`#tf-${payload.topup_method}`, "data-tdet") : {};
    }
    return payload;
  }

  // ---- Step 5: verify ---------------------------------------------------------
  el.btnVerify.addEventListener("click", async () => {
    el.btnVerify.disabled = true;
    el.verifyOut.innerHTML = '<div class="small muted"><span class="spinner"></span> Checking…</div>';
    try {
      const r = await fetch("/payments/api/verify/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": rfCsrf() },
        body: JSON.stringify(buildPayload()),
      });
      const d = await r.json();
      verified = d.ok;
      if (d.ok) {
        el.verifyOut.innerHTML = `
          <div class="verify-result verify-ok">
            <b>✓ All checks passed.</b> Occupant confirmed as current resident,
            amounts match (${rfMoney(d.total_rent)} for ${d.months.join(", ")})
            ${Number(d.topup_total) > 0 ? ` plus a rent-increase top-up of ${rfMoney(d.topup_total)}` : ""}.
            ${d.warnings.length ? "<ul>" + d.warnings.map((w) => `<li>${w}</li>`).join("") + "</ul>" : ""}
          </div>`;
        el.btnPreview.hidden = false;
        markDone(5, false);
      } else {
        el.verifyOut.innerHTML = `
          <div class="verify-result verify-bad">
            <b>Fix the following before generating an invoice:</b>
            <ul>${d.errors.map((e) => `<li>${e}</li>`).join("")}</ul>
          </div>`;
        el.btnPreview.hidden = true;
      }
    } catch {
      rfToast("Verification failed — network error.", "error");
    }
    el.btnVerify.disabled = false;
  });

  // ---- preview + generate --------------------------------------------------------
  el.btnPreview.addEventListener("click", () => {
    const sel = selectedMonths();
    const chosen = ctx.months.filter((m) => sel.some((s) => s.key === m.key));
    const total = chosen.reduce((a, m) => a + Number(m.rent), 0);
    $("#inv-preview").innerHTML = `
      <div class="head"><b>RentFlow — Rent invoice</b><span>${new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}</span></div>
      <table class="table">
        <tr><th>Billed to</th><td>${ctx.occupant.name} (${ctx.occupant.occupant_id})</td></tr>
        <tr><th>Property</th><td>Flat ${el.flat.options[el.flat.selectedIndex].text}</td></tr>
        ${chosen.map((m) => `<tr><td>${m.label} rent</td><td class="num">${rfMoney(m.rent)}</td></tr>`).join("")}
        <tr><th>Total</th><th class="num" style="color:var(--orange-600)">${rfMoney(total)}</th></tr>
      </table>`;
    $("#inv-email").value = ctx.occupant.email;
    rfModal.open("invoice-modal");
  });

  el.btnGenerate.addEventListener("click", async () => {
    if (!verified) { rfToast("Run the auto-check first.", "warning"); return; }
    $("#gen-spin").hidden = false;
    el.btnGenerate.disabled = true;
    const payload = buildPayload();
    payload.email = $("#inv-email").value.trim();
    payload.send_email = $("#inv-send-email").checked;
    try {
      const r = await fetch("/payments/api/generate-invoice/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": rfCsrf() },
        body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (d.ok) {
        rfToast(`Invoice ${d.invoice.number} generated${d.invoice.email_sent ? " and emailed" : ""}.`, "success");
        setTimeout(() => (window.location.href = d.redirect), 700);
      } else {
        rfModal.close("invoice-modal");
        rfToast((d.errors || ["Generation failed."]).join(" "), "error", 7000);
      }
    } catch {
      rfToast("Network error while generating the invoice.", "error");
    }
    $("#gen-spin").hidden = true;
    el.btnGenerate.disabled = false;
  });

  // ---- preselect via ?flat= --------------------------------------------------------
  (async function preselect() {
    if (!window.RF_PRESELECT_FLAT) return;
    // find the building that owns this flat by probing context directly
    const r = await fetch(`/payments/api/flat-context/?flat=${window.RF_PRESELECT_FLAT}`);
    if (!r.ok) return;
    // brute force: iterate buildings until the flat list contains it
    for (const opt of [...el.building.options].filter((o) => o.value)) {
      const fr = await fetch(`/payments/api/flats/?building=${opt.value}`);
      const fd = await fr.json();
      if (fd.flats.some((f) => String(f.id) === String(window.RF_PRESELECT_FLAT))) {
        el.building.value = opt.value;
        el.flat.innerHTML = '<option value="">— Select flat —</option>' +
          fd.flats.map((f) => `<option value="${f.id}">${f.label}</option>`).join("");
        el.flat.disabled = false;
        el.flat.value = window.RF_PRESELECT_FLAT;
        loadFlatContext();
        break;
      }
    }
  })();
})();
