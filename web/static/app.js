const logEl = document.getElementById("log");
const form = document.getElementById("form");
const text = document.getElementById("text");
const dialog = document.getElementById("confirm");
const confirmNote = document.getElementById("confirm-note");
const confirmPlan = document.getElementById("confirm-plan");
const confirmationPhrase = document.getElementById("confirmation-phrase");
const confirmForm = document.getElementById("confirm-form");

let pendingId = null;

function line(cls, msg) {
  const li = document.createElement("li");
  li.className = cls;
  li.textContent = msg;
  logEl.appendChild(li);
}

async function refresh() {
  const bill = await (await fetch("/api/bill")).json();
  document.getElementById("denomination").textContent =
    "$" + (bill.cents / 100).toFixed(2);
  document.getElementById("status").textContent = bill.status;
  document.getElementById("meta").textContent =
    "role " + bill.role + " · " + bill.identity + " · " + bill.mode;
}

function showConfirm(pending) {
  pendingId = pending.id;
  confirmNote.textContent =
    pending.note + " Type exactly: " + pending.confirmation_phrase;
  confirmPlan.textContent = [
    "amount: $" + (pending.cents / 100).toFixed(2) + " USDT",
    "base units: " + pending.amount_base_units,
    "balance before: $" +
      (pending.balance_before_cents / 100).toFixed(2),
    "recipient: " + pending.recipient_id,
    "fee: " + pending.fee_rate_sat_vb + " sat/vB",
    "invoice sha256: " + pending.invoice_sha256,
    "transport endpoints: []",
  ].join("\n");
  confirmationPhrase.value = "";
  confirmationPhrase.placeholder = pending.confirmation_phrase;
  dialog.showModal();
  confirmationPhrase.focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = text.value.trim();
  if (!value) return;
  line("you", value);
  text.value = "";
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: value }),
  });
  const data = await res.json();
  line("bot", data.reply || data.error || "Request completed.");
  if (data.pending) showConfirm(data.pending);
  await refresh();
});

confirmForm.addEventListener("submit", async (event) => {
  const submitter = event.submitter;
  if (submitter && submitter.id === "approve" && pendingId) {
    event.preventDefault();
    const res = await fetch("/api/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: pendingId,
        phrase: confirmationPhrase.value,
      }),
    });
    const data = await res.json();
    if (data.ok) {
      dialog.close();
      pendingId = null;
      confirmationPhrase.value = "";
    }
    line(
      "bot",
      data.ok && data.completed
        ? "Broadcast complete and exact consignment staged over BLE."
        : data.ok && data.recovery_required
          ? "Broadcast complete. Consignment retained; use retry stage only."
          : data.error,
    );
    await refresh();
  }
});

dialog.addEventListener("close", async () => {
  if (dialog.returnValue === "cancel") {
    const cancelledId = pendingId;
    pendingId = null;
    confirmationPhrase.value = "";
    if (cancelledId) {
      await fetch("/api/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: cancelledId }),
      });
      line("bot", "Transfer plan cancelled. Nothing was broadcast.");
      await refresh();
    }
  }
});

refresh();
