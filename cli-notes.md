# Phala Cloud CLI SDK Integration Documentation

## Overview

The Phala Cloud CLI (`phala-cloud-cli`) provides a command-line interface that wraps the `@phala/cloud` SDK to manage Phala Cloud deployments. The CLI is structured with a clear separation between commands, API layer, and utilities.

## Architecture

```
Commands → API Layer → SDK → Phala Cloud
   ↓           ↓        ↓
CLI Logic   API Wrappers  Direct SDK Calls
```

## SDK Integration Patterns

### 1. **Direct SDK Usage** (Primary Pattern)

Most commands use the SDK directly through the API layer:

```typescript
// From commands/cvms/create.ts
import { createClient } from '@phala/cloud';
import { encryptEnvVars } from '@phala/dstack-sdk/encrypt-env-vars';

// Create SDK client
const apiClient = createClient({ apiKey: apiKey });

// Use SDK functions directly
const encrypted_env = await encryptEnvVars(envs, pubkey.app_env_encrypt_pubkey);
```

### 2. **Safe SDK Wrapper Functions** (Deploy Command)

The deploy command uses "safe" wrapper functions that provide better error handling:

```typescript
// From commands/deploy/index.ts
import {
  safeProvisionCvm,
  safeCommitCvmProvision,
  safeGetAvailableNodes,
  safeGetKmsList,
  safeDeployAppAuth
} from "@phala/cloud";

// Safe function calls with result validation
const provision_result = await safeProvisionCvm(client, app_compose);
if (!provision_result.success) {
  throw new Error('Failed to provision CVM:', provision_result.error);
}
```

## Command-SDK Mapping

### **CVM Management Commands**

#### `phala cvms create`
- **SDK Calls**: 
  - `createClient()` - Creates authenticated client
  - `getPubkeyFromCvm()` - Gets encryption public key
  - `encryptEnvVars()` - Encrypts environment variables
  - `createCvm()` - Creates CVM via API

#### `phala cvms list`
- **SDK Calls**: 
  - `createClient()` - Creates authenticated client
  - `getCvms()` - Lists all CVMs

#### `phala cvms start/stop/restart`
- **SDK Calls**: 
  - `startCvm()`, `stopCvm()`, `restartCvm()` - Control CVM lifecycle

#### `phala cvms upgrade`
- **SDK Calls**: 
  - `upgradeCvm()` - Updates CVM configuration

#### `phala cvms resize`
- **SDK Calls**: 
  - `resizeCvm()` - Resizes CVM resources

#### `phala cvms attestation`
- **SDK Calls**: 
  - `getCvmAttestation()` - Gets CVM attestation info

### **Deployment Command**

#### `phala deploy` (Main Command)
- **SDK Calls**:
  - `safeGetAvailableNodes()` - Gets available nodes
  - `safeGetKmsList()` - Gets KMS instances
  - `safeProvisionCvm()` - Provisions CVM
  - `safeCommitCvmProvision()` - Commits CVM creation
  - `safeDeployAppAuth()` - Deploys app authentication (on-chain KMS)
  - `encryptEnvVars()` - Encrypts environment variables

### **Node Management Commands**

#### `phala nodes list`
- **SDK Calls**: 
  - `getTeepods()` - Gets available TEE nodes and KMS instances

### **Authentication Commands**

#### `phala auth login`
- **SDK Calls**: 
  - `getUserInfo()` - Validates API key

#### `phala status`
- **SDK Calls**: 
  - `safeGetCurrentUser()` - Gets current user information

## API Layer Implementation

### **CVMs API** (`src/api/cvms.ts`)

```typescript
export async function getCvms(): Promise<CvmInstance[]> {
  const apiKey = getApiKey();
  const apiClient = createClient({ apiKey: apiKey });
  const response = await apiClient.get<CvmInstance[]>(API_ENDPOINTS.CVMS(0));
  return z.array(cvmInstanceSchema).parse(response);
}
```

**Key Functions**:
- `getCvms()` - Lists all CVMs
- `createCvm()` - Creates new CVM
- `getCvmByAppId()` - Gets specific CVM
- `startCvm()`, `stopCvm()`, `restartCvm()` - Lifecycle management
- `upgradeCvm()` - Updates CVM
- `deleteCvm()` - Deletes CVM
- `getCvmAttestation()` - Gets attestation info
- `resizeCvm()` - Resizes resources
- `replicateCvm()` - Creates CVM replica

### **Auth API** (`src/api/auth.ts`)

```typescript
export async function getUserInfo(apiKey?: string): Promise<GetUserInfoResponse> {
  const apiClient = createClient({ apiKey: apiKey });
  const response = await apiClient.get<any>(API_ENDPOINTS.USER_INFO);
  return getUserInfoResponseSchema.parse(response);
}
```

### **TEEPods API** (`src/api/teepods.ts`)

```typescript
export async function getTeepods(): Promise<TeepodResponse> {
  const apiKey = getApiKey();
  const apiClient = createClient({ apiKey: apiKey });
  const response = await (await apiClient).get<TeepodResponse>(API_ENDPOINTS.TEEPODS);
  return teepodResponseSchema.parse(response);
}
```

## SDK Function Categories Used

### **Core Client Functions**
- `createClient({ apiKey })` - Creates authenticated HTTP client

### **CVM Management Functions**
- `provisionCvm()` - Provisions CVM configuration
- `commitCvmProvision()` - Creates CVM from provisioned data
- `getCvmInfo()` - Gets CVM information
- `getCvmList()` - Lists CVMs
- `getCvmComposeFile()` - Gets compose configuration

### **KMS Functions**
- `getKmsInfo()` - Gets KMS information
- `getKmsList()` - Lists available KMS instances

### **Node Functions**
- `getAvailableNodes()` - Lists available nodes
- `getCurrentUser()` - Gets current user information

### **Utility Functions**
- `encryptEnvVars()` - Encrypts environment variables
- `parseEnvVars()` - Parses environment variable files

## Error Handling Patterns

### **1. API Layer Error Handling**
```typescript
try {
  const response = await apiClient.get<CvmInstance[]>(API_ENDPOINTS.CVMS(0));
  return z.array(cvmInstanceSchema).parse(response);
} catch (error) {
  throw new Error(`Failed to get CVMs: ${error instanceof Error ? error.message : String(error)}`);
}
```

### **2. Safe Function Error Handling**
```typescript
const result = await safeProvisionCvm(client, app_compose);
if (!result.success) {
  if ("isRequestError" in result.error) {
    throw new Error(`HTTP ${result.error.status}: ${result.error.message}`);
  } else {
    throw new Error(`Validation error: ${result.error.issues}`);
  }
}
```

### **3. Schema Validation**
```typescript
try {
  return postCvmResponseSchema.parse(response);
} catch (error) {
  if (error instanceof z.ZodError) {
    logger.error('Schema validation error:', JSON.stringify(error.errors, null, 2));
    throw new Error(`Response validation failed: ${JSON.stringify(error.errors)}`);
  }
  throw new Error(`Failed to create CVM: ${error instanceof Error ? error.message : String(error)}`);
}
```

## Configuration and Constants

### **API Endpoints** (`src/utils/constants.ts`)
```typescript
export const API_ENDPOINTS = {
  CVMS: (userId: number) => `cvms?user_id=${userId}`,
  CVM_BY_APP_ID: (appId: string) => `cvms/app_${appId}`,
  CVM_START: (appId: string) => `cvms/app_${appId}/start`,
  // ... more endpoints
};
```

### **Default Values**
```typescript
export const DEFAULT_VCPU = 1;
export const DEFAULT_MEMORY = 2048; // MB
export const DEFAULT_DISK_SIZE = 40; // GB
export const DEFAULT_IMAGE = 'dstack-0.3.6';
```

## Key Integration Points

### **1. Environment Variable Encryption**
```typescript
// Get public key from CVM
const pubkey = await getPubkeyFromCvm(vmConfig);

// Encrypt environment variables using SDK
const encrypted_env = await encryptEnvVars(envs, pubkey.app_env_encrypt_pubkey);
```

### **2. KMS Integration**
```typescript
// For on-chain KMS
const deploy_result = await safeDeployAppAuth({
  chain: chain,
  rpcUrl: rpc_url,
  kmsContractAddress: kms_contract_address,
  privateKey: privateKey,
  deviceId: device_id,
  composeHash: compose_hash,
});
```

### **3. Docker Compose Integration**
```typescript
const compose_manifest = {
  docker_compose_file: composeString,
  features: ['kms', 'tproxy-net'],
  kms_enabled: true,
  manifest_version: 2,
  // ... more configuration
};
```

## Summary

The Phala Cloud CLI provides a comprehensive command-line interface that leverages the `@phala/cloud` SDK for all cloud operations. The architecture follows a clean separation of concerns:

- **Commands** handle user interaction and orchestrate operations
- **API Layer** provides typed wrappers around SDK calls with error handling
- **SDK** handles the actual HTTP communication and business logic
- **Utilities** provide common functionality like logging, configuration, and validation

The CLI supports both centralized and decentralized KMS deployments, with the deploy command being the primary entry point for creating new CVMs with full SDK integration.
