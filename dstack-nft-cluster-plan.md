# NFT-Gated DStack Node Cluster Design Document

## Overview

This document outlines the implementation plan for an NFT-based membership system that controls deployment authorization in DStack clusters. The system transforms DStack's unlimited deployment model into a scarcity-based network where **1 NFT = 1 authorized node deployment**.

## Architecture

### Core Components

**1. NFT Membership Contract (DstackApp + ERC721)**
```solidity
contract DstackMembershipNFT is DstackApp, ERC721 {
    // Instance management
    mapping(uint256 => bytes32) public tokenToInstance;     // NFT → instanceID
    mapping(bytes32 => uint256) public instanceToToken;     // instanceID → NFT  
    mapping(bytes32 => bool) public activeInstances;        // instanceID → active
    
    // Byzantine fault tolerant leader election state
    struct Vote {
        address voter;
        uint256 tokenId;
        bool isNoConfidence;
        uint256 timestamp;
    }
    
    mapping(address => Vote) public currentVotes;           // voter → current vote
    mapping(address => uint256) public noConfidenceCount;   // leader → votes against
    uint256 public totalActiveNodes;                        // Current cluster size
    uint256 public requiredVotes;                           // f+1 threshold for 2f+1 nodes
    
    address public currentLeader;                           // Current leader's wallet
    uint256 public currentLeaderTokenId;                    // Leader's NFT token
    
    // Leader election events
    event LeaderElected(address indexed leader, uint256 indexed tokenId, bytes32 instanceId);
    event VoteCast(address indexed voter, address indexed target, bool isNoConfidence);
    event LeaderChallenged(address indexed newLeader, address indexed oldLeader, uint256 voteCount);
    
    function registerInstance(bytes32 instanceId, uint256 tokenId) external;
    function castVote(address target, bool isNoConfidence) external;
    function electLeader() external;
    function isAppAllowed(AppBootInfo calldata bootInfo) external view override;
}
```

**Byzantine Fault Tolerant Leader Election:**
- **Cluster Size**: Requires 2f+1 nodes where f is maximum failures
- **Challenge Threshold**: f+1 votes needed to challenge current leader
- **Immediate Challenges**: No timeout required - nodes vote when they detect unresponsiveness
- **Democratic Process**: Any active node can vote no-confidence against current leader
- **Automatic Failover**: Leader change triggered when f+1 votes accumulated
- **Vote Management**: Nodes can change votes based on leader responsiveness

**2. Demo Application: Distributed Counter Service**
- Simple consensus-based counter with leader election
- Demonstrates core distributed database primitives (leader election, replication, failover)
- Foundation for future PostgreSQL + Patroni clustering

**3. Development Environment**
- **Local**: Pure Python development with mock components
- **Docker**: Full validation with real KMS + Anvil blockchain  
- **Production**: Phala Cloud deployment with Base mainnet

## Implementation Phases

### Phase 1: Local Development Environment

**Components:**
- Anvil (local blockchain)
- Mock KMS (`dstack/kms/auth-mock`) - bypasses validation
- Pure Python counter application
- Direct NFT contract interaction

**Benefits:**
- Fast iteration cycle
- No blockchain costs
- Easy debugging
- No container complexity

**Setup:**
```bash
# Terminal 1: Local blockchain
anvil --host 0.0.0.0 --port 8545

# Terminal 2: Mock KMS (always succeeds)
cd refs/dstack/kms/auth-mock && bun start

# Terminal 3: Deploy & test
python3 counter.py --instance-id mock-node1
```

### Phase 2: Docker Integration Environment  

**Components:**
- Anvil (local blockchain in container)
- Real KMS (`dstack/kms/auth-eth-bun`) connecting to Anvil
- Dockerized counter application
- **Real compose hash validation**

**Critical Value:**
This stage exercises the actual compose hash validation that production will use.

**Docker Compose:**
```yaml
services:
  anvil:
    image: ghcr.io/foundry-rs/foundry:latest
    command: anvil --host 0.0.0.0 --port 8545
    ports: ["8545:8545"]
    
  kms-auth:
    build: refs/dstack/kms/auth-eth-bun
    environment:
      - ETH_RPC_URL=http://anvil:8545
      - KMS_CONTRACT_ADDR=${CONTRACT_ADDRESS}
    ports: ["3000:3000"]
    
  counter:
    build: .
    environment:
      - CONTRACT_ADDRESS=${CONTRACT_ADDRESS}
    ports: ["8080:8080"]
```

**Validation Test:**
```bash
# 1. Calculate compose hash
python3 -c "
from dstack_sdk import get_compose_hash, AppCompose
app_compose = AppCompose(
    runner='docker-compose',
    docker_compose_file=open('docker-compose.yml').read(),
    manifest_version=2,
    kms_enabled=True
)
print('0x' + get_compose_hash(app_compose, normalize=True))
"

# 2. Deploy DstackMembershipNFT contract via KMS factory 
cast send $KMS_CONTRACT "deployAndRegisterApp(address,bool,bool,bytes32,bytes32)" \
  $OWNER false true "0x0000000000000000000000000000000000000000000000000000000000000000" $COMPOSE_HASH \
  --rpc-url http://localhost:8545 --private-key $PRIVATE_KEY

# 3. Extract deployed contract address from transaction
CONTRACT_ADDRESS=$(cast abi-decode "deployAndRegisterApp(address,bool,bool,bytes32,bytes32)(address)" $TX_RESULT)

# 4. Test KMS validation with correct contract structure  
curl -X POST http://localhost:3000/bootAuth/app \
  -d '{"composeHash":"'$COMPOSE_HASH'","appId":"'$CONTRACT_ADDRESS'","instanceId":"0x456",...}'
# Should return {"isAllowed": true} - validates both compose hash AND calls contract's isAppAllowed()
```

### Phase 3: Phala Cloud Production

**Components:**
- Base mainnet blockchain
- Phala-hosted KMS instances (via `--kms-id`)
- Real DStack TEE nodes
- Instance registration flow

**Deployment:**
```bash
# 1. Calculate compose hash for validation
COMPOSE_HASH=$(python3 -c "
from dstack_sdk import get_compose_hash, AppCompose
app_compose = AppCompose(
    runner='docker-compose',
    docker_compose_file=open('docker-compose.yml').read(),
    manifest_version=2,
    kms_enabled=True,
    gateway_enabled=True
)
print('0x' + get_compose_hash(app_compose, normalize=True))
")

# 2. Deploy DstackMembershipNFT via KMS factory (combines DstackApp + ERC721)
cast send $KMS_CONTRACT "deployAndRegisterApp(address,bool,bool,bytes32,bytes32)" \
  $DEPLOYER_ADDRESS false true \
  "0x0000000000000000000000000000000000000000000000000000000000000000" \
  $COMPOSE_HASH \
  --private-key $PRIVATE_KEY --rpc-url $BASE_RPC_URL

# 3. Get deployed contract address from transaction receipt
CONTRACT_ADDRESS=$(cast abi-decode "deployAndRegisterApp(address,bool,bool,bytes32,bytes32)(address)" $TX_RESULT)

# 4. Deploy CVM via Phala Cloud
phala deploy \
  --node-id 12 \
  --kms-id kms-base-prod7 \
  --rpc-url $BASE_RPC_URL \
  --private-key $PRIVATE_KEY \
  docker-compose.yml

# 5. Mint NFT and register instance (post-deployment)
cast send $CONTRACT_ADDRESS "mintNodeAccess(address,string)" $OWNER "node1" --rpc-url $BASE_RPC_URL
cast send $CONTRACT_ADDRESS "registerInstance(bytes32,uint256)" $INSTANCE_ID 1 --rpc-url $BASE_RPC_URL
```

**Key Insight**: Using `KMS.deployAndRegisterApp()` creates a contract that is both a valid DstackApp (for KMS validation) and an ERC721 (for NFT functionality), deployed via the KMS factory pattern in a single transaction.

## Demo Application: Distributed Counter

### Core Features
- **HTTP API**: Simple REST endpoints for counter operations
- **Leader Election**: One NFT holder becomes write leader
- **Strong Consistency**: All writes through leader, replicated to followers  
- **Automatic Failover**: New leader election when current fails

### API Design
```typescript
GET  /counter        // Current counter value
POST /increment      // Propose increment (requires consensus)  
GET  /log           // View operation log
GET  /status        // Node role (leader/follower) + health
GET  /members       // List active instanceIDs from contract
```

### Node Communication & Leader Integration
- **Discovery**: Query contract for active `instanceToToken` mappings
- **Addressing**: `https://{instanceId}-8080.dstack-{node}.phala.network/`
- **Leader Discovery**: Query `contract.currentLeader()` and `contract.currentLeaderTokenId()`  
- **Authentication**: KMS-signed messages for inter-node communication
- **Consensus**: Only current leader processes writes, followers replicate
- **Heartbeat Integration**: Leader node calls `contract.leaderHeartbeat()` every 4 minutes
- **Failover Detection**: Followers monitor `contract.leadershipExpiry()`, challenge if expired

**Leader Election Flow:**
```python
# In counter.py
async def monitor_leader_health():
    current_leader = await self.contract.call("currentLeader()")
    
    if current_leader == self.wallet_address:
        # I am the leader - respond to requests promptly
        self.is_leader = True
    else:
        # Monitor leader responsiveness
        try:
            response = await self.ping_leader(current_leader, timeout=5.0)
            if not response:
                # Leader unresponsive - vote no confidence
                await self.contract.call("castVote(address,bool)", current_leader, True)
            else:
                # Leader responsive - clear any no-confidence vote
                await self.contract.call("castVote(address,bool)", current_leader, False)
        except Exception:
            # Network issue - vote no confidence
            await self.contract.call("castVote(address,bool)", current_leader, True)
            
async def ping_leader(self, leader_address, timeout=5.0):
    # Direct node-to-node health check
    leader_instance_id = await self.get_instance_by_leader(leader_address)
    leader_url = f"https://{leader_instance_id}-8080.dstack-{self.node_id}.phala.network/status"
    return await self.http_client.get(leader_url, timeout=timeout)
```

### PostgreSQL Pathway
The counter demonstrates core database clustering primitives:
- Replace "counter state" → "SQL transaction processing"
- Replace "increment log" → "Write-Ahead Log (WAL)"
- Replace "simple leader election" → "Patroni consensus"
- Same networking, discovery, and failover patterns apply

## Development Tools & Utilities

### Compose Hash Generation
```python
# Python SDK
from dstack_sdk import get_compose_hash, AppCompose

app_compose = AppCompose(
    runner="docker-compose",
    docker_compose_file=compose_content,
    manifest_version=2,
    kms_enabled=True,
    gateway_enabled=True,
    allowed_envs=["CONTRACT_ADDRESS"]
)

hash_value = get_compose_hash(app_compose, normalize=True)
```

### Contract Development

**Contract Structure:**
```solidity
// DstackMembershipNFT.sol - Complete implementation
contract DstackMembershipNFT is DstackApp, ERC721 {
    // Inherit DstackApp's compose hash validation + ERC721 NFT functionality
    
    function electLeader() external {
        require(ownerOf(walletToTokenId[msg.sender]) == msg.sender, "Must own NFT");
        require(activeInstances[tokenToInstance[walletToTokenId[msg.sender]]], "Instance not active");
        
        if (currentLeader == address(0)) {
            // First leader election
            currentLeader = msg.sender;
            currentLeaderTokenId = walletToTokenId[msg.sender];
            emit LeaderElected(msg.sender, currentLeaderTokenId, tokenToInstance[currentLeaderTokenId]);
        }
    }
    
    function castVote(address target, bool isNoConfidence) external {
        require(ownerOf(walletToTokenId[msg.sender]) == msg.sender, "Must own NFT");
        require(activeInstances[tokenToInstance[walletToTokenId[msg.sender]]], "Instance not active");
        
        // Clear previous vote if exists
        if (currentVotes[msg.sender].voter != address(0)) {
            if (currentVotes[msg.sender].isNoConfidence) {
                noConfidenceCount[target]--;
            }
        }
        
        // Record new vote
        currentVotes[msg.sender] = Vote({
            voter: msg.sender,
            tokenId: walletToTokenId[msg.sender],
            isNoConfidence: isNoConfidence,
            timestamp: block.timestamp
        });
        
        if (isNoConfidence) {
            noConfidenceCount[target]++;
            
            // Check if threshold reached for current leader
            if (noConfidenceCount[target] >= requiredVotes && target == currentLeader) {
                _electNewLeader();
            }
        }
        
        emit VoteCast(msg.sender, target, isNoConfidence);
    }
    
    function _electNewLeader() internal {
        address oldLeader = currentLeader;
        
        // Find new leader: active node with lowest no-confidence votes
        // Tie-breaker: lowest tokenId
        uint256 minVotes = type(uint256).max;
        uint256 minTokenId = type(uint256).max;
        address newLeader = address(0);
        
        for (uint256 i = 1; i <= totalSupply(); i++) {
            address candidate = ownerOf(i);
            bytes32 instanceId = tokenToInstance[i];
            
            if (activeInstances[instanceId] && candidate != oldLeader) {
                uint256 votes = noConfidenceCount[candidate];
                if (votes < minVotes || (votes == minVotes && i < minTokenId)) {
                    minVotes = votes;
                    minTokenId = i;
                    newLeader = candidate;
                }
            }
        }
        
        if (newLeader != address(0)) {
            currentLeader = newLeader;
            currentLeaderTokenId = minTokenId;
            
            // Clear votes for new leader
            noConfidenceCount[newLeader] = 0;
            
            emit LeaderChallenged(newLeader, oldLeader, noConfidenceCount[oldLeader]);
        }
    }
    
    function updateClusterSize() external {
        // Recalculate total active nodes and required votes (f+1)
        uint256 activeCount = 0;
        for (uint256 i = 1; i <= totalSupply(); i++) {
            if (activeInstances[tokenToInstance[i]]) {
                activeCount++;
            }
        }
        totalActiveNodes = activeCount;
        requiredVotes = (activeCount / 2) + 1; // f+1 for 2f+1 nodes
    }
    
    // Override DstackApp's isAppAllowed to add instance validation
    function isAppAllowed(AppBootInfo calldata bootInfo) external view override returns (bool, string memory) {
        // First check compose hash (inherited from DstackApp)
        (bool allowed, string memory reason) = super.isAppAllowed(bootInfo);
        if (!allowed) return (false, reason);
        
        // Then check if instanceId is registered with an NFT
        uint256 tokenId = instanceToToken[bootInfo.instanceId];
        if (tokenId == 0) return (false, "Instance not registered with NFT");
        
        // Verify NFT still exists and is active
        if (_ownerOf(tokenId) == address(0)) return (false, "NFT no longer exists");
        if (!activeInstances[bootInfo.instanceId]) return (false, "Instance marked inactive");
        
        return (true, "");
    }
}
```

**Development Commands:**
```bash
# Deploy contract via KMS (inherits both DstackApp and ERC721)
cast send $KMS_CONTRACT "deployAndRegisterApp(address,bool,bool,bytes32,bytes32)" \
  $DEPLOYER_ADDRESS false true "0x0000000000000000000000000000000000000000000000000000000000000000" $COMPOSE_HASH

# NFT and instance management  
cast send $CONTRACT "mintNodeAccess(address,string)" $USER "node1"
cast send $CONTRACT "registerInstance(bytes32,uint256)" $INSTANCE_ID $TOKEN_ID

# Voting and leader election interactions
cast send $CONTRACT "castVote(address,bool)" $TARGET_LEADER true --from $VOTER_ADDRESS  # Vote no confidence
cast send $CONTRACT "castVote(address,bool)" $TARGET_LEADER false --from $VOTER_ADDRESS # Clear vote
cast send $CONTRACT "electLeader()" --from $CANDIDATE_ADDRESS
cast send $CONTRACT "updateClusterSize()" --from $ANY_ADDRESS

# Query leadership and voting state
cast call $CONTRACT "currentLeader()" 
cast call $CONTRACT "noConfidenceCount(address)" $LEADER_ADDRESS
cast call $CONTRACT "totalActiveNodes()"
cast call $CONTRACT "requiredVotes()"
cast call $CONTRACT "currentVotes(address)" $VOTER_ADDRESS
cast call $CONTRACT "isAppAllowed((address,address,bytes32,bytes32,bytes32,bytes32,bytes32,string,string[]))" "[$APP_ID,$INSTANCE_ID,$COMPOSE_HASH,...]"
```

### Testing Flow
```bash
#!/bin/bash
# Fast Byzantine fault tolerance test (2f+1 = 3 nodes, f+1 = 2 votes needed)

# 1. Deploy & mint 3 NFTs to different owners for realistic voting
cast send $CONTRACT "mintNodeAccess(address,string)" $OWNER1 "node1"
cast send $CONTRACT "mintNodeAccess(address,string)" $OWNER2 "node2"  
cast send $CONTRACT "mintNodeAccess(address,string)" $OWNER3 "node3"

# 2. Launch 3 counter instances
python3 counter.py --instance-id node1 --wallet $OWNER1 --port 8081 &
python3 counter.py --instance-id node2 --wallet $OWNER2 --port 8082 &
python3 counter.py --instance-id node3 --wallet $OWNER3 --port 8083 &

# 3. Register instances and update cluster size
python3 register_instances.py
cast send $CONTRACT "updateClusterSize()"

# 4. Test normal consensus
curl -X POST http://localhost:8081/increment  # Leader increments
curl http://localhost:8082/counter           # Follower shows same value

# 5. Test immediate leader challenge (no 5-minute wait!)
# Simulate unresponsive leader by blocking port 8081
sudo iptables -A INPUT -p tcp --dport 8081 -j DROP

# 6. Nodes 2 & 3 detect unresponsiveness and vote (happens in ~10 seconds)
sleep 15
curl http://localhost:8082/status            # Check if node2 became leader
curl http://localhost:8083/status            # Verify node3 sees new leader

# 7. Test continued operation with new leader
curl -X POST http://localhost:8082/increment # New leader processes writes

# 8. Restore original leader and test vote clearing
sudo iptables -D INPUT -p tcp --dport 8081 -j DROP
sleep 10
curl http://localhost:8081/status            # Original node back online, votes cleared
```

## Key Benefits

### Technical
- **Scarcity enforcement**: Network size limited by NFT supply
- **Transferable membership**: NFT sales transfer node authorization
- **Multiple deployments**: Single owner can run multiple nodes (1:1 ratio)
- **Standard integration**: Uses existing DStack KMS validation flow

### Development  
- **Progressive complexity**: Local → Docker → Production pipeline
- **Real validation testing**: Stage 2 exercises production compose hash logic
- **Clean migration path**: Same contracts work across all environments
- **Educational value**: Demonstrates distributed systems primitives

## Future Extensions

### Immediate (PostgreSQL Clustering)
- Replace counter with PostgreSQL + Patroni
- Use same consensus primitives for database clustering
- Maintain NFT-based cluster membership

### Advanced
- **Multi-cluster support**: Different NFT collections for different database clusters
- **Resource-based NFTs**: Different NFT tiers for different node sizes
- **Governance integration**: NFT holder voting for cluster configuration
- **Cross-chain support**: Multi-blockchain cluster coordination

## Success Metrics

1. **Stage 1**: Local counter with simulated consensus (3+ nodes)
2. **Stage 2**: Docker environment with real compose hash validation  
3. **Stage 3**: Phala Cloud deployment with Base mainnet contracts
4. **Stage 4**: PostgreSQL cluster replacement demonstrating same patterns

This design provides a clear progression from simple local development to production-ready NFT-gated database clusters, with each stage building validation confidence for the next.