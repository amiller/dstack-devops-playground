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

### NFT-based access control

See nft-auth-nodes.md 

## Still todo

This hasn't incorporated the dstack simulator yet, this should be a path to develop on-chain KMS.

Nerla's code uses kurtosis and should be studied
https://github.com/njeans/dstack/tree/update-demo

Self hosting instructions. If you have a tdx machine you should be able to run dstack fully, though the phala cloud api itself.

It also hasn't incorporated test blockchain networks.