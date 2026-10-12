# RGB cash-bill diagrams

These diagrams are generated from the current design, GATT contract, and
implemented component boundaries. The opaque physical transport and the real
wallet-to-BLE Mutinynet transfer were both live accepted on 2026-10-11.

| Diagram | Purpose | Source |
| --- | --- | --- |
| [System architecture](01-system-architecture.png) | Two docks, two bills, custody, radio, and Mutinynet | [Mermaid](src/01-system-architecture.mmd) |
| [Component ownership](02-component-ownership.png) | Repository modules and their responsibilities | [Mermaid](src/02-component-ownership.mmd) |
| [RGB transfer sequence](03-rgb-transfer-sequence.png) | Invoice, confirmation, broadcast, OOB consignment, and settlement | [Mermaid](src/03-rgb-transfer-sequence.mmd) |
| [Bill state machine](04-bill-state-machine.png) | OLED/GATT status progression and failure paths | [Mermaid](src/04-bill-state-machine.mmd) |
| [GATT contract](05-gatt-contract.png) | Frozen dock-core v1 and implemented tap service v1 | [Mermaid](src/05-gatt-contract.mmd) |
| [Chunk frame](06-chunk-frame.png) | Binary frame v1 byte layout and validation | [Mermaid](src/06-chunk-frame.mmd) |
| [Bill hardware](07-bill-hardware.png) | LOLIN32 peripherals and prototype pin assignments | [Mermaid](src/07-bill-hardware.mmd) |
| [Trust boundaries](08-trust-boundaries.png) | Secrets, confirmation, network, and OOB constraints | [Mermaid](src/08-trust-boundaries.mmd) |

## Status colors

- Green: live-verified or settled behavior.
- Blue: implemented local hardware/software behavior.
- Amber: specified but not yet integrated or implemented.
- Gray: external system or invariant boundary.

## Render

From the bill project root:

```bash
docs/diagrams/render.sh
```

The renderer pins `@mermaid-js/mermaid-cli@12.0.0`, uses the installed Google
Chrome binary, and regenerates every PNG from `src/*.mmd`. Generated PNGs are
documentation artifacts; edit the Mermaid sources, not the images.
