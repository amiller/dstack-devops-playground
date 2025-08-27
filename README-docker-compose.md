# Docker Compose Single Node Setup

This document explains how to use the Docker Compose setup to run individual Python counter nodes, simulating multiple NFT owners deploying separate instances.

## Overview

Instead of running all nodes in a single Docker Compose file, we create **separate Docker Compose instances** for each node. This approach:

- **Simulates real-world deployment**: Each NFT owner deploys their own node independently
- **Tests key manager contract integration**: Each containerized node calls the smart contract
- **Enables independent scaling**: Each node can be started/stopped independently
- **Follows single-file pattern**: Uses the heredoc approach from `README-singlefiledockercompose.md`

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Node 1        │    │   Node 2        │    │   Node 3        │
│   Port 8081     │    │   Port 8082     │    │   Port 8083     │
│   Account 0     │    │   Account 1     │    │   Account 2     │
│   NFT Token 1   │    │   NFT Token 2   │    │   NFT Token 3   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   Local Anvil   │
                    │   Port 8545     │
                    │   Contract:     │
                    │   0x5FbDB...    │
                    └─────────────────┘
```

## Files Created

- `docker-compose-single-node.yaml` - Single node Docker Compose template
- `env.single-node.example` - Environment configuration template
- `deploy-3-nodes.sh` - Script to create 3 node configurations
- `README-docker-compose.md` - This documentation

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose installed
- Anvil running locally: `anvil --host 0.0.0.0 --port 8545`
- Contract deployed (should be at `0x5FbDB2315678afecb367f032d93F642f64180aa3`)

### 2. Deploy 3 Nodes

```bash
# Run the deployment script
./deploy-3-nodes.sh

# This creates:
# - node1/ directory with configuration for Account 0
# - node2/ directory with configuration for Account 1  
# - node3/ directory with configuration for Account 2
```

### 3. Start Individual Nodes

```bash
# Start Node 1 (Account 0)
cd node1
docker compose up -d

# Start Node 2 (Account 1)
cd ../node2
docker compose up -d

# Start Node 3 (Account 2)
cd ../node3
docker compose up -d
```

### 4. Test the Nodes

```bash
# Check status of each node
curl http://localhost:8081/status
curl http://localhost:8082/status
curl http://localhost:8083/status

# Test counter functionality
curl http://localhost:8081/counter
curl -X POST http://localhost:8081/increment
```

## How It Works

### Single Node Docker Compose

The `docker-compose-single-node.yaml` file:

1. **Builds Python container**: Uses Python 3.11-slim with required dependencies
2. **Embeds Python code**: Uses bash heredoc to create `counter.py` at runtime
3. **Configurable via environment**: All settings come from environment variables
4. **Connects to host Anvil**: Uses `host.docker.internal:8545` to reach local blockchain

### Key Manager Contract Integration

Each containerized node:

1. **Connects to blockchain**: Uses Web3.py to interact with local Anvil
2. **Calls smart contract**: Executes functions like `castVote()`, `electLeader()`, etc.
3. **Uses NFT authentication**: Each node has a private key that owns an NFT
4. **Participates in consensus**: Votes for leader election and Byzantine fault tolerance

### Environment Configuration

Each node gets its own `.env` file with:

```bash
INSTANCE_ID=node1          # Unique node identifier
NODE_PORT=8081            # Port this node listens on
WALLET_PRIVATE_KEY=0x...  # Private key of NFT holder
CONTRACT_ADDRESS=0x...     # Smart contract address
RPC_URL=http://host...     # Connection to local Anvil
```

## Testing Key Manager Contract

### 1. Check Node Registration

```bash
# Each node should be able to call the contract
curl http://localhost:8081/members
curl http://localhost:8082/members
curl http://localhost:8083/members
```

### 2. Test Leader Election

```bash
# Check current leader
curl http://localhost:8081/status | jq '.current_leader'

# All nodes should show the same leader
curl http://localhost:8082/status | jq '.current_leader'
curl http://localhost:8083/status | jq '.current_leader'
```

### 3. Test Byzantine Fault Tolerance

```bash
# Simulate leader failure by stopping a node
cd node1
docker compose down

# Wait for failover (should happen in ~10 seconds)
sleep 15

# Check if new leader was elected
curl http://localhost:8082/status | jq '.current_leader'
curl http://localhost:8083/status | jq '.current_leader'
```

## Troubleshooting

### Common Issues

1. **Port conflicts**: Make sure ports 8081, 8082, 8083 are available
2. **Anvil not running**: Check `curl http://localhost:8545` returns response
3. **Contract not deployed**: Verify contract exists at specified address
4. **Permission denied**: Ensure script is executable: `chmod +x deploy-3-nodes.sh`

### Debug Commands

```bash
# Check if containers are running
docker ps | grep counter-node

# View logs for specific node
cd node1
docker compose logs -f

# Check container environment
docker compose exec counter-node env

# Test contract connection from container
docker compose exec counter-node python -c "
import os
print('Contract:', os.environ.get('CONTRACT_ADDRESS'))
print('RPC:', os.environ.get('RPC_URL'))
"
```

## Next Steps

This Docker Compose setup demonstrates:

✅ **Containerized Python nodes** - Each node runs in its own container  
✅ **Smart contract integration** - Nodes call the key manager contract  
✅ **NFT-based authentication** - Each node uses a different NFT holder's wallet  
✅ **Independent deployment** - Each node can be deployed separately  

The next phase would be to:
1. **Integrate with real KMS** - Replace mock validation with actual KMS
2. **Add compose hash validation** - Validate Docker Compose files on-chain
3. **Deploy to Phala Cloud** - Move from local containers to TEE nodes

## Commands Reference

```bash
# Full deployment workflow
./deploy-3-nodes.sh

# Start all nodes
cd node1 && docker compose up -d
cd ../node2 && docker compose up -d  
cd ../node3 && docker compose up -d

# Stop all nodes
cd node1 && docker compose down
cd ../node2 && docker compose down
cd ../node3 && docker compose down

# View all logs
docker compose logs -f counter-node

# Clean up
rm -rf node1 node2 node3
```
