# Enterprise Platform User Policy & Terms of Service
**Document Version:** 3.2-Enterprise  
**Effective Date:** January 1, 2026  
**Document ID:** POL-CORP-2026-004  

---

## Section 1: Acceptable Use & Account Security

### 1.1 Account Credentials & Authentication
All authorized users must maintain strict confidentiality of their account credentials, API tokens, and access keys. Sharing account credentials across multiple individuals is strictly prohibited. Every user accessing enterprise endpoints must authenticate using Multi-Factor Authentication (MFA) with time-based one-time passwords (TOTP) or FIDO2 hardware security keys.

### 1.2 Prohibited Activities
Users are expressly prohibited from:
* Using automated scrapers, crawlers, or high-concurrency botnets against platform APIs without prior rate-limit authorization.
* Reverse-engineering, decompiling, or attempting to extract proprietary model weights or system prompts.
* Submitting prompts or data designed to bypass safety filters (jailbreaking), extract PII, or generate malicious code.
* Reselling, sublicensing, or providing unauthorized multi-tenant access to enterprise endpoints.

---

## Section 2: Billing, Subscription & Refund Rules

### 2.1 Billing Cycles & Invoicing
Subscriptions are billed in advance on a recurring monthly or annual schedule based on the contract date. Enterprise tier invoices are issued with Net-30 payment terms from the date of invoice generation.

### 2.2 Strict 30-Day Refund Policy
* **Standard 30-Day Window:** Customers may request a full refund within exactly thirty (30) calendar days from the initial purchase date if the platform does not meet the technical specifications outlined in the service contract.
* **Ineligibility After 30 Days:** Refund requests submitted more than thirty (30) calendar days after the initial transaction date are strictly non-refundable under all circumstances.
* **Usage Caps on Refunds:** Refunds will not be granted if the account has consumed more than 1,000,000 model tokens or generated more than 10,000 API requests during the initial 30-day period.

### 2.3 Cancellations & Proration
Customers may cancel their subscription at any time via the billing portal. Cancellations take effect at the conclusion of the current active billing cycle. Unused portions of pre-paid annual commitments will be prorated on a monthly basis, subject to a 10% administrative termination fee.

---

## Section 3: Data Privacy, Retention & GDPR Compliance

### 3.1 Data Encryption at Rest and in Transit
All customer data, execution traces, prompt inputs, and model outputs are encrypted in transit using TLS 1.3 with forward secrecy. At rest, all persistent storage volumes, analytical databases, and audit logs are encrypted using AES-256-GCM authenticated encryption.

### 3.2 Right to Erasure (GDPR Deletion Requests)
In accordance with GDPR Article 17, customers hold the legal right to request the complete erasure of their personal and organizational data:
* **Deletion Turnaround:** Data deletion requests submitted via `privacy@agentlens.local` or through the Project Settings API will be executed within thirty (30) calendar days of verification.
* **Audit Log Exemption:** Aggregated telemetry metadata stripped of PII may be retained in cold storage for compliance purposes for up to twelve (12) months.

### 3.3 Customer Data Isolation
Enterprise customer data is logically partitioned by unique `project_id` boundaries. Cross-tenant access is strictly blocked at the database engine and API gateway levels. Customer prompts and completions are never utilized to train foundational models.

---

## Section 4: AI Model Usage & Content Moderation

### 4.1 Rate Limits & Concurrency Tiers
* **Standard Tier:** 120 requests per minute (RPM), with a concurrency burst allowance of 20 concurrent threads.
* **Enterprise Tier:** 1,200 requests per minute (RPM), with a concurrency burst allowance of 100 concurrent threads.
* Exceeding allocated rate limits results in standard HTTP 429 (Too Many Requests) responses with a `Retry-After` header.

### 4.2 Content Safety Guidelines
The platform automatically scans input prompts and output responses for prohibited content:
* Content promoting self-harm, cyberattacks, chemical weapons, or hate speech will be blocked at the ingestion layer.
* Accounts repeatedly violating content safety triggers (more than 5 flag violations in 24 hours) will be placed in administrative review.

---

## Section 5: Service Level Agreements (SLAs) & Performance Guarantees

### 5.1 System Uptime Guarantee
The platform guarantees an overall uptime of 99.9% during each calendar month. Uptime excludes scheduled maintenance windows announced at least 48 hours in advance.

### 5.2 Latency Thresholds & Service Credits
* **P95 Latency SLA:** The 95th percentile (P95) latency for trace ingestion API endpoints must remain under 1,200 milliseconds.
* **Service Credits:** If monthly uptime falls below 99.9% or P95 latency exceeds 1,200ms for more than 4 consecutive hours:
  * 99.0% – 99.8% Uptime: 10% monthly service credit.
  * 95.0% – 98.9% Uptime: 25% monthly service credit.
  * Below 95.0% Uptime: 50% monthly service credit.

---

## Section 6: Termination & Legal Governing Law

### 6.1 Termination for Cause
The platform reserves the right to immediately suspend or terminate any account without prior notice if:
* The user violates the Acceptable Use Policy in Section 1.2.
* Account invoices remain overdue for more than forty-five (45) days.
* Security vulnerabilities or malicious payloads are actively transmitted through platform credentials.

### 6.2 Governing Law & Dispute Jurisdiction
These Terms and Policies are governed by and construed under the laws of the State of Delaware, United States, without regard to its conflict of law principles. Any legal dispute or claim arising under this agreement shall be settled through binding arbitration administered by JAMS in Wilmington, Delaware.
