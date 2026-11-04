# 🌙 NightShift Bot // Autonomous Recharge Agent

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Bitrefill Track](https://img.shields.io/badge/Bitrefill-Agentic%20Commerce-orange.svg)](https://www.bitrefill.com)
[![Zcash Track](https://img.shields.io/badge/Zcash-Orchard%20Settlement-yellow.svg)](https://z.cash)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **"While you were asleep..."** — An autonomous AI agent designed to guarantee your household telecom never disconnects. NightShift monitors carrier validity in the background, enforces strict user-defined budget guardrails, triggers Bitrefill recharges, and settles anonymously using 512-byte **Zcash Orchard Shielded Memos**.

---

## ⚡ The Problem & The Solution

* **The Problem:** Telecom validity typically expires at midnight. Missing a recharge disconnects critical two-factor authentication (2FA), banking OTPs, and emergency home connectivity before you even wake up.
* **The Solution:** NightShift functions as a tireless autonomous agent running on your behalf. When plan expiry drops below 24 hours, the agent verifies spending caps, checks telecom intelligence, purchases the required carrier plan via Bitrefill, and logs private zero-knowledge cryptographic receipts on the Zcash shielded network.

---

## 🏛️ System Architecture

```
                 +---------------------------------------------+
                 |            Telegram User Interface          |
                 |     /start  /add  /list  /credits  /audit   |
                 +----------------------+----------------------+
                                        |
                                        v
                 +---------------------------------------------+
                 |             NightShift Agent Core           |
                 |      • In-Memory Mandate State Engine       |
                 |      • Budget Guardrails ($5.00 Safety Cap) |
                 |      • 60-Second Autonomous Heartbeat       |
                 +----------+--------------------+-------------+
                            |                    |
         +------------------+                    +------------------+
         |                                                          |
         v                                                          v
+-----------------------------+                           +-----------------------------+
|    Way2API Intelligence     |                           |  Bitrefill Commerce Engine  |
|  • Real-time carrier check  |                           |  • REST API v2              |
|  • Validity & expiry parsing|                           |  • Sandbox fallback         |
|  • Fallback simulation      |                           +--------------+--------------+
+-----------------------------+                                          |
                                                                         v
                                                          +-----------------------------+
                                                          |  Zcash Shielded Settlement  |
                                                          |  • Orchard Shielded Pool    |
                                                          |  • 512-Byte Encrypted Memo  |
                                                          |  • Incoming Viewing Key(IVK)|
                                                          +-----------------------------+
```

---

## 🚀 Key Features

1. **Telecom Intelligence (Way2API):**
   - Automatically inspects phone carrier, circle, previous recharge amount, and validity date.
   - Built-in graceful fallback logic ensures testing is never interrupted by external API downtime.

2. **Autonomous Commerce Engine (Bitrefill REST API v2):**
   - Discovers appropriate telecom operator SKUs.
   - Safely provisions orders via sandbox products (`delos-syldavia`) or live products.

3. **Private Settlement via Zcash Orchard Pool:**
   - Packages order metadata, masked recipient info, and settlement verification into a **512-byte shielded memo**.
   - Generates verifiable 64-character shielded transaction hashes (`zx...`).
   - Supports `/audit` with Incoming Viewing Keys (IVK) for cryptographic verification without exposing user balance or identity.

4. **Safety Guardrails & Testing Caps:**
   - **$5.00 USD Hard Spending Limit:** Prevents accidental credit drain during test runs.
   - **Per-Device Spending Caps:** User sets maximum budget per line (e.g. `/add +919876543210 $5`).

5. **Autonomous Background Heartbeat:**
   - Non-blocking asynchronous scheduler checks all mandates every 60 seconds.
   - Fires proactive alerts: *"🌙 While you were asleep... Autonomous Recharge Executed"*.

---

## 🕹️ Command Reference

| Command | Description | Example |
| :--- | :--- | :--- |
| `/start` | Displays cyberpunk briefing and autonomous protocol rules | `/start` |
| `/add <phone> <cap>` | Enrolls a number, fetches telecom intel, and sets budget cap | `/add +919876543210 $5` |
| `/list` | Shows all enrolled numbers, carrier, expiry, and statuses | `/list` |
| `/credits` | Inspects remaining testing credit allowance ($5.00 pool) | `/credits` |
| `/simulate` | Immediately triggers the autonomous purchase loop | `/simulate` |
| `/audit` | Inspects Zcash Orchard IVK cryptographic settlement proof | `/audit` |

---

## 🛠️ Quickstart Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Arya8569/NightShiftAgent.git
cd NightShiftAgent
```

### 2. Set Up Environment & Dependencies
```bash
# Recommended: Create a virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Configure API Keys
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Populate your credentials in `.env`:
```env
TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
BITREFILL_API_KEY="your_bitrefill_key"
WAY2API_KEY="your_way2api_key"
```

### 4. Run the Bot
```bash
python bot.py
```

---

## 🔒 Privacy & Cryptographic Verification

NightShift prioritizes personal financial sovereignty and privacy. By integrating with the **Zcash Orchard Shielded Pool**:
- **Zero-Knowledge Proofs:** Transaction details remain confidential on-chain.
- **512-Byte Shielded Memos:** Store tamper-proof purchase receipts directly within encrypted payload outputs.
- **Incoming Viewing Keys (IVK):** Allow selective disclosure and auditing without compromising spending authority or wallet balances.

---

## 📜 License
Distributed under the MIT License. See [LICENSE](LICENSE) for more information.
