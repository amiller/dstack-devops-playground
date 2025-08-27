# dstack Python SDK & Guest Agent Analysis - Developer Quick Reference

## Overview
dstack enables deployment of containerized apps to Intel TDX Trusted Execution Environments with end-to-end security. Applications access TEE functionality via Unix socket (`/var/run/dstack.sock`) through the Python SDK.

## Architecture Components
- **dstack-guest-agent**: Service inside CVM handling cryptographic operations
- **dstack-kms**: Key Management Service for root key derivation  
- **dstack-vmm**: VM management service on TDX host
- **dstack-gateway**: TLS reverse proxy for CVMs
- **dstack Python SDK**: Primary client library for TEE interaction

## Guest Agent RPC Services Analysis

### Current Services (3 services exposed)

#### 1. DstackGuest Service (Primary - v0.5+)
- **GetTlsKey**: Random TLS certificate generation
- **GetKey**: Deterministic secp256k1 key derivation  
- **GetQuote**: TDX attestation quote (raw report data only)
- **EmitEvent**: Custom event logging to RTMR3
- **Info**: TEE instance information

#### 2. Tappd Service (Legacy - deprecated)
- **DeriveKey**: TLS key with path-based derivation + random option
- **DeriveK256Key**: K256 key derivation (same as GetKey)
- **TdxQuote**: Advanced quote generation with hash algorithms
- **RawQuote**: Raw TDX quote (same as GetQuote)
- **Info**: TEE instance information

#### 3. Worker Service (External)
- **Info**: Public TEE instance info (limited TCB data)
- **Version**: Guest agent version information

## Python SDK Implementation Analysis

### Core Methods Available in Python SDK

| Method | Status | Purpose |
|--------|--------|---------|
| `get_key(path, purpose)` | ✅ | Deterministic secp256k1 key derivation |
| `get_tls_key(**options)` | ✅ | Random TLS certificate generation |
| `get_quote(report_data)` | ✅ | TDX attestation quote (raw only) |
| `emit_event(event, payload)` | ✅ | Custom event logging to RTMR3 |
| `info()` | ✅ | TEE instance information |
| `is_reachable()` | ✅ | Connectivity test |

## TEE Instance Information (`info()` method)

The `info()` method returns comprehensive TEE instance data structured as follows:

### InfoResponse Structure
```python
class InfoResponse:
    app_id: str              # Unique application identifier (hex)
    instance_id: str         # Unique instance identifier (hex)  
    app_cert: str           # Application certificate (PEM format)
    tcb_info: TcbInfo       # Trusted Computing Base information
    app_name: str           # Application name from configuration
    device_id: str          # TEE device identifier (hex)
    os_image_hash: str      # Operating system measurement (hex, optional)
    key_provider_info: str  # Key management configuration
    compose_hash: str       # Application configuration hash (hex)
```

### TcbInfo Structure (Detailed TEE Measurements)
```python
class TcbInfo:
    mrtd: str              # Measurement of TEE domain (hex)
    rtmr0: str             # Runtime Measurement Register 0 (hex) - initial configuration
    rtmr1: str             # Runtime Measurement Register 1 (hex) - OS kernel/initramfs
    rtmr2: str             # Runtime Measurement Register 2 (hex) - applications/containers
    rtmr3: str             # Runtime Measurement Register 3 (hex) - custom events
    os_image_hash: str     # OS image hash (hex, optional)
    compose_hash: str      # Docker compose configuration hash (hex)
    device_id: str         # Hardware device identifier (hex)
    app_compose: str       # Original app-compose.json content
    event_log: List[EventLog]  # Boot and runtime events
```

### EventLog Entries
```python
class EventLog:
    imr: int               # Which RTMR this event extends (0-3)
    event_type: int        # Type of event (boot, config, custom)
    digest: str            # SHA384 digest of event data (hex)
    event: str             # Human-readable event description
    event_payload: str     # Base64-encoded event payload data
```

### Key Fields for Applications

- **`app_id`**: Persistent identifier across deployments
- **`instance_id`**: Unique per container restart
- **`device_id`**: Hardware-bound identifier
- **`rtmr0-3`**: Cryptographic measurements for verification
- **`app_cert`**: Certificate for RA-TLS authentication
- **`compose_hash`**: Verifies application configuration integrity

### Key Functionality Gaps Identified

#### 1. **Path-Based TLS Key Derivation Missing**
**Current**: `get_tls_key()` generates random keys each call
**Missing**: Legacy `DeriveKey` path-based deterministic TLS keys with `random_seed=false`

**Impact**: Cannot create reproducible TLS certificates for persistent service identity

#### 2. **Worker Service Underutilized**
**Available**: Version info, public instance data
**Usage**: Python SDK doesn't expose Worker service methods

#### 3. **Raw Socket API Capabilities Not Exposed**
The guest agent supports direct HTTP API calls but Python SDK doesn't expose:
- Custom timeout configuration
- Raw response access  
- HTTP header customization
- Parallel request batching

## Python SDK Contribution Opportunities

### 1. **Deterministic TLS Key Derivation** (Priority: High)  
Add path-based TLS certificate generation:

```python
# Proposed API  
client.get_deterministic_tls_key(
    path="service/frontend",
    subject="api.example.com", 
    alt_names=["www.example.com"]
)
```

**Why Critical**: Enables persistent service identity across container restarts. Currently `get_tls_key()` generates random keys each call, preventing reproducible TLS certificates.

### 2. **Worker Service Integration** (Priority: Medium)
Expose Worker service methods:

```python
# Proposed API
client.get_version()     # Guest agent version info
client.get_public_info() # Public attestation info without auth
```

**Why Useful**: Version compatibility checking and public attestation data access

### 3. **Advanced Client Features** (Priority: Medium)
- Connection pooling and reuse
- Custom timeout configuration  
- Batch request support
- Raw HTTP response access
- Better error categorization (connection vs crypto failures)

### 4. **Enhanced Info Method** (Priority: Low)
Add convenience methods for InfoResponse:

```python
# Proposed API
info = client.info()
info.verify_compose_hash(expected_hash)  # Verify app integrity
info.get_measurement_summary()           # Human-readable RTMR summary  
info.replay_rtmr_history()              # Compute final RTMRs from event log
```

## Key Derivation Security Model

### Master Key Flow
```
KMS Root Key → App-Specific K256 Key → Path-Derived Keys
     |              |                        |
  (Sealed)     (32-byte seed)         (deterministic)
```

### Key Types
- **GetKey**: Deterministic secp256k1 (blockchain wallets)
- **GetTlsKey**: Random TLS/X.509 (HTTPS certificates)  
- **Legacy DeriveKey**: Path-based TLS (persistent identity)

## Implementation Notes

### Socket Communication
- **Production**: `/var/run/dstack.sock` (Unix domain socket)
- **Development**: HTTP endpoint via `DSTACK_SIMULATOR_ENDPOINT`
- **Transport**: JSON-RPC over HTTP

### Error Handling Patterns
- SDKs wrap guest-agent errors consistently
- Connection failures vs cryptographic operation failures
- Timeout handling varies by implementation

### Security Boundaries
- Master keys never leave TEE
- Signature chains prove key authenticity  
- Quote generation provides execution environment proof
- Encrypted environment variables protect deployment secrets

## Quick Development Setup

1. **Local Testing**: Use dstack-simulator for development
2. **Socket Mounting**: Ensure `/var/run/dstack.sock:/var/run/dstack.sock` in compose
3. **SDK Selection**: Python most feature-complete, Go needs work
4. **Legacy Compatibility**: Tappd methods still work but deprecated

## Recommended Python SDK Contribution Strategy

1. **Start with deterministic TLS keys** - clear scope, enables persistent service identity
2. **Add Worker service methods** - simple addition with useful functionality  
3. **Enhance client features** - improves developer experience
4. **Add Info convenience methods** - better data handling utilities

The guest agent has rich capabilities that aren't fully exposed by the current Python SDK. Contributing missing functionality would significantly improve developer experience, especially for applications needing persistent identity and better TEE instance management.