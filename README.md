# Examples repo for devops practice on dstack, including on-chain kms

Dstack is a TEE framework for making decentralized applications out of confidential containers.

Local docker environments is good enough for practice packaging applications as confidential containers.
The web UI and basic commands are already good for launching single-server backends "in the TEE."

But, we need to build tools/experience for working with on-chain contracts and devops for multi-server and p2p backends.
So this repo is a starter pack to close this gap.

## Requirements

See .env.example.

- API for Phala cloud. All the command line tools use an API key, we may also look at playwright.
- a "Base" wallet private key for deploying App contracts. Other evm blockchains included testnets should be supported too. The gas required should be minimal, fraction of a penny per deployment.

```
PRIVATEKEY=0x...
PHALA_CLOUD_API_KEY=phak_...
RPC_URL=https://base.llamarpc.com
```

## Context source repos set up

Git clone relevant source code repos for source practice:
 (make them read only)
- https://github.com/Dstack-TEE/dstack
- https://github.com/Phala-Network/phala-cloud-cli
- https://github.com/Phala-Network/phala-cloud-sdks
- https://github.com/Dstack-TEE/dstack-examples

The point is to familiarize you and your coding agents with how to use the phala cloud api for launching CVMs.
I have checked in some notes already, but you're encouraged to send subagents to study the code again.
- sdknotes.md
- cli-notes.md

It seems like a good idea to mark these read only so your agent doesn't start editing in there.
I would set up git submodules but I never remember how, from setup to cloning to updating.

## Suggested practice tasks

### List the cvms

Use both the command line tools and example scripts to list the available cvms and nodes. One-shot a javascript that selects a configuration with support for on-chain kms and a chain of your choice.

### Launching sample applications
Make a fresh copy of the phala-cloud-sdks/examples as myexamples.
Compare deploy.ts there with the implementation of "deploy" command in the CLI.

For example, this command launches with on-chain KMS enabled, replicate it with ts.
```
phala deploy --node-id 12 --kms-id kms-base-prod7 docker-compose.yml --rpc-url $RPC_URL --private-key $PRIVATEKEY
```

One-shot a modified application in the docker-compose

### Make a cleanup tool
Make sure to set the "name" of repos launched during this session.
Then you can make a cleanup tool to delete all these CVMs when you're done.

Note: delete api not understanding so well from the sdk. Delete by CVM vs delete by App

### Accessing CVM logs and info

Each running CVM exposes an info service on port 8090. You can access:

- **Node info**: `https://{app-id}-8090.dstack-{node}.phala.network/`
- **Service logs**: `https://{app-id}-8090.dstack-{node}.phala.network/logs/{service}?text&bare&timestamps&tail=20`

To find the correct URLs:
1. Get App ID from `phala cvms list` 
2. Identify node from the "Node Info URL" (e.g., `dstack-prod10` for prod10 node)
3. Visit the root URL to see actual service names in the container table
4. Use those service names (like `tapp-workload-1`) in the logs URL

Example:
```bash
# Get CVM info page  
curl https://ae8c818575426ef2a3f6f184296022c9db4f44c8-8090.dstack-prod10.phala.network/

# Get logs for a specific service
curl "https://ae8c818575426ef2a3f6f184296022c9db4f44c8-8090.dstack-prod10.phala.network/logs/tapp-workload-1?text&bare&timestamps&tail=20"
```

### Play with the SSH tool and gateway.

Read the docs on how the dstack-gateway does subdomain-based routing of TLS/HTTP to different ports within a docker compose payload.

The dstack-examples repo contains a ssh-over-gateway docker compose, with a readme showing how to configure SSH to connect over this tls/http channel.

Add the ssh forwarding service to the existing docker-compose.

Figure out the SSH one-line equivalent to the suggested .ssh/config settings.

Launch a dstack CVM and ssh into it.

Note: The "dev" instances have sshd running on the host vm. Can we modify the ssh-over-gateway example to provide ssh from the container instead?

### NFT-based access control

See nft-auth-nodes.md 

## Still todo

This hasn't incorporated the dstack simulator yet, this should be a path to develop on-chain KMS.

Nerla's code uses kurtosis and should be studied
https://github.com/njeans/dstack/tree/update-demo

Self hosting instructions. If you have a tdx machine you should be able to run dstack fully, though the phala cloud api itself.

It also hasn't incorporated test blockchain networks.