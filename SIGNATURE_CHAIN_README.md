# Signature Chain Verification in DStack NFT Cluster

This document describes the integration of signature chain verification into the DStack NFT cluster system, providing **implicit attestation** through cryptographic proof of KMS validation.

## Overview

The signature chain verification adds an extra layer of security by ensuring that only KMS-attested TEE instances can register with the cluster. This prevents unauthorized nodes from joining the network, even if they possess valid NFTs.

## How It Works

### 1. **Signature Chain Structure**
Every DStack key derivation includes a signature chain:
```
App Key → signs → Derived Key
  ↓
KMS Root → signs → App Key
```

### 2. **Verification Process**
1. **App Signature**: App signs the derived key with its private key
2. **KMS Signature**: KMS root signs the app's public key during attestation
3. **Contract Verification**: Smart contract verifies both signatures to prove attestation

### 3. **Fallback Behavior**
- If signature verification fails, falls back to basic registration
- Ensures cluster operation even with verification issues
- Maintains backward compatibility

## Contract Changes

### New Functions

```solidity
function registerInstanceWithProof(
    bytes32 instanceId, 
    uint256 tokenId,
    bytes memory derivedPublicKey,
    bytes memory appSignature,
    bytes memory kmsSignature,
    string memory purpose
) external;

function verifySignatureChain(
    bytes32 appId,
    bytes memory derivedPublicKey,
    bytes memory appSignature,
    bytes memory kmsSignature,
    string memory purpose
) public view returns (bool);
```

### State Variables

```solidity
address public kmsRootAddress;  // KMS root public key address
```

## Application Changes

### Enhanced Registration Flow

```python
async def register_instance_with_proof(self):
    """Register instance with signature chain proof of attestation"""
    # Get signature chain from DStack
    key_response = self.dstack_client.get_key(self.dstack_key_path, self.dstack_key_purpose)
    
    # Extract signature components
    app_signature = key_response.signature_chain[0]
    kms_signature = key_response.signature_chain[1]
    
    # Call enhanced registration
    await self.contract.functions.registerInstanceWithProof(
        instance_id, token_id, derived_public_key,
        app_signature, kms_signature, purpose
    ).call()
```

### Fallback Registration

```python
async def register_instance_basic(self):
    """Fallback to basic registration without attestation proof"""
    # Standard registration without verification
    await self.contract.functions.registerInstance(instance_id, token_id).call()
```

## Testing

### Local Development

1. **Deploy Contract with Mock KMS Root**
```bash
cd contracts
export KMS_ROOT_ADDRESS="0x1234567890123456789012345678901234567890"
forge script script/Deploy.s.sol --rpc-url http://localhost:8545 --broadcast
```

2. **Test with DStack Integration**
```bash
python3 counter.py --instance-id node1 --contract $CONTRACT_ADDRESS --use-dstack --port 8081
```

3. **Test Fallback Registration**
```bash
python3 counter.py --instance-id node2 --contract $CONTRACT_ADDRESS --wallet $PRIVATE_KEY --port 8082
```

### Automated Testing

```bash
# Run the deployment and testing script
./deploy_and_test.sh

# Run contract tests
cd contracts && forge test
```

## Security Benefits

### 1. **Implicit Attestation**
- No need to verify TDX quotes directly
- Cryptographic proof of KMS validation
- Works across different TEE technologies

### 2. **Enhanced Access Control**
- Only KMS-attested instances can register
- Prevents unauthorized node injection
- Maintains NFT-based membership model

### 3. **Fallback Security**
- Graceful degradation if verification fails
- Maintains cluster operation
- Audit trail of verification attempts

## Production Deployment

### 1. **Set Real KMS Root**
```bash
# Get KMS root from production KMS
curl $KMS_ENDPOINT/get_meta | jq '.kmsInfo.k256Pubkey'

# Deploy contract with real KMS root
export KMS_ROOT_ADDRESS=$REAL_KMS_ROOT
forge script script/Deploy.s.sol --rpc-url $BASE_RPC_URL --broadcast
```

### 2. **Phala Cloud Integration**
```bash
# Deploy with production KMS
phala deploy --node-id 12 --kms-id kms-base-prod7 docker-compose.yml
```

## Monitoring and Debugging

### Log Messages

- `"Instance registered with attestation proof"` - Success with verification
- `"Instance registered with basic method"` - Fallback registration
- `"Invalid attestation proof"` - Verification failed

### Status Endpoints

```bash
# Check node status
curl http://localhost:8081/status

# Check cluster members
curl http://localhost:8081/members

# Check wallet info
curl http://localhost:8081/wallet-info
```

## Future Enhancements

### 1. **Multi-KMS Support**
- Support for multiple KMS providers
- KMS rotation and failover
- Cross-KMS attestation verification

### 2. **Advanced Verification**
- Timestamp-based signature validation
- Nonce-based replay protection
- Batch signature verification

### 3. **Governance Integration**
- NFT holder voting for KMS root updates
- Multi-signature KMS root management
- Emergency KMS root rotation

## Troubleshooting

### Common Issues

1. **"Invalid attestation proof"**
   - Check KMS root address in contract
   - Verify DStack connection and key derivation
   - Check signature chain length

2. **"Insufficient signature chain length"**
   - Ensure DStack SDK is properly configured
   - Check KMS endpoint connectivity
   - Verify key derivation path

3. **Fallback to basic registration**
   - Check DStack logs for errors
   - Verify contract deployment
   - Check network connectivity

### Debug Commands

```bash
# Check contract state
cast call $CONTRACT "kmsRootAddress()"

# Check instance registration
cast call $CONTRACT "getInstanceInfo(bytes32)" $INSTANCE_ID

# Verify signature chain manually
cast call $CONTRACT "verifySignatureChain(bytes32,bytes,bytes,bytes,string)" \
  $APP_ID $DERIVED_KEY $APP_SIG $KMS_SIG $PURPOSE
```

## Conclusion

The signature chain verification provides a robust, cryptographic foundation for ensuring only authorized, attested TEE instances can join the DStack NFT cluster. This enhancement maintains the simplicity of the NFT-based membership model while adding enterprise-grade security through implicit attestation.

The fallback behavior ensures operational continuity while providing a clear audit trail of verification attempts, making this system suitable for both development and production environments.
