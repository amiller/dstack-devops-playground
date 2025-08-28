#!/bin/bash
# Start the distributed counter cluster

# Activate virtual environment
source venv/bin/activate

# Contract address from deployment
CONTRACT_ADDRESS="0x5FbDB2315678afecb367f032d93F642f64180aa3"

# Test wallet private keys
WALLET1_PRIVATE_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
WALLET2_PRIVATE_KEY="0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
WALLET3_PRIVATE_KEY="0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"

echo "🚀 Starting Distributed Counter Cluster"
echo "======================================"
echo "Contract Address: $CONTRACT_ADDRESS"
echo "RPC URL: http://localhost:8545"
echo ""

# Start counter service 1
echo "Starting counter service 1 on port 8081..."
python counter.py \
    --instance-id "node1" \
    --wallet "$WALLET1_PRIVATE_KEY" \
    --contract "$CONTRACT_ADDRESS" \
    --rpc-url "http://localhost:8545" \
    --port 8081 &

COUNTER1_PID=$!
echo "Counter 1 started with PID: $COUNTER1_PID"

# Start counter service 2
echo "Starting counter service 2 on port 8082..."
python counter.py \
    --instance-id "node2" \
    --wallet "$WALLET2_PRIVATE_KEY" \
    --contract "$CONTRACT_ADDRESS" \
    --rpc-url "http://localhost:8545" \
    --port 8082 &

COUNTER2_PID=$!
echo "Counter 2 started with PID: $COUNTER2_PID"

# Start counter service 3
echo "Starting counter service 3 on port 8083..."
python counter.py \
    --instance-id "node3" \
    --wallet "$WALLET3_PRIVATE_KEY" \
    --contract "$CONTRACT_ADDRESS" \
    --rpc-url "http://localhost:8545" \
    --port 8083 &

COUNTER3_PID=$!
echo "Counter 3 started with PID: $COUNTER3_PID"

echo ""
echo "✅ All counter services started!"
echo "Counter 1 (PID: $COUNTER1_PID) - http://localhost:8081"
echo "Counter 2 (PID: $COUNTER2_PID) - http://localhost:8082"
echo "Counter 3 (PID: $COUNTER3_PID) - http://localhost:8083"
echo ""
echo "🔗 Useful endpoints:"
echo "  - Status: /status"
echo "  - Counter: /counter"
echo "  - Increment: POST /increment"
echo "  - Members: /members"
echo "  - Log: /log"
echo ""
echo "Press Ctrl+C to stop all services"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🧹 Shutting down counter services..."
    kill $COUNTER1_PID 2>/dev/null || true
    kill $COUNTER2_PID 2>/dev/null || true
    kill $COUNTER3_PID 2>/dev/null || true
    echo "✅ All services stopped"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for all background processes
wait
