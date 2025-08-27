# NFT-Gated DStack Node Cluster

A Byzantine fault-tolerant distributed system that uses NFT-based membership to control node deployment authorization in DStack clusters.

## 🎯 Overview

This project transforms DStack's unlimited deployment model into a scarcity-based network where **1 NFT = 1 authorized node deployment**. It implements:

- **NFT-based membership**: ERC721 tokens control node authorization
- **Byzantine fault tolerance**: 2f+1 nodes with f+1 vote threshold for leader challenges
- **Automatic leader election**: Democratic process with immediate failover
- **Distributed consensus**: Leader handles writes, followers replicate state

## 🏗️ Architecture

### Core Components

1. **DstackMembershipNFT Contract**: Combines DstackApp validation with ERC721 functionality
2. **Distributed Counter Service**: Demo application showing consensus primitives
3. **Byzantine Fault Tolerant Leader Election**: No timeout required, immediate challenges
4. **Local Development Environment**: Anvil + Python for fast iteration

### Byzantine Fault Tolerance

- **Cluster Size**: Requires 2f+1 nodes where f is maximum failures
- **Challenge Threshold**: f+1 votes needed to challenge current leader
- **Immediate Challenges**: No timeout required - nodes vote when they detect unresponsiveness
- **Democratic Process**: Any active node can vote no-confidence against current leader
- **Automatic Failover**: Leader change triggered when f+1 votes accumulated

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Anvil (local blockchain)
- Web3.py and dependencies

### 1. Clone and Setup

```bash
git clone <repository-url>
cd dstack-nft-cluster
pip install -r requirements.txt
```

### 2. Start Local Environment

```bash
# Option A: Full automated setup
./deploy_local.sh

# Option B: Manual setup
anvil --host 0.0.0.0 --port 8545 &
python3 deploy_contract.py
./start_counters.sh
```

### 3. Test the Cluster

```bash
./test_cluster.sh
```

## 📁 Project Structure

```
dstack-nft-cluster/
├── contracts/                 # Smart contract source
│   ├── src/
│   │   └── DstackMembershipNFT.sol
│   └── test/
│       └── DstackMembershipNFT.t.sol
├── counter.py                 # Distributed counter service
├── deploy_contract.py         # Contract deployment script
├── deploy_local.sh            # Full environment setup
├── start_counters.sh          # Start counter services
├── test_cluster.sh            # Test cluster functionality
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## 🔧 Development

### Smart Contract Development

The `DstackMembershipNFT` contract combines:
- **DstackApp interface**: For KMS validation
- **ERC721 functionality**: NFT-based membership
- **Leader election logic**: Byzantine fault tolerant consensus

```solidity
contract DstackMembershipNFT is DstackApp, ERC721 {
    // Instance management
    mapping(uint256 => bytes32) public tokenToInstance;
    mapping(bytes32 => uint256) public instanceToToken;
    
    // Byzantine fault tolerant leader election
    address public currentLeader;
    mapping(address => uint256) public noConfidenceCount;
    uint256 public requiredVotes;
    
    function castVote(address target, bool isNoConfidence) external;
    function electLeader() external;
    function isAppAllowed(AppBootInfo calldata bootInfo) external view override;
}
```

### Counter Service

The distributed counter demonstrates:
- **HTTP API**: REST endpoints for operations
- **Leader election**: One NFT holder becomes write leader
- **Strong consistency**: All writes through leader, replicated to followers
- **Automatic failover**: New leader election when current fails

```python
class DistributedCounter:
    async def monitor_leader_health(self):
        """Monitor leader health and participate in consensus"""
        current_leader = await self.contract.call("currentLeader()")
        
        if current_leader == self.wallet_address:
            self.is_leader = True
        else:
            # Check if leader is responsive
            is_responsive = await self.ping_leader(current_leader)
            if not is_responsive:
                await self.vote_no_confidence(current_leader)
```

## 🧪 Testing

### Local Testing

```bash
# Start 3-node cluster
./start_counters.sh

# Test consensus
curl -X POST http://localhost:8081/increment
curl http://localhost:8082/counter
curl http://localhost:8083/counter

# Check cluster status
curl http://localhost:8081/status
```

### Byzantine Fault Tolerance Test

```bash
# Simulate leader failure
sudo iptables -A INPUT -p tcp --dport 8081 -j DROP

# Wait for failover (should happen in ~10 seconds)
sleep 15

# Check new leader
curl http://localhost:8082/status
```

## 🔄 Development Phases

### Phase 1: Local Development ✅
- [x] Smart contract with Forge
- [x] Anvil local blockchain
- [x] Python counter application
- [x] Basic consensus testing

### Phase 2: Docker Integration (Next)
- [ ] Anvil in container
- [ ] Real KMS validation
- [ ] Compose hash validation
- [ ] Full deployment pipeline

### Phase 3: Phala Cloud Production
- [ ] Base mainnet deployment
- [ ] Phala-hosted KMS
- [ ] Real TEE nodes
- [ ] Production scaling

## 🎓 Learning Outcomes

This project demonstrates key distributed systems concepts:

1. **Consensus Algorithms**: Byzantine fault tolerance in practice
2. **Leader Election**: Democratic process with automatic failover
3. **State Replication**: Leader handles writes, followers replicate
4. **Failure Detection**: Health monitoring and voting mechanisms
5. **Smart Contract Integration**: Blockchain-based membership control

## 🔮 Future Extensions

- **PostgreSQL Clustering**: Replace counter with real database
- **Multi-cluster Support**: Different NFT collections for different clusters
- **Resource-based NFTs**: Different tiers for different node sizes
- **Governance Integration**: NFT holder voting for cluster configuration
- **Cross-chain Support**: Multi-blockchain cluster coordination

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **DStack**: For the underlying infrastructure
- **OpenZeppelin**: For secure smart contract libraries
- **Foundry**: For smart contract development tools
- **Phala Network**: For TEE infrastructure

---

**Ready to build the future of decentralized infrastructure?** 🚀

Start with `./deploy_local.sh` and experience Byzantine fault tolerance in action!
