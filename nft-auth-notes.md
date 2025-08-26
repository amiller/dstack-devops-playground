# NFT-Based Authentication for DStack Apps

## Current DStack App Authorization

DStack uses a **two-tier authorization model** where app owners can deploy unlimited CVM instances:

1. **KMS-Level**: Validates OS image, hardware measurements, basic security
2. **App-Level**: Validates compose hash and optionally restricts devices

**Current behavior**: Any number of CVMs can boot if they use allowed compose hashes and meet KMS requirements.

**Source**: [DstackApp.sol:125-140](https://github.com/Phala-Network/dstack/blob/da5152/kms/auth-eth/contracts/DstackApp.sol#L125-L140)
```solidity
function isAppAllowed(AppBootInfo calldata bootInfo) external view returns (bool, string memory) {
    if (!allowedComposeHashes[bootInfo.composeHash]) {
        return (false, "Compose hash not allowed");
    }
    if (!allowAnyDevice && !allowedDeviceIds[bootInfo.deviceId]) {
        return (false, "Device not allowed");
    }
    return (true, ""); // ✅ UNLIMITED instances can pass
}
```

**The Opportunity**: The `instanceId` field in `AppBootInfo` is currently unused but available for NFT-based restrictions.

## Instance ID Timing

**Critical Finding**: `instance_id` is only available **after** CVM deployment, not during provisioning.

**Evidence from Phala Cloud SDK**:
- **Provision Response** ([phala-cloud-sdks/js/src/actions/provision_cvm.ts:65-75](https://github.com/Phala-Network/phala-cloud-sdks/blob/5129cf/js/src/actions/provision_cvm.ts#L65-L75)): No `instance_id`
- **Commit Response** ([phala-cloud-sdks/js/src/actions/commit_cvm_provision.ts:98](https://github.com/Phala-Network/phala-cloud-sdks/blob/5129cf/js/src/actions/commit_cvm_provision.ts#L98)): Contains `instance_id`

## NFT-Gated Network Design

**Goal**: Transform from unlimited deployment to **1 NFT token = 1 CVM node**.

**Simple 3-Step Process**:
1. Deploy CVM normally (provision → commit)
2. Get `instance_id` from commit response
3. Register `instance_id` with NFT token on contract

## DstackAppNFT Contract

**Source**: Extends `dstack/kms/auth-eth/contracts/DstackApp.sol`

```solidity
contract DstackAppNFT is DstackApp {
    IERC721 public nftContract;
    
    mapping(uint256 => bytes32) public tokenToInstance;  // Token ID → instance ID
    mapping(bytes32 => uint256) public instanceToToken;  // Instance ID → token ID
    
    event InstanceRegistered(address indexed nftHolder, uint256 indexed tokenId, bytes32 indexed instanceId);
    
    function registerInstance(bytes32 instanceId, uint256 tokenId) external {
        require(nftContract.ownerOf(tokenId) == msg.sender, "Not the NFT owner");
        require(tokenToInstance[tokenId] == bytes32(0), "Token already used");
        require(instanceToToken[instanceId] == 0, "Instance already registered");
        
        tokenToInstance[tokenId] = instanceId;
        instanceToToken[instanceId] = tokenId;
        
        emit InstanceRegistered(msg.sender, tokenId, instanceId);
    }
    
    // Modified authorization with NFT validation
    function isAppAllowed(AppBootInfo calldata bootInfo) external view override returns (bool, string memory) {
        // Existing validations
        if (!allowedComposeHashes[bootInfo.composeHash]) {
            return (false, "Compose hash not allowed");
        }
        if (!allowAnyDevice && !allowedDeviceIds[bootInfo.deviceId]) {
            return (false, "Device not allowed");
        }
        
        // NEW: NFT validation
        if (address(nftContract) != address(0)) {
            bytes32 instanceId = bytes32(bootInfo.instanceId);
            uint256 tokenId = instanceToToken[instanceId];
            
            if (tokenId == 0) {
                return (false, "Instance not registered with any NFT token");
            }
            if (nftContract.ownerOf(tokenId) == address(0)) {
                return (false, "Backing NFT token no longer exists");
            }
        }
        
        return (true, "");
    }
}
```

## Deployment Example

**Based on**: [myexamples/deploy-multi.ts](https://github.com/Phala-Network/phala-cloud-cli/blob/acf3c9/myexamples/deploy-multi.ts)

```typescript
async function deployNFTGatedCVM(nftTokenId: number, isFirstDeployment: boolean = true) {
    const phalaClient = createClient({ apiKey: process.env.PHALA_CLOUD_API_KEY });
    
    // 1. Get onchain KMS node and info
    const nodes = await getAvailableNodes(phalaClient);
    const target = nodes.nodes.find((node) => node.support_onchain_kms);
    const kms_list = await getKmsList(phalaClient);
    const kms = kms_list.items.find((k) => k.slug === process.env.KMS_ID);
    
    // 2. Provision CVM
    const provision = await provisionCvm(phalaClient, {
        name: `nft-node-${nftTokenId}`,
        compose_file: { docker_compose_file: dockerComposeYml, kms_enabled: true },
        vcpu: 1, memory: 1024, disk_size: 10,
        node_id: target.teepod_id,
        image: target.images[0].name,
        kms_id: kms.slug
    });
    
    // 3. Deploy DstackAppNFT contract (first time only)
    if (isFirstDeployment) {
        const deployed_contract = await deployAppAuth({
            chain: kms.chain, rpcUrl: process.env.RPC_URL,
            kmsContractAddress: kms.kms_contract_address,
            privateKey: process.env.PRIVATE_KEY,
            deviceId: target.device_id,
            composeHash: provision.compose_hash,
        });
        // Save: deployed_contract.appId, deployed_contract.appAuthAddress, deployed_contract.deployer
    }
    
    // 4. Commit CVM
    const cvm = await commitCvmProvision(phalaClient, {
        app_id: appId, compose_hash: provision.compose_hash,
        kms_id: kms.slug, contract_address: contractAddress, deployer_address: deployerAddress
    });
    
    // 5. Register instance with NFT token
    await walletClient.writeContract({
        address: contractAddress,
        abi: dstackAppNFTAbi,
        functionName: 'registerInstance',
        args: [`0x${cvm.instance_id}`, BigInt(nftTokenId)]
    });
    
    return { cvmId: cvm.id, instanceId: cvm.instance_id };
}
```

## Key Benefits

- **Scarcity-based network**: Network size limited to NFT supply
- **Transferable membership**: Selling NFT transfers node authorization  
- **Multiple nodes**: Holders with multiple NFTs can run multiple nodes (1:1 ratio)
- **Simple implementation**: Standard deployment + one registration transaction

## Evidence References

- **DStack App Contract**: [dstack/kms/auth-eth/contracts/DstackApp.sol](https://github.com/Phala-Network/dstack/blob/da5152/kms/auth-eth/contracts/DstackApp.sol)
- **Boot Info Structure**: [dstack/kms/auth-eth/contracts/IAppAuth.sol:36-46](https://github.com/Phala-Network/dstack/blob/da5152/kms/auth-eth/contracts/IAppAuth.sol#L36-L46)
- **Phala Cloud Provision**: [phala-cloud-sdks/js/src/actions/provision_cvm.ts](https://github.com/Phala-Network/phala-cloud-sdks/blob/5129cf/js/src/actions/provision_cvm.ts)
- **Phala Cloud Commit**: [phala-cloud-sdks/js/src/actions/commit_cvm_provision.ts](https://github.com/Phala-Network/phala-cloud-sdks/blob/5129cf/js/src/actions/commit_cvm_provision.ts)
- **Deployment Pattern**: [myexamples/deploy-multi.ts](https://github.com/Phala-Network/phala-cloud-cli/blob/acf3c9/myexamples/deploy-multi.ts)