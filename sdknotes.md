# Phala Cloud SDK Study Notes

## Repository Structure
- **Main SDK**: `/phala-cloud-sdks/js/` contains the core TypeScript SDK
- **CLI Tool**: Uses the SDK as a dependency (`@phala/cloud: ^0.0.9`)
- **Examples**: Working examples in `/phala-cloud-sdks/js/examples/`

## Key SDK Functions Discovered

### Core Deployment Flow
1. **`safeProvisionCvm(client, appCompose)`** - Reserves CVM resources
   - Returns: `{ compose_hash, app_id?, app_env_encrypt_pubkey?, device_id?, ... }`
   - For centralized KMS: provides `app_id` + `app_env_encrypt_pubkey` immediately
   - For on-chain KMS: provides `compose_hash` for contract deployment

2. **`safeDeployAppAuth({ chain, rpcUrl, kmsContractAddress, privateKey, deviceId, composeHash })`** - Blockchain contract deployment
   - Only needed for on-chain KMS nodes
   - Returns: `{ appId, appAuthAddress, deployer }`
   - This is the blockchain transaction part

3. **`safeGetAppEnvEncryptPubKey(client, { app_id, kms })`** - Get encryption key
   - Used with on-chain KMS after contract deployment
   - Returns: `{ public_key }`

4. **`safeCommitCvmProvision(client, payload)`** - Final CVM creation
   - Links everything together and creates the actual CVM
   - Returns full CVM details including `vm_uuid`

### Environment Variable Handling
- **`encryptEnvVars(envVars, publicKey)`** - Client-side encryption
- EnvVars format: `{ key: string, value: string }[]`
- All env vars are encrypted before sending to Phala Cloud

## Two Deployment Modes

### Centralized KMS (Simple)
```typescript
const app = await provisionCvm(client, appCompose);
// app.app_id and app.app_env_encrypt_pubkey are provided
const encrypted_env = await encryptEnvVars(envVars, app.app_env_encrypt_pubkey);
const cvm = await commitCvmProvision(client, {
  app_id: app.app_id,
  encrypted_env,
  compose_hash: app.compose_hash
});
```

### On-Chain KMS (Contract-based)
```typescript
const app = await provisionCvm(client, appCompose);
// Deploy blockchain contract first
const contract = await deployAppAuth({
  chain, rpcUrl, kmsContractAddress, privateKey, deviceId,
  composeHash: app.compose_hash
});
// Get encryption key using contract's app_id
const pubkey = await getAppEnvEncryptPubKey(client, {
  app_id: contract.appId,
  kms: kmsSlug
});
const encrypted_env = await encryptEnvVars(envVars, pubkey.public_key);
const cvm = await commitCvmProvision(client, {
  app_id: contract.appId,
  encrypted_env,
  compose_hash: app.compose_hash,
  kms_id: kmsSlug,
  contract_address: contract.appAuthAddress,
  deployer_address: contract.deployer
});
```

## Key Insights for Multi-CVM Deployment

### Same App ID Strategy
To deploy multiple CVMs to the same app_id:

1. **One-time contract deployment** (for on-chain KMS):
   ```typescript
   const contract = await deployAppAuth({ ... });
   // contract.appId can be reused for multiple CVMs
   ```

2. **Multiple CVM instances**:
   ```typescript
   for (let i = 0; i < numCVMs; i++) {
     const app = await provisionCvm(client, appCompose);
     const pubkey = await getAppEnvEncryptPubKey(client, {
       app_id: contract.appId,  // Reuse same app_id
       kms: kmsSlug
     });
     const encrypted_env = await encryptEnvVars(instanceEnvVars[i], pubkey.public_key);
     const cvm = await commitCvmProvision(client, {
       app_id: contract.appId,  // Same app_id
       encrypted_env,
       compose_hash: app.compose_hash,
       kms_id: kmsSlug,
       contract_address: contract.appAuthAddress,  // Same contract
       deployer_address: contract.deployer
     });
   }
   ```

## Example Code Structure
The `deploy.ts` example shows:
- Command-line argument parsing with `arg`
- Environment variable parsing from `.env` files
- Proper error handling with assertions
- Support for both deployment modes
- Update functionality for existing CVMs

## Required Dependencies
```json
{
  "@phala/cloud": "latest",
  "arg": "^5.0.2",
  "viem": "^2.7.0"
}
```

## Key Files to Study
- `/js/examples/deploy.ts` - Complete deployment example
- `/js/src/actions/deploy_app_auth.ts` - Contract deployment logic
- `/js/src/actions/provision_cvm.ts` - CVM provisioning
- `/js/src/actions/commit_cvm_provision.ts` - Final CVM creation

## Security Notes
- Private keys are handled client-side only
- All environment variables are encrypted before transmission
- Contract addresses and deployer addresses are tracked for audit
- TEE device IDs ensure hardware-level security