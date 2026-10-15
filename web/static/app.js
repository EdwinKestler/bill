const logEl = document.getElementById("log");
const form = document.getElementById("form");
const text = document.getElementById("text");
const dialog = document.getElementById("confirm");
const confirmNote = document.getElementById("confirm-note");
const confirmPlan = document.getElementById("confirm-plan");
const confirmationPhrase = document.getElementById("confirmation-phrase");
const confirmForm = document.getElementById("confirm-form");
const scanDevice = document.getElementById("scan-device");
const connectDevice = document.getElementById("connect-device");
const registerDevice = document.getElementById("register-device");
const deviceList = document.getElementById("device-list");
const deviceBadge = document.getElementById("device-badge");
const deviceSummary = document.getElementById("device-summary");
const deviceMessage = document.getElementById("device-message");
const sendUsdt = document.getElementById("send-usdt");
const receiveUsdt = document.getElementById("receive-usdt");
const workflowMessage = document.getElementById("workflow-message");

let pendingId = null;
let selectedDevice = null;
let activeDevice = null;
let activeRole = null;

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
  renderDevice(bill.device);
  activeRole = bill.role;
  sendUsdt.disabled = bill.role !== "A" || !(bill.device && bill.device.registered);
  receiveUsdt.disabled = bill.role !== "B" || !(bill.device && bill.device.registered);
  document.getElementById("workflow-help").textContent =
    bill.role === "A"
      ? "Send USDT checks for an invoice on Bill A before reading it."
      : "Receive USDT stages an invoice when empty, or imports a received consignment.";
}

function renderDevice(device) {
  activeDevice = device || null;
  const record = device && device.device;
  const connection = device && device.connection;
  const address = device && device.active_address;
  deviceBadge.className = "device-badge";
  if (record) {
    const verifiedRegistered =
      connection &&
      connection.connected &&
      connection.address === record.address;
    deviceBadge.textContent =
      verifiedRegistered ? "Verified" : "Registered";
    deviceBadge.classList.add("ready");
    deviceSummary.textContent =
      record.name + " · " + record.identity + " · " + record.address;
  } else if (address) {
    const verifiedConfigured =
      connection && connection.connected && connection.address === address;
    deviceBadge.textContent =
      verifiedConfigured ? "Verified" : "Configured";
    deviceBadge.classList.add("configured");
    deviceSummary.textContent =
      "Environment address " +
      address +
      " · scan and register it to save this selection.";
  } else {
    deviceBadge.textContent = "Not registered";
    deviceSummary.textContent =
      "Scan for a nearby RgbBill advertising the authorized dock service.";
  }
  connectDevice.disabled = !selectedDevice && !address;
}

function selectedAddress() {
  const checked = deviceList.querySelector(
    'input[name="device-address"]:checked',
  );
  return checked ? checked.value : null;
}

function renderCandidates(devices) {
  deviceList.replaceChildren();
  selectedDevice = null;
  registerDevice.disabled = true;
  const legend = document.createElement("legend");
  legend.textContent = "Authorized nearby bills";
  deviceList.appendChild(legend);
  if (!devices.length) {
    const empty = document.createElement("p");
    empty.className = "empty-device-list";
    empty.textContent = "No authorized RGBill advertisements found.";
    deviceList.appendChild(empty);
    renderDevice(activeDevice);
    return;
  }
  for (const device of devices) {
    const label = document.createElement("label");
    label.className = "device-option";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "device-address";
    radio.value = device.address;
    if (device.registered) {
      radio.checked = true;
      selectedDevice = device.address;
      registerDevice.disabled = false;
    }
    radio.addEventListener("change", () => {
      selectedDevice = device.address;
      connectDevice.disabled = false;
      registerDevice.disabled = false;
      deviceMessage.textContent =
        "Selected " + device.name + ". Connect to verify or register it now.";
    });
    const description = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent =
      device.name + (device.registered ? " · registered" : "");
    const details = document.createElement("small");
    details.textContent =
      device.address + " · RSSI " + device.rssi + " dBm";
    description.append(title, details);
    label.append(radio, description);
    deviceList.appendChild(label);
  }
}

async function postDevice(path, payload = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!data.ok) throw new Error(data.error || "Device operation failed.");
  return data;
}

scanDevice.addEventListener("click", async () => {
  scanDevice.disabled = true;
  deviceMessage.textContent = "Scanning for authorized RGBill devices…";
  try {
    const data = await postDevice("/api/device/scan", { timeout: 5 });
    renderCandidates(data.devices);
    deviceMessage.textContent = data.count
      ? "Found " +
        data.count +
        " authorized bill" +
        (data.count === 1 ? "." : "s.")
      : "No authorized bills found. Check power and keep the bill nearby.";
  } catch (error) {
    deviceMessage.textContent = error.message;
  } finally {
    scanDevice.disabled = false;
  }
});

connectDevice.addEventListener("click", async () => {
  connectDevice.disabled = true;
  deviceMessage.textContent = "Connecting for a read-only identity check…";
  try {
    const data = await postDevice("/api/device/connect", {
      address:
        selectedAddress() || (activeDevice && activeDevice.active_address),
    });
    const connection = data.connection;
    deviceMessage.textContent =
      "Verified " +
      connection.name +
      " · " +
      connection.identity +
      " · " +
      connection.address;
    if (connection.artifact) {
      const artifact = connection.artifact;
      const kind = artifact.kind === 1 ? "invoice" : artifact.kind === 2 ? "consignment" : "empty";
      deviceMessage.textContent +=
        " · " + artifact.direction + " " + kind +
        (artifact.denomination_cents
          ? " $" + (artifact.denomination_cents / 100).toFixed(2)
          : "");
    }
    renderDevice(data.device);
  } catch (error) {
    deviceMessage.textContent = error.message;
  } finally {
    connectDevice.disabled =
      !selectedDevice && !(activeDevice && activeDevice.active_address);
  }
});

async function runWorkflow(path) {
  sendUsdt.disabled = true;
  receiveUsdt.disabled = true;
  workflowMessage.textContent = "Inspecting the registered bill…";
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cents: 500 }),
    });
    const data = await response.json();
    workflowMessage.textContent = data.reply || data.error || "Step completed.";
    line("bot", workflowMessage.textContent);
    if (data.pending) showConfirm(data.pending);
  } catch (error) {
    workflowMessage.textContent = error.message;
  } finally {
    await refresh();
  }
}

sendUsdt.addEventListener("click", () => runWorkflow("/api/workflow/send"));
receiveUsdt.addEventListener("click", () => runWorkflow("/api/workflow/receive"));

registerDevice.addEventListener("click", async () => {
  const address = selectedAddress();
  if (!address) return;
  registerDevice.disabled = true;
  deviceMessage.textContent = "Verifying and saving this bill…";
  try {
    const data = await postDevice("/api/device/register", { address });
    deviceMessage.textContent = data.reply;
    renderDevice(data.device);
    await refresh();
  } catch (error) {
    deviceMessage.textContent = error.message;
    registerDevice.disabled = false;
  }
});

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
