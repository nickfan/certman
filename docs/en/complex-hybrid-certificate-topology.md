# Complex Hybrid Certificate Governance (CertMan Implementation)

This document describes a realistic multi-cloud and hybrid-network background, then maps it to an implementable CertMan architecture and operational workflow.

## 1. Scenario and Pain Points

Target endpoints include:

- Aliyun CDN
- Aliyun ALB + WAF
- Self-managed Kubernetes on ECS
- AWS ACM
- Nginx on EC2
- Third-party global accelerator provider
- OpenResty on office LAN server
- Local React frontend debugging on mobile office laptop

### 1.1 Shared Requirements

- Every endpoint must use HTTPS certificates
- Certificates must be renewed regularly
- DNS-01 verification is usually centralized at DNS providers (Route53/Aliyun/Cloudflare)
- Issuance is only one step; delivery, reload, rollback, and validation are the hard part

### 1.2 Core Problems

- Single-node tools like certbot/acme.sh solve local issuance, not global orchestration
- Multi-cloud + on-prem + local environments need a unified certificate control plane
- Renewal windows, retries, asset tracking, secret safety, and auditing are easy to fragment

### 1.3 Network Topology (Background Only)

```mermaid
graph TB
    internet[(Internet)]

    subgraph aliyun[Aliyun Cloud and VPC]
        waf[WAF Public Entry]
        alb[ALB Public Entry]
        cdn[CDN Edge Service]
        ecsk8s[ECS Hosted K8s NodePool]
    end

    subgraph aws[AWS Cloud and VPC]
        acm[AWS ACM]
        ec2nginx[EC2 Nginx]
        route53[Route53]
    end

    subgraph office[Office LAN and IDC]
        openresty[PC Server OpenResty]
        officepc[Office PC and Internal Services]
    end

    subgraph mobile[Mobile Office]
        laptop[Developer Laptop React]
        devtools[Local Dev Tools and Browser]
    end

    internet --> waf
    internet --> alb
    internet --> cdn
    internet --> route53
    route53 --> ec2nginx
    internet --> acm
    internet --> ecsk8s
    officepc --> openresty
    laptop --> devtools
```

## 2. CertMan Positioning

CertMan acts as a cross-environment certificate control plane:

- Unified integration with ACME CAs (Let's Encrypt / ZeroSSL)
- Unified DNS-01 execution through Route53 / Aliyun / Cloudflare
- Unified job lifecycle (issue, renew, status tracking)
- Unified delivery to cloud, k8s, on-prem, and local targets
- Unified API, CLI, and MCP access for platform and AI integration

## 3. Implementable Target Architecture (with Agent proxy capability)

```mermaid
graph TB
    subgraph ingress[Ingress and External]
        webhook[Webhook Endpoint]
        dns[DNS Providers]
        ca[ACME CAs]
    end

    subgraph control[CertMan Control Plane]
        scheduler[Scheduler]
        api[API Server]
        bus[Event and Job Bus]
        worker[Worker]
        hooks[Hook Runner]
        db[(DB)]
    end

    subgraph edge[Agent Plane]
        localScheduler[Isolated Scheduler]
        agent[Edge Agent]
        cache[Encrypted Bundle Cache]
        proxy[Proxy Deployer]
    end

    subgraph cloudTargets[Cloud Targets]
        cdn[Aliyun CDN]
        alb[Aliyun ALB + WAF]
        acm[AWS ACM]
        ga[Third Party GA]
    end

    subgraph localTargets[Private and Local Targets]
        k8s[ECS Hosted K8s]
        nginx[EC2 Nginx]
        openresty[Office OpenResty]
        react[Developer React Local]
    end

    cloudDelivery[Cloud Delivery Adapter]
    localDelivery[Local Delivery Adapter]

    webhook --> api
    scheduler --> bus
    api --> bus
    bus --> worker
    worker --> db
    worker --> hooks

    worker --> dns
    worker --> ca

    localScheduler --> agent
    agent --> api
    agent --> cache
    cache --> proxy

    hooks --> cloudDelivery
    cloudDelivery --> cdn
    cloudDelivery --> alb
    cloudDelivery --> acm
    cloudDelivery --> ga

    proxy --> localDelivery
    localDelivery --> k8s
    localDelivery --> nginx
    localDelivery --> openresty
    localDelivery --> react
```

### 3.1 Agent Mode Design Points

1. Scheduler is decoupled and can run on server side or agent-side isolated networks.
2. No inbound public port is required for private networks; agent can work with outbound pull.
3. Dual channels:

- Control channel: authenticated API for polling assignments and metadata.
- Data channel: short-lived signed URL for encrypted bundle fetch.

1. Bundle encryption: envelope encryption on server and local decrypt on agent.
2. Trigger mode:

- Webhook push only when agent has a public reachable HTTPS endpoint.
- Otherwise use pull polling or scheduler-driven pull.

1. Local triggers: agent can load conf-based internal webhook triggers in its local network.
2. Delivery feedback: callback by webhook or poll-based acknowledgment.
3. Minimized exposure: short TTL URL, one-time token, nonce replay protection.

## 4. End-to-End Process

### 4.1 Initial Issuance Flow

```mermaid
flowchart TB
    S1[Step1 Submit certificate job] --> S2[Step2 Select DNS provider and CA]
    S2 --> S3[Step3 Generate DNS01 challenge record]
    S3 --> S4[Step4 Write TXT via provider API]
    S4 --> S5[Step5 CA validates challenge]
    S5 --> S6{Step6 Validation result}
    S6 -->|Pass| S7[Step7 Fetch cert and private key]
    S6 -->|Fail| S8[Step8 Retry or alert]
    S7 --> S9[Step9 Persist and audit]
    S9 --> S10[Step10 Deliver to targets]
    S10 --> S11[Step11 Post-deploy health check]
```

### 4.2 Renewal and Rotation Flow

```mermaid
flowchart TB
    R1[Step1 Scheduler scans expiring certs] --> R2[Step2 Create renewal jobs]
    R2 --> R3[Step3 Worker runs DNS01 renewal]
    R3 --> R4{Step4 Renewal result}
    R4 -->|Success| R5[Step5 Trigger delivery pipeline]
    R4 -->|Failure| R6[Step6 Mark failed and alert]
    R5 --> R7[Step7 Multi-target deployment and reload]
    R7 --> R8[Step8 Cert and chain validation]
    R8 --> R9[Step9 Update inventory and reports]
```

## 5. Sequence Diagrams

### 5.1 DNS-01 Issuance Sequence

```mermaid
sequenceDiagram
    participant U as UserOrPlatform
    participant C as CertManAPI
    participant W as CertManWorker
    participant D as DNSProvider
    participant A as ACMECA
    participant T as TargetEndpoint

    U->>C: CreateCertificateJob domains
    C->>W: EnqueueJob
    W->>A: CreateOrder
    A-->>W: ChallengeTXT
    W->>D: UpsertTXTRecord
    W->>A: NotifyReady
    A-->>W: ChallengeValid
    W->>A: FinalizeOrderAndDownload
    A-->>W: FullchainAndPrivateKey
    W->>C: PersistBundleAndStatus
    W->>T: DeliverCertificateByHook
    T-->>W: DeployOK
    W->>C: JobSucceeded
```

### 5.2 Private Network Delivery Sequence (Agent)

```mermaid
sequenceDiagram
    participant S as IsolatedScheduler
    participant A as EdgeAgent
    participant G as PublicAPIGateway
    participant C as CertManServer
    participant W as CertManWorker
    participant B as BundleStore
    participant P as LocalProxyDeployer
    participant T as TargetService

    S->>A: TriggerRenewWindow
    A->>G: PullJobsWithMutualAuth
    G->>C: ForwardAuthenticatedRequest
    C->>W: PrepareRenewAndBundle
    W->>B: StoreEncryptedBundleShortTTL
    C-->>A: JobMeta and SignedBundleURL
    A->>B: PullBundleBySignedURL
    A->>P: DecryptAndStageFiles
    P->>T: InstallAndReload
    T-->>P: HealthOK and Fingerprint
    A->>G: WebhookCallbackSigned
    G->>C: UpdateJobStateSuccess
```

## 6. Current CertMan Capability Mapping

Available now:

- One-shot scheduler: certman-scheduler once
- Loop scheduler: certman-scheduler run --loop
- Agent one-shot and loop: certman-agent --once / certman-agent --loop
- One-shot local cert flow: certman oneshot-issue / oneshot-renew
- Unified API + CLI + MCP surface
- DNS providers: Route53 / Aliyun / Cloudflare

Implemented Agent-Server handshake and execution chain:

1. POST /api/v1/nodes/register
2. POST /api/v1/node-agent/poll
3. GET /api/v1/node-agent/bundles/{job_id}
4. POST /api/v1/node-agent/result

## 7. Phased Implementation Plan

### Phase A: Domain and policy modeling

1. Inventory all domains and certificate boundaries.
2. Map authoritative DNS validation paths by domain group.
3. Define renewal window, retries, and alerting policy.

### Phase B: Control plane rollout

1. Deploy API, worker, scheduler.
2. Store provider credentials securely.
3. Validate issuance/renewal with test domains first.

### Phase C: Endpoint adaptation and delivery

1. Cloud services through hook adapters.
2. Host services through file deploy and reload commands.
3. K8s through secret update and rolling reload.
4. Local React debug with one-shot output.
5. Private segments through agent pull and local deployment.

## 8. Quick Start

### 8.1 Local one-shot

```bash
certman oneshot-issue \
  -d dev.example.com \
  -sp route53 \
  --ak "$AWS_ACCESS_KEY_ID" \
  --sk "$AWS_SECRET_ACCESS_KEY" \
  -o ./data/output/dev
```

### 8.2 Platform-triggered one-shot scan

```bash
certman-scheduler once
```

### 8.3 Continuous renewal loop

```bash
certman-scheduler run --loop
```

## 9. Security and Governance Notes

- Least-privilege DNS credentials
- Minimal key exposure on disk
- TLS + signature verification for delivery paths
- Nonce replay protection and auditing
- Low-traffic rotation windows and rollback strategy

## 10. Target Mapping Table

| Target Type | Recommended Delivery | Activation | Validation |
| --- | --- | --- | --- |
| Aliyun CDN | Cloud API hook | Publish cert via API | TLS handshake and chain check |
| ALB/WAF | Cloud API hook | Bind or swap cert | Entry TLS check |
| ECS K8s | Secret/volume delivery | Reload or rolling update | Ingress cert verification |
| AWS ACM | AWS API hook | Attach listener cert | ALB/NLB cert check |
| EC2 Nginx | Agent file deploy + command | nginx reload | openssl s_client |
| Third-party GA | Provider API hook | Publish in platform | Edge domain TLS check |
| Office OpenResty | Agent file deploy + command | openresty reload | Internal TLS check |
| Local React debug | one-shot local output | restart dev server | Browser chain check |

## 11. Implemented Status and Next Steps

Implemented:

1. Agent loop mode is now available.
2. Agent execution chain is complete: poll -> bundle -> execute -> result.
3. Bundle endpoint is implemented with signature and nonce replay protection.
4. NodeExecutor supports local file delivery and hooks.

Next steps:

1. Add explicit subscribe and heartbeat APIs for push-plus-pull hybrid mode.
2. Add delivery target type and network-scope fields to job model.
3. Add short-lived bundle token and finer-grained permissions.
4. Add scheduler target-scope scanning.
5. Add more adapters for nginx/openresty/k8s ingress specifics.

## 12. Conclusion

In this hybrid topology, the hard problem is not issuing a single certificate, but turning certificate lifecycle into a schedulable, observable, and auditable system capability.

CertMan provides that path through unified validation entry, unified orchestration, and unified delivery adapters.
