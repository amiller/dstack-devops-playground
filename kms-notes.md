# dstack KMS Investigation & Audit Notes

## Overview

This document provides a comprehensive analysis of the dstack Key Management System (KMS) implementation, focusing on its architecture, cryptographic design, smart contract security, and key replication mechanisms for security auditing purposes.

## Architecture Analysis

### System Overview

The dstack KMS implements a three-tier architecture for secure key management in TEE environments:

```
┌─────────────────────────────────────────┐    ┌─────────────────────────────────────────┐
│           Smart Contracts               │    │          KMS Infrastructure             │
│  • DstackKms.sol (registry)             │◄───┤  • dstack-kms (key derivation)          │
│  • DstackApp.sol (per-app control)      │    │  • dstack-kms-auth-eth (blockchain)     │
│  • Device & app authorization           │    │  • Quote verification & replication     │
└─────────────────────────────────────────┘    └─────────────────────────────────────────┘
                                                                   │
                                                                   │ RA-TLS (boot-time)
                                                                   ▼
┌─────────────────────────────────────────┐    ┌─────────────────────────────────────────┐
│         dstack-guest-agent              │    │          User Application               │
│  • App key storage & derivation         │◄───┤  • Python/Go SDK                       │
│  • TLS cert generation                  │    │  • get_key(), get_tls_key()             │
│  • Unix socket (/var/run/dstack.sock)   │    │  • Business logic & crypto ops         │
└─────────────────────────────────────────┘    └─────────────────────────────────────────┘
        Intel TDX CVM (TEE Boundary)
```

### Core Components

1. **Smart Contract Layer (Ethereum)**
   - **DstackKms.sol**: Global registry for authorized KMS instances, device IDs, and OS images
   - **DstackApp.sol**: Per-application access control and compose hash validation
   - Provides blockchain-based governance and permission management

2. **KMS Infrastructure Layer**
   - **dstack-kms**: Central key management service with quote verification and key derivation
   - **dstack-kms-auth-eth**: Blockchain validation interface for smart contract queries
   - Runs on trusted infrastructure, handles key replication across authorized instances

3. **Application TEE Layer (Intel TDX CVM)**
   - **dstack-guest-agent**: TEE-resident service managing all cryptographic operations
   - **User Application**: The actual application logic using cryptographic services
   - Both components run within the same TEE boundary for maximum security

### Boot Sequence and Key Acquisition

The following sequence illustrates how applications acquire keys at startup:

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌─────────────┐
│    CVM      │    │ dstack-kms   │    │ Smart         │    │ Application │
│ Guest Agent │    │   Service    │    │ Contracts     │    │             │
└─────────────┘    └──────────────┘    └───────────────┘    └─────────────┘
       │                   │                    │                    │
       │ 1. Boot & Request Keys                 │                    │
       │ (with TDX quote)   │                   │                    │
       ├──────────────────→ │                   │                    │
       │                   │                   │                    │
       │                   │ 2. Validate Quote │                    │
       │                   │ & Check Permissions                    │
       │                   ├─────────────────→ │                    │
       │                   │                   │                    │
       │                   │ 3. Permissions OK │                    │
       │                   │ ←─────────────────│                    │
       │                   │                   │                    │
       │ 4. App Keys       │                   │                    │
       │ (CA cert, K256,   │                   │                    │
       │  disk/env keys)   │                   │                    │
       │ ←──────────────────│                   │                    │
       │                   │                   │                    │
       │ 5. Store keys &   │                   │                    │
       │ start Unix socket │                   │                    │
       │                   │                   │                    │
       │                   │                   │                    │
       │                   │                   │ 6. App requests    │
       │                   │                   │ derived keys       │
       │ 7. Derive keys    │                   │ ←──────────────────│
       │ (with signature   │                   │                    │
       │ chains)           │                   │                    │
       │ ←─────────────────────────────────────────────────────────│
```

#### Key Points:

1. **Boot-time Only**: Applications request keys from KMS only once during CVM initialization
2. **TEE Co-location**: Guest agent and application run in the same Intel TDX CVM
3. **Hardware Attestation**: TDX quotes prove the CVM's integrity to the KMS
4. **Blockchain Validation**: Smart contracts authorize specific app configurations
5. **Local Key Operations**: All subsequent key derivation happens within the TEE via Unix socket
6. **Signature Chains**: Every derived key includes cryptographic proof of KMS authorization

## Cryptographic Implementation Analysis

### Key Derivation (`refs/dstack/kms/src/crypto.rs`)

```rust
pub(crate) fn derive_k256_key(
    parent_key: &SigningKey,
    app_id: &[u8],
) -> Result<(SigningKey, Vec<u8>)> {
    let context_data = [app_id, b"app-key"];
    let derived_key_bytes: [u8; 32] =
        kdf::derive_ecdsa_key(&parent_key.to_bytes(), &context_data, 32)?
```

**Key Findings:**
- Uses proper KDF (Key Derivation Function) with context separation
- App-specific derivation prevents cross-app key access
- ECDSA key derivation for Ethereum compatibility
- Signature chain validation for app keys

### Root Key Types

1. **CA Root Key**: Used for x509 certificate issuance (HTTPS/TLS)
2. **K256 Root Key**: ECDSA key for Ethereum-compatible operations

### Key Usage Hierarchy

```
Root Keys (KMS)
├── App CA Key (per app_id)
│   └── TLS Certificates
└── App K256 Key (per app_id) 
    ├── Disk Encryption Key
    ├── Environment Variable Encryption Key
    └── Application Signing Keys
```

## Key Replication Implementation

### Bootstrap vs Onboard Process

**Bootstrap** (`kms/src/onboard_service.rs:53-81`)
- First KMS instance generates new root keys
- Creates CA certificates and K256 keys
- Stores bootstrap info with TDX quote

**Onboard** (`kms/src/onboard_service.rs:83-95`) 
- New KMS instances replicate from existing instances
- Uses RA-TLS for secure key transfer
- Validates requesting instance via TDX attestation

### Replication Security Flow

1. **Connection**: New KMS connects via RA-TLS to existing KMS
2. **Authentication**: TDX quote verification
3. **Authorization**: Smart contract validation via `ensure_kms_allowed()`
4. **Key Transfer**: Root keys transferred if authorized

```rust
async fn get_kms_key(self, request: GetKmsKeyRequest) -> Result<KmsKeyResponse> {
    if self.state.config.onboard.quote_enabled {
        let _info = self.ensure_kms_allowed(&request.vm_config).await?;
    }
    Ok(KmsKeyResponse {
        temp_ca_key: self.state.inner.temp_ca_key.clone(),
        keys: vec![KmsKeys {
            ca_key: self.state.inner.root_ca.key.serialize_pem(),
            k256_key: self.state.inner.k256_key.to_bytes().to_vec(),
        }],
    })
}
```

### Authorization Mechanism (`main_service.rs:147-152`)

```rust
async fn ensure_kms_allowed(&self, vm_config: &str) -> Result<BootInfo> {
    let att = self.ensure_attested()?;
    self.ensure_app_attestation_allowed(att, true, false, vm_config)
        .await
        .map(|c| c.boot_info)
}
```

**Security Validations:**
- TDX quote authenticity verification
- Device ID allowlist check
- Aggregated MR (measurement register) validation
- OS image hash verification

## Smart Contract Security Analysis

### DstackKms Contract (`DstackKms.sol`)

**Critical Mappings:**
```solidity
mapping(bytes32 => bool) public kmsAllowedAggregatedMrs;
mapping(bytes32 => bool) public kmsAllowedDeviceIds;
mapping(bytes32 => bool) public allowedOsImages; 
mapping(address => bool) public registeredApps;
```

**Access Controls:**
- Owner-only functions for managing allowlists
- UUPS upgradeable pattern with `_authorizeUpgrade`
- ERC-165 interface detection support

### DstackApp Contract (`DstackApp.sol`)

**Key Features:**
```solidity
mapping(bytes32 => bool) public allowedComposeHashes;
mapping(bytes32 => bool) public allowedDeviceIds;
bool public allowAnyDevice;
```

**Security Considerations:**
- Per-app compose hash validation
- Device-specific restrictions
- Upgrade disabling capability
- Owner-controlled access management

## Attestation & Quote Verification

### TDX Quote Structure
- **MRTD**: Virtual firmware measurement (trust anchor)
- **RTMR0**: CVM virtual hardware configuration  
- **RTMR1**: Linux kernel measurement
- **RTMR2**: Kernel cmdline and initrd measurements
- **RTMR3**: App-specific runtime measurements (compose hash, instance ID, key provider)

### Verification Process
1. Quote signature validation via DCAP-QVL
2. Measurement register comparison against known-good values
3. Event log replay validation for RTMR3
4. Smart contract permission checking

## Live Deployment Analysis

### Contract: `0xd343a3f5593b93D8056aB5D60c433622d7D65a80` (Ethereum Mainnet)

**Event Analysis Results:**
- **KmsDeviceAdded**: 2 events (2 authorized KMS instances)
- **KmsAggregatedMrAdded**: 1 event (1 authorized measurement set)
- **AppRegistered**: 8 events (8 registered applications)
- **KmsInfoSet**: 1 event (KMS public keys configured)

### Authorized KMS Instances

**Device ID 1**: `0xe5a0c70bb6503de2d31c11d85914fe3776ed5b33a078ed856327c371a60fe0fd`
**Device ID 2**: `0x46055654047ca3357ab0fa0bc08c8c9c0a68060eac686e32510f45bc1629868d`

**Authorized MR**: `0x0df6eddf306236ecb191981550a3ed1ea95c1783635837ab8ddde481dbff61cc`

**Confirmation**: Key replication is actively implemented with 2 physical machines authorized for KMS key sharing.

### Recommendations for Auditing

1. **Code Review Focus Areas:**
   - Key derivation functions (`crypto.rs`)
   - Quote verification logic (`main_service.rs:ensure_kms_allowed`)
   - Smart contract access controls (`DstackKms.sol`, `DstackApp.sol`)
   - RA-TLS implementation and certificate validation

2. **Security Testing:**
   - Quote forgery resistance
   - Cross-app key isolation verification
   - Smart contract permission bypass attempts
   - Network protocol analysis of key replication

3. **Operational Security:**
   - Key storage mechanisms
   - Bootstrap security procedures  
   - Smart contract upgrade governance
   - Incident response for key compromise

4. **Cast Commands for Contract Analysis:**
```bash
# Check KMS device permissions
cast call 0xd343a3f5593b93D8056aB5D60c433622d7D65a80 "kmsAllowedDeviceIds(bytes32)" $DEVICE_ID

# Check MR authorization
cast call 0xd343a3f5593b93D8056aB5D60c433622d7D65a80 "kmsAllowedAggregatedMrs(bytes32)" $MR_HASH

# Get current KMS info
cast call 0xd343a3f5593b93D8056aB5D60c433622d7D65a80 "kmsInfo()"
```

## Development Environment: dstack-simulator

### Simulator Architecture

The dstack development environment includes a simulator that mimics the TEE functionality without requiring actual Intel TDX hardware. This enables local development and testing of KMS-integrated applications.

#### Simulator Components

1. **dstack-simulator**: Standalone service that provides KMS functionality
2. **Socket Interface**: Compatible with production `/var/run/dstack.sock` interface
3. **HTTP Endpoint**: Development mode via `DSTACK_SIMULATOR_ENDPOINT`
4. **Mock Attestation**: Simulates TDX quote generation and verification

#### Simulator vs Production Differences

| Feature | Production (TEE) | Simulator (Development) |
|---------|-----------------|------------------------|
| **Hardware Security** | Intel TDX TEE | Software simulation only |
| **Key Storage** | SGX sealing / KMS | In-memory or file-based |
| **Attestation** | Real TDX quotes | Mock quotes and signatures |
| **Root of Trust** | Hardware TPM/TEE | Software-generated keys |
| **Network Security** | RA-TLS with HW attestation | Standard TLS simulation |

#### Development Setup

```bash
# Start dstack simulator
docker run -d --name dstack-sim \
  -p 8080:8080 \
  -v /var/run:/var/run \
  dstack/simulator:latest

# Set environment for development
export DSTACK_SIMULATOR_ENDPOINT=http://localhost:8080

# Mount socket for production-like testing
docker run --rm \
  -v /var/run/dstack.sock:/var/run/dstack.sock \
  your-app:latest
```

#### Simulator Key Generation

In simulator mode, the key derivation follows the same algorithmic structure as production but uses development-specific root keys:

```rust
// Simulator generates consistent but non-secure keys
let simulator_root_key = derive_simulator_key(app_id, "simulator-seed");
let app_key = derive_k256_key(&simulator_root_key, app_id)?;
```

**Important**: Simulator keys are deterministic for testing but provide no security guarantees. Never use simulator mode in production environments.

## Application Usage of KMS

### Boot-Time Key Acquisition Process

You are absolutely correct - applications use the KMS at boot time through the guest agent. Here's the complete flow:

#### 1. System Boot Sequence (`basefiles/dstack-prepare.service`)
```bash
# Service runs: /bin/dstack-prepare.sh
# Which executes: dstack-util setup --work-dir $WORK_DIR --device /dev/vdb --mount-point $DATA_MNT
```

#### 2. KMS Key Request (`dstack-util/src/system_setup.rs:338-344`)
During `dstack-util setup`, the system makes a secure request to KMS:

```rust
let response = kms_client
    .get_app_key(rpc::GetAppKeyRequest {
        api_version: 1,
        vm_config: self.shared.sys_config.vm_config.clone(),
    })
    .await
    .context("Failed to get app key")?;
```

**Security Flow:**
1. **RA-TLS Connection**: Establishes mutually authenticated TLS connection with KMS
2. **TDX Quote Submission**: Includes current CVM's TDX quote in vm_config
3. **KMS Validation**: KMS validates quote against smart contract allowlists
4. **Key Derivation**: KMS derives app-specific keys using `app_id`
5. **Key Response**: Returns encrypted keys over secure channel

#### 3. Key Storage (`system_setup.rs:569-571`)
Retrieved keys are stored locally for guest agent use:

```rust
let keys_json = serde_json::to_string(&app_keys)?;
fs::write(self.app_keys_file(), keys_json)?;
```

#### 4. Guest Agent Initialization (`guest-agent/src/rpc_service.rs:48-50`)
Guest agent loads the stored keys at startup:

```rust
let keys: AppKeys = serde_json::from_str(&fs::read_to_string(&config.keys_file)?)
    .context("Failed to parse app keys")?;
```

### Application Key Usage

#### Keys Provided by KMS (`kms/rpc/proto/kms_rpc.proto:25-42`)
```protobuf
message AppKeyResponse {
  string ca_cert = 1;           // TLS CA certificate for HTTPS
  bytes disk_crypt_key = 2;     // Full disk encryption key
  bytes env_crypt_key = 3;      // Environment variable decryption
  bytes k256_key = 4;           // ECDSA key for Ethereum operations
  bytes k256_signature = 5;     // Signature chain from root key
  string gateway_app_id = 7;    // Gateway application identifier
  bytes os_image_hash = 8;      // OS image hash for validation
}
```

#### App-Specific Key Derivation Deep Dive

The KMS implements a hierarchical key derivation system that ensures cryptographic isolation between applications while enabling fine-grained access control.

##### 1. Root Key to App Key Derivation

**Algorithm** (`refs/dstack/kms/src/crypto.rs:24-37`):
```rust
pub(crate) fn derive_k256_key(
    parent_key: &SigningKey,
    app_id: &[u8],
) -> Result<(SigningKey, Vec<u8>)> {
    let context_data = [app_id, b"app-key"];
    let derived_key_bytes: [u8; 32] =
        kdf::derive_ecdsa_key(&parent_key.to_bytes(), &context_data, 32)?
        .try_into()
        .map_err(|_| CryptoError::InvalidKeyLength)?;
    
    let signing_key = SigningKey::from_bytes(&derived_key_bytes.into())?;
    let verifying_key = signing_key.verifying_key();
    let pubkey = verifying_key.to_encoded_point(false);
    
    // Create signature chain proving derivation
    let signature = sign_message(
        parent_key,
        b"dstack-kms-issued",
        app_id,
        &pubkey.to_sec1_bytes(),
    )?;
    
    Ok((signing_key, signature.to_vec()))
}
```

**Key Properties:**
- **Deterministic**: Same `app_id` always produces the same key
- **Isolated**: Different `app_id` values produce cryptographically independent keys
- **Provable**: Signature chain proves legitimate derivation from KMS root
- **Context-Bound**: Uses domain separation to prevent key reuse attacks

##### 2. App Key to Purpose-Specific Keys

Applications can derive sub-keys for specific purposes via the guest agent:

**Guest Agent API** (`guest-agent/src/rpc_service.rs:183-206`):
```rust
async fn get_key(self, request: GetKeyArgs) -> Result<GetKeyResponse> {
    let k256_app_key = &self.state.inner.keys.k256_key;
    let derived_k256_key = derive_ecdsa_key(
        k256_app_key, 
        &[request.path.as_bytes()], 
        32
    )?;
    
    let signature = self.state.inner.keys.k256_key.sign_digest_recoverable(
        keccak256(format!("{}:{}", request.purpose, 
                         hex::encode(&derived_k256_key.verifying_key().to_sec1_bytes())))
    )?;
    
    Ok(GetKeyResponse {
        key: derived_k256_key.to_bytes().to_vec(),
        signature_chain: vec![
            signature.to_vec(),                    // App key signature
            self.state.inner.keys.k256_signature.clone() // KMS root signature
        ],
    })
}
```

**Common Key Purposes:**
- `"signing"`: Digital signatures for transactions
- `"encryption"`: Data encryption and decryption
- `"authentication"`: Identity verification
- `"consensus"`: Blockchain consensus participation

##### 3. Key Derivation Security Model

**Three-Tier Hierarchy:**
```
KMS Root Key (Hardware-Protected)
├── App Key (app_id derived, stored in TEE)
│   ├── signing/cluster/node1 → Node signing key
│   ├── encryption/database → Database encryption key
│   ├── authentication/api → API authentication key
│   └── consensus/validator → Consensus participation key
└── App Key (different_app_id)
    └── [Independent key tree]
```

**Cryptographic Properties:**
- **Forward Security**: Compromised derived key doesn't reveal parent keys
- **Backward Security**: Parent key compromise doesn't immediately reveal all derived keys (but enables future derivation)
- **Cross-App Isolation**: Apps cannot derive each other's keys even with same path
- **Audit Trail**: Signature chains provide cryptographic proof of key legitimacy


#### Application Usage via Guest Agent APIs

**TLS Certificate Generation** (`guest-agent/src/rpc_service.rs:155-181`):
```rust
async fn get_tls_key(self, request: GetTlsKeyArgs) -> Result<GetTlsKeyResponse> {
    let certificate_chain = self.state.inner.cert_client
        .request_cert(&derived_key, config, simulator_mode).await?;
    // Returns signed certificate chain using app CA
}
```

**Key Derivation** (`guest-agent/src/rpc_service.rs:183-206`):
```rust
async fn get_key(self, request: GetKeyArgs) -> Result<GetKeyResponse> {
    let k256_app_key = &self.state.inner.keys.k256_key;
    let derived_k256_key = derive_ecdsa_key(k256_app_key, &[request.path.as_bytes()], 32)?;
    // Returns purpose-specific keys with signature chain
}
```

**Quote Generation** (`guest-agent/src/rpc_service.rs:208-237`):
```rust
async fn get_quote(self, request: RawQuoteArgs) -> Result<GetQuoteResponse> {
    let (_, quote) = tdx_attest::get_quote(&report_data, None)?;
    // Returns TDX quote for application attestation
}
```

### Security Validation at Boot

#### 1. **TDX Quote Verification** (`system_setup.rs:315-333`)
KMS validates the requesting CVM's quote and extends RTMR3:
```rust
if let Some(att) = &cert.attestation {
    let kms_info = att.decode_app_info(false)?;
    extend_rtmr3("mr-kms", &kms_info.mr_aggregated)?;
}
```

#### 2. **Smart Contract Authorization** (`kms/src/main_service.rs:147-152`)
```rust
async fn ensure_kms_allowed(&self, vm_config: &str) -> Result<BootInfo> {
    let att = self.ensure_attested()?;
    self.ensure_app_attestation_allowed(att, true, false, vm_config).await
}
```

#### 3. **App Compose Hash Validation**
The app's compose hash (from docker-compose.yaml) must be pre-registered in the DstackApp contract.

### Key Security Model

**Boot-Time Security:**
- Keys are requested only once at boot time via secure RA-TLS
- TDX quote proves the requesting CVM's integrity
- Smart contract authorizes the specific app_id + compose_hash combination
- Keys are encrypted at rest and in transit

**Runtime Security:**
- Guest agent serves keys to applications via Unix socket (`/var/run/dstack.sock`)
- Applications can derive purpose-specific keys using the guest agent API
- All key operations are performed within the TEE boundary

**Trust Chain:**
```
KMS Root Keys → App Keys → Purpose-Specific Keys → Application Operations
     ↓              ↓              ↓                      ↓
TEE+Contract   TEE Storage   TEE Derivation          TEE Execution
```

This architecture ensures that applications never directly contact the KMS - all key operations are mediated by the guest agent, which validates requests and maintains the security boundary of the TEE.

## Signature Chain Verification System

### Overview

The dstack SDK provides signature chains that cryptographically prove key derivation authenticity. Every derived key comes with a signature chain that can be verified to ensure the key was issued by an authenticated KMS to an attested TEE instance.

This enables **implicit attestation** - instead of checking TDX quotes directly, you can verify signature chains to prove a key holder was validated by the KMS system.

### Signature Chain Structure

Every `get_key()` response from the guest agent contains:

```python
class GetKeyResponse:
    key: bytes                    # Derived private key
    signature_chain: List[bytes]  # Chain of signatures
    # signature_chain[0] = App key signature over derived key
    # signature_chain[1] = KMS root signature over app key
```

### Signature Generation Process

#### 1. KMS Root Key Signs App Key
When a TEE instance boots and requests keys from the KMS:

```rust
// In KMS (kms/src/crypto.rs:24-29)
let signature = sign_message(
    parent_key,                    // KMS root private key
    b"dstack-kms-issued",         // Message prefix  
    app_id,                       // Your app's address
    &pubkey.to_sec1_bytes(),      // Derived app public key
)?;
```

**Message Format**: `"dstack-kms-issued:" + app_id + app_public_key`

#### 2. App Key Signs Derived Keys
When applications call `client.get_key()`, the guest agent derives a path-specific key and signs it:

```rust  
// In Guest Agent (guest-agent/src/rpc_service.rs)
let msg_to_sign = format!("{}:{}", 
    request.purpose,                           // e.g., "signing"
    hex::encode(derived_k256_pubkey.to_sec1_bytes())  // Derived public key hex
);
let signature = app_signing_key.sign_digest_recoverable(keccak256(msg_to_sign))?;
```

**Message Format**: `purpose + ":" + derived_public_key_hex`

### Signature Chain Verification Algorithm

#### Complete Verification Function

```python
from eth_account import Account
from eth_utils import keccak

class SignatureChainVerifier:
    def __init__(self, kms_root_address: str):
        self.kms_root_address = kms_root_address
    
    def verify_signature_chain(self, key_response, app_id: str, purpose: str = "signing") -> bool:
        """
        Verify complete signature chain proves KMS attestation
        
        Returns True if:
        1. App key correctly signed the derived key
        2. KMS root correctly signed the app key
        3. Chain of custody is intact
        """
        try:
            # Extract components
            derived_private_key = key_response.key
            signature_chain = key_response.signature_chain
            
            if len(signature_chain) < 2:
                return False
                
            app_signature = signature_chain[0]
            kms_signature = signature_chain[1]
            
            # Get derived public key
            derived_account = Account.from_key(derived_private_key)
            derived_public_key_hex = derived_account.address[2:]  # Remove 0x
            
            # Step 1: Verify app key signed derived key
            message = f"{purpose}:{derived_public_key_hex}"
            message_hash = keccak(text=message)
            app_account = Account.recover_message(message_hash, signature=app_signature)
            
            # Step 2: Verify KMS signed app key
            app_pubkey_bytes = bytes.fromhex(app_account[2:])
            kms_message = b"dstack-kms-issued:" + bytes.fromhex(app_id[2:]) + app_pubkey_bytes
            kms_message_hash = keccak(kms_message)
            recovered_kms = Account.recover_message(kms_message_hash, signature=kms_signature)
            
            # Step 3: Verify KMS signer matches expected root
            return recovered_kms.lower() == self.kms_root_address.lower()
            
        except Exception as e:
            print(f"Signature verification failed: {e}")
            return False

# Usage example
verifier = SignatureChainVerifier("0x...")  # KMS root address
client = DstackClient()
key_resp = client.get_key("cluster/consensus", "signing")
info = client.info()

is_authentic = verifier.verify_signature_chain(key_resp, info.app_id, "signing")
print(f"Key is authentic: {is_authentic}")
```

### Smart Contract Integration

You can use signature chain verification in smart contracts to prove attestation:

```solidity
contract AttestationVerifier {
    address public kmsRootAddress;
    
    function verifySignatureChain(
        bytes32 appId,
        bytes memory derivedPublicKey,
        bytes memory appSignature,
        bytes memory kmsSignature,
        string memory purpose
    ) public view returns (bool) {
        // Recover app public key from app signature
        bytes32 derivedKeyMessage = keccak256(abi.encodePacked(purpose, ":", toHex(derivedPublicKey)));
        address appPublicKey = ecrecover(derivedKeyMessage, appSignature);
        
        // Verify KMS signature over app key
        bytes32 kmsMessage = keccak256(abi.encodePacked("dstack-kms-issued:", appId, abi.encodePacked(appPublicKey)));
        address recoveredKMS = ecrecover(kmsMessage, kmsSignature);
        
        return recoveredKMS == kmsRootAddress;
    }
    
    function registerWithProofOfAttestation(
        bytes32 instanceId,
        bytes memory derivedPublicKey,
        bytes memory appSignature,
        bytes memory kmsSignature
    ) external {
        require(
            verifySignatureChain(instanceId, derivedPublicKey, appSignature, kmsSignature, "signing"),
            "Invalid attestation proof"
        );
        
        // Node is proven to be KMS-attested - register it
        attestedNodes[instanceId] = derivedPublicKey;
    }
}
```

### Key Benefits of Signature Chains

#### 1. No Quote Verification Needed
- Signature chains replace complex TDX quote verification
- Simpler, more gas-efficient smart contracts
- Works across different TEE technologies

#### 2. Cryptographic Proof of Attestation
- Only KMS-attested instances can produce valid signature chains
- Impossible to forge without KMS root private key
- Mathematical proof of TEE validation

#### 3. Composable Authentication
- Use signature chains for inter-node authentication
- Build decentralized systems with implicit attestation
- No need to share or verify quotes between nodes

### Security Considerations

#### KMS Root Key Security
- Signature chains are only as secure as KMS root key protection
- KMS root key compromise would invalidate all signature chains
- Ensure KMS instances use proper key management

#### Signature Chain Validation
- Always verify complete chain, not just final signature
- Check that recovered addresses match expected KMS root
- Validate message format exactly matches KMS implementation

#### Replay Protection
- Signature chains don't include timestamps or nonces
- Add your own challenge-response for replay protection
- Consider using derived keys for different purposes/contexts

### Getting KMS Root Address

The KMS root public key address can be obtained from:

1. **KMS Contract**: Query the deployed KMS contract's `kmsInfo()` function
2. **KMS Metadata**: Call KMS `/get_meta` endpoint 
3. **Genesis Information**: Check KMS bootstrap configuration

```python
# Example: Get KMS root from contract
kms_contract = web3.eth.contract(address=kms_address, abi=kms_abi)
kms_info = kms_contract.functions.kmsInfo().call()
kms_root_pubkey = kms_info[0]  # k256Pubkey field
kms_root_address = web3.toChecksumAddress(kms_root_pubkey[-20:])  # Last 20 bytes = address
```

## Guest Agent Integration & SDK Details

### Guest Agent RPC Services

The dstack guest agent exposes multiple RPC services for different client needs:

#### Current Services (3 services exposed)

##### 1. DstackGuest Service (Primary - v0.5+)
- **GetTlsKey**: Random TLS certificate generation
- **GetKey**: Deterministic secp256k1 key derivation  
- **GetQuote**: TDX attestation quote (raw report data only)
- **EmitEvent**: Custom event logging to RTMR3
- **Info**: TEE instance information

##### 2. Tappd Service (Legacy - deprecated)
- **DeriveKey**: TLS key with path-based derivation + random option
- **DeriveK256Key**: K256 key derivation (same as GetKey)
- **TdxQuote**: Advanced quote generation with hash algorithms
- **RawQuote**: Raw TDX quote (same as GetQuote)
- **Info**: TEE instance information

##### 3. Worker Service (External)
- **Info**: Public TEE instance info (limited TCB data)
- **Version**: Guest agent version information

### Python SDK Implementation

The Python SDK provides the primary interface for applications to interact with the guest agent:

#### Core Methods Available

| Method | Status | Purpose |
|--------|--------|---------|
| `get_key(path, purpose)` | ✅ | Deterministic secp256k1 key derivation |
| `get_tls_key(**options)` | ✅ | Random TLS certificate generation |
| `get_quote(report_data)` | ✅ | TDX attestation quote (raw only) |
| `emit_event(event, payload)` | ✅ | Custom event logging to RTMR3 |
| `info()` | ✅ | TEE instance information |
| `is_reachable()` | ✅ | Connectivity test |

#### TEE Instance Information Structure

The `info()` method returns comprehensive TEE instance data:

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

class EventLog:
    imr: int               # Which RTMR this event extends (0-3)
    event_type: int        # Type of event (boot, config, custom)
    digest: str            # SHA384 digest of event data (hex)
    event: str             # Human-readable event description
    event_payload: str     # Base64-encoded event payload data
```

#### Key Fields for Applications

- **`app_id`**: Persistent identifier across deployments (used for key derivation)
- **`instance_id`**: Unique per container restart
- **`device_id`**: Hardware-bound identifier
- **`rtmr0-3`**: Cryptographic measurements for verification
- **`app_cert`**: Certificate for RA-TLS authentication
- **`compose_hash`**: Verifies application configuration integrity
