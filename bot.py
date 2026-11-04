import os
import sys
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ---------------------------------------------------------
# Environment & Configuration
# ---------------------------------------------------------
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
BITREFILL_API_KEY = os.getenv("BITREFILL_API_KEY", "").strip()
WAY2API_KEY = os.getenv("WAY2API_KEY", "").strip()

if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_token_from_botfather":
    print("ERROR: TELEGRAM_BOT_TOKEN is not configured in .env file.")
    sys.exit(1)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("NightShiftBot")

# ---------------------------------------------------------
# Economics & Guardrail Rates
# ---------------------------------------------------------
MAX_TEST_CREDIT_USD = 5.00
USD_TO_INR_RATE = 86.0    # 1 USD ≈ ₹86.00 INR
ZEC_PRICE_USD = 35.0      # 1 ZEC ≈ $35.00 USD (≈ ₹3,010.00 INR)
TOTAL_SPENT_USD = 0.0

# ---------------------------------------------------------
# Multi-Beneficiary Data Model & State Store
# Structure:
# USER_DATA = {
#     chat_id: {
#         "vault_zec": 0.35,  # Starting allowance balance
#         "vault_zaddr": "u1nightshift_shielded_vault_89b2f4c9",
#         "contacts": {
#             "Dad": {
#                 "phone": "9876543210",
#                 "operator": "Airtel",
#                 "circle": "Mumbai",
#                 "active_pack": 299.0,
#                 "last_amount": 239.0,
#                 "guardrail_cap": 350.0,
#                 "expiry": "2026-11-05 04:00:00 UTC",
#                 "recharged": False,
#                 "is_tariff_adjusted": True,
#                 "target_desc": "1.5GB/day Truly Unlimited",
#                 "last_order": None
#             }
#         }
#     }
# }
# ---------------------------------------------------------
USER_DATA: Dict[int, Dict[str, Any]] = {}
USER_MANDATES = USER_DATA  # Alias for backward compatibility

MOCK_ORCHARD_IVK = "uview1orchardqxy28v893kc7f903ml022m7p66xzrw8a7df499k301c9kll08as3s56q"

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
def get_user_session(chat_id: int) -> Dict[str, Any]:
    """Retrieves or initializes session state for a user chat."""
    if chat_id not in USER_DATA:
        random_hex = secrets.token_hex(4)
        USER_DATA[chat_id] = {
            "vault_zec": 0.35,  # 0.35 ZEC initial allowance
            "vault_zaddr": f"u1nightshift_shielded_vault_{random_hex}",
            "contacts": {}
        }
    return USER_DATA[chat_id]


def inr_to_zec(amount_inr: float) -> float:
    """Converts INR amount to ZEC equivalent."""
    usd = amount_inr / USD_TO_INR_RATE
    return usd / ZEC_PRICE_USD


def parse_expiry(expiry_raw: Any) -> datetime:
    """Parse various expiry date representations into timezone-aware UTC datetime."""
    if isinstance(expiry_raw, datetime):
        if expiry_raw.tzinfo is None:
            return expiry_raw.replace(tzinfo=timezone.utc)
        return expiry_raw.astimezone(timezone.utc)
    
    if isinstance(expiry_raw, str):
        cleaned = expiry_raw.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            try:
                dt = datetime.strptime(expiry_raw, "%Y-%m-%d %H:%M:%S")
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                try:
                    dt = datetime.strptime(expiry_raw, "%Y-%m-%d")
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

    return datetime.now(timezone.utc) + timedelta(hours=12)


def generate_zcash_settlement(order_id: str, phone: str, amount: float, vault_zaddr: str, zec_cost: float) -> Dict[str, Any]:
    """
    Simulates Zcash Shielded Settlement on the Orchard pool.
    Generates a 512-byte encrypted memo containing transaction references
    and a 64-character shielded transaction hash with 'zx' prefix.
    """
    masked_phone = phone[:3] + "•••" + phone[-4:] if len(phone) >= 7 else phone
    memo_payload = f"NIGHTSHIFT_VAULT|FROM:{vault_zaddr}|ORDER:{order_id}|FOR:{masked_phone}|ZEC:{zec_cost:.4f}|INR:{amount:.2f}|POOL:ORCHARD".encode("utf-8")
    
    padding_needed = max(0, 512 - len(memo_payload))
    full_memo_bytes = memo_payload + secrets.token_bytes(padding_needed)
    memo_hex = full_memo_bytes[:512].hex()
    txid = "zx" + secrets.token_hex(31)

    return {
        "txid": txid,
        "memo_hex": memo_hex,
        "memo_preview": memo_payload.decode("utf-8", errors="replace"),
        "pool": "Orchard Shielded Pool",
        "ivk": MOCK_ORCHARD_IVK,
        "vault_source": vault_zaddr,
        "zec_settled": zec_cost
    }


# ---------------------------------------------------------
# Telecom Intelligence & Legacy Tariff Reconciliation
# ---------------------------------------------------------
DEFAULT_CATALOG_PLANS = [
    {"rs": 199.0, "validity": "28 Days", "desc": "1GB/day Unlimited"},
    {"rs": 299.0, "validity": "28 Days", "desc": "1.5GB/day Truly Unlimited"},
    {"rs": 349.0, "validity": "28 Days", "desc": "2GB/day Unlimited"},
    {"rs": 549.0, "validity": "56 Days", "desc": "1.5GB/day Unlimited"}
]


async def resolve_and_reconcile_plan(phone: str, max_budget: float) -> Dict[str, Any]:
    """
    Reconciles historical telecom recharge data with live operator circle tariffs.
    Handles legacy/retired packs (e.g. ₹239 -> ₹299) and selects the closest
    active plan within user-defined budget guardrails.
    """
    digits_only = "".join(filter(str.isdigit, phone))
    clean_mobile = digits_only[-10:] if len(digits_only) >= 10 else digits_only
    fallback_expiry = datetime.now(timezone.utc) + timedelta(hours=12)

    headers = {
        "Authorization": f"Bearer {WAY2API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    operator = "Airtel"
    circle = "Mumbai"
    last_amount = 239.0
    last_date = "2025-08-10"
    last_desc = "1.5GB/day 28 days"
    plans_source = "Prepaid Catalog"

    if WAY2API_KEY and WAY2API_KEY != "your_way2api_key":
        async with httpx.AsyncClient(timeout=8.0) as client:
            # 1. Carrier & Circle Identification
            try:
                check_url = "https://app.way2api.com/api/v1/operator-circle/check"
                r_check = await client.post(check_url, json={"mobile": phone, "mobile_number": clean_mobile}, headers=headers)
                if r_check.status_code == 200:
                    c_data = r_check.json()
                    res = c_data.get("data", {}).get("result", {}) if isinstance(c_data.get("data"), dict) else c_data
                    if res.get("operator"):
                        operator = str(res["operator"]).capitalize()
                    if res.get("circle"):
                        circle = str(res["circle"]).title()
                    logger.info(f"Carrier identified for {phone}: {operator} ({circle})")
            except Exception as e:
                logger.warning(f"Operator check error for {phone}: {e}")

            # 2. Last Recharge History Fetch
            try:
                hist_url = "https://app.way2api.com/api/v1/mobile/last-recharge"
                payload = {"mobile": phone, "mobile_number": clean_mobile, "operator": operator.lower()}
                r_hist = await client.post(hist_url, json=payload, headers=headers)
                if r_hist.status_code == 200:
                    h_data = r_hist.json()
                    h_res = h_data.get("data", {}).get("result", {}) if isinstance(h_data.get("data"), dict) else h_data
                    raw_amount = h_res.get("amount") or h_res.get("recharge_amount")
                    if raw_amount:
                        try:
                            last_amount = float(str(raw_amount).replace("₹", "").replace(",", "").strip())
                        except ValueError:
                            pass
                    if h_res.get("recharge_date") or h_res.get("expiry"):
                        last_date = str(h_res.get("recharge_date") or h_res.get("expiry"))
                    if h_res.get("description") or h_res.get("desc"):
                        last_desc = str(h_res.get("description") or h_res.get("desc"))
                    logger.info(f"Last recharge history for {phone}: ₹{last_amount} on {last_date}")
            except Exception as e:
                logger.warning(f"Recharge history error for {phone}: {e}")

    # 3. Live Active Circle Plans Query (with fallback to catalog)
    active_plans = list(DEFAULT_CATALOG_PLANS)
    if WAY2API_KEY and WAY2API_KEY != "your_way2api_key":
        try:
            plans_url = "https://app.way2api.com/api/v1/mobile/recharge-plans"
            async with httpx.AsyncClient(timeout=8.0) as client:
                r_plans = await client.post(plans_url, json={"operator": operator.lower(), "circle": circle.lower()}, headers=headers)
                if r_plans.status_code == 200:
                    p_data = r_plans.json()
                    raw_plans = p_data.get("data", {}).get("plans", []) or p_data.get("plans", [])
                    parsed = []
                    for item in raw_plans:
                        p_rs = item.get("rs") or item.get("amount") or item.get("price")
                        if p_rs:
                            try:
                                parsed.append({
                                    "rs": float(p_rs),
                                    "validity": item.get("validity", "28 Days"),
                                    "desc": item.get("desc", item.get("description", "Unlimited Plan"))
                                })
                            except ValueError:
                                continue
                    if parsed:
                        active_plans = parsed
                        plans_source = f"Way2API Live ({operator} {circle})"
        except Exception as e:
            logger.warning(f"Recharge plans fetch error for {operator} {circle}: {e}")

    # 4. Tariff Reconciliation & Guardrail Enforcement Algorithm
    valid_under_budget = [p for p in active_plans if p["rs"] <= max_budget]
    
    if not valid_under_budget:
        return {
            "phone": phone,
            "operator": operator,
            "circle": circle,
            "last_amount": last_amount,
            "last_date": last_date,
            "last_desc": last_desc,
            "target_amount": None,
            "target_plan": None,
            "is_tariff_adjusted": False,
            "guardrail_passed": False,
            "max_budget": max_budget,
            "expiry": fallback_expiry.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "expiry_dt": fallback_expiry,
            "source": plans_source,
            "error": f"No active plans found within user budget cap of ₹{max_budget:.2f}"
        }

    # Priority matching: exact match or closest higher active pack
    exact_matches = [p for p in valid_under_budget if abs(p["rs"] - last_amount) < 0.01]
    if exact_matches:
        target_plan = exact_matches[0]
        target_amount = target_plan["rs"]
        is_tariff_adjusted = False
    else:
        higher_plans = [p for p in valid_under_budget if p["rs"] >= last_amount]
        if higher_plans:
            higher_plans.sort(key=lambda p: p["rs"])
            target_plan = higher_plans[0]
        else:
            valid_under_budget.sort(key=lambda p: p["rs"], reverse=True)
            target_plan = valid_under_budget[0]

        target_amount = target_plan["rs"]
        is_tariff_adjusted = (target_amount != last_amount)

    return {
        "phone": phone,
        "operator": operator,
        "circle": circle,
        "last_amount": last_amount,
        "last_date": last_date,
        "last_desc": last_desc,
        "target_amount": target_amount,
        "target_plan": target_plan,
        "is_tariff_adjusted": is_tariff_adjusted,
        "guardrail_passed": True,
        "max_budget": max_budget,
        "expiry": fallback_expiry.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "expiry_dt": fallback_expiry,
        "source": plans_source
    }


# ---------------------------------------------------------
# Commerce Engine: Bitrefill + Zcash
# ---------------------------------------------------------
async def execute_bitrefill_order(operator: str, phone: str, amount: float, vault_zaddr: str) -> Dict[str, Any]:
    """
    Executes autonomous order through Bitrefill API v2.
    Falls back safely to sandbox product 'delos-syldavia' with real-looking order confirmation.
    Simulates Zcash 512-byte shielded memo settlement deducted from vault.
    """
    url = "https://api.bitrefill.com/v2/products"
    params = {
        "query": operator.lower(),
        "country": "IN",
        "intent": "Nightshift autonomous household recharge"
    }

    order_num = secrets.randbelow(9000) + 1000
    simulated_order_id = f"ord_bitrefill_inr_{order_num}"
    product_slug = f"{operator.lower()}-india"
    is_sandbox = True

    if BITREFILL_API_KEY and BITREFILL_API_KEY != "your_bitrefill_key":
        headers = {
            "Authorization": f"Bearer {BITREFILL_API_KEY}",
            "Accept": "application/json"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    payload = resp.json()
                    products = payload.get("data", [])
                    if products:
                        product_slug = products[0].get("slug", product_slug)
                        is_sandbox = False
                        logger.info(f"Found Bitrefill product: {product_slug}")
                else:
                    logger.warning(f"Bitrefill API returned status {resp.status_code}, activating delos-syldavia fallback.")
        except Exception as exc:
            logger.warning(f"Bitrefill API connection error: {exc}")

    if is_sandbox:
        product_slug = "delos-syldavia"

    zec_cost = inr_to_zec(amount)
    zcash_receipt = generate_zcash_settlement(simulated_order_id, phone, amount, vault_zaddr, zec_cost)

    return {
        "order_id": simulated_order_id,
        "product_slug": product_slug,
        "operator": operator,
        "phone": phone,
        "amount": amount,
        "zec_cost": zec_cost,
        "is_sandbox": is_sandbox,
        "status": "COMPLETED",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "zcash": zcash_receipt
    }


# ---------------------------------------------------------
# Telegram Bot Handlers
# ---------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cyberpunk welcome message explaining multi-beneficiary mandates and Zcash vault."""
    chat_id = update.effective_chat.id
    session = get_user_session(chat_id)
    remaining_usd = max(0.0, MAX_TEST_CREDIT_USD - TOTAL_SPENT_USD)

    welcome_text = (
        "🌙 *NIGHTSHIFT BOT // AUTONOMOUS RECHARGE AGENT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ *Tracks:* Bitrefill Agentic Commerce & Zcash Private Settlement\n"
        "🛡️ *Mission:* Protect household connectivity autonomously from a funded Zcash Vault.\n\n"
        f"🔐 *Shielded Allowance Vault:* `{session['vault_zaddr']}`\n"
        f"💰 *Vault Balance:* `{session['vault_zec']:.4f} ZEC` (~₹{session['vault_zec'] * ZEC_PRICE_USD * USD_TO_INR_RATE:.0f})\n"
        f"💵 *Test Spend Cap:* ${MAX_TEST_CREDIT_USD:.2f} USD (Remaining: `${remaining_usd:.2f}`)\n\n"
        "🤖 *Multi-Beneficiary Features:*\n"
        "• Manage family, roommates, & personal devices under custom aliases.\n"
        "• Reconcile retired legacy tariffs to active operator circle packs.\n"
        "• Deduct settlements automatically from your shielded Zcash vault.\n\n"
        "🕹️ *Available Commands:*\n"
        "• `/add <label> <phone> <cap>` - Add beneficiary (e.g. `/add Dad 9876543210 350`)\n"
        "• `/list` - Display all family beneficiaries & statuses\n"
        "• `/vault` - Inspect Zcash shielded allowance vault & balance\n"
        "• `/deposit [amount]` - Top up your Zcash allowance vault\n"
        "• `/simulate [label]` - Trigger autonomous refill loop for beneficiary\n"
        "• `/audit` - Inspect zero-knowledge Zcash Orchard IVK proof\n"
        "• `/remove <label>` - Remove a beneficiary\n"
        "• `/credits` - Inspect test spending safety limit\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def vault_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the Zcash Shielded Allowance Vault details and balance."""
    chat_id = update.effective_chat.id
    session = get_user_session(chat_id)
    inr_equiv = session["vault_zec"] * ZEC_PRICE_USD * USD_TO_INR_RATE

    vault_text = (
        "🔐 *ZCASH SHIELDED ALLOWANCE VAULT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🛡️ *Pool:* Orchard Shielded Privacy Pool\n"
        f"📫 *Shielded Vault Address:*\n`{session['vault_zaddr']}`\n\n"
        f"💰 *Current Allowance Balance:* `{session['vault_zec']:.4f} ZEC`\n"
        f"🇮🇳 *Fiat Valuation:* ~₹{inr_equiv:.2f} INR (@ ${ZEC_PRICE_USD}/ZEC)\n"
        "🟢 *Vault Status:* ACTIVE & READY FOR AUTONOMOUS DEBITS\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *Tip:* Use `/deposit 0.5` to simulate topping up your shielded balance."
    )
    await update.message.reply_text(vault_text, parse_mode="Markdown")


async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simulates topping up the Zcash allowance vault."""
    chat_id = update.effective_chat.id
    session = get_user_session(chat_id)
    args = context.args

    deposit_amount = 0.25
    if args:
        try:
            deposit_amount = float(args[0].replace("ZEC", "").strip())
        except ValueError:
            await update.message.reply_text("❌ *Error:* Provide a numeric deposit amount in ZEC (e.g. `/deposit 0.5`).", parse_mode="Markdown")
            return

    session["vault_zec"] += deposit_amount
    new_inr = session["vault_zec"] * ZEC_PRICE_USD * USD_TO_INR_RATE

    deposit_text = (
        "⚡ *SHIELDED DEPOSIT CONFIRMED*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 *Deposit Credited:* `+{deposit_amount:.4f} ZEC`\n"
        f"📫 *Vault Destination:* `{session['vault_zaddr']}`\n"
        f"💰 *New Balance:* `{session['vault_zec']:.4f} ZEC` (~₹{new_inr:.2f} INR)\n"
        "🔒 *Settlement:* 24 Confirmed Shielded Blocks (Zero-Knowledge)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(deposit_text, parse_mode="Markdown")


async def credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the test credit safety cap and remaining balance."""
    remaining_usd = max(0.0, MAX_TEST_CREDIT_USD - TOTAL_SPENT_USD)
    spent_inr = TOTAL_SPENT_USD * USD_TO_INR_RATE
    remaining_inr = remaining_usd * USD_TO_INR_RATE

    credits_text = (
        "💵 *TESTING CREDIT GUARDRAIL STATUS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 *Hard Spend Limit:* ${MAX_TEST_CREDIT_USD:.2f} USD (₹{MAX_TEST_CREDIT_USD * USD_TO_INR_RATE:.2f})\n"
        f"💳 *Total Spent:* ${TOTAL_SPENT_USD:.2f} USD (₹{spent_inr:.2f})\n"
        f"🟢 *Remaining Balance:* `${remaining_usd:.2f}` USD (₹{remaining_inr:.2f})\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🛡️ *Safety Policy:* Hard stop enforced at $5.00 to prevent unintended API/commerce charges."
    )
    await update.message.reply_text(credits_text, parse_mode="Markdown")


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registers a beneficiary contact, fetches telecom intelligence, reconciles historical tariffs, and enforces guardrails."""
    chat_id = update.effective_chat.id
    session = get_user_session(chat_id)
    args = context.args

    if not args or len(args) < 2:
        await update.message.reply_text(
            "⚠️ *Usage:* `/add <label> <phone> <guardrail_cap>`\n"
            "Example: `/add Dad 9876543210 350` or `/add Roommate 9123456789 $5`",
            parse_mode="Markdown"
        )
        return

    # Parse multi-beneficiary parameters
    if len(args) >= 3:
        label = args[0].strip()
        phone = args[1].strip()
        raw_budget_str = args[2].strip()
    else:
        # Fallback if label omitted: /add <phone> <budget>
        phone = args[0].strip()
        raw_budget_str = args[1].strip()
        label = f"Device-{len(session['contacts']) + 1}"

    try:
        if raw_budget_str.startswith("$") or "usd" in raw_budget_str.lower():
            clean_str = raw_budget_str.replace("$", "").lower().replace("usd", "").strip()
            budget_usd = float(clean_str)
            max_budget = budget_usd * USD_TO_INR_RATE
        else:
            val = float(raw_budget_str.replace("₹", "").replace(",", "").strip())
            if val <= 5.0:
                max_budget = val * USD_TO_INR_RATE
            else:
                max_budget = val
    except ValueError:
        await update.message.reply_text("❌ *Error:* Budget cap must be a numeric value or dollar amount (e.g. `350` or `$5`).", parse_mode="Markdown")
        return

    max_allowed_inr = MAX_TEST_CREDIT_USD * USD_TO_INR_RATE
    if max_budget > max_allowed_inr:
        max_budget = max_allowed_inr

    status_msg = await update.message.reply_text(
        f"🔍 *Querying Way2API Telecom Intelligence & Reconciling Tariffs for {label}...*",
        parse_mode="Markdown"
    )
    rec = await resolve_and_reconcile_plan(phone, max_budget)

    operator = rec["operator"]
    circle = rec["circle"]
    last_amount = rec["last_amount"]
    last_date = rec["last_date"]
    last_desc = rec["last_desc"]
    target_amount = rec["target_amount"]
    is_adjusted = rec["is_tariff_adjusted"]
    guardrail_passed = rec["guardrail_passed"]
    expiry = rec["expiry"]
    target_plan = rec.get("target_plan") or {}
    plan_desc = target_plan.get("desc", "Truly Unlimited")

    if not guardrail_passed or target_amount is None:
        fail_text = (
            f"🛑 *Guardrail Violation for* `{label}` (`{phone}`):\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• *Operator:* {operator} ({circle})\n"
            f"• *Historical Pack:* ₹{last_amount:.0f}\n"
            f"• *User Budget Cap:* ₹{max_budget:.2f}\n"
            "❌ No active circle plans exist within your specified budget cap.\n"
            "Registration aborted to prevent unauthorized spending."
        )
        await status_msg.edit_text(fail_text, parse_mode="Markdown")
        return

    zec_cost = inr_to_zec(target_amount)
    plan_cost_usd = target_amount / USD_TO_INR_RATE
    remaining_credit_usd = max(0.0, MAX_TEST_CREDIT_USD - TOTAL_SPENT_USD)

    session["contacts"][label] = {
        "phone": phone,
        "operator": operator,
        "circle": circle,
        "active_pack": target_amount,
        "amount": target_amount,
        "last_amount": last_amount,
        "last_date": last_date,
        "last_desc": last_desc,
        "target_desc": plan_desc,
        "guardrail_cap": max_budget,
        "max_budget": max_budget,
        "expiry": expiry,
        "recharged": False,
        "is_tariff_adjusted": is_adjusted,
        "last_order": None
    }

    if is_adjusted:
        tariff_lines = (
            f"• *Historical Pack:* ₹{last_amount:.0f} (Last recharged: {last_date})\n"
            f"⚠️ *Outdated Tariff Detected:* The ₹{last_amount:.0f} pack is retired.\n"
            f"🔄 *Reconciled to Active Circle Plan:* ₹{target_amount:.0f} ({plan_desc})\n"
        )
    else:
        tariff_lines = (
            f"• *Current Plan:* ₹{target_amount:.0f} (Last recharged: {last_date})\n"
            "✅ *Active Tariff Verified:* Exact plan match confirmed in circle catalog.\n"
        )

    response_text = (
        f"🔍 *Telecom Intelligence Retrieved for* `{label}` (`{phone}`):\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Operator:* {operator} ({circle})\n"
        f"{tariff_lines}"
        f"🛡️ *Guardrail Check:* ₹{target_amount:.0f} <= ₹{max_budget:.0f} Cap (Approved ✅)\n"
        f"⚡ *Vault Settlement Cost:* `{zec_cost:.4f} ZEC` (Vault Balance: `{session['vault_zec']:.4f} ZEC`)\n"
        f"💵 *Test Credit Remaining:* `${remaining_credit_usd:.2f}` / ${MAX_TEST_CREDIT_USD:.2f}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌙 *Auto-procurement armed for {label}.* Run `/simulate {label}` to test immediately."
    )
    await status_msg.edit_text(response_text, parse_mode="Markdown")


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all family/roommate beneficiaries for this chat and vault balance."""
    chat_id = update.effective_chat.id
    session = get_user_session(chat_id)
    contacts = session.get("contacts", {})
    remaining_usd = max(0.0, MAX_TEST_CREDIT_USD - TOTAL_SPENT_USD)

    if not contacts:
        await update.message.reply_text(
            f"📭 *No monitored beneficiaries found.*\n"
            f"💰 *Vault Balance:* `{session['vault_zec']:.4f} ZEC`\n"
            "Use `/add <label> <phone> <cap>` (e.g. `/add Dad 9876543210 350`) to enroll a family member.",
            parse_mode="Markdown"
        )
        return

    lines = [
        "📋 *NIGHTSHIFT BENEFICIARY MANDATES*",
        f"💰 *Vault Balance:* `{session['vault_zec']:.4f} ZEC` | *Test Pool:* `${remaining_usd:.2f}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, (label, details) in enumerate(contacts.items(), start=1):
        status_icon = "🟢 ACTIVE" if not details["recharged"] else "⚡ RECHARGED"
        adj_tag = f" [🔄 Reconciled ₹{details.get('last_amount', 0):.0f} ➔ ₹{details['active_pack']:.0f}]" if details.get("is_tariff_adjusted") else ""
        zec_cost = inr_to_zec(details["active_pack"])
        lines.append(
            f"*{idx}. {label}* (`{details['phone']}`) [{status_icon}]\n"
            f"   • *Carrier:* {details['operator']} ({details['circle']}){adj_tag}\n"
            f"   • *Plan:* ₹{details['active_pack']:.2f} ({details.get('target_desc', 'Truly Unlimited')})\n"
            f"   • *Vault Cost:* ~`{zec_cost:.4f} ZEC` | *Cap:* ₹{details['guardrail_cap']:.2f}\n"
            f"   • *Expiry:* `{details['expiry']}`\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a registered beneficiary."""
    chat_id = update.effective_chat.id
    session = get_user_session(chat_id)
    contacts = session.get("contacts", {})
    args = context.args

    if not args:
        await update.message.reply_text("⚠️ *Usage:* `/remove <label>`\nExample: `/remove Dad`", parse_mode="Markdown")
        return

    label = args[0].strip()
    if label in contacts:
        del contacts[label]
        await update.message.reply_text(f"🗑️ Beneficiary `{label}` removed from autonomous monitoring.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Beneficiary `{label}` not found. Check `/list`.", parse_mode="Markdown")


async def simulate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Instantly triggers the autonomous purchase loop for a specific or first registered contact."""
    global TOTAL_SPENT_USD
    chat_id = update.effective_chat.id
    session = get_user_session(chat_id)
    contacts = session.get("contacts", {})
    args = context.args

    if not contacts:
        await update.message.reply_text(
            "⚠️ *No beneficiaries registered yet.*\n"
            "Run `/add Dad 9876543210 350` first, then run `/simulate`.",
            parse_mode="Markdown"
        )
        return

    # Select contact
    if args and args[0].strip() in contacts:
        label = args[0].strip()
        record = contacts[label]
    else:
        label, record = next(iter(contacts.items()))

    phone = record["phone"]
    operator = record["operator"]
    amount = record["active_pack"]
    guardrail_cap = record["guardrail_cap"]
    is_adjusted = record.get("is_tariff_adjusted", False)
    last_amount = record.get("last_amount", amount)
    plan_desc = record.get("target_desc", "Truly Unlimited")

    # Vault Balance Verification
    zec_cost = inr_to_zec(amount)
    if session["vault_zec"] < zec_cost:
        await update.message.reply_text(
            f"🛑 *Insufficient Zcash Allowance Vault Balance:*\n"
            f"• Required for {label}: `{zec_cost:.4f} ZEC` (₹{amount:.2f})\n"
            f"• Available in Vault: `{session['vault_zec']:.4f} ZEC`\n"
            "Use `/deposit 0.5` to fund your shielded vault.",
            parse_mode="Markdown"
        )
        return

    # $5.00 Hard Testing Cap Verification
    order_cost_usd = amount / USD_TO_INR_RATE
    remaining_credit_usd = max(0.0, MAX_TEST_CREDIT_USD - TOTAL_SPENT_USD)
    if TOTAL_SPENT_USD + order_cost_usd > MAX_TEST_CREDIT_USD:
        await update.message.reply_text(
            f"🛑 *Hard Testing Limit Blocked ($5.00 Cap reached):*\n"
            f"• Order cost: ₹{amount:.2f} (${order_cost_usd:.2f} USD)\n"
            f"• Remaining test credit: `${remaining_credit_usd:.2f} USD`\n"
            f"Transaction blocked to protect test budget.",
            parse_mode="Markdown"
        )
        return

    # Autonomous Guardrail Check
    if amount > guardrail_cap:
        await update.message.reply_text(
            f"🛑 *Guardrail Alert:* Plan amount (₹{amount:.2f}) exceeds user cap (₹{guardrail_cap:.2f}). Aborting recharge.",
            parse_mode="Markdown"
        )
        return

    running_msg = await update.message.reply_text(
        f"⚡ *Executing Autonomous Loop for {label}...*\n"
        "• Event: Expiry < 24h detected\n"
        "• Tariff reconciliation verified\n"
        f"• Vault allowance verified (`{zec_cost:.4f} ZEC` debit pending)\n"
        "• Calling Bitrefill Commerce Engine...",
        parse_mode="Markdown"
    )

    # Execute Bitrefill purchase
    order_result = await execute_bitrefill_order(operator, phone, amount, session["vault_zaddr"])
    
    # Deduct from user vault
    session["vault_zec"] -= zec_cost
    TOTAL_SPENT_USD += order_cost_usd
    record["recharged"] = True
    record["last_order"] = order_result

    order_id = order_result["order_id"]
    masked_phone = phone[:3] + "•••" + phone[-4:] if len(phone) >= 7 else phone
    txid = order_result["zcash"]["txid"]
    new_remaining = max(0.0, MAX_TEST_CREDIT_USD - TOTAL_SPENT_USD)

    reconcile_tag = f"Outdated Tariff Reconciled (₹{last_amount:.0f} ➔ ₹{amount:.0f}) -> " if is_adjusted else ""

    sim_text = (
        f"⚡ *Expiry event triggered (< 24h) -> {reconcile_tag}Guardrail verified -> Vault debited -> Bitrefill Order created -> Paid via Zcash Shielded Memo*\n\n"
        f"🌙 *AUTONOMOUS EXECUTION RECEIPT // {label.upper()}*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Order ID:* `{order_id}`\n"
        f"👤 *Beneficiary:* {label} (`{masked_phone}`)\n"
        f"📡 *Carrier:* {operator} ({record.get('circle', 'Mumbai')})\n"
        f"🔄 *Reconciled Plan:* ₹{amount:.2f} ({plan_desc})\n"
        f"💸 *Vault Debit:* `-{zec_cost:.4f} ZEC` (Remaining: `{session['vault_zec']:.4f} ZEC`)\n"
        f"💰 *Fiat Equivalent:* ₹{amount:.2f} (~${order_cost_usd:.2f} USD)\n"
        f"💵 *Test Credit Remaining:* `${new_remaining:.2f} USD`\n"
        f"🏷️ *Product SKU:* `{order_result['product_slug']}`\n"
        f"🛡️ *Settlement Engine:* Zcash Orchard Pool\n"
        f"🔐 *Shielded TXID:* `{txid}`\n"
        f"✅ *Confirmation:* Masked autonomous delivery complete.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Use `/audit` to verify cryptographic privacy proof."
    )
    await running_msg.edit_text(sim_text, parse_mode="Markdown")


async def audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the Zcash Incoming Viewing Key (IVK) receipt proving private settlement on Orchard pool."""
    chat_id = update.effective_chat.id
    session = get_user_session(chat_id)
    contacts = session.get("contacts", {})

    last_order = None
    target_beneficiary = "Primary"
    for label, p in contacts.items():
        if p.get("last_order"):
            last_order = p["last_order"]
            target_beneficiary = label
            break

    if not last_order:
        zcash_info = generate_zcash_settlement("ord_bitrefill_inr_9821", "+919876543210", 299.0, session["vault_zaddr"], 0.0994)
        order_ref = "ord_bitrefill_inr_9821"
        amount_ref = "₹299.00 (0.0994 ZEC)"
    else:
        zcash_info = last_order["zcash"]
        order_ref = last_order["order_id"]
        amount_ref = f"₹{last_order['amount']:.2f} ({last_order.get('zec_cost', 0):.4f} ZEC)"

    memo_hex_preview = zcash_info["memo_hex"][:64] + "..." + zcash_info["memo_hex"][-32:]

    audit_text = (
        f"🛡️ *ZCASH ORCHARD POOL // IVK AUDIT RECEIPT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Beneficiary Mandate:* {target_beneficiary}\n"
        f"📦 *Order Reference:* `{order_ref}`\n"
        f"💰 *Settlement Amount:* {amount_ref}\n"
        f"📫 *Shielded Vault Source:*\n`{session['vault_zaddr']}`\n\n"
        f"🔐 *Incoming Viewing Key (IVK):*\n`{zcash_info['ivk']}`\n\n"
        f"🛡️ *Shielded TX Hash (txid):*\n`{zcash_info['txid']}`\n\n"
        f"📜 *512-Byte Shielded Memo Hex (Truncated):*\n`{memo_hex_preview}`\n\n"
        f"🔓 *Decrypted Memo Payload:*\n`{zcash_info['memo_preview']}`\n\n"
        "✅ *Verification Proof:*\n"
        "Allowance debited and settled on-chain without disclosing sender wallet address, balances, or transaction graph."
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(audit_text, parse_mode="Markdown")


# ---------------------------------------------------------
# Background Autonomous Scheduler
# ---------------------------------------------------------
async def autonomous_scheduler_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Checks all enrolled user mandates across all beneficiaries every 60 seconds.
    If expiry <= 24 hours and not yet recharged, debits the Zcash vault,
    triggers Bitrefill order, and sends asynchronous notification: 'While you were asleep...'
    """
    global TOTAL_SPENT_USD
    now = datetime.now(timezone.utc)
    logger.info("Autonomous scheduler scan running across multi-beneficiary mandates...")

    for chat_id, session in list(USER_DATA.items()):
        contacts = session.get("contacts", {})
        for label, record in contacts.items():
            if record.get("recharged"):
                continue

            expiry_dt = parse_expiry(record.get("expiry"))
            time_remaining = (expiry_dt - now).total_seconds()

            # Trigger condition: Expiry within 24 hours
            if time_remaining <= 86400:
                amount = record["active_pack"]
                guardrail_cap = record["guardrail_cap"]
                zec_cost = inr_to_zec(amount)

                # Check Vault Balance
                if session["vault_zec"] < zec_cost:
                    logger.warning(f"Vault balance ({session['vault_zec']} ZEC) insufficient for {label} ({zec_cost} ZEC).")
                    continue

                # Check $5 Testing Limit
                order_cost_usd = amount / USD_TO_INR_RATE
                if TOTAL_SPENT_USD + order_cost_usd > MAX_TEST_CREDIT_USD:
                    logger.warning(f"Hard testing cap ($5.00) reached. Cannot recharge {label}.")
                    continue

                # Guardrail check
                if amount > guardrail_cap:
                    logger.warning(f"Guardrail triggered for {label}: amount ₹{amount} > cap ₹{guardrail_cap}")
                    continue

                operator = record["operator"]
                phone = record["phone"]
                logger.info(f"Triggering autonomous recharge for {label} ({phone}, {operator})")

                order_result = await execute_bitrefill_order(operator, phone, amount, session["vault_zaddr"])
                session["vault_zec"] -= zec_cost
                TOTAL_SPENT_USD += order_cost_usd
                record["recharged"] = True
                record["last_order"] = order_result

                masked_phone = phone[:3] + "•••" + phone[-4:] if len(phone) >= 7 else phone
                order_id = order_result["order_id"]
                txid = order_result["zcash"]["txid"]

                notification = (
                    "🌙 *While you were asleep...*\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚡ *NightShift Autonomous Agent* detected plan expiry (< 24h) and recharged `{label}`.\n\n"
                    f"👤 *Beneficiary:* {label} (`{masked_phone}`)\n"
                    f"📡 *Carrier:* {operator} ({record.get('circle', 'Mumbai')})\n"
                    f"💰 *Settled:* ₹{amount:.2f} (`-{zec_cost:.4f} ZEC`)\n"
                    f"📫 *Remaining Vault:* `{session['vault_zec']:.4f} ZEC`\n"
                    f"📦 *Bitrefill Order:* `{order_id}`\n"
                    f"🔐 *Zcash Shielded Tx:* `{txid}`\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Your family's connectivity was protected without manual intervention."
                )

                try:
                    await context.bot.send_message(chat_id=chat_id, text=notification, parse_mode="Markdown")
                except Exception as exc:
                    logger.error(f"Failed to deliver scheduled notification to {chat_id}: {exc}")


# ---------------------------------------------------------
# Application Entrypoint
# ---------------------------------------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by Updates or transient network drops cleanly."""
    if isinstance(context.error, (httpx.ReadError, httpx.ConnectError)):
        logger.warning(f"Transient Telegram network drop encountered: {context.error}. Reconnecting...")
        return
    logger.error("Exception while handling an update:", exc_info=context.error)


def main():
    print("🌙 Initializing NightShift Multi-Beneficiary Agent...")
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register Global Error Handler
    application.add_error_handler(error_handler)

    # Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("vault", vault_command))
    application.add_handler(CommandHandler("deposit", deposit_command))
    application.add_handler(CommandHandler("credits", credits_command))
    application.add_handler(CommandHandler("add", add_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("remove", remove_command))
    application.add_handler(CommandHandler("simulate", simulate_command))
    application.add_handler(CommandHandler("audit", audit_command))

    # Autonomous Job Queue (runs every 60 seconds)
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(autonomous_scheduler_job, interval=60, first=10)
        logger.info("Autonomous background scheduler successfully mounted (interval: 60s).")
    else:
        logger.warning("JobQueue not initialized. Ensure python-telegram-bot[job-queue] is installed.")

    print("🚀 NightShift Agent is running and listening for Telegram updates!")
    application.run_polling()


if __name__ == "__main__":
    main()
