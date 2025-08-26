This note describes a script for automated deployment and persistent SSH access to avoid common pitfalls.
It is based on studying the example in dstack-examples/ssh-over-gateway.

### Quick Start

1. **Deploy the CVM**:
   ```bash
   phala deploy --image dstack-dev-0.3.6 docker-compose.yaml --name ssh-playground
   ```
   - Must use `--image dstack-dev-0.3.6` or similar dev image for SSH access
   - Don't specify `--node-id` to let Phala auto-select a node
   - Copy the example to a writable directory first (read-only repos cause permission errors)

2. **Find the Gateway Domain**:
   ```bash
   phala cvms list
   ```
   Look for your CVM and note the "Node Info URL" to determine the gateway domain (e.g., `dstack-prod10.phala.network`)

3. **Set Up Persistent SSH Connection**:
   Use the provided scripts for efficient SSH access:
   
   ```bash
   # Start persistent SSH master connection (runs in background)
   ./ssh_master.sh
   
   # Execute commands via the persistent connection (no re-authentication)
   ./ssh_cmd.sh 'whoami; ps aux'
   ./ssh_cmd.sh 'cat /var/log/dpkg.log | tail -10'
   ```

### Script Details

- **ssh_master.sh**: Establishes persistent SSH master connection using SSH ControlMaster
  - Uses `expect` to handle password authentication automatically  
  - Maintains connection for 30 minutes with ControlPersist
  - Password is hardcoded as `123456` (from ROOT_PW in docker-compose)

- **ssh_cmd.sh**: Executes commands via the existing master connection
  - No re-authentication needed
  - Fast execution since connection is reused
  - Perfect for log examination and system monitoring

### Common Pitfalls Avoided

1. **Permission Errors**: Copy examples to writable directory before deployment
3. **Gateway Domain**: Always check `phala cvms list` for the correct gateway domain
4. **SSH Key Conflicts**: Scripts use `StrictHostKeyChecking=no` to avoid host key issues
5. **Re-authentication**: Master connection eliminates repeated password prompts
6. **Connection Overhead**: Persistent connection dramatically reduces latency for multiple commands

### Manual SSH Command (for reference)

If you need to connect manually without the scripts:
```bash
ssh -o "ProxyCommand=openssl s_client -quiet -connect <APP-ID>-1022.<GATEWAY-DOMAIN>:443" -o StrictHostKeyChecking=no root@<APP-ID>-1022.<GATEWAY-DOMAIN>
```

Default password: `123456`