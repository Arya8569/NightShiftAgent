# 🌙 NightShift Bot // Autonomous Multi-Beneficiary Telecom Agent

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Bitrefill Track](https://img.shields.io/badge/Bitrefill-Agentic%20Commerce-orange.svg)](https://www.bitrefill.com)
[![Zcash Track](https://img.shields.io/badge/Zcash-Orchard%20Vault%20Settlement-yellow.svg)](https://z.cash)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **"While you were asleep..."** — An autonomous AI agent daemon built to ensure your entire household (family, friends, roommates) never disconnects. NightShift reconciles legacy tariffs via Way2API, monitors carrier validity, enforces per-beneficiary spending caps, and settles autonomous Bitrefill orders privately by debiting a user-funded **Zcash Shielded Allowance Vault**.

---

## ⚡ Key Highlights & Architecture

```
                 +---------------------------------------------------------+
                 |                 Telegram User Interface                 |
                 |      /add Dad 9876543210 350   •   /vault   •  /audit   |
                 +----------------------------+----------------------------+
                                              |
                                              v
                 +---------------------------------------------------------+
                 |                  NightShift Agent Core                  |
                 |      • Multi-Beneficiary Registry (Family / Roommates)  |
                 |      • Zcash Shielded Allowance Vault (`0.35 ZEC`)      |
                 |      • Legacy Tariff Reconciliation Engine              |
                 |      • 60-Second Autonomous Heartbeat Scheduler         |
                 +---------------+-------------------------+---------------+
                                 |                         |
            +--------------------+                         +--------------------+
            |                                                                   |
            v                                                                   v
+-----------------------------+                                    +-----------------------------+
|    Way2API Intelligence     |                                    |  Bitrefill Commerce Engine  |
|  • Carrier & Circle Lookup  |                                    |  • REST API v2              |
|  • Historical Pack Lookup   |                                    |  • Sandbox fallback         |
|  • Retired Tariff Detection |                                    +--------------+--------------+
|  • Active Circle Matching   |                                                   |
+-----------------------------+                                                   v
                                                                   +-----------------------------+
                                                                   |  Zcash Shielded Settlement  |
                                                                   |  • Orchard Shielded Pool    |
                                                                   |  • Vault Allowance Debit    |
                                                                   |  • 512-Byte Encrypted Memo  |
                                                                   |  • Incoming Viewing Key(IVK)|
                                                                   +-----------------------------+
```

---

## 🚀 Core Features

1. **Multi-Beneficiary Household Management:**
   - Organize and protect your family and friends under aliases (e.g. *Dad*, *Mom*, *Roommate*, *Sister*).
   - Set individual spending caps per beneficiary (`/add Dad 9876543210 350`).

2. **Automated Legacy Tariff Reconciliation (Way2API):**
   - Detects when a contact's last recharge was on a retired or inflated plan (e.g., an old **₹239** pack).
   - Automatically queries active circle catalogs and reconciles to the closest valid plan (e.g., **₹299** Truly Unlimited) while respecting user guardrails.

3. **Zcash Shielded Allowance Vault:**
   - Every user receives a private **Zcash Orchard Shielded Vault** (initial funding: `0.35 ZEC`).
   - Recharges are settled autonomously by debiting the required ZEC directly from the vault balance.
   - Inspect balance with `/vault` and simulate deposits with `/deposit [amount]`.

4. **Cryptographic 512-Byte Orchard Shielded Memos:**
   - Generates tamper-proof 512-byte encrypted memos containing order metadata and vault debit references.
   - Auditable on-chain via **Incoming Viewing Keys (IVK)** without exposing balances or transaction graphs.

5. **Autonomous Background Heartbeat:**
   - Asynchronous scheduler runs every 60 seconds.
   - Scans all enrolled beneficiaries: when any line expires within $< 24\text{h}$, it verifies spending caps, checks vault balance, executes the Bitrefill order, and sends:
     > *"🌙 While you were asleep... Autonomous Agent recharged Dad (9876543210)"*.

---

## 🕹️ Command Reference

| Command | Syntax | Description | Example |
| :--- | :--- | :--- | :--- |
| **`/start`** | `/start` | Overview of system architecture, vault balance, and commands | `/start` |
| **`/add`** | `/add <label> <phone> <cap>` | Enrolls a beneficiary, reconciles tariffs, and verifies guardrails | `/add Dad 9876543210 350`<br>`/add Mom 9123456789 $5` |
| **`/list`** | `/list` | Displays all enrolled family beneficiaries, tariffs, and caps | `/list` |
| **`/vault`** | `/vault` | Displays shielded vault address, current balance, and fiat value | `/vault` |
| **`/deposit`** | `/deposit [amount]` | Top up your Zcash allowance vault with additional ZEC | `/deposit 0.5` |
| **`/simulate`** | `/simulate [label]` | Instantly triggers autonomous purchase loop for a beneficiary | `/simulate Dad` |
| **`/audit`** | `/audit` | Inspects Zcash Orchard IVK cryptographic settlement proof | `/audit` |
| **`/remove`** | `/remove <label>` | Removes a beneficiary from autonomous monitoring | `/remove Dad` |
| **`/credits`** | `/credits` | Inspects \$5.00 testing spend safety guardrail status | `/credits` |

---

## 🚀 1-Click Deployment on Render

This project is pre-configured with a [`render.yaml`](render.yaml) blueprint and an automated HTTP health-check server for **Render Free Tier**:

1. Fork or push this repo to your GitHub account (`Arya8569/NightShiftAgent`).
2. Go to **[Render Dashboard](https://dashboard.render.com/)** $\rightarrow$ Click **New +** $\rightarrow$ **Web Service** (or **Blueprint**).
3. Connect your repository.
4. Add the 3 Environment Variables under settings:
   - `TELEGRAM_BOT_TOKEN`: Your token from @BotFather
   - `BITREFILL_API_KEY`: Your Bitrefill API v2 key
   - `WAY2API_KEY`: Your Way2API key
5. Click **Deploy** — your bot will automatically run 24/7 in the cloud!

---

## 🛠️ Local Quickstart

```bash
# 1. Clone & install
git clone https://github.com/Arya8569/NightShiftAgent.git
cd NightShiftAgent
pip install -r requirements.txt

# 2. Configure .env
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN, BITREFILL_API_KEY, and WAY2API_KEY

# 3. Launch Daemon
python bot.py
```

---

## 📜 License
MIT License.
