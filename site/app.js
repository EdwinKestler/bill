"use strict";

const steps = [
  {
    source: "INVOICE",
    channel: "WITNESS RECEIVE",
    destinationLabel: "DOCK / BILL B",
    destination: "READY",
    tag: "START WITH THE RECEIVER",
    title: "A place for the dollars to land.",
    description:
      "Dock B creates a witness receive invoice using its independent RGB wallet, then stages it on Bill B. The tap invoice has empty transport endpoints.",
    detail: "RGB invoice · transport_endpoints = []",
  },
  {
    source: "INVOICE",
    channel: "BLE · B → A",
    destinationLabel: "BILL A",
    destination: "INVOICE",
    tag: "ONE PRESS, THEN RELEASE",
    title: "The receiving intent crosses the air.",
    description:
      "Press Bill A’s touch input once. A 15-second discovery window finds a nearby bill at RSSI ≥ −60 dBm. The invoice moves from Bill B to Bill A in acknowledged BLE chunks.",
    detail: "Accepted run · 210 bytes · 2 tap frames",
  },
  {
    source: "REVIEW",
    channel: "DOCK A · RGB",
    destinationLabel: "MUTINYNET",
    destination: "BROADCAST",
    tag: "A HUMAN AUTHORIZES THE SPEND",
    title: "Review the plan. Confirm exactly once.",
    description:
      "Dock A retrieves and validates the invoice, then presents the recipient, amount, fees, and expiry. The exact CONFIRM <plan_id> phrase enables one broadcast. An ambiguous send is never retried automatically.",
    detail: "One-use confirmation · donation=true",
  },
  {
    source: "RGB DATA",
    channel: "BLE · A → B",
    destinationLabel: "BILL B",
    destination: "RGB DATA",
    tag: "THE EXACT ARTIFACT, OVER BLE",
    title: "The consignment follows the invoice.",
    description:
      "Dock A stages the consignment produced by rgb-lib on Bill A. Press Bill B once to receive it. Ordered chunks, CRC32 checks, and per-frame ACKs carry the exact bytes to the receiver.",
    detail: "Accepted run · 12,496 bytes · 70 tap frames",
  },
  {
    source: "RGB DATA",
    channel: "DOCK B · IMPORT",
    destinationLabel: "WALLET B",
    destination: "SETTLED",
    tag: "INDEPENDENT WALLET VALIDATION",
    title: "Receive, validate, and settle.",
    description:
      "Dock B persists and hashes the received artifact before importing it through rgb-lib. Both wallets refresh against Mutinynet until the transfer settles. Artifact staging and import can be recovered without another send.",
    detail: "Accepted run · A: 80 → 60 · B: 20 → 40 USDT",
  },
];

const tabs = [...document.querySelectorAll("[data-step]")];
const panel = document.getElementById("flow-panel");
let selected = 0;
function showStep(index, focus = false) {
  selected = (index + steps.length) % steps.length;
  const step = steps[selected];
  tabs.forEach((tab, i) => {
    tab.setAttribute("aria-selected", String(i === selected));
    tab.tabIndex = i === selected ? 0 : -1;
  });
  panel.setAttribute("aria-labelledby", tabs[selected].id);
  const values = {
    "flow-counter": `0${selected + 1} / 05`,
    "flow-source": step.source,
    "flow-channel": step.channel,
    "flow-destination-label": step.destinationLabel,
    "flow-destination": step.destination,
    "flow-tag": step.tag,
    "flow-subtitle": step.title,
    "flow-description": step.description,
    "flow-detail": step.detail,
  };
  values["flow-source-label"] = [
    "DOCK / BILL B",
    "BILL B",
    "DOCK A",
    "BILL A",
    "DOCK B",
  ][selected];
  for (const [id, value] of Object.entries(values))
    document.getElementById(id).textContent = value;
  document.getElementById("next-step").innerHTML =
    selected === steps.length - 1
      ? 'Start again <span aria-hidden="true">↺</span>'
      : 'Next step <span aria-hidden="true">→</span>';
  if (focus) tabs[selected].focus();
}
tabs.forEach((tab, index) => {
  tab.setAttribute(
    "aria-label",
    `${index + 1}. ${tab.querySelector("strong").textContent}`,
  );
  tab.addEventListener("click", () => showStep(index));
  tab.addEventListener("keydown", (event) => {
    const target = {
      ArrowDown: selected + 1,
      ArrowUp: selected - 1,
      ArrowRight: selected + 1,
      ArrowLeft: selected - 1,
      Home: 0,
      End: steps.length - 1,
    }[event.key];
    if (target !== undefined) {
      event.preventDefault();
      showStep(target, true);
    }
  });
});
document
  .getElementById("next-step")
  .addEventListener("click", () => showStep(selected + 1));

const descriptions = {
  "01-system-architecture":
    "System architecture — two docks, two bills, separate wallets, and Mutinynet settlement.",
  "02-component-ownership":
    "Component ownership — firmware, dock radio, web desk, and wallet adapter responsibilities.",
  "03-rgb-transfer-sequence":
    "RGB transfer sequence — invoice, confirmation, broadcast, consignment, and settlement.",
  "04-bill-state-machine":
    "Bill state machine — display and GATT status progression, including failure paths.",
  "05-gatt-contract":
    "GATT contract — the frozen dock-core service and implemented tap service.",
  "06-chunk-frame":
    "Chunk frame — the binary envelope, counters, payload, and CRC32 validation.",
  "07-bill-hardware":
    "Bill hardware — the WEMOS LOLIN32 peripherals and prototype pin assignments.",
  "08-trust-boundaries":
    "Trust boundaries — wallet secrets, human confirmation, network, and out-of-band constraints.",
};
document
  .getElementById("diagram-select")
  .addEventListener("change", (event) => {
    const name = event.target.value;
    if (!Object.hasOwn(descriptions, name)) return;
    const path = `assets/diagrams/${name}.png`;
    const image = document.getElementById("diagram-image");
    image.src = path;
    image.alt = descriptions[name];
    // Preserve each diagram's own aspect ratio after switching.
    image.removeAttribute("width");
    image.removeAttribute("height");
    document.getElementById("diagram-full").href = path;
    document.getElementById("diagram-caption").textContent = descriptions[name];
  });
