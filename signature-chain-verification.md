# DStack SDK Signature Chain Verification Guide

## Overview

The DStack SDK provides a powerful but underdocumented feature: **signature chains** that cryptographically prove key derivation authenticity. Every derived key comes with a signature chain that can be verified to ensure the key was issued by an authenticated KMS to an attested TEE instance.

This enables **implicit attestation** - instead of checking TDX quotes directly, you can verify signature chains to prove a key holder was validated by the KMS system.

## How Signature Chains Work

### 1. **KMS Root Key Signs App Key**
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

### 2. **App Key Signs Derived Keys**
When you call `client.get_key()`, the guest agent derives a path-specific key and signs it:

```rust  
// In Guest Agent (guest-agent/src/rpc_service.rs)
let msg_to_sign = format!("{}:{}", 
    request.purpose,                           // e.g., "signing"
    hex::encode(derived_k256_pubkey.to_sec1_bytes())  // Derived public key hex
);
let signature = app_signing_key.sign_digest_recoverable(keccak256(msg_to_sign))?;
```

**Message Format**: `purpose + ":" + derived_public_key_hex`

### 3. **Signature Chain Structure**
Every `get_key()` response contains:

```python
class GetKeyResponse:
    key: bytes                    # Derived private key
    signature_chain: List[bytes]  # Chain of signatures
    # signature_chain[0] = App key signature over derived key
    # signature_chain[1] = KMS root signature over app key
```

## Verification Algorithm

### **Step 1: Extract Components**
```python
from dstack_sdk import DstackClient
import json
from eth_account import Account
from eth_utils import keccak

client = DstackClient()
key_response = client.get_key("cluster/consensus", "signing")

derived_private_key = key_response.key
signature_chain = key_response.signature_chain
app_key_signature = signature_chain[0]  # App signed derived key
kms_signature = signature_chain[1]      # KMS signed app key

# Get derived public key
derived_public_key = Account.from_key(derived_private_key).address
derived_public_key_hex = derived_public_key[2:]  # Remove 0x prefix
```

### **Step 2: Recover App Public Key**
```python
def recover_app_public_key(derived_public_key_hex: str, app_signature: bytes, purpose: str = "signing") -> str:
    """Recover app public key from its signature over derived key"""
    
    # Reconstruct signed message
    message = f"{purpose}:{derived_public_key_hex}"
    message_hash = keccak(text=message)
    
    # Recover app public key from signature
    app_account = Account.recover_message(message_hash, signature=app_signature)
    return app_account  # This is the app's Ethereum address

app_public_key = recover_app_public_key(derived_public_key_hex, app_key_signature)
```

### **Step 3: Verify KMS Signature**
```python
def verify_kms_signature(app_public_key: str, kms_signature: bytes, app_id: str, kms_root_address: str) -> bool:
    """Verify KMS root signature over app key"""
    
    # Reconstruct KMS signed message  
    # Format: "dstack-kms-issued:" + app_id + app_public_key_bytes
    app_pubkey_bytes = bytes.fromhex(app_public_key[2:])  # Remove 0x, convert to bytes
    message = b"dstack-kms-issued:" + bytes.fromhex(app_id[2:]) + app_pubkey_bytes
    message_hash = keccak(message)
    
    # Recover signer from KMS signature
    recovered_signer = Account.recover_message(message_hash, signature=kms_signature)
    
    # Verify it matches expected KMS root address
    return recovered_signer.lower() == kms_root_address.lower()

# Get KMS root address (available from KMS contract or metadata)
kms_root_address = "0x..."  # KMS root public key address
app_id = client.info().app_id

is_valid = verify_kms_signature(app_public_key, kms_signature, app_id, kms_root_address)
```

## Complete Verification Function

```python
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

## Smart Contract Integration

You can use this verification in smart contracts to prove attestation:

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

## Key Benefits

### 1. **No Quote Verification Needed**
- Signature chains replace complex TDX quote verification
- Simpler, more gas-efficient smart contracts
- Works across different TEE technologies

### 2. **Cryptographic Proof of Attestation**
- Only KMS-attested instances can produce valid signature chains
- Impossible to forge without KMS root private key
- Mathematical proof of TEE validation

### 3. **Composable Authentication**
- Use signature chains for inter-node authentication
- Build decentralized systems with implicit attestation
- No need to share or verify quotes between nodes

## Security Considerations

### **KMS Root Key Security**
- Signature chains are only as secure as KMS root key protection
- KMS root key compromise would invalidate all signature chains
- Ensure KMS instances use proper key management

### **Signature Chain Validation**
- Always verify complete chain, not just final signature
- Check that recovered addresses match expected KMS root
- Validate message format exactly matches KMS implementation

### **Replay Protection**
- Signature chains don't include timestamps or nonces
- Add your own challenge-response for replay protection
- Consider using derived keys for different purposes/contexts

## Getting KMS Root Address

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

## Conclusion

Signature chain verification provides a powerful mechanism for building attestation-based authentication systems without requiring complex quote verification. This underdocumented feature enables secure, gas-efficient smart contracts that can cryptographically verify TEE attestation through the existing KMS infrastructure.

The signature chain acts as a **certificate of attestation** - proof that the KMS system validated the holder's TEE instance and granted them cryptographic keys. This enables building decentralized systems with strong security guarantees while leveraging existing DStack infrastructure.