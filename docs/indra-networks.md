# Indra: two networks, one compatibility commitment

Status: source observations and development plan, not implemented isolation.
Source base: `6048720cafac4e72cb12267985197ce0d5d22f97`.

## Observed upstream identifiers

`src/CrossPlatformMesh.swift` lines 54–63 defines:

- BLE service: `0541`, equivalent to `00000541-0000-1000-8000-00805F9B34FB`.
- BLE characteristic: `0542`.
- Bonjour type: `_oshi-mesh._tcp.`; domain: `local.`.

Its comments describe a 16-bit advertising choice for cross-platform visibility.
That is an upstream claim to verify on target devices, not permission to assign
another reserved short UUID arbitrarily.

`src/MeshNetworkManager.swift` lines 57–62 has four MultipeerConnectivity service
types: `ihsotahs`, `mesh-chat`, `p2p-message`, and `local-mesh`.
The repository also has upstream relay URLs, queue state, and global managers.
Changing the BLE UUID alone would not isolate all these paths.

## Proposed profiles

| Boundary | OSHI-compatible profile | Indra test profile |
|---|---|---|
| BLE discovery | Preserve existing identifiers | New standards-appropriate UUID, pending device tests |
| Bonjour / Multipeer discovery | Preserve upstream services | Distinct valid service types |
| Peers, sessions, identity | Upstream behavior | Explicitly scoped test state |
| Storage, queued sends, dedup | Original profile provenance | Separate namespaces and original-profile delivery |
| Internet / LoRa / bot transport | Existing compatibility requirement | Test-only endpoints or disabled until separately scoped |
| Failure / fallback | Upstream behavior | No fallback to main-net services |

Both profiles should be available next to each other. Whether they run concurrently
needs a target-platform decision and measured radio/background limits. No automatic
bridge between them is intended. No test UUID has been selected or installed yet.

## Acceptance evidence

- Stock OSHI ↔ Indra main profile: discovery, handshake, payload semantics.
- Indra test ↔ Indra test: delivery and routing in a controlled lab.
- Main ↔ test: no cross-net discovery, delivery, queued resend, or relay fallback.
- Switch/restart/device loss: state remains scoped; recovery is comprehensible.
- Existing storage upgrades remain compatible; test data does not migrate to main.
- Both active, if supported: measure background reliability, airtime, and battery.

The public source does not include a buildable application shell. First select
the target platform and obtain or create that shell; then implement profile
boundaries with protocol fixtures and real-device evidence.
