from fastapi import FastAPI, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import os
import json
import random
import secrets
import hashlib
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg2
import requests

load_dotenv()

app = FastAPI()

VERIFY_TOKEN = "my_custom_secure_token"
DATABASE_URL = os.getenv("DATABASE_URL")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
ADMIN_PHONE = os.getenv("ADMIN_PHONE")
MONIME_SECRET_KEY = os.getenv("MONIME_SECRET_KEY")
MONIME_SPACE_ID = os.getenv("MONIME_SPACE_ID")

@app.on_event("startup")
async def startup_event():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        
        try:
            # Auto-Migration for new columns needed by client fixes
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT FALSE;")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS vehicle_image_id VARCHAR(255);")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS momo_number VARCHAR(255);")
            cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_qty INTEGER DEFAULT 1;")
            conn.commit()
        except Exception as mig_err:
            conn.rollback()
            
        print("\n" + "="*50)
        print("✅ Successfully connected to Supabase & Tables Verified!")
        print("="*50 + "\n")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")

@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403)

LANGUAGES = {
    "english": {
        "welcome": "Welcome to Agro Market 🌱\nYour trusted agricultural marketplace.\n\nPlease select your role for today:\n\n1️⃣ Sell Produce (Farmer)\n2️⃣ Buy Produce & Inputs (Buyer)\n3️⃣ Sell Farm Inputs\n4️⃣ Driver / Rider\n\n_Reply with the number (e.g., 1)_",
        "farmer_menu": "🌾 *Farmer Dashboard*\nWhat would you like to do today?\n\n1️⃣ Add Produce\n2️⃣ My Inventory\n3️⃣ View Orders\n4️⃣ Buy Supplies\n5️⃣ Market Prices\n\n_Reply with a number_",
        "buyer_menu": "🛒 *Buyer Dashboard*\nWhat would you like to do today?\n\n1️⃣ Buy Produce\n2️⃣ Buy Farm Inputs\n3️⃣ My Orders\n4️⃣ Market Prices\n\n_Reply with a number_",
        "input_menu": "🌱 *Input Seller Dashboard*\nWhat would you like to do today?\n\n1️⃣ Add Supply\n2️⃣ My Inventory\n3️⃣ View Orders\n4️⃣ Market Prices\n\n_Reply with a number_",
        "driver_menu": "🚚 *Driver Dashboard*\nWhat would you like to do today?\n\n1️⃣ Find Deliveries\n2️⃣ My Deliveries\n\n_Reply with a number_"
    },
    "krio": {
        "welcome": "Wɛlkɔm to Agro Makit 🌱\n\nFɔ stat, tɛl wi aw yu want fɔ yuz dis platfɔm tide:\n\n1️⃣ Sɛl Produce (Fama)\n2️⃣ Bay Produce & Inputs (Baya)\n3️⃣ Sɛl Farm Inputs\n4️⃣ Drayva / Rayda\n\n_Reply with the number (e.g., 1)_",
        "farmer_menu": "🌾 *Fama Dashboard*\nWetin yu want fo du tide?\n\n1️⃣ Add Produce\n2️⃣ My Inventory\n3️⃣ View Orders\n4️⃣ Buy Supplies\n5️⃣ Market Prices\n\n_Reply with a number_",
        "buyer_menu": "🛒 *Baya Dashboard*\nWetin yu want fo du tide?\n\n1️⃣ Buy Produce\n2️⃣ Buy Farm Inputs\n3️⃣ My Orders\n4️⃣ Market Prices\n\n_Reply with a number_",
        "input_menu": "🌱 *Input Seller Dashboard*\nWetin yu want fo du tide?\n\n1️⃣ Add Supply\n2️⃣ My Inventory\n3️⃣ View Orders\n4️⃣ Market Prices\n\n_Reply with a number_",
        "driver_menu": "🚚 *Driver Dashboard*\nWetin yu want fo du tide?\n\n1️⃣ Find Deliveries\n2️⃣ My Deliveries\n\n_Reply with a number_"
    }
}

def send_whatsapp_message(phone_number, message_text):
    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": phone_number, "type": "text", "text": {"body": message_text}}
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e: pass

def send_whatsapp_image(phone_number, image_id, caption_text):
    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": phone_number, "type": "image", "image": {"id": image_id, "caption": caption_text}}
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e: pass

def send_role_menu(phone_number, lang="english"):
    t = LANGUAGES.get("english")
    send_whatsapp_message(phone_number, t["welcome"])

def send_main_menu(phone_number, role, lang="english"):
    t = LANGUAGES.get("english")
    menus = {"role_farmer": t["farmer_menu"], "role_buyer": t["buyer_menu"], "role_driver": t["driver_menu"], "role_input": t["input_menu"]}
    send_whatsapp_message(phone_number, menus.get(role, "Menu unavailable."))

def get_user_profile(phone_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT u.role, u.nin_status, u.language, us.current_flow, us.current_step, u.name, u.vehicle_number, u.is_approved, u.momo_number FROM users u LEFT JOIN user_sessions us ON u.phone = us.phone WHERE u.phone = %s", (phone_number,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result: return {"role": result[0], "nin_status": result[1], "language": result[2] or "english", "flow": result[3], "step": result[4], "name": result[5], "vehicle_number": result[6], "is_approved": result[7], "momo_number": result[8]}
        return None
    except: return None

def get_user_location(phone_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT location FROM users WHERE phone = %s", (phone_number,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result and result[0] else ""
    except: return ""

def update_session(phone_number, flow, step):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO user_sessions (phone, current_flow, current_step) VALUES (%s, %s, %s) ON CONFLICT (phone) DO UPDATE SET current_flow = EXCLUDED.current_flow, current_step = EXCLUDED.current_step;", (phone_number, flow, step))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e: pass

def update_session_data(phone_number, new_data_dict):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT temp_data FROM user_sessions WHERE phone = %s", (phone_number,))
        result = cursor.fetchone()
        current_data = result[0] if result and result[0] else {}
        current_data.update(new_data_dict)
        cursor.execute("UPDATE user_sessions SET temp_data = %s WHERE phone = %s", (json.dumps(current_data), phone_number))
        conn.commit()
        cursor.close()
        conn.close()
    except: pass

def get_session_data(phone_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT temp_data FROM user_sessions WHERE phone = %s", (phone_number,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else {}
    except: return {}

def save_new_product(phone_number, image_id, category='produce'):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT temp_data FROM user_sessions WHERE phone = %s", (phone_number,))
        result = cursor.fetchone()
        temp_data = result[0] if result and result[0] else {}
        name = temp_data.get("produce_name", "Unknown")
        price = temp_data.get("produce_price", "Unknown")
        quantity = temp_data.get("produce_quantity", "Unknown")
        cursor.execute("INSERT INTO products (farmer_phone, product_name, price, quantity, image_id, category) VALUES (%s, %s, %s, %s, %s, %s)", (phone_number, name, price, quantity, image_id, category))
        cursor.execute("UPDATE user_sessions SET temp_data = NULL WHERE phone = %s", (phone_number,))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e: pass

def get_user_inventory(phone_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT product_name, price FROM products WHERE farmer_phone = %s ORDER BY created_at DESC", (phone_number,))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def search_marketplace(query, category='produce', buyer_location=""):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        search_term = f"%{query}%"
        loc_term = f"%{buyer_location}%"
        cursor.execute("""
            SELECT p.id, p.product_name, p.price, p.quantity, p.image_id, p.farmer_phone, u.name, u.location
            FROM products p JOIN users u ON p.farmer_phone = u.phone
            WHERE p.product_name ILIKE %s AND p.category = %s
            ORDER BY (u.location ILIKE %s) DESC, p.created_at DESC LIMIT 5
        """, (search_term, category, loc_term))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def get_product_by_id(product_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT p.id, p.product_name, p.price, p.quantity, p.image_id, p.farmer_phone, u.name, u.location FROM products p JOIN users u ON p.farmer_phone = u.phone WHERE p.id = %s", (product_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result
    except: return None

def create_order(buyer_phone, product_id, preference, payment_method, order_qty=1, custom_name=None, custom_address=None):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT product_name, farmer_phone, price FROM products WHERE id = %s", (product_id,))
        prod = cursor.fetchone()
        if not prod: return None
        prod_name, farmer_phone, price = prod
        
        clean_price = int(''.join(filter(str.isdigit, str(price)))) if any(c.isdigit() for c in str(price)) else 1500
        if clean_price == 0: clean_price = 1500
        
        subtotal = clean_price * int(order_qty)
        delivery_fee = 0 
        platform_fee = 5
        total_amount = subtotal + delivery_fee + platform_fee
        
        if custom_name:
            cursor.execute("UPDATE users SET name = %s WHERE phone = %s", (custom_name, buyer_phone))
        if custom_address:
            cursor.execute("UPDATE users SET location = %s WHERE phone = %s", (custom_address, buyer_phone))
            
        cursor.execute("""
            INSERT INTO orders (buyer_phone, farmer_phone, product_id, product_name, status, delivery_preference, payment_method, subtotal, delivery_fee, total_amount, order_qty) 
            VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s) RETURNING id
        """, (buyer_phone, farmer_phone, product_id, prod_name, preference, payment_method, subtotal, delivery_fee, total_amount, order_qty))
        order_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        return {"id": order_id, "farmer_phone": farmer_phone, "product_name": prod_name, "price": clean_price, "subtotal": subtotal, "d_fee": delivery_fee, "total": total_amount}
    except Exception as e:
        return None

def get_farmer_orders(farmer_phone):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.id, o.product_name, u.name, u.phone, u.location, o.delivery_preference, o.payment_method, o.total_amount
            FROM orders o JOIN users u ON o.buyer_phone = u.phone
            WHERE o.farmer_phone = %s AND o.status = 'pending' ORDER BY o.created_at DESC
        """, (farmer_phone,))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def get_buyer_orders(buyer_phone):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT o.id, o.product_name, o.status, u.name, u.phone, o.receipt_number FROM orders o JOIN users u ON o.farmer_phone = u.phone WHERE o.buyer_phone = %s ORDER BY o.created_at DESC", (buyer_phone,))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def get_order_by_id(order_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT o.id, o.product_name, o.buyer_phone, u.name, o.status, o.delivery_preference, o.payment_method, o.receipt_number, o.subtotal, o.delivery_fee, o.total_amount, o.wallet_status FROM orders o JOIN users u ON o.buyer_phone = u.phone WHERE o.id = %s", (order_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result
    except: return None

def update_order_status(order_id, new_status):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, order_id))
        conn.commit()
        cursor.close()
        conn.close()
    except: pass

def get_available_deliveries():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.id, o.product_name, f.name AS farmer_name, f.location AS farmer_loc, b.name AS buyer_name, b.location AS buyer_loc
            FROM orders o JOIN users f ON o.farmer_phone = f.phone JOIN users b ON o.buyer_phone = b.phone
            WHERE o.status = 'AWAITING_DRIVER' AND o.delivery_preference = 'delivery' AND o.driver_phone IS NULL ORDER BY o.created_at DESC LIMIT 5
        """)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def get_delivery_details(order_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.id, o.product_name, f.name AS farmer_name, f.location AS farmer_loc, f.phone AS farmer_phone, 
                   b.name AS buyer_name, b.location AS buyer_loc, b.phone AS buyer_phone, o.payment_method, p.price, o.order_qty,
                   o.receipt_number, o.subtotal, o.delivery_fee, o.total_amount, u_d.name as driver_name, u_d.vehicle_number, u_d.phone as driver_phone
            FROM orders o 
            JOIN users f ON o.farmer_phone = f.phone 
            JOIN users b ON o.buyer_phone = b.phone 
            LEFT JOIN products p ON o.product_id = p.id
            LEFT JOIN users u_d ON o.driver_phone = u_d.phone
            WHERE o.id = %s
        """, (order_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result
    except: return None

def assign_driver_update_fee(order_id, driver_phone, fee):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET driver_phone = %s, delivery_fee = %s, total_amount = subtotal + 5 + %s WHERE id = %s", (driver_phone, fee, fee, order_id))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

def get_driver_deliveries(driver_phone):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.id, o.product_name, f.name, f.location, f.phone, b.name, b.location, b.phone
            FROM orders o JOIN users f ON o.farmer_phone = f.phone JOIN users b ON o.buyer_phone = b.phone
            WHERE o.driver_phone = %s AND o.status = 'dispatched' ORDER BY o.created_at DESC
        """, (driver_phone,))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def create_user_with_language(phone_number, lang):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (phone, language) VALUES (%s, %s) ON CONFLICT (phone) DO UPDATE SET language = EXCLUDED.language;", (phone_number, lang))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

def update_user_role(phone_number, role_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = %s WHERE phone = %s", (role_id, phone_number))
        cursor.execute("SELECT name, location FROM users WHERE phone = %s", (phone_number,))
        user = cursor.fetchone()
        if user and user[0] and user[1]:
            cursor.execute("UPDATE user_sessions SET current_flow = 'main_menu', current_step = 'idle' WHERE phone = %s", (phone_number,))
            is_registered = True
        else:
            next_step = 'awaiting_name'
            cursor.execute("INSERT INTO user_sessions (phone, current_flow, current_step) VALUES (%s, 'registration', %s) ON CONFLICT (phone) DO UPDATE SET current_flow = EXCLUDED.current_flow, current_step = EXCLUDED.current_step;", (phone_number, next_step))
            is_registered = False
        conn.commit()
        cursor.close()
        conn.close()
        return is_registered
    except Exception as e:
        return False

def update_user_name_and_step(phone_number, name):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET name = %s WHERE phone = %s", (name, phone_number))
        cursor.execute("SELECT role FROM users WHERE phone = %s", (phone_number,))
        user_role = cursor.fetchone()[0]
        
        if user_role == 'role_driver':
            next_step = 'awaiting_vehicle'
        elif user_role == 'role_buyer':
            next_step = 'awaiting_location'
        else:
            next_step = 'awaiting_momo'
            
        cursor.execute("UPDATE user_sessions SET current_step = %s WHERE phone = %s", (next_step, phone_number))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

def update_user_vehicle(phone_number, vehicle_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET vehicle_number = %s WHERE phone = %s", (vehicle_number, phone_number))
        cursor.execute("UPDATE user_sessions SET current_step = 'awaiting_vehicle_image' WHERE phone = %s", (phone_number,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

def update_user_momo(phone_number, momo):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET momo_number = %s WHERE phone = %s", (momo, phone_number))
        cursor.execute("UPDATE user_sessions SET current_step = 'awaiting_location' WHERE phone = %s", (phone_number,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

def update_user_location_and_finish(phone_number, location):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE phone = %s", (phone_number,))
        res = cursor.fetchone()
        role = res[0] if res else ""
        
        is_approved = True if role == 'role_buyer' else False
        flow_state = 'main_menu' if is_approved else 'pending_approval'
        
        cursor.execute("UPDATE users SET location = %s, is_approved = %s WHERE phone = %s", (location, is_approved, phone_number))
        cursor.execute("UPDATE user_sessions SET current_flow = %s, current_step = 'idle' WHERE phone = %s", (flow_state, phone_number))
        conn.commit()
        cursor.close()
        conn.close()
        return is_approved
    except: return False

def get_market_prices(include_id=False):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        if include_id:
            cursor.execute("SELECT id, crop_name, location, price FROM market_prices ORDER BY crop_name, location")
        else:
            cursor.execute("SELECT crop_name, location, price FROM market_prices ORDER BY crop_name, location")
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def add_market_price(crop_name, location, price):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO market_prices (crop_name, location, price) VALUES (%s, %s, %s)", (crop_name, location, price))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

def delete_market_price(price_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM market_prices WHERE id = %s", (price_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

def get_dashboard_stats():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users;")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status != 'DELIVERED';")
        active_orders = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'DELIVERED';")
        total_deliveries = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {"total_users": total_users, "active_orders": active_orders, "total_deliveries": total_deliveries}
    except:
        return {"total_users": 0, "active_orders": 0, "total_deliveries": 0}

def render_order_row(row):
    o_id, b_num, p_item, t_val, state, wallet, rcpt_code, timestamp = row
    rcpt_display = rcpt_code if rcpt_code else "<span style='color:#777;font-style:italic;'>Unreleased</span>"
    status_color = "#f57c00" if state in ["pending", "AWAITING_PAYMENT", "AWAITING_DRIVER"] else "#0288d1" if state in ["paid", "dispatched"] else "#2e7d32" if state in ["DELIVERED", "Successful"] else "#d32f2f"
    wallet_color = "#7b1fa2" if wallet == "held" else "#2e7d32" if wallet == "released" else "#555"
    return f"<tr><td><b>#{o_id}</b></td><td>+{b_num}</td><td>{str(p_item).upper()}</td><td>SLE {t_val}</td><td><span style=\"background:{status_color};color:white;padding:3px 8px;border-radius:4px;font-size:12px;font-weight:bold;\">{state.upper()}</span></td><td><span style=\"background:{wallet_color};color:white;padding:3px 8px;border-radius:4px;font-size:12px;font-weight:bold;\">{str(wallet).upper()}</span></td><td><code>{rcpt_display}</code></td></tr>"

# ========================================================
# SECURE HELPER FUNCTION FOR CHECKOUT
# ========================================================
def generate_payment_link(order_id, action_user_phone=None):
    try:
        order_details = get_order_by_id(order_id)
        if not order_details: return
        _, p_name, b_phone, b_name, status, pref, pay_method, receipt, subtotal, d_fee, total_amt, wallet = order_details
        
        update_order_status(order_id, "AWAITING_PAYMENT")
        
        token = os.getenv("MONIME_SECRET_KEY")
        space_id = os.getenv("MONIME_SPACE_ID")
        unique_idempotency_token = f"key_{order_id}_{secrets.token_hex(8)}"
        
        monime_payload = {
            "name": f"Agro Market Order #{order_id}",
            "reference": str(order_id),
            "successUrl": "https://agro-market-bot.onrender.com/admin", 
            "cancelUrl": "https://agro-market-bot.onrender.com/admin",
            "lineItems": [
                {
                    "type": "custom",
                    "name": str(p_name).upper(),
                    "price": {
                        "currency": "SLE",
                        "value": int(total_amt) * 100 
                    },
                    "quantity": 1
                }
            ]
        }
        
        monime_headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": unique_idempotency_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        api_url = "https://api.monime.io/v1/checkout-sessions"
        if token and str(token).startswith("mon_test_"):
            api_url = "https://api.sandbox.monime.io/v1/checkout-sessions"
            monime_headers["X-Space-Id"] = str(space_id).strip()
        else:
            if space_id:
                monime_headers["Monime-Space-Id"] = str(space_id).strip()
        
        response = requests.post(api_url, headers=monime_headers, json=monime_payload, timeout=15)
        
        if response.status_code in [200, 201]:
            res_data = response.json()
            live_url = res_data.get("result", {}).get("redirectUrl") or res_data.get("redirectUrl") or res_data.get("result", {}).get("url") or res_data.get("url")
            
            if live_url:
                summary = f"📦 *Order Summary:*\nProduct: {p_name.upper()}\nSubtotal: SLE {subtotal}\nDelivery Fee: SLE {d_fee}\nPlatform Fee: SLE 5\n*Total Payable: SLE {total_amt}*"
                send_whatsapp_message(b_phone, f"🎉 *Good News!* The final availability has been confirmed.\n\n{summary}\n\n🔗 *Monime Live Payment Link:*\n{live_url}")
            else:
                if action_user_phone: send_whatsapp_message(action_user_phone, f"⚠️ API Success, but URL token string missing: {res_data}")
        else:
            if action_user_phone: send_whatsapp_message(action_user_phone, f"❌ *Monime API Rejected the Payload!*\nStatus Code: {response.status_code}\nError Details: {response.text}")
            simulated_paylink = f"https://agro-market-bot.onrender.com/checkout/pay/{order_id}"
            send_whatsapp_message(b_phone, f"🎉 *Order Confirmed!* (Fallback Simulator Link):\n🔗 {simulated_paylink}")
            
    except Exception as api_err:
        if action_user_phone: send_whatsapp_message(action_user_phone, f"❌ *Connection Exception details caught:* {str(api_err)}")
        simulated_paylink = f"https://agro-market-bot.onrender.com/checkout/pay/{order_id}"
        send_whatsapp_message(b_phone, f"🔗 Fallback Simulator Link:\n{simulated_paylink}")
        
    if action_user_phone:
        update_session(action_user_phone, "main_menu", "idle")
        send_whatsapp_message(action_user_phone, "✅ Buyer has been notified to complete payment.")
        prof = get_user_profile(action_user_phone)
        if prof and prof.get("is_approved"):
            send_main_menu(action_user_phone, prof["role"], prof.get("language", "english"))

# ========================================================
# SECURE ADMIN WEB DASHBOARD ROUTES
# ========================================================
def is_admin_authorized(request: Request):
    session_cookie = request.cookies.get("secure_admin_session")
    if not session_cookie: return False
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT phone FROM admin_auth WHERE session_token = %s", (session_cookie,))
        auth_check = cursor.fetchone()
        cursor.close()
        conn.close()
        if not auth_check or auth_check[0] != ADMIN_PHONE: return False
        return True
    except: return False

@app.get("/checkout/pay/{order_id}", response_class=HTMLResponse)
async def checkout_payment_page(order_id: int):
    order_data = get_order_by_id(order_id)
    if not order_data:
        return "<h3>❌ Order entry not found inside current records.</h3>"
    
    p_name = order_data[1]
    buyer_phone = order_data[2]
    
    subtotal = order_data[8] if order_data[8] else 0
    d_fee = order_data[9] if order_data[9] else 0
    total_amt = order_data[10] if order_data[10] else 0
    platform_fee = 5 
    
    display_amt = total_amt if total_amt > 0 else 6500
    
    html_layout = f"""
    <html>
        <head>
            <title>Monime Secured Escrow Checkout</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #0c1017; padding: 20px; text-align: center; color: #c9d1d9; }}
                .pay-card {{ background: #161b22; padding: 30px; border-radius: 12px; box-shadow: 0 4px 25px rgba(0,0,0,0.5); max-width: 420px; margin: 60px auto; border-top: 6px solid #2ea44f; }}
                h2 {{ color: #2ea44f; margin-bottom: 5px; }}
                .price-tag {{ font-size: 36px; font-weight: bold; color: #ffffff; margin: 25px 0; letter-spacing: 1px; }}
                .btn-submit {{ background-color: #238636; color: white; border: none; padding: 16px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; font-size: 16px; transition: 0.2s; }}
                .btn-submit:hover {{ background-color: #2ea44f; }}
                .details {{ text-align: left; background: #0d1117; padding: 18px; border-radius: 6px; margin-bottom: 25px; font-size: 14px; color: #8b949e; line-height: 1.6; border: 1px solid #30363d; }}
                .provider-badge {{ display: inline-block; background: #21262d; color: #58a6ff; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="pay-card">
                <h2>Monime Payment Engine 💳</h2>
                <p style="color:#8b949e; margin-top:0; font-size: 14px;">Sierra Leone Interbank & Mobile Money Rails</p>
                <div class="details">
                    <b>📦 Product Description:</b> {p_name.upper()}<br>
                    <b>🔢 Order Reference Key:</b> AGM-ORD-{order_id}<br>
                    <b>📱 Payer Account MSISDN:</b> +{buyer_phone}<br>
                    <hr style="border: 0; border-top: 1px solid #30363d; margin: 10px 0;">
                    <b>Subtotal (Qty x Price):</b> SLE {subtotal}.00<br>
                    <b>Delivery Fee:</b> SLE {d_fee}.00<br>
                    <b>Platform Fee:</b> SLE {platform_fee}.00<br>
                    <span class="provider-badge" style="margin-top:10px;">🛡️ Immuta Ledger Escrow Container Enabled</span>
                </div>
                <div class="price-tag">SLE {display_amt}.00</div>
                <form action="/admin/api/simulate-webhook-trigger/{order_id}" method="post">
                    <button type="submit" class="btn-submit">🔒 Authorize Orange Money Deposit</button>
                </form>
            </div>
        </body>
    </html>
    """
    return html_layout

@app.post("/admin/api/simulate-webhook-trigger/{order_id}")
async def simulate_webhook_trigger(order_id: int):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        tx_id = f"TX-MONIME-{random.randint(10000000, 99999999)}"
        rec_num = f"AGM-{datetime.now().strftime('%Y')}-{str(order_id).zfill(6)}"
        
        cursor.execute("SELECT total_amount FROM orders WHERE id = %s", (order_id,))
        current_amt = cursor.fetchone()[0]
        final_amt = current_amt if current_amt and current_amt > 0 else 6500
        
        cursor.execute("""
            UPDATE orders 
            SET status = 'paid', transaction_id = %s, receipt_number = %s, wallet_status = 'held', total_amount = %s
            WHERE id = %s RETURNING buyer_phone, farmer_phone, product_name, total_amount
        """, (tx_id, rec_num, final_amt, order_id))
        res = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        if res:
            b_phone, f_phone, p_name, total_amt = res
            success_msg = f"💳 *Monime Escrow Hold Confirmed!* SLE {total_amt}.00 for your order of *{p_name}* has been successfully secured to our safe settlement account.\n\nFunds are strictly locked down until delivery receipt confirmation is dispatched."
            send_whatsapp_message(b_phone, success_msg)
            send_whatsapp_message(f_phone, f"💰 *Escrow Funded Notification!* The buyer has successfully cleared payment parameters via Monime for Order #{order_id} ({p_name}). Proceed with transport logs immediately.")
            
        return HTMLResponse("<script>alert('🎉 Monime Escrow Authorization Emulated! WhatsApp processing chains triggered.'); window.close();</script>")
    except Exception as e:
        return f"Payment Rails Error: {e}"

@app.get("/admin/login", response_class=HTMLResponse)
async def login_page():
    return """
    <html>
        <body style="font-family: Arial; padding: 50px; text-align: center; background-color: #f4f7f6;">
            <div style="background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 400px; margin: auto;">
                <h2 style="color: #2E7D32;">Admin Login</h2>
                <form action="/admin/process-login" method="post" style="margin: 0;">
                    <input type="password" name="password" placeholder="Enter Password" required style="padding: 10px; width: 100%; margin-bottom: 20px; border: 1px solid #ccc; border-radius: 4px;">
                    <button type="submit" style="background-color: #2E7D32; color: white; border: none; padding: 12px 20px; width: 100%; border-radius: 4px; cursor: pointer; font-weight: bold; width:100%;">Login</button>
                </form>
            </div>
        </body>
    </html>
    """

@app.post("/admin/process-login")
async def process_login(request: Request):
    form_data = await request.form()
    password = form_data.get("password")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM admin_auth WHERE phone = %s", (str(ADMIN_PHONE),))
        result = cursor.fetchone()
        
        if result and hashlib.sha256(password.encode('utf-8')).hexdigest() == result[0]:
            session_token = secrets.token_hex(32)
            cursor.execute("UPDATE admin_auth SET session_token = %s WHERE phone = %s", (session_token, str(ADMIN_PHONE)))
            conn.commit()
            cursor.close()
            conn.close()
            
            response = RedirectResponse(url="/admin", status_code=302)
            response.set_cookie(key="secure_admin_session", value=session_token, httponly=True, secure=False, samesite="lax", max_age=86400)
            return response
            
        cursor.close()
        conn.close()
    except Exception as e:
        pass
    return HTMLResponse("<script>alert('Invalid Password.'); window.location.href='/admin/login';</script>")

@app.post("/admin/user/toggle/{phone}")
async def toggle_user_approval(phone: str, request: Request):
    if not is_admin_authorized(request): return RedirectResponse(url="/admin/login", status_code=303)
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT is_approved, role FROM users WHERE phone = %s", (phone,))
        res = cursor.fetchone()
        if res:
            new_status = not res[0]
            cursor.execute("UPDATE users SET is_approved = %s WHERE phone = %s", (new_status, phone))
            
            if new_status:
                cursor.execute("UPDATE user_sessions SET current_flow = 'main_menu', current_step = 'idle' WHERE phone = %s", (phone,))
                send_whatsapp_message(phone, "🎉 *Congratulations!* Your Agro Market profile has been approved by the Administrator.\n\nType *'menu'* to access your active dashboard.")
            else:
                cursor.execute("UPDATE user_sessions SET current_flow = 'pending_approval', current_step = 'idle' WHERE phone = %s", (phone,))
                send_whatsapp_message(phone, "⚠️ Your Agro Market account access has been revoked by the Administrator.")
            
            conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        pass
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/price/add")
async def admin_add_price(request: Request):
    if not is_admin_authorized(request): return RedirectResponse(url="/admin/login", status_code=303)
    form_data = await request.form()
    add_market_price(form_data.get("crop_name"), form_data.get("location"), form_data.get("price"))
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/price/delete/{price_id}")
async def admin_delete_price(price_id: int, request: Request):
    if not is_admin_authorized(request): return RedirectResponse(url="/admin/login", status_code=303)
    delete_market_price(price_id)
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not is_admin_authorized(request): return RedirectResponse(url="/admin/login")
    market_prices = get_market_prices(include_id=True)
    stats = get_dashboard_stats()
    
    successful_ledger_rows = ""
    pending_ledger_rows = ""
    unsuccessful_ledger_rows = ""
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, buyer_phone, product_name, total_amount, status, wallet_status, receipt_number, created_at FROM orders WHERE status = 'Successful' ORDER BY created_at DESC LIMIT 1000;")
        for row in cursor.fetchall():
            successful_ledger_rows += render_order_row(row)
            
        cursor.execute("SELECT id, buyer_phone, product_name, total_amount, status, wallet_status, receipt_number, created_at FROM orders WHERE status IN ('Unsuccessful', 'DECLINED') ORDER BY created_at DESC LIMIT 1000;")
        for row in cursor.fetchall():
            unsuccessful_ledger_rows += render_order_row(row)
            
        cursor.execute("SELECT id, buyer_phone, product_name, total_amount, status, wallet_status, receipt_number, created_at FROM orders WHERE status NOT IN ('Successful', 'Unsuccessful', 'DECLINED') ORDER BY created_at DESC LIMIT 1000;")
        for row in cursor.fetchall():
            pending_ledger_rows += render_order_row(row)
        
        cursor.execute("SELECT name, phone, location, is_approved, momo_number FROM users WHERE role IN ('role_farmer', 'role_input') ORDER BY is_approved DESC, created_at ASC LIMIT 1000;")
        farmers_html = ""
        for row in cursor.fetchall():
            name = str(row[0]) if row[0] else "Unknown"
            phone = str(row[1]) if row[1] else "Unknown"
            location = str(row[2]) if row[2] else "Unknown"
            momo = str(row[4]) if row[4] else "N/A"
            status_badge = "<span style='color:#2e7d32;font-weight:bold;'>Approved ✅</span>" if row[3] else "<span style='color:#f57c00;font-weight:bold;'>Pending ⏳</span>"
            action_btn = "Revoke" if row[3] else "Approve"
            btn_class = "btn-revoke" if row[3] else "btn-approve"
            form = f'<form action="/admin/user/toggle/{phone}" method="post" style="margin:0;"><button type="submit" class="btn {btn_class}">{action_btn}</button></form>'
            farmers_html += f"<tr><td>{name}</td><td>+{phone}</td><td>{location}</td><td>{momo}</td><td>{status_badge}</td><td>{form}</td></tr>"
            
        cursor.execute("SELECT name, phone, vehicle_number, is_approved, momo_number FROM users WHERE role = 'role_driver' ORDER BY is_approved DESC, created_at ASC LIMIT 1000;")
        drivers_html = ""
        for row in cursor.fetchall():
            name = str(row[0]) if row[0] else "Unknown"
            phone = str(row[1]) if row[1] else "Unknown"
            vehicle = str(row[2]) if row[2] else "N/A"
            momo = str(row[4]) if row[4] else "N/A"
            status_badge = "<span style='color:#0288d1;font-weight:bold;'>Active 🚚</span>" if row[3] else "<span style='color:#f57c00;font-weight:bold;'>Pending ⏳</span>"
            action_btn = "Revoke" if row[3] else "Approve"
            btn_class = "btn-revoke" if row[3] else "btn-approve"
            form = f'<form action="/admin/user/toggle/{phone}" method="post" style="margin:0;"><button type="submit" class="btn {btn_class}">{action_btn}</button></form>'
            drivers_html += f"<tr><td>{name}</td><td>+{phone}</td><td>{vehicle}</td><td>{momo}</td><td>{status_badge}</td><td>{form}</td></tr>"

        cursor.execute("SELECT name, phone, location, is_approved FROM users WHERE role = 'role_buyer' ORDER BY is_approved DESC, created_at ASC LIMIT 1000;")
        buyers_html = ""
        for row in cursor.fetchall():
            name = str(row[0]) if row[0] else "Unknown"
            phone = str(row[1]) if row[1] else "Unknown"
            location = str(row[2]) if row[2] else "Unknown"
            status_badge = "<span style='color:#2e7d32;font-weight:bold;'>Approved ✅</span>" if row[3] else "<span style='color:#f57c00;font-weight:bold;'>Revoked ⏳</span>"
            action_btn = "Revoke" if row[3] else "Approve"
            btn_class = "btn-revoke" if row[3] else "btn-approve"
            form = f'<form action="/admin/user/toggle/{phone}" method="post" style="margin:0;"><button type="submit" class="btn {btn_class}">{action_btn}</button></form>'
            buyers_html += f"<tr><td>{name}</td><td>+{phone}</td><td>{location}</td><td>{status_badge}</td><td>{form}</td></tr>"

        cursor.close()
        conn.close()
    except Exception as err:
        pass

    html_content = f"""
    <html>
        <head>
            <title>Agro Market Admin Panel</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; padding: 40px; margin:0; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                h1 {{ color: #2E7D32; margin-top: 0; }}
                h2 {{ color: #333; margin-top: 40px; border-bottom: 2px solid #2E7D32; padding-bottom: 10px; text-transform: uppercase; font-size: 18px; letter-spacing: 0.5px; display: flex; justify-content: space-between; align-items: flex-end; }}
                table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-radius: 6px; overflow: hidden; margin-bottom: 10px; }}
                th, td {{ padding: 14px 18px; text-align: left; border-bottom: 1px solid #eef2f5; font-size: 14px; }}
                th {{ background-color: #2E7D32; color: white; font-weight: 600; text-transform: uppercase; font-size: 12px; letter-spacing: 0.5px; }}
                tr:hover {{ background-color: #f9fbf9; }}
                
                .btn {{ border: none; padding: 8px 15px; text-align: center; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 13px; transition: all 0.3s ease; box-shadow: 0 2px 4px rgba(0,0,0,0.1); color: white; display: inline-block; }}
                .btn-approve {{ background-color: #2ea44f; }}
                .btn-approve:hover {{ background-color: #22863a; transform: translateY(-1px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }}
                .btn-revoke {{ background-color: #d73a49; }}
                .btn-revoke:hover {{ background-color: #cb2431; transform: translateY(-1px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }}
                .btn-add {{ background-color: #008CBA; padding: 10px 20px; }}
                .btn-reject {{ background-color: #f44336; }}
                
                .add-form {{ background: white; padding: 25px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-radius: 6px; }}
                input[type=text] {{ padding: 10px; margin: 5px 10px 5px 0; border: 1px solid #ccc; border-radius: 4px; width: 25%; font-size: 14px; }}
                
                .stat-card {{ background: white; padding: 25px; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); flex: 1; text-align: center; border-top: 5px solid #2E7D32; }}
                .stat-card p {{ margin: 15px 0 0; font-size: 32px; font-weight: bold; color: #2E7D32; }}
                .logout-btn {{ float: right; background-color: #555; color: white; padding: 10px 18px; border-radius: 4px; font-weight: bold; font-size: 13px; text-decoration: none; }}
                .search-bar {{ width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 6px; font-size: 15px; box-sizing: border-box; }}
                
                .pagination {{ display: flex; justify-content: center; gap: 5px; margin-bottom: 40px; margin-top: 10px; }}
                .page-btn {{ padding: 6px 12px; border: 1px solid #ccc; background-color: #fff; cursor: pointer; border-radius: 4px; font-weight: bold; color: #333; transition: 0.2s; }}
                .page-btn:hover:not(:disabled) {{ background-color: #eef2f5; }}
                .page-btn.active {{ background-color: #2E7D32; color: #fff; border-color: #2E7D32; }}
                .page-btn:disabled {{ color: #aaa; cursor: not-allowed; opacity: 0.6; }}
            </style>
            <script>
                const rowsPerPage = 10;
                const tableState = {{
                    'sellersTable': 1, 'driversTable': 1, 'buyersTable': 1,
                    'successfulOrdersTable': 1, 'pendingOrdersTable': 1, 'unsuccessfulOrdersTable': 1,
                    'pricesTable': 1
                }};

                function renderTable(tableId, searchInputId, paginationId) {{
                    let input = document.getElementById(searchInputId);
                    let filter = input ? input.value.toLowerCase() : "";
                    let table = document.getElementById(tableId);
                    if(!table) return;
                    let tbody = table.getElementsByTagName("tbody")[0];
                    if(!tbody) return;
                    let tr = tbody.getElementsByTagName("tr");
                    
                    let filteredRows = [];
                    for (let i = 0; i < tr.length; i++) {{
                        let rowText = tr[i].innerText.toLowerCase();
                        if (rowText.includes(filter)) {{
                            filteredRows.push(tr[i]);
                        }}
                        tr[i].style.display = "none";
                    }}
                    
                    let totalRows = filteredRows.length;
                    let totalPages = Math.ceil(totalRows / rowsPerPage) || 1;
                    
                    if (tableState[tableId] > totalPages) tableState[tableId] = totalPages;
                    let currentPage = tableState[tableId];
                    
                    let start = (currentPage - 1) * rowsPerPage;
                    let end = start + rowsPerPage;
                    
                    for (let i = start; i < end && i < totalRows; i++) {{
                        filteredRows[i].style.display = "";
                    }}
                    
                    renderPagination(tableId, searchInputId, paginationId, currentPage, totalPages);
                }}

                function renderPagination(tableId, searchInputId, paginationId, currentPage, totalPages) {{
                    let container = document.getElementById(paginationId);
                    if (!container) return;
                    
                    let html = '';
                    html += `<button class="page-btn" onclick="goToPage('${{tableId}}', '${{searchInputId}}', '${{paginationId}}', 1)" ${{currentPage === 1 ? 'disabled' : ''}}>&lt;&lt;</button>`;
                    html += `<button class="page-btn" onclick="goToPage('${{tableId}}', '${{searchInputId}}', '${{paginationId}}', ${{currentPage - 1}})" ${{currentPage === 1 ? 'disabled' : ''}}>&lt;</button>`;
                    
                    let startPage = Math.max(1, currentPage - 2);
                    let endPage = Math.min(totalPages, currentPage + 2);
                    
                    for (let i = startPage; i <= endPage; i++) {{
                        html += `<button class="page-btn ${{i === currentPage ? 'active' : ''}}" onclick="goToPage('${{tableId}}', '${{searchInputId}}', '${{paginationId}}', ${{i}})">${{i}}</button>`;
                    }}
                    
                    html += `<button class="page-btn" onclick="goToPage('${{tableId}}', '${{searchInputId}}', '${{paginationId}}', ${{currentPage + 1}})" ${{currentPage === totalPages ? 'disabled' : ''}}>&gt;</button>`;
                    html += `<button class="page-btn" onclick="goToPage('${{tableId}}', '${{searchInputId}}', '${{paginationId}}', ${{totalPages}})" ${{currentPage === totalPages ? 'disabled' : ''}}>&gt;&gt;</button>`;
                    
                    container.innerHTML = html;
                }}

                function goToPage(tableId, searchInputId, paginationId, page) {{
                    tableState[tableId] = page;
                    renderTable(tableId, searchInputId, paginationId);
                }}

                function onSearch(tableId, searchInputId, paginationId) {{
                    tableState[tableId] = 1;
                    renderTable(tableId, searchInputId, paginationId);
                }}

                window.onload = function() {{
                    renderTable('sellersTable', 'searchSellers', 'sellersPagination');
                    renderTable('driversTable', 'searchDrivers', 'driversPagination');
                    renderTable('buyersTable', 'searchBuyers', 'buyersPagination');
                    renderTable('successfulOrdersTable', 'searchSuccessful', 'successfulPagination');
                    renderTable('pendingOrdersTable', 'searchPending', 'pendingPagination');
                    renderTable('unsuccessfulOrdersTable', 'searchUnsuccessful', 'unsuccessfulPagination');
                    renderTable('pricesTable', 'searchPrices', 'pricesPagination');
                }};
            </script>
        </head>
        <body>
            <div class="container">
                <a href="/admin/logout" class="logout-btn">🔒 Logout</a>
                <h1>🛡️ Agro Market Admin Dashboard</h1>
                
                <div class="stats-container" style="display:flex; gap:20px; margin-bottom:30px;">
                    <div class="stat-card"><h3>👥 Total Users</h3><p>{stats['total_users']}</p></div>
                    <div class="stat-card"><h3>🛒 Active Orders</h3><p>{stats['active_orders']}</p></div>
                    <div class="stat-card"><h3>✅ Total Deliveries</h3><p>{stats['total_deliveries']}</p></div>
                </div>

                <h2>🧑‍🌾 Verified Seller Directory</h2>
                <input type="text" id="searchSellers" class="search-bar" placeholder="🔍 Search Sellers by Name, Phone, or Location..." onkeyup="onSearch('sellersTable', 'searchSellers', 'sellersPagination')">
                <table id="sellersTable"><thead><tr><th>Name</th><th>Phone Number</th><th>Farm Location</th><th>MoMo Number</th><th>Status</th><th>Action</th></tr></thead><tbody>{farmers_html}</tbody></table>
                <div id="sellersPagination" class="pagination"></div>
                
                <h2>🚚 Logistics Delivery Fleet</h2>
                <input type="text" id="searchDrivers" class="search-bar" placeholder="🔍 Search Riders by Name, Phone, or Plate..." onkeyup="onSearch('driversTable', 'searchDrivers', 'driversPagination')">
                <table id="driversTable"><thead><tr><th>Rider Name</th><th>Phone Number</th><th>Vehicle Plate</th><th>MoMo Number</th><th>Status</th><th>Action</th></tr></thead><tbody>{drivers_html}</tbody></table>
                <div id="driversPagination" class="pagination"></div>

                <h2>🛒 Registered Buyers Directory</h2>
                <input type="text" id="searchBuyers" class="search-bar" placeholder="🔍 Search Buyers by Name, Phone, or Location..." onkeyup="onSearch('buyersTable', 'searchBuyers', 'buyersPagination')">
                <table id="buyersTable"><thead><tr><th>Name</th><th>Phone Number</th><th>Delivery Location</th><th>Status</th><th>Action</th></tr></thead><tbody>{buyers_html}</tbody></table>
                <div id="buyersPagination" class="pagination"></div>

                <h2>✅ Successful Transactions</h2>
                <input type="text" id="searchSuccessful" class="search-bar" placeholder="🔍 Search completed orders..." onkeyup="onSearch('successfulOrdersTable', 'searchSuccessful', 'successfulPagination')">
                <table id="successfulOrdersTable">
                    <thead><tr><th>ID</th><th>Buyer Number</th><th>Product</th><th>Amount</th><th>Order Status</th><th>Escrow State</th><th>Receipt Code</th></tr></thead>
                    <tbody>{successful_ledger_rows}</tbody>
                </table>
                <div id="successfulPagination" class="pagination"></div>

                <h2>⏳ Pending Transactions</h2>
                <input type="text" id="searchPending" class="search-bar" placeholder="🔍 Search pending or processing orders..." onkeyup="onSearch('pendingOrdersTable', 'searchPending', 'pendingPagination')">
                <table id="pendingOrdersTable">
                    <thead><tr><th>ID</th><th>Buyer Number</th><th>Product</th><th>Amount</th><th>Order Status</th><th>Escrow State</th><th>Receipt Code</th></tr></thead>
                    <tbody>{pending_ledger_rows}</tbody>
                </table>
                <div id="pendingPagination" class="pagination"></div>

                <h2>❌ Unsuccessful / Disputed Transactions</h2>
                <input type="text" id="searchUnsuccessful" class="search-bar" placeholder="🔍 Search declined or disputed orders..." onkeyup="onSearch('unsuccessfulOrdersTable', 'searchUnsuccessful', 'unsuccessfulPagination')">
                <table id="unsuccessfulOrdersTable">
                    <thead><tr><th>ID</th><th>Buyer Number</th><th>Product</th><th>Amount</th><th>Order Status</th><th>Escrow State</th><th>Receipt Code</th></tr></thead>
                    <tbody>{unsuccessful_ledger_rows}</tbody>
                </table>
                <div id="unsuccessfulPagination" class="pagination"></div>
                
                <h2>📈 Daily Commodity Pricing Management Dashboard</h2>
                <input type="text" id="searchPrices" class="search-bar" placeholder="🔍 Search Prices by Crop or Location..." onkeyup="onSearch('pricesTable', 'searchPrices', 'pricesPagination')">
                <table id="pricesTable">
                    <thead>
                        <tr>
                            <th>Crop / Item Name</th><th>Market Location</th><th>Current Reference Price</th><th>Action Panel</th>
                        </tr>
                    </thead>
                    <tbody>
    """
    if not market_prices:
        html_content += "<tr><td colspan='4' class='empty'>No market price vectors currently stored inside table configurations.</td></tr>"
    else:
        for p in market_prices:
            p_id, crop, loc, price = p
            html_content += f"""
                <tr>
                    <td><b>{crop}</b></td><td>{loc}</td><td><b>{price}</b></td>
                    <td>
                        <form action="/admin/price/delete/{p_id}" method="post" style="margin:0;">
                            <button type="submit" class="btn btn-reject">Delete Price</button>
                        </form>
                    </td>
                </tr>
            """
    html_content += """
                    </tbody>
                </table>
                <div id="pricesPagination" class="pagination"></div>
                
                <div class="add-form">
                    <h3>➕ Add New Market Price</h3>
                    <form action="/admin/price/add" method="post" style="margin:0;">
                        <input type="text" name="crop_name" placeholder="e.g., Cassava" required>
                        <input type="text" name="location" placeholder="e.g., Makeni" required>
                        <input type="text" name="price" placeholder="e.g., SLE 45.00" required>
                        <button type="submit" class="btn btn-add">Add Price to Dashboard</button>
                    </form>
                </div>
            </div>
        </body>
    </html>
    """
    return html_content

def search_order_by_receipt(receipt_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT id, product_name, buyer_phone, farmer_phone, status, total_amount FROM orders WHERE receipt_number = %s", (receipt_number.strip().upper(),))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result
    except: return None

@app.get("/admin/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("secure_admin_session")
    return response

# --- STANDALONE RELATIONAL CONFIRM DELIVERY FUNCTION ---
def process_confirm_delivery(sender_phone, action_choice):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        target_buyer = str(sender_phone).strip()
        
        cursor.execute("""
            SELECT id, product_name, farmer_phone, total_amount, subtotal, delivery_fee, delivery_option, driver_phone
            FROM orders WHERE buyer_phone = %s AND status IN ('DELIVERED', 'paid', 'dispatched') AND wallet_status = 'held' ORDER BY id DESC LIMIT 1
        """, (target_buyer,))
        escrow_match = cursor.fetchone()
        
        if escrow_match:
            o_id, p_name, target_farmer_phone, total_amt, s_total, d_fee, d_opt, target_driver_phone = escrow_match
            
            if action_choice == "A":
                monime_api_endpoint = "https://api.monime.io/v1/financial-account/transfers"
                monime_headers = {"Authorization": f"Bearer {MONIME_SECRET_KEY}", "Content-Type": "application/json"}
                monime_payload = {"source_account": "agro_market_escrow_holding", "destination_wallet": f"wallet_{target_farmer_phone}", "amount": int(total_amt if total_amt else 0), "currency": "SLE", "metadata": {"order_id": o_id}}
                try: requests.post(monime_api_endpoint, headers=monime_headers, json=monime_payload, timeout=5)
                except Exception as api_err: pass
                
                cursor.execute("UPDATE orders SET status = 'Successful', wallet_status = 'released' WHERE id = %s", (o_id,))
                conn.commit()
                
                send_whatsapp_message(target_buyer, "✅ You have successfully confirmed delivery! The escrow funds have been securely released to the seller.")
                if str(target_buyer) != str(target_farmer_phone):
                    send_whatsapp_message(str(target_farmer_phone), f"💸 *Escrow Balance Released!* Order #{o_id} delivery was confirmed by the buyer. SLE {total_amt} has been deposited to your wallet.")
                    
                if ADMIN_PHONE:
                    send_whatsapp_message(ADMIN_PHONE, f"🔔 *ADMIN ALERT: Escrow Cleared* \n\nOrder #{o_id} ({str(p_name).upper()}) has been successfully fulfilled. Funds are released.")
                    
            elif action_choice == "B":
                cursor.execute("UPDATE orders SET status = 'Unsuccessful', wallet_status = 'held' WHERE id = %s", (o_id,))
                conn.commit()
                
                send_whatsapp_message(target_buyer, "⚠️ You have marked the order as Not Received. An administrator has been notified to investigate and resolve this dispute.")
                if ADMIN_PHONE:
                    send_whatsapp_message(ADMIN_PHONE, f"🚨 *DISPUTE ALERT!*\nBuyer marked Order #{o_id} ({str(p_name).upper()}) as Not Received. Funds are locked in escrow until manual review.")

        else:
            send_whatsapp_message(target_buyer, f"🔍 No active transaction matched current lookup criteria for delivery confirmation.")
        cursor.close()
        conn.close()
    except Exception as e:
        pass

# ========================================================
# LIVE PRODUCTION MONIME WEBHOOK ENDPOINT
# ========================================================
@app.post("/webhook/monime")
async def monime_payment_webhook(request: Request):
    try:
        payload = await request.json()
        event = payload.get("event")
        result_obj = payload.get("result", {})
        
        order_id = None
        if "reference" in result_obj:
            order_id = result_obj["reference"]
        elif "order_id" in payload.get("metadata", {}):
            order_id = payload["metadata"]["order_id"]
        elif "orderNumber" in result_obj:
            order_id = result_obj["orderNumber"]
            
        if order_id and isinstance(order_id, str) and order_id.startswith("AGM-ORD-"):
            order_id = order_id.replace("AGM-ORD-", "")
            
        if (event == "payment.success" or event == "checkout_session.completed") and order_id and str(order_id).isdigit():
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            tx_id = result_obj.get("id") or result_obj.get("transaction_id") or f"OM-{random.randint(10000000, 99999999)}"
            rec_num = result_obj.get("orderNumber") or f"AGM-{datetime.now().strftime('%Y')}-{str(order_id).zfill(6)}"
            
            cursor.execute("""
                UPDATE orders 
                SET status = 'paid', transaction_id = %s, receipt_number = %s, wallet_status = 'held' 
                WHERE id = %s RETURNING buyer_phone, farmer_phone, product_name, total_amount
            """, (str(tx_id), str(rec_num), int(order_id)))
            res = cursor.fetchone()
            conn.commit()
            
            if res:
                b_phone, f_phone, p_name, total_amt = res
                
                details = get_delivery_details(order_id)
                drv_phone = None
                if details:
                    o_id, p_name, f_name, f_loc, f_phone, b_name, b_loc, b_phone, pay_method, price, qty, rcpt, sub, d_fee, tot, d_name, d_veh, drv_phone = details
                    
                    d_name_display = d_name if d_name else ("Pending Rider Assignment" if d_fee and d_fee > 0 else "Self Pickup / Vendor Delivery")
                    d_veh_display = d_veh if d_veh else "N/A"
                    date_now = datetime.now().strftime("%d %b %Y")
                    
                    receipt_msg = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         AGRO MARKET 🌱
   Agricultural Marketplace
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📄 RECEIPT NUMBER:
{str(rec_num)}

📅 ORDER DATE:
{str(date_now)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👨‍🌾 SELLER DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Seller Name: {str(f_name)}
Phone Number: +{str(f_phone).lstrip('+')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛒 BUYER DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Buyer Name: {str(b_name)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 ORDER DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Product: {str(p_name).upper()}
Quantity: {str(qty)}
Subtotal: SLE {str(sub)}
Delivery Fee: SLE {str(d_fee)}
Platform Fee: SLE 5

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 PAYMENT DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Amount Paid: SLE {str(tot)}

Payment Status:
✅ PAID (FUNDS SECURED IN ESCROW)

Payment Method:
Orange Money / Monime Escrow

Transaction ID:
{str(tx_id)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚚 DELIVERY DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rider/Driver Name: {str(d_name_display)}
Vehicle Type: {str(d_veh_display)}

Delivery Status:
⏳ AWAITING DISPATCH / PICKUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

                    buyer_msg = f"💳 *Payment Successful!* Your payment of SLE {total_amt} for Order #{order_id} has been secured in escrow.\n\nHere is your official order receipt:\n\n{receipt_msg}\n\n*Important:* Once you receive your item, reply with:\n*A.* Confirm Delivery\n*B.* Not Received"
                    send_whatsapp_message(b_phone, buyer_msg)
                    
                    seller_msg = f"💰 *Escrow Funded Notification!* The buyer has secured payment for Order #{order_id}. Proceed with handover/delivery immediately.\n\n{receipt_msg}"
                    send_whatsapp_message(f_phone, seller_msg)
                    
                    if drv_phone:
                        driver_msg = f"🚚 *Delivery Authorized!*\n\nOrder #{order_id} has been paid for by the buyer. Please proceed with the delivery route."
                        send_whatsapp_message(drv_phone, driver_msg)
                
            cursor.close()
            conn.close()
    except Exception as e: pass
    return {"status": "processed"}

# ========================================================
# Helper Function to Trigger Payment Link Generation
# ========================================================
def generate_payment_link(order_id, action_user_phone=None):
    try:
        order_details = get_order_by_id(order_id)
        if not order_details: return
        _, p_name, b_phone, b_name, status, pref, pay_method, receipt, subtotal, d_fee, total_amt, wallet = order_details
        
        update_order_status(order_id, "AWAITING_PAYMENT")
        
        token = os.getenv("MONIME_SECRET_KEY")
        space_id = os.getenv("MONIME_SPACE_ID")
        unique_idempotency_token = f"key_{order_id}_{secrets.token_hex(8)}"
        
        monime_payload = {
            "name": f"Agro Market Order #{order_id}",
            "reference": str(order_id),
            "successUrl": "https://agro-market-bot.onrender.com/admin", 
            "cancelUrl": "https://agro-market-bot.onrender.com/admin",
            "lineItems": [
                {
                    "type": "custom",
                    "name": str(p_name).upper(),
                    "price": {
                        "currency": "SLE",
                        "value": int(total_amt) * 100 
                    },
                    "quantity": 1
                }
            ]
        }
        
        monime_headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": unique_idempotency_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        api_url = "https://api.monime.io/v1/checkout-sessions"
        if token and str(token).startswith("mon_test_"):
            api_url = "https://api.sandbox.monime.io/v1/checkout-sessions"
            monime_headers["X-Space-Id"] = str(space_id).strip()
        else:
            if space_id:
                monime_headers["Monime-Space-Id"] = str(space_id).strip()
        
        response = requests.post(api_url, headers=monime_headers, json=monime_payload, timeout=15)
        
        if response.status_code in [200, 201]:
            res_data = response.json()
            live_url = res_data.get("result", {}).get("redirectUrl") or res_data.get("redirectUrl") or res_data.get("result", {}).get("url") or res_data.get("url")
            
            if live_url:
                summary = f"📦 *Order Summary:*\nProduct: {p_name.upper()}\nSubtotal: SLE {subtotal}\nDelivery Fee: SLE {d_fee}\nPlatform Fee: SLE 5\n*Total Payable: SLE {total_amt}*"
                send_whatsapp_message(b_phone, f"🎉 *Good News!* The final availability has been confirmed.\n\n{summary}\n\n🔗 *Monime Live Payment Link:*\n{live_url}")
            else:
                if action_user_phone: send_whatsapp_message(action_user_phone, f"⚠️ API Success, but URL token string missing: {res_data}")
        else:
            if action_user_phone: send_whatsapp_message(action_user_phone, f"❌ *Monime API Rejected the Payload!*\nStatus Code: {response.status_code}\nError Details: {response.text}")
            simulated_paylink = f"https://agro-market-bot.onrender.com/checkout/pay/{order_id}"
            send_whatsapp_message(b_phone, f"🎉 *Order Confirmed!* (Fallback Simulator Link):\n🔗 {simulated_paylink}")
            
    except Exception as api_err:
        if action_user_phone: send_whatsapp_message(action_user_phone, f"❌ *Connection Exception details caught:* {str(api_err)}")
        simulated_paylink = f"https://agro-market-bot.onrender.com/checkout/pay/{order_id}"
        send_whatsapp_message(b_phone, f"🔗 Fallback Simulator Link:\n{simulated_paylink}")
        
    if action_user_phone:
        update_session(action_user_phone, "main_menu", "idle")
        send_whatsapp_message(action_user_phone, "✅ Buyer has been notified to complete payment.")
        prof = get_user_profile(action_user_phone)
        if prof and prof.get("is_approved"):
            send_main_menu(action_user_phone, prof["role"], prof.get("language", "english"))

def assign_driver_update_fee(order_id, driver_phone, fee):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET driver_phone = %s, delivery_fee = %s, total_amount = subtotal + 5 + %s WHERE id = %s", (driver_phone, fee, fee, order_id))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

def update_user_momo(phone_number, momo):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET momo_number = %s WHERE phone = %s", (momo, phone_number))
        cursor.execute("UPDATE user_sessions SET current_step = 'awaiting_location' WHERE phone = %s", (phone_number,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

# ========================================================
# MAIN WEBHOOK - ALL FEATURES + TEXT NAVIGATION
# ========================================================
@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    try:
        entry = body.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        
        if "messages" in value:
            message_data = value["messages"][0]
            sender_phone = message_data["from"]
            msg_type = message_data.get("type")
            profile = get_user_profile(sender_phone)
            
            if msg_type in ["audio", "voice"]:
                send_whatsapp_message(sender_phone, "🎙️ *Voice Note Processing...*\n_Simulated AI Translation:_ 'Menu'")
                if not profile:
                    create_user_with_language(sender_phone, "english")
                update_session(sender_phone, "onboarding", "awaiting_role")
                send_role_menu(sender_phone, profile.get("language", "english") if profile else "english")
                return {"status": "ok"}
            
            elif msg_type == "location":
                if profile and profile.get("step") == "awaiting_location":
                    lat = message_data["location"]["latitude"]
                    long = message_data["location"]["longitude"]
                    address = message_data["location"].get("name", f"Location: {lat}, {long}")
                    
                    is_approved = update_user_location_and_finish(sender_phone, address)
                    if is_approved:
                        send_whatsapp_message(sender_phone, f"📍 Location Saved: {address}\n\n✅ Registration Complete! 🎉")
                        fresh_profile = get_user_profile(sender_phone)
                        send_main_menu(sender_phone, fresh_profile["role"], fresh_profile["language"])
                    else:
                        send_whatsapp_message(sender_phone, "✅ Registration Complete!\n\n⏳ Your profile has been successfully submitted and is *pending admin approval*. You will be notified as soon as you are verified to use the platform.")
                return {"status": "ok"}
            
            elif msg_type == "image":
                if profile and profile.get("step") == "awaiting_produce_image":
                    image_id = message_data["image"]["id"]
                    category = 'input' if profile["flow"] == "add_input" else 'produce'
                    save_new_product(sender_phone, image_id, category=category)
                    update_session(sender_phone, "main_menu", "idle")
                    send_whatsapp_message(sender_phone, "✅ Listing Complete! Your item is now live and buyers can view its image.")
                    if profile.get("is_approved"):
                        send_main_menu(sender_phone, profile["role"], profile.get("language", "english"))
                
                elif profile and profile.get("step") == "awaiting_vehicle_image":
                    image_id = message_data["image"]["id"]
                    try:
                        conn = psycopg2.connect(DATABASE_URL)
                        cursor = conn.cursor()
                        cursor.execute("UPDATE users SET vehicle_image_id = %s WHERE phone = %s", (image_id, sender_phone))
                        cursor.execute("UPDATE user_sessions SET current_step = 'awaiting_momo' WHERE phone = %s", (sender_phone,))
                        conn.commit()
                        cursor.close()
                        conn.close()
                    except: pass
                    send_whatsapp_message(sender_phone, "✅ Vehicle photo saved! Please enter your **Mobile Money (MoMo) Number** for receiving payouts.")
                    
                return {"status": "ok"}

            elif msg_type == "text":
                text = message_data["text"]["body"].strip()
                text_lower = text.lower()
                
                if text_lower in ["a", "a.", "confirm delivery", "confirm"]:
                    process_confirm_delivery(sender_phone, "A")
                    return {"status": "ok"}
                    
                if text_lower in ["b", "b.", "not received", "unconfirmed"]:
                    process_confirm_delivery(sender_phone, "B")
                    return {"status": "ok"}
                
                if text_lower.startswith("accept "):
                    order_id_str = text_lower.replace("accept ", "").strip()
                    if order_id_str.isdigit():
                        order_id = int(order_id_str)
                        order_details = get_order_by_id(order_id)
                        if order_details and profile and profile.get("role") in ["role_farmer", "role_input"]:
                            pref = order_details[5] if order_details else "pickup"
                            
                            if pref == "delivery":
                                update_session_data(sender_phone, {"target_order": order_id})
                                update_session(sender_phone, "manage_order", "awaiting_delivery_choice")
                                send_whatsapp_message(sender_phone, f"✅ Order #{order_id} acknowledged.\n\nThe buyer requested delivery. How will this be handled?\n\n1️⃣ Do Delivery (I will enter the cost)\n2️⃣ Contact Delivery Partner (A platform driver will accept and set a fee)")
                            else:
                                generate_payment_link(order_id, sender_phone)
                    return {"status": "ok"}
                    
                if text_lower.startswith("reject "):
                    order_id_str = text_lower.replace("reject ", "").strip()
                    if order_id_str.isdigit():
                        order_id = int(order_id_str)
                        order_details = get_order_by_id(order_id)
                        if order_details and profile and profile.get("role") in ["role_farmer", "role_input"]:
                            b_phone = order_details[2] if order_details else ""
                            p_name = order_details[1] if order_details else "item"
                            
                            update_order_status(order_id, "DECLINED")
                            send_whatsapp_message(sender_phone, f"❌ Request #{order_id} rejected.")
                            send_whatsapp_message(b_phone, f"遭遇 😔 Unfortunately, the seller declined your request for {p_name}. Try ordering from another listing.")
                            update_session(sender_phone, "main_menu", "idle")
                    return {"status": "ok"}
                
                if text_lower in ["hi", "hello", "menu"]:
                    if profile and profile.get("role"):
                        if not profile.get("is_approved"):
                            send_whatsapp_message(sender_phone, "⏳ Your account is currently under review by our Admin team. We will notify you once approved to access the dashboard!")
                        else:
                            update_session(sender_phone, "main_menu", "idle")
                            send_main_menu(sender_phone, profile["role"], profile.get("language", "english"))
                    else:
                        if not profile:
                            create_user_with_language(sender_phone, "english")
                        update_session(sender_phone, "onboarding", "awaiting_role")
                        send_role_menu(sender_phone, "english")
                    return {"status": "ok"}

                flow = profile.get("flow")
                step = profile.get("step")
                
                if flow == "pending_approval":
                    send_whatsapp_message(sender_phone, "⏳ Your profile is still pending admin approval. Please wait for the confirmation message to access platform features.")
                    return {"status": "ok"}

                if flow == "onboarding":
                    if step == "awaiting_language":
                        if text_lower == "1": lang = "english"
                        elif text_lower == "2": lang = "krio"
                        else:
                            send_whatsapp_message(sender_phone, "Invalid. Reply 1 for English or 2 for Krio.")
                            return {"status": "ok"}
                        create_user_with_language(sender_phone, lang)
                        update_session(sender_phone, "onboarding", "awaiting_role")
                        send_role_menu(sender_phone, lang)
                    elif step == "awaiting_role":
                        roles = {"1": "role_farmer", "2": "role_buyer", "3": "role_input", "4": "role_driver"}
                        if text_lower in roles:
                            is_registered = update_user_role(sender_phone, roles[text_lower])
                            if is_registered:
                                send_main_menu(sender_phone, roles[text_lower], profile.get("language", "english"))
                            else: 
                                send_whatsapp_message(sender_phone, "Awesome! Let's get you registered.\n\nPlease type your *Full Name*.")
                        else: 
                            send_whatsapp_message(sender_phone, "Invalid. Please reply with 1, 2, 3, or 4.")

                elif flow == "registration":
                    if step == "awaiting_name":
                        update_user_name_and_step(sender_phone, text)
                        fresh_prof = get_user_profile(sender_phone)
                        if fresh_prof:
                            if fresh_prof["role"] == "role_driver":
                                send_whatsapp_message(sender_phone, "Responded! 1️⃣ Logistics Profile Detected!\n\nPlease type your **Vehicle License Plate Number** (e.g., AEK-458).")
                            elif fresh_prof["role"] == "role_buyer":
                                send_whatsapp_message(sender_phone, "Thanks! Now share your delivery location 📍 OR type your district/city.")
                            else:
                                send_whatsapp_message(sender_phone, "Thanks! Please enter your **Mobile Money (MoMo) Number** for receiving payouts.")
                    elif step == "awaiting_vehicle":
                        update_user_vehicle(sender_phone, text.upper())
                        send_whatsapp_message(sender_phone, "Vehicle linked successfully. 📸 Now, please send a *Photo* of your vehicle (Car/Van/Bike).")
                    elif step == "awaiting_vehicle_image":
                        send_whatsapp_message(sender_phone, "Please upload an actual image 📸 of your vehicle.")
                    elif step == "awaiting_momo":
                        update_user_momo(sender_phone, text)
                        send_whatsapp_message(sender_phone, "✅ MoMo Number saved! Now share your delivery location 📍 OR type your district/city.")
                    elif step == "awaiting_location":
                        is_approved = update_user_location_and_finish(sender_phone, text)
                        fresh_profile = get_user_profile(sender_phone)
                        if is_approved:
                            send_whatsapp_message(sender_phone, "✅ Registration Complete! 🎉")
                            send_main_menu(sender_phone, fresh_profile["role"], fresh_profile["language"])
                        else:
                            send_whatsapp_message(sender_phone, "✅ Registration Complete!\n\n⏳ Your profile has been submitted and is *pending admin approval*. We will message you as soon as you are verified to use the platform.")

                elif flow in ["add_produce", "add_input"]:
                    if step == "awaiting_produce_name":
                        update_session_data(sender_phone, {"produce_name": text})
                        update_session(sender_phone, flow, "awaiting_produce_quantity")
                        send_whatsapp_message(sender_phone, f"Got it: *{text}*. How much do you have available? (e.g., 50 bags, 200kg)")
                    elif step == "awaiting_produce_quantity":
                        update_session_data(sender_phone, {"produce_quantity": text})
                        update_session(sender_phone, flow, "awaiting_produce_price")
                        send_whatsapp_message(sender_phone, "Got it. ⚖️ Enter your price per unit/bag.\n\n_OR reply 0️⃣ to use the current market price._")
                    elif step == "awaiting_produce_price":
                        price = text if text_lower != "0" else "Market Price"
                        update_session_data(sender_phone, {"produce_price": price})
                        update_session(sender_phone, flow, "awaiting_produce_image")
                        send_whatsapp_message(sender_phone, "Perfect. 📸 Finally, **send a photo** of the product!")

                elif flow == "main_menu" and step == "idle":
                    role = profile["role"]
                    if role == "role_farmer":
                        if text_lower == "1":
                            update_session(sender_phone, "add_produce", "awaiting_produce_name")
                            send_whatsapp_message(sender_phone, "Great! 🌾 What is the name of the produce?")
                        elif text_lower == "2":
                            inventory = get_user_inventory(sender_phone)
                            if not inventory: send_whatsapp_message(sender_phone, "📦 Inventory is empty.")
                            else:
                                msg = "📦 *Active Inventory:*\n\n"
                                for item in inventory: msg += f"✔️ {item[0]} - {item[1]}\n"
                                send_whatsapp_message(sender_phone, msg)
                        elif text_lower == "3":
                            orders = get_farmer_orders(sender_phone)
                            if not orders: send_whatsapp_message(sender_phone, "✅ No pending orders.")
                            else:
                                msg = "📋 *Pending Requests for Review:*\n\n"
                                for o in orders:
                                    msg_block = f"📦 *Order Request #{o[0]}*\n\nBuyer: {o[2]} (📍 {o[4]})\nProduct: {o[1]}\nPreference: {o[5]}\n\n👉 Reply *ACCEPT {o[0]}* to confirm.\n👉 Reply *REJECT {o[0]}* to decline."
                                    send_whatsapp_message(sender_phone, msg_block)
                        elif text_lower == "4":
                            update_session(sender_phone, "farmer_search", "awaiting_search_query")
                            update_session_data(sender_phone, {"search_category": "input"})
                            send_whatsapp_message(sender_phone, "🚜 What supplies do you need? (e.g., Seeds, Fertilizer)")
                        elif text_lower == "5":
                            prices = get_market_prices()
                            msg = "📊 *Today's Market Prices:*\n\n"
                            for p in prices: msg += f"🌾 {p[0]} (📍 {p[1]}): {p[2]}\n"
                            send_whatsapp_message(sender_phone, msg)
                            
                    elif role == "role_buyer":
                        if text_lower == "1":
                            update_session(sender_phone, "buyer_search", "awaiting_search_query")
                            update_session_data(sender_phone, {"search_category": "produce"})
                            send_whatsapp_message(sender_phone, "🔍 What produce are you looking for? (e.g., Rice, Cassava)")
                        elif text_lower == "2":
                            update_session(sender_phone, "buyer_search", "awaiting_search_query")
                            update_session_data(sender_phone, {"search_category": "input"})
                            send_whatsapp_message(sender_phone, "🚜 What farm inputs are you looking for? (e.g., Fertilizer, Tools)")
                        elif text_lower == "3":
                            orders = get_buyer_orders(sender_phone)
                            if not orders: send_whatsapp_message(sender_phone, "🛒 No recent orders.")
                            else:
                                msg = "🛒 *Recent Orders:*\n\n"
                                for o in orders: 
                                    rcpt_info = f" (Receipt: {o[5]})" if o[5] else ""
                                    msg += f"📦 {o[1]} (Status: {o[2].upper()}){rcpt_info}\n"
                                send_whatsapp_message(sender_phone, msg)
                        elif text_lower == "4":
                            prices = get_market_prices()
                            msg = "📊 *Today's Market Prices:*\n\n"
                            for p in prices: msg += f"🌾 {p[0]} (📍 {p[1]}): {p[2]}\n"
                            send_whatsapp_message(sender_phone, msg)

                    elif role == "role_input":
                        if text_lower == "1":
                            update_session(sender_phone, "add_input", "awaiting_produce_name")
                            send_whatsapp_message(sender_phone, "Great! 🚜 What is the name of the supply/tool?")
                        elif text_lower == "2":
                            inventory = get_user_inventory(sender_phone)
                            if not inventory: send_whatsapp_message(sender_phone, "📦 Inventory is empty.")
                            else:
                                msg = "📦 *Active Inventory:*\n\n"
                                for item in inventory: msg += f"✔️ {item[0]} - {item[1]}\n"
                                send_whatsapp_message(sender_phone, msg)
                        elif text_lower == "3":
                            orders = get_farmer_orders(sender_phone)
                            if not orders: send_whatsapp_message(sender_phone, "✅ No pending orders.")
                            else:
                                msg = "📋 *Pending Orders:*\n\n"
                                for o in orders:
                                    msg_block = f"📦 *Order Request #{o[0]}*\n\nBuyer: {o[2]} (📍 {o[4]})\nProduct: {o[1]}\nPreference: {o[5]}\n\n👉 Reply *ACCEPT {o[0]}* to confirm.\n👉 Reply *REJECT {o[0]}* to decline."
                                    send_whatsapp_message(sender_phone, msg_block)
                        elif text_lower == "4":
                            prices = get_market_prices()
                            msg = "📊 *Today's Market Prices:*\n\n"
                            for p in prices: msg += f"🌾 {p[0]} (📍 {p[1]}): {p[2]}\n"
                            send_whatsapp_message(sender_phone, msg)

                    elif role == "role_driver":
                        if text_lower == "1":
                            deliveries = get_available_deliveries()
                            if not deliveries: send_whatsapp_message(sender_phone, "🚫 No deliveries available right now.")
                            else:
                                msg = "🚚 *Available Deliveries:*\n\n"
                                temp_map = {}
                                for idx, d in enumerate(deliveries, 1):
                                    msg += f"{idx}️⃣ Job #{d[0]} - {d[1]}\n📍 From: {d[3]} ➔ To: {d[5]}\n\n"
                                    temp_map[str(idx)] = d[0]
                                msg += "_Reply with number to View & Accept_"
                                update_session_data(sender_phone, {"deliv_map": temp_map})
                                update_session(sender_phone, "driver_flow", "awaiting_accept")
                                send_whatsapp_message(sender_phone, msg)
                        elif text_lower == "2":
                            my_jobs = get_driver_deliveries(sender_phone)
                            if not my_jobs: send_whatsapp_message(sender_phone, "🚚 No active jobs.")
                            else:
                                msg = "🚚 *My Active Shipments:*\n\n"
                                temp_map = {}
                                for idx, d in enumerate(my_jobs, 1):
                                    msg += f"{idx}️⃣ Job #{d[0]} - {d[1]}\n🎯 Dropoff: {d[6]}\n\n"
                                    temp_map[str(idx)] = d[0]
                                msg += "_Reply with number to Complete Delivery Route_"
                                update_session_data(sender_phone, {"active_map": temp_map})
                                update_session(sender_phone, "driver_flow", "awaiting_complete")
                                send_whatsapp_message(sender_phone, msg)

                # --- SEARCH & PURCHASE FLOW ---
                elif flow in ["buyer_search", "farmer_search"]:
                    if step == "awaiting_search_query":
                        category = get_session_data(sender_phone).get("search_category", "produce") if flow == "buyer_search" else "input"
                        buyer_location = get_user_location(sender_phone)
                        results = search_marketplace(text_lower, category=category, buyer_location=buyer_location)
                        
                        if not results:
                            send_whatsapp_message(sender_phone, f"😔 Nothing found for '{text}'. Type 'menu' to go back.")
                            update_session(sender_phone, "main_menu", "idle")
                        else:
                            msg = f"🔍 Found these for '{text}':\n\n"
                            result_dict = {}
                            for idx, item in enumerate(results, 1):
                                msg += f"{idx}️⃣ {item[1]} - {item[2]} ({item[3]})\n🧑‍🌾 Seller: {item[6]} (📍 {item[7]})\n\n"
                                result_dict[str(idx)] = item[0] 
                            msg += "_Reply with the number to view the item, or type 'menu'_"
                            update_session_data(sender_phone, {"search_results": result_dict})
                            update_session(sender_phone, flow, "awaiting_item_selection")
                            send_whatsapp_message(sender_phone, msg)
                            
                    elif step == "awaiting_item_selection":
                        session_data = get_session_data(sender_phone)
                        results = session_data.get("search_results", {})
                        if text_lower in results:
                            product_id = results[text_lower]
                            details = get_product_by_id(product_id)
                            if details:
                                p_id, p_name, price, qty, img_id, f_phone, f_name, loc = details
                                caption = f"📦 *{p_name}*\n💰 Unit Price: {price}\n⚖️ Available Stock: {qty}\n🧑‍🌾 Seller: {f_name} ({loc})\n\n1️⃣ 🛒 Place Order\n2️⃣ 🔍 Search Again\n\n_Reply 1 or 2_"
                                send_whatsapp_image(sender_phone, img_id, caption)
                                update_session_data(sender_phone, {"temp_buy_id": p_id})
                                update_session(sender_phone, flow, "awaiting_buy_decision")
                        else:
                            send_whatsapp_message(sender_phone, "Invalid number. Please try again.")
                            
                    elif step == "awaiting_buy_decision":
                        if text_lower == "1":
                            update_session(sender_phone, "buyer_checkout", "awaiting_quantity")
                            session_data = get_session_data(sender_phone)
                            prod_id = session_data.get("temp_buy_id")
                            details = get_product_by_id(prod_id)
                            p_name = details[1] if details else "item"
                            send_whatsapp_message(sender_phone, f"🔢 How many units/items of {p_name} do you want to order?\n\n_Reply with a number (e.g., 1, 5, 10)_")
                        elif text_lower == "2":
                            update_session(sender_phone, flow, "awaiting_search_query")
                            send_whatsapp_message(sender_phone, "🔍 What else are you looking for?")

                # --- CHECKOUT FLOW ---
                elif flow == "buyer_checkout":
                    session_data = get_session_data(sender_phone)
                    if step == "awaiting_quantity":
                        if text_lower.isdigit():
                            update_session_data(sender_phone, {"temp_buy_qty": int(text_lower)})
                            update_session(sender_phone, "buyer_checkout", "awaiting_delivery")
                            send_whatsapp_message(sender_phone, "📦 Delivery Selection\n\nHow would you like to receive this?\n1️⃣ Request Local Delivery (Van, Bike, Truck) 🚚\n2️⃣ Self Pickup / Vendor Delivery 🚶\n\n_Reply 1 or 2_")
                        else:
                            send_whatsapp_message(sender_phone, "Invalid quantity. Please reply with a number.")
                            
                    elif step == "awaiting_delivery":
                        if text_lower == "1": 
                            update_session_data(sender_phone, {"temp_delivery_pref": "delivery"})
                            update_session(sender_phone, "buyer_checkout", "awaiting_delivery_address")
                            send_whatsapp_message(sender_phone, "📍 Please type your full name and delivery address (e.g., Abdulai, 32 Kissy Road, Freetown):")
                            return {"status": "ok"}
                        elif text_lower == "2": 
                            pref = "pickup"
                            update_session_data(sender_phone, {"temp_delivery_pref": pref})
                            prod_id = session_data.get("temp_buy_id")
                            order_qty = session_data.get("temp_buy_qty", 1)
                            
                            order_map = create_order(sender_phone, prod_id, pref, "Monime Escrow Hold", order_qty)
                            if order_map:
                                send_whatsapp_message(sender_phone, f"🕒 *Order Submitted!*\nSubtotal: SLE {order_map['subtotal']}\nPlatform Fee: SLE 5\n\nWaiting for seller to confirm stock availability.")
                                farmer_phone = order_map['farmer_phone']
                                alert_msg = f"🚨 *NEW ORDER REQUEST!* 🚨\n\n📦 Item: {order_map['product_name']}\n🔢 Quantity: {order_qty}\n💰 Unit Price: SLE {order_map['price']}\n\n👉 Reply *ACCEPT {order_map['id']}* to confirm availability.\n👉 Reply *REJECT {order_map['id']}* to decline."
                                send_whatsapp_message(farmer_phone, alert_msg)
                            update_session(sender_phone, "main_menu", "idle")
                            return {"status": "ok"}
                        else:
                            send_whatsapp_message(sender_phone, "Invalid. Reply 1 or 2.")
                            return {"status": "ok"}
                            
                    elif step == "awaiting_delivery_address":
                        pref = session_data.get("temp_delivery_pref", "delivery")
                        order_qty = session_data.get("temp_buy_qty", 1)
                        
                        user_input_parts = text.split(",", 1)
                        custom_buyer_name = user_input_parts[0].strip() if len(user_input_parts) > 1 else "Agro Registered Buyer"
                        delivery_address = user_input_parts[1].strip() if len(user_input_parts) > 1 else text.strip()
                        
                        prod_id = session_data.get("temp_buy_id")
                        order_map = create_order(sender_phone, prod_id, pref, "Monime Escrow Hold", order_qty, custom_buyer_name, delivery_address)
                        
                        if order_map:
                            send_whatsapp_message(sender_phone, f"📍 Name & Address Saved.\n\n🕒 *Order Submitted!*\nSubtotal: SLE {order_map['subtotal']}\nPlatform Fee: SLE 5\n\nWaiting for seller to confirm stock and assign a delivery route cost.")
                            farmer_phone = order_map['farmer_phone']
                            
                            alert_msg = f"🚨 *NEW ORDER REQUEST!* 🚨\n\nBuyer Name: {custom_buyer_name}\nAddress: {delivery_address}\nPhone: +{sender_phone}\n\n📦 Item: {order_map['product_name']}\n🔢 Quantity: {order_qty}\n💰 Unit Price: SLE {order_map['price']}\n\n👉 Reply *ACCEPT {order_map['id']}* to confirm availability.\n👉 Reply *REJECT {order_map['id']}* to decline."
                            send_whatsapp_message(farmer_phone, alert_msg)
                        update_session(sender_phone, "main_menu", "idle")

                # --- SELLER ORDER MANAGEMENT ---
                elif flow == "manage_order":
                    session_data = get_session_data(sender_phone)
                    if step == "awaiting_selection":
                        order_map = session_data.get("manage_map", {})
                        if text_lower in order_map:
                            order_id = order_map[text_lower]
                            order_details = get_order_by_id(order_id)
                            if order_details:
                                _, p_name, b_phone, b_name, status, pref, pay_method, receipt, subtotal, d_fee, total_amt, wallet = order_details
                                msg = f"📦 *Manage Request #{order_id}*\n\nBuyer: {b_name}\nItem: {p_name}\nPreference: {pref}\n\n1️⃣ Accept Request ✅\n2️⃣ Reject Order ❌\n\n_Reply 1 or 2_"
                                update_session_data(sender_phone, {"target_order": order_id})
                                update_session(sender_phone, "manage_order", "awaiting_action")
                                send_whatsapp_message(sender_phone, msg)
                        else:
                            send_whatsapp_message(sender_phone, "Invalid selection tracker.")
                            
                    elif step == "awaiting_action":
                        order_id = session_data.get("target_order")
                        order_details = get_order_by_id(order_id)
                        pref = order_details[5] if order_details else "pickup"
                        
                        if text_lower == "1":
                            if pref == "delivery":
                                update_session(sender_phone, "manage_order", "awaiting_delivery_choice")
                                send_whatsapp_message(sender_phone, "The buyer requested delivery. How will this be handled?\n\n1️⃣ Do Delivery (I will enter the cost)\n2️⃣ Contact Delivery Partner (A platform driver will accept and set a fee)")
                            else:
                                generate_payment_link(order_id, sender_phone)
                        elif text_lower == "2":
                            b_phone = order_details[2] if order_details else ""
                            p_name = order_details[1] if order_details else "item"
                            update_order_status(order_id, "DECLINED")
                            send_whatsapp_message(sender_phone, f"❌ Request #{order_id} rejected.")
                            send_whatsapp_message(b_phone, f"遭遇 😔 Unfortunately, the seller declined your request for {p_name}. Try ordering from another listing.")
                            update_session(sender_phone, "main_menu", "idle")
                            if profile.get("is_approved"):
                                send_main_menu(sender_phone, profile["role"], profile.get("language", "english"))
                        else:
                            send_whatsapp_message(sender_phone, "Invalid option. Reply 1 or 2.")
                    
                    elif step == "awaiting_delivery_choice":
                        order_id = session_data.get("target_order")
                        if text_lower == "1":
                            update_session(sender_phone, "manage_order", "awaiting_delivery_fee")
                            send_whatsapp_message(sender_phone, "Enter the delivery cost in SLE (e.g., 20):")
                        elif text_lower == "2":
                            update_order_status(order_id, "AWAITING_DRIVER")
                            update_session(sender_phone, "main_menu", "idle")
                            send_whatsapp_message(sender_phone, "✅ Request sent to delivery partners! The buyer will receive a payment link once a driver accepts and provides a fee.")
                            if profile.get("is_approved"):
                                send_main_menu(sender_phone, profile["role"], profile.get("language", "english"))
                        else:
                            send_whatsapp_message(sender_phone, "Invalid option. Reply 1 or 2.")
                                
                    elif step == "awaiting_delivery_fee":
                        order_id = session_data.get("target_order")
                        if text_lower.isdigit():
                            fee = int(text_lower)
                            try:
                                conn = psycopg2.connect(DATABASE_URL)
                                cursor = conn.cursor()
                                cursor.execute("UPDATE orders SET delivery_fee = %s, total_amount = subtotal + 5 + %s WHERE id = %s", (fee, fee, order_id))
                                conn.commit()
                                cursor.close()
                                conn.close()
                            except: pass
                            generate_payment_link(order_id, sender_phone)
                        else:
                            send_whatsapp_message(sender_phone, "Please enter a valid number for the fee.")

                # --- DRIVER FLOW ---
                elif flow == "driver_flow":
                    session_data = get_session_data(sender_phone)
                    if step == "awaiting_accept":
                        job_map = session_data.get("deliv_map", {})
                        if text_lower in job_map:
                            order_id = job_map[text_lower]
                            details = get_delivery_details(order_id)
                            if details:
                                o_id, p_name, f_name, f_loc, f_phone, b_name, b_loc, b_phone, *rest = details
                                msg = f"🚚 *Delivery Job #{o_id}*\n\n📦 Item: {p_name}\n📍 Pickup: {f_name} ({f_loc})\n🎯 Dropoff: {b_name} ({b_loc})\n\n1️⃣ Accept Job ✅\n2️⃣ Cancel ❌\n\n_Reply 1 or 2_"
                                update_session_data(sender_phone, {"target_job": order_id})
                                update_session(sender_phone, "driver_flow", "awaiting_confirm_accept")
                                send_whatsapp_message(sender_phone, msg)
                        else:
                            send_whatsapp_message(sender_phone, "Invalid number.")
                    elif step == "awaiting_confirm_accept":
                        order_id = session_data.get("target_job")
                        if text_lower == "1":
                            update_session(sender_phone, "driver_flow", "awaiting_driver_fee")
                            send_whatsapp_message(sender_phone, f"Please enter your required delivery fee for Job #{order_id} in SLE (e.g., 35):")
                        else:
                            update_session(sender_phone, "main_menu", "idle")
                            send_whatsapp_message(sender_phone, "Job discarded. Type 'menu' to return to dashboard.")
                            if profile.get("is_approved"):
                                send_main_menu(sender_phone, profile["role"], profile.get("language", "english"))
                    elif step == "awaiting_driver_fee":
                        order_id = session_data.get("target_job")
                        if text_lower.isdigit():
                            fee = int(text_lower)
                            if assign_driver_update_fee(order_id, sender_phone, fee):
                                update_session(sender_phone, "main_menu", "idle")
                                send_whatsapp_message(sender_phone, f"✅ You've claimed Order #{order_id} with a fee of SLE {fee}. The buyer has been sent the final payment link!")
                                generate_payment_link(order_id)
                                if profile.get("is_approved"):
                                    send_main_menu(sender_phone, profile["role"], profile.get("language", "english"))
                            else:
                                send_whatsapp_message(sender_phone, "❌ Delivery match claimed by another agent.")
                        else:
                            send_whatsapp_message(sender_phone, "Please enter a valid numeric fee.")
                            
                    elif step == "awaiting_complete":
                        job_map = session_data.get("active_map", {})
                        if text_lower in job_map:
                            order_id = job_map[text_lower]
                            details = get_delivery_details(order_id)
                            if details:
                                o_id, p_name, _, _, f_phone, b_name, _, b_phone, *rest = details
                                msg = f"🚚 *Job #{o_id} In Progress*\n\n📦 Item: {p_name}\n🎯 Dropoff: {b_name}\n📞 Seller: wa.me/{f_phone}\n📞 Buyer: wa.me/{b_phone}\n\n1️⃣ Mark Package Delivered ✅\n2️⃣ Cancel Route ❌\n\n_Reply 1 or 2_"
                                update_session_data(sender_phone, {"target_job": order_id})
                                update_session(sender_phone, "driver_flow", "awaiting_complete")
                                send_whatsapp_message(sender_phone, msg)
                        else:
                            send_whatsapp_message(sender_phone, "Invalid number.")
                    elif step == "awaiting_confirm_complete":
                        order_id = session_data.get("target_job")
                        if text_lower == "1":
                            update_order_status(order_id, "DELIVERED")
                            send_whatsapp_message(sender_phone, f"✅ Job #{order_id} flagged as delivered! Awaiting buyer completion approval to clear system escrow parameters.")
                            details = get_delivery_details(order_id)
                            if details:
                                _, p_name, _, _, f_phone, _, _, b_phone, *rest = details
                                send_whatsapp_message(f_phone, f"🚚 Delivery complete for Job #{order_id}. Awaiting buyer validation parameter to release cash holdings.")
                                send_whatsapp_message(b_phone, f"🔔 *Delivery Arrival Notification!*\n\nYour order of *{p_name}* has been dropped off. Please check the package and reply with:\n\n*A.* Confirm Delivery\n*B.* Not Received")
                        update_session(sender_phone, "main_menu", "idle")
                        if profile.get("is_approved"):
                            send_main_menu(sender_phone, profile["role"], profile.get("language", "english"))

        return {"status": "ok"}
    except Exception as e:
        print(f"Error logic layer main arrays: {e}")
    return {"status": "ok"}
