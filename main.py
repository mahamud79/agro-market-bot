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

@app.on_event("startup")
async def startup_event():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        print("\n" + "="*50)
        print("✅ Successfully connected to Supabase!")
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

# --- TEXT-BASED DICTIONARY (UPDATED TO MATCH SCRIPT) ---
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

# --- COMMUNICATION WRAPPERS ---
def send_whatsapp_message(phone_number, message_text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message_text}
    }
    requests.post(url, headers=headers, json=payload)

def send_whatsapp_image(phone_number, image_id, caption_text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "image",
        "image": {
            "id": image_id,
            "caption": caption_text
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_language_menu(phone_number):
    msg = "🌍 Welcome to Agro Market! / Wɛlkɔm to Agro Makit!\n\nPlease select your preferred language:\n\n1️⃣ English\n2️⃣ Krio\n\n_Reply with 1 or 2_"
    send_whatsapp_message(phone_number, msg)

def send_role_menu(phone_number, lang="english"):
    t = LANGUAGES.get(lang, LANGUAGES["english"])
    send_whatsapp_message(phone_number, t["welcome"])

def send_main_menu(phone_number, role, lang="english"):
    t = LANGUAGES.get(lang, LANGUAGES["english"])
    menus = {
        "role_farmer": t["farmer_menu"],
        "role_buyer": t["buyer_menu"],
        "role_driver": t["driver_menu"],
        "role_input": t["input_menu"]
    }
    send_whatsapp_message(phone_number, menus.get(role, "Menu unavailable."))

# --- DATABASE FUNCTIONS ---
def get_user_profile(phone_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT u.role, u.nin_status, u.language, us.current_flow, us.current_step, u.name FROM users u LEFT JOIN user_sessions us ON u.phone = us.phone WHERE u.phone = %s", (phone_number,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result: return {"role": result[0], "nin_status": result[1], "language": result[2] or "english", "flow": result[3], "step": result[4], "name": result[5]}
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
    except Exception as e: print(f"DB Error session: {e}")

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
        return result[0] if result and result[0] else {}
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
    except Exception as e: print(f"DB Error save: {e}")

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

def create_order(buyer_phone, product_id, preference, payment_method):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT product_name, farmer_phone, price FROM products WHERE id = %s", (product_id,))
        prod = cursor.fetchone()
        if not prod: return None
        prod_name, farmer_phone, price = prod
        cursor.execute("INSERT INTO orders (buyer_phone, farmer_phone, product_id, product_name, status, delivery_preference, payment_method) VALUES (%s, %s, %s, %s, 'pending', %s, %s)", (buyer_phone, farmer_phone, product_id, prod_name, preference, payment_method))
        conn.commit()
        cursor.close()
        conn.close()
        return {"farmer_phone": farmer_phone, "product_name": prod_name, "price": price}
    except: return None

def get_farmer_orders(farmer_phone):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.id, o.product_name, u.name, u.phone, u.location, o.delivery_preference, o.payment_method
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
        cursor.execute("SELECT o.id, o.product_name, o.status, u.name, u.phone FROM orders o JOIN users u ON o.farmer_phone = u.phone WHERE o.buyer_phone = %s ORDER BY o.created_at DESC", (buyer_phone,))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def get_order_by_id(order_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT o.id, o.product_name, o.buyer_phone, u.name, o.status, o.delivery_preference, o.payment_method FROM orders o JOIN users u ON o.buyer_phone = u.phone WHERE o.id = %s", (order_id,))
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
            WHERE o.status = 'ACCEPTED' AND o.delivery_preference = 'delivery' ORDER BY o.created_at DESC LIMIT 5
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
            SELECT o.id, o.product_name, f.name AS farmer_name, f.location AS farmer_loc, f.phone AS farmer_phone, b.name AS buyer_name, b.location AS buyer_loc, b.phone AS buyer_phone
            FROM orders o JOIN users f ON o.farmer_phone = f.phone JOIN users b ON o.buyer_phone = b.phone WHERE o.id = %s
        """, (order_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result
    except: return None

def assign_driver_to_order(order_id, driver_phone):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'IN_TRANSIT', driver_phone = %s WHERE id = %s", (driver_phone, order_id))
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
            WHERE o.driver_phone = %s AND o.status = 'IN_TRANSIT' ORDER BY o.created_at DESC
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

# --- NEW SMART ROLE UPDATER ---
def update_user_role(phone_number, role_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = %s WHERE phone = %s", (role_id, phone_number))
        cursor.execute("SELECT name, location FROM users WHERE phone = %s", (phone_number,))
        user = cursor.fetchone()
        
        # If user already registered fully, skip registration flow!
        if user and user[0] and user[1]:
            cursor.execute("UPDATE user_sessions SET current_flow = 'main_menu', current_step = 'idle' WHERE phone = %s", (phone_number,))
            is_registered = True
        else:
            cursor.execute("INSERT INTO user_sessions (phone, current_flow, current_step) VALUES (%s, 'registration', 'awaiting_name') ON CONFLICT (phone) DO UPDATE SET current_flow = EXCLUDED.current_flow, current_step = EXCLUDED.current_step;", (phone_number,))
            is_registered = False
            
        conn.commit()
        cursor.close()
        conn.close()
        return is_registered
    except Exception as e:
        print(f"Role Update Error: {e}")
        return False

def update_user_name_and_step(phone_number, name):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET name = %s WHERE phone = %s", (name, phone_number))
        cursor.execute("UPDATE user_sessions SET current_step = 'awaiting_nin' WHERE phone = %s", (phone_number,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

# --- INSTANT AUTO VERIFICATION UPDATE ---
def update_user_nin_and_step(phone_number, nin):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET nin_number = %s, nin_status = 'verified' WHERE phone = %s", (nin, phone_number))
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
        cursor.execute("UPDATE users SET location = %s WHERE phone = %s", (location, phone_number))
        cursor.execute("UPDATE user_sessions SET current_flow = 'main_menu', current_step = 'idle' WHERE phone = %s", (phone_number,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
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

def get_pending_verifications():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT name, phone, role, nin_number FROM users WHERE nin_status = 'pending' AND role != 'role_buyer'")
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def approve_user_nin(phone_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET nin_status = 'verified' WHERE phone = %s", (phone_number,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

def reject_user_nin(phone_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE phone = %s", (phone_number,))
        cursor.execute("DELETE FROM user_sessions WHERE phone = %s", (phone_number,))
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


# ========================================================
# PRIVACY POLICY (FOR META APPROVAL)
# ========================================================
@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    return """
    <html>
        <head><title>Privacy Policy - Agro Market</title></head>
        <body style="font-family: Arial; padding: 40px;">
            <h1>Privacy Policy for Agro Market Bot</h1>
            <p>This service connects farmers and buyers via WhatsApp.</p>
            <p>We only collect data necessary for deliveries (phone number, location) and do not sell your data to third parties.</p>
        </body>
    </html>
    """

# ========================================================
# SECURE ADMIN WEB DASHBOARD ROUTES (PASSWORD + OTP RESET)
# ========================================================

def hash_password(password: str):
    """Securely scrambles the password using built-in SHA-256"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

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

@app.get("/admin/login", response_class=HTMLResponse)
async def login_page():
    # 1. Main Login Form (Only asks for password)
    # 2. Change Password button (Triggers WhatsApp OTP)
    return """
    <html>
        <body style="font-family: Arial; padding: 50px; text-align: center; background-color: #f4f7f6;">
            <div style="background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 400px; margin: auto;">
                <h2 style="color: #2E7D32;">Admin Login</h2>
                <form action="/admin/process-login" method="post">
                    <input type="password" name="password" placeholder="Enter Password" required style="padding: 10px; width: 100%; margin-bottom: 20px; border: 1px solid #ccc; border-radius: 4px;">
                    <button type="submit" style="background-color: #2E7D32; color: white; border: none; padding: 12px 20px; width: 100%; border-radius: 4px; cursor: pointer; font-weight: bold;">Login</button>
                </form>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 25px 0;">
                <form action="/admin/trigger-reset" method="post" style="margin:0;">
                    <button type="submit" style="background-color: transparent; color: #555; border: none; cursor: pointer; text-decoration: underline;">Change / Forgot Password?</button>
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
        cursor.execute("SELECT password_hash FROM admin_auth WHERE phone = %s", (ADMIN_PHONE,))
        result = cursor.fetchone()
        
        if result and result[0]:
            db_hash = result[0]
            # Check if entered password matches DB hash
            if hash_password(password) == db_hash:
                session_token = secrets.token_hex(32)
                cursor.execute("UPDATE admin_auth SET session_token = %s WHERE phone = %s", (session_token, ADMIN_PHONE))
                conn.commit()
                cursor.close()
                conn.close()
                
                response = RedirectResponse(url="/admin", status_code=302)
                response.set_cookie(key="secure_admin_session", value=session_token, httponly=True, secure=True, max_age=86400)
                return response
                
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Login Error: {e}")
        
    return HTMLResponse("<script>alert('Invalid Password. If this is your first time, click Change Password.'); window.location.href='/admin/login';</script>")

@app.post("/admin/trigger-reset")
async def trigger_reset():
    otp = str(random.randint(100000, 999999))
    expires = datetime.now() + timedelta(minutes=5)
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO admin_auth (phone, otp_code, expires_at) VALUES (%s, %s, %s) ON CONFLICT (phone) DO UPDATE SET otp_code = EXCLUDED.otp_code, expires_at = EXCLUDED.expires_at;", (ADMIN_PHONE, otp, expires))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Reset DB Error: {e}")
        return HTMLResponse("<script>alert('Database Error.'); window.location.href='/admin/login';</script>")
    
    send_whatsapp_message(ADMIN_PHONE, f"🔒 *Agro Market Password Reset*\n\nYour security code to change the admin dashboard password is: *{otp}*\n\nThis code expires in 5 minutes.")
    
    return f"""
    <html>
        <body style="font-family: Arial; padding: 50px; text-align: center; background-color: #f4f7f6;">
            <div style="background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 400px; margin: auto;">
                <h2 style="color: #2E7D32;">Change Password</h2>
                <p>We just sent a 6-digit code to the Admin WhatsApp number.</p>
                <form action="/admin/save-new-password" method="post">
                    <input type="text" name="otp" placeholder="6-digit WhatsApp Code" required style="padding: 10px; width: 100%; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; text-align: center; font-size: 18px; letter-spacing: 3px;">
                    <input type="password" name="new_password" placeholder="New Password" required style="padding: 10px; width: 100%; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px;">
                    <input type="password" name="confirm_password" placeholder="Confirm New Password" required style="padding: 10px; width: 100%; margin-bottom: 20px; border: 1px solid #ccc; border-radius: 4px;">
                    <button type="submit" style="background-color: #2E7D32; color: white; border: none; padding: 12px 20px; width: 100%; border-radius: 4px; cursor: pointer; font-weight: bold;">Set Password & Login</button>
                </form>
            </div>
        </body>
    </html>
    """

@app.post("/admin/save-new-password")
async def save_new_password(request: Request):
    form_data = await request.form()
    user_otp = form_data.get("otp")
    new_pwd = form_data.get("new_password")
    conf_pwd = form_data.get("confirm_password")
    
    if new_pwd != conf_pwd:
        return HTMLResponse("<script>alert('Passwords do not match!'); window.history.back();</script>")
        
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT otp_code, expires_at FROM admin_auth WHERE phone = %s", (ADMIN_PHONE,))
        result = cursor.fetchone()
        
        if result:
            db_otp, expires_at = result
            if user_otp == db_otp and datetime.now() < expires_at:
                # OTP is valid! Hash new password and create login session
                new_hash = hash_password(new_pwd)
                session_token = secrets.token_hex(32)
                
                cursor.execute("UPDATE admin_auth SET password_hash = %s, session_token = %s WHERE phone = %s", (new_hash, session_token, ADMIN_PHONE))
                conn.commit()
                cursor.close()
                conn.close()
                
                response = RedirectResponse(url="/admin", status_code=302)
                response.set_cookie(key="secure_admin_session", value=session_token, httponly=True, secure=True, max_age=86400)
                return response
                
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Save Pwd Error: {e}")
        
    return HTMLResponse("<script>alert('Invalid or expired code. Please try again.'); window.location.href='/admin/login';</script>")

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not is_admin_authorized(request): return RedirectResponse(url="/admin/login")

    pending_users = get_pending_verifications()
    market_prices = get_market_prices(include_id=True)
    stats = get_dashboard_stats()
    
    html_content = f"""
    <html>
        <head>
            <title>Agro Market Admin Panel</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; padding: 40px; }}
                h1 {{ color: #2E7D32; }}
                h2 {{ color: #333; margin-top: 40px; border-bottom: 2px solid #2E7D32; padding-bottom: 10px; }}
                table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.2); margin-bottom: 20px;}}
                th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #2E7D32; color: white; }}
                .btn {{ color: white; border: none; padding: 8px 15px; text-align: center; border-radius: 5px; cursor: pointer; font-weight: bold;}}
                .btn-approve {{ background-color: #4CAF50; }}
                .btn-approve:hover {{ background-color: #45a049; }}
                .btn-reject {{ background-color: #f44336; }}
                .btn-reject:hover {{ background-color: #da190b; }}
                .btn-add {{ background-color: #008CBA; padding: 10px 20px;}}
                .btn-add:hover {{ background-color: #007399; }}
                .empty {{ color: #555; font-style: italic; }}
                .action-form {{ display: inline-block; margin: 0; }}
                .add-form {{ background: white; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.2); border-radius: 5px;}}
                input[type=text] {{ padding: 10px; margin: 5px 10px 5px 0; border: 1px solid #ccc; border-radius: 4px; width: 25%;}}
                .stats-container {{ display: flex; gap: 20px; margin-bottom: 40px; }}
                .stat-card {{ background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); flex: 1; text-align: center; border-top: 5px solid #2E7D32; }}
                .stat-card h3 {{ margin: 0; color: #555; font-size: 16px; text-transform: uppercase; letter-spacing: 1px; }}
                .stat-card p {{ margin: 15px 0 0; font-size: 36px; font-weight: bold; color: #2E7D32; }}
                .logout-btn {{ float: right; background-color: #555; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <a href="/admin/logout" class="logout-btn">🔒 Logout</a>
            <h1>🛡️ Agro Market Admin Dashboard</h1>
            <div class="stats-container">
                <div class="stat-card">
                    <h3>👥 Total Users</h3><p>{stats['total_users']}</p>
                </div>
                <div class="stat-card">
                    <h3>🛒 Active Orders</h3><p>{stats['active_orders']}</p>
                </div>
                <div class="stat-card">
                    <h3>✅ Total Deliveries</h3><p>{stats['total_deliveries']}</p>
                </div>
            </div>
            <h2>⏳ Pending User Verifications</h2>
            <table>
                <tr>
                    <th>Full Name</th><th>Phone Number</th><th>Requested Role</th><th>NIN Number</th><th>Action</th>
                </tr>
    """
    
    if not pending_users:
        html_content += "<tr><td colspan='5' class='empty'>No pending verifications at this time.</td></tr>"
    else:
        for u in pending_users:
            name, phone, role, nin = u
            display_role = role.replace("role_", "").capitalize()
            html_content += f"""
                <tr>
                    <td>{name}</td><td>{phone}</td><td>{display_role}</td><td><b>{nin}</b></td>
                    <td>
                        <form action="/admin/verify/{phone}" method="post" class="action-form">
                            <button type="submit" class="btn btn-approve">✅ Approve</button>
                        </form>
                        <form action="/admin/reject/{phone}" method="post" class="action-form" onsubmit="return confirm('Are you sure you want to completely reject and delete this user?');">
                            <button type="submit" class="btn btn-reject">❌ Reject</button>
                        </form>
                    </td>
                </tr>
            """
            
    html_content += """
            </table>
            <h2>📈 Daily Market Price Management</h2>
            <table>
                <tr>
                    <th>Crop / Item Name</th><th>Location</th><th>Current Price</th><th>Action</th>
                </tr>
    """
    
    if not market_prices:
        html_content += "<tr><td colspan='4' class='empty'>No market prices currently set.</td></tr>"
    else:
        for p in market_prices:
            p_id, crop, loc, price = p
            html_content += f"""
                <tr>
                    <td>{crop}</td><td>{loc}</td><td><b>{price}</b></td>
                    <td>
                        <form action="/admin/price/delete/{p_id}" method="post" class="action-form">
                            <button type="submit" class="btn btn-reject">🗑️ Remove</button>
                        </form>
                    </td>
                </tr>
            """
            
    html_content += """
            </table>
            <div class="add-form">
                <h3>➕ Add New Market Price</h3>
                <form action="/admin/price/add" method="post">
                    <input type="text" name="crop_name" placeholder="e.g., Cassava" required>
                    <input type="text" name="location" placeholder="e.g., Makeni" required>
                    <input type="text" name="price" placeholder="e.g., Le 500" required>
                    <button type="submit" class="btn btn-add">Add Price to Dashboard</button>
                </form>
            </div>
        </body>
    </html>
    """
    return html_content

@app.get("/admin/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("secure_admin_session")
    return response

# --- SECURED POST ROUTES ---
@app.post("/admin/verify/{phone}")
async def verify_user(phone: str, request: Request):
    if not is_admin_authorized(request): return HTMLResponse("<script>alert('Unauthorized'); window.location.href='/admin/login';</script>")
    if approve_user_nin(phone):
        send_whatsapp_message(phone, "🎉 *Identity Verified!*\n\nYour NIN has been successfully reviewed by our admin team. You are now a trusted and verified member of Agro Market.\n\nType *'menu'* to access your full dashboard.")
    return HTMLResponse("<script>alert('User Successfully Verified! They have been notified via WhatsApp.'); window.location.href='/admin';</script>")

@app.post("/admin/reject/{phone}")
async def reject_user(phone: str, request: Request):
    if not is_admin_authorized(request): return HTMLResponse("<script>alert('Unauthorized'); window.location.href='/admin/login';</script>")
    if reject_user_nin(phone):
        send_whatsapp_message(phone, "❌ *Identity Verification Failed*\n\nUnfortunately, we were unable to verify your National Identification Number (NIN). Your registration has been rejected. Please type 'Hi' to register again with a valid NIN.")
    return HTMLResponse("<script>alert('User Rejected and Deleted.'); window.location.href='/admin';</script>")

@app.post("/admin/price/add")
async def admin_add_price(request: Request):
    if not is_admin_authorized(request): return HTMLResponse("<script>alert('Unauthorized'); window.location.href='/admin/login';</script>")
    form_data = await request.form()
    add_market_price(form_data.get("crop_name"), form_data.get("location"), form_data.get("price"))
    return HTMLResponse("<script>window.location.href='/admin';</script>")

@app.post("/admin/price/delete/{price_id}")
async def admin_delete_price(price_id: int, request: Request):
    if not is_admin_authorized(request): return HTMLResponse("<script>alert('Unauthorized'); window.location.href='/admin/login';</script>")
    delete_market_price(price_id)
    return HTMLResponse("<script>window.location.href='/admin';</script>")

    

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
            
            # --- 🎙️ VOICE NOTES (SIMULATED FOR DEMO) ---
            if msg_type in ["audio", "voice"]:
                send_whatsapp_message(sender_phone, "🎙️ *Voice Note Processing...*\n_Simulated AI Translation:_ 'Menu'")
                if not profile:
                    create_user_with_language(sender_phone, "english")
                    update_session(sender_phone, "onboarding", "awaiting_role")
                    send_role_menu(sender_phone, "english")
                else:
                    update_session(sender_phone, "onboarding", "awaiting_role")
                    send_role_menu(sender_phone, profile.get("language", "english"))
                return {"status": "ok"}
            
            # --- 📍 LOCATION PINS ---
            elif msg_type == "location":
                if profile and profile.get("step") == "awaiting_location":
                    lat = message_data["location"]["latitude"]
                    long = message_data["location"]["longitude"]
                    address = message_data["location"].get("name", f"Location: {lat}, {long}")
                    if update_user_location_and_finish(sender_phone, address):
                        send_whatsapp_message(sender_phone, f"📍 Location Saved: {address}\n\n✅ Registration Complete! 🎉")
                        # Fetch fresh profile to send the correct dashboard
                        fresh_profile = get_user_profile(sender_phone)
                        send_main_menu(sender_phone, fresh_profile["role"], fresh_profile["language"])
                return {"status": "ok"}
            
            # --- 📸 IMAGE UPLOADS ---
            elif msg_type == "image":
                if profile and profile.get("step") == "awaiting_produce_image":
                    image_id = message_data["image"]["id"]
                    category = 'input' if profile["flow"] == "add_input" else 'produce'
                    save_new_product(sender_phone, image_id, category=category)
                    update_session(sender_phone, "main_menu", "idle")
                    send_whatsapp_message(sender_phone, "✅ Listing Complete! Your item is now live and buyers can view its image.\n\nType 'menu' to return to your dashboard.")
                return {"status": "ok"}

            # --- 💬 TEXT AND NUMBER REPLIES ---
            elif msg_type == "text":
                text = message_data["text"]["body"].strip().lower()
                
                # --- NEW FEATURE: ROLE SWITCHING & MENU LOOPHOLE ---
                if text in ["hi", "hello", "menu"]:
                    if not profile:
                        create_user_with_language(sender_phone, "english")
                    update_session(sender_phone, "onboarding", "awaiting_role")
                    send_role_menu(sender_phone, profile.get("language", "english") if profile else "english")
                    return {"status": "ok"}

                # 2. FAILSAFE FOR GHOST USERS (If DB drops the session)
                if not profile: 
                    if text == "1":
                        create_user_with_language(sender_phone, "english")
                        update_session(sender_phone, "onboarding", "awaiting_role")
                        send_role_menu(sender_phone, "english")
                    elif text == "2":
                        create_user_with_language(sender_phone, "krio")
                        update_session(sender_phone, "onboarding", "awaiting_role")
                        send_role_menu(sender_phone, "krio")
                    return {"status": "ok"}

                flow = profile.get("flow")
                step = profile.get("step")

                # --- ONBOARDING FLOW ---
                if flow == "onboarding":
                    if step == "awaiting_language":
                        if text == "1": lang = "english"
                        elif text == "2": lang = "krio"
                        else:
                            send_whatsapp_message(sender_phone, "Invalid. Reply 1 for English or 2 for Krio.")
                            return {"status": "ok"}
                        create_user_with_language(sender_phone, lang)
                        update_session(sender_phone, "onboarding", "awaiting_role")
                        send_role_menu(sender_phone, lang)
                        
                    elif step == "awaiting_role":
                        roles = {"1": "role_farmer", "2": "role_buyer", "3": "role_input", "4": "role_driver"}
                        if text in roles:
                            # SMART UPDATE: Checks if they are already fully registered
                            is_registered = update_user_role(sender_phone, roles[text])
                            if is_registered:
                                send_main_menu(sender_phone, roles[text], profile.get("language", "english"))
                            else: 
                                send_whatsapp_message(sender_phone, "Awesome! Let's get you registered.\n\nPlease type your *Full Name*.")
                        else: 
                            send_whatsapp_message(sender_phone, "Invalid. Please reply with 1, 2, 3, or 4.")

                # --- REGISTRATION FLOW ---
                elif flow == "registration":
                    if step == "awaiting_name":
                        update_user_name_and_step(sender_phone, text)
                        send_whatsapp_message(sender_phone, "Thanks! Now please enter your *NIN (National ID Number)*.")
                    elif step == "awaiting_nin":
                        # UPDATED: Instant Auto-Verification
                        update_user_nin_and_step(sender_phone, text)
                        send_whatsapp_message(sender_phone, "⏳ Verifying your identity...\n\n✅ Identity verified successfully.\n\nNow share your location 📍 OR type your district.")
                    elif step == "awaiting_location":
                        update_user_location_and_finish(sender_phone, text)
                        fresh_profile = get_user_profile(sender_phone)
                        send_whatsapp_message(sender_phone, "✅ Registration Complete! 🎉")
                        send_main_menu(sender_phone, fresh_profile["role"], fresh_profile["language"])

                # --- ADD PRODUCE / INPUT FLOW ---
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
                        price = text
                        # UPDATED: Handles market price shortcut
                        if text == "0": price = "Market Price"
                        update_session_data(sender_phone, {"produce_price": price})
                        update_session(sender_phone, flow, "awaiting_produce_image")
                        send_whatsapp_message(sender_phone, "Perfect. 📸 Finally, **send a photo** of the product!")

                # --- MAIN MENU ROUTING ---
                elif flow == "main_menu" and step == "idle":
                    role = profile["role"]
                    
                    if role == "role_farmer":
                        if text == "1":
                            update_session(sender_phone, "add_produce", "awaiting_produce_name")
                            send_whatsapp_message(sender_phone, "Great! 🌾 What is the name of the produce?")
                        elif text == "2":
                            inventory = get_user_inventory(sender_phone)
                            if not inventory: send_whatsapp_message(sender_phone, "📦 Inventory is empty.")
                            else:
                                msg = "📦 *Active Inventory:*\n\n"
                                for item in inventory: msg += f"✔️ {item[0]} - {item[1]}\n"
                                send_whatsapp_message(sender_phone, msg)
                        elif text == "3":
                            orders = get_farmer_orders(sender_phone)
                            if not orders: send_whatsapp_message(sender_phone, "✅ No pending orders.")
                            else:
                                msg = "📋 *Pending Orders:*\n\n"
                                temp_map = {}
                                for idx, o in enumerate(orders, 1):
                                    msg += f"{idx}️⃣ Order #{o[0]} - {o[1]} for {o[2]}\n"
                                    temp_map[str(idx)] = o[0]
                                msg += "\n_Reply with a number to manage an order_"
                                update_session_data(sender_phone, {"manage_map": temp_map})
                                update_session(sender_phone, "manage_order", "awaiting_selection")
                                send_whatsapp_message(sender_phone, msg)
                        elif text == "4":
                            update_session(sender_phone, "farmer_search", "awaiting_search_query")
                            update_session_data(sender_phone, {"search_category": "input"})
                            send_whatsapp_message(sender_phone, "🚜 What supplies do you need? (e.g., Seeds, Fertilizer)")
                        elif text == "5":
                            prices = get_market_prices()
                            msg = "📊 *Today's Market Prices:*\n\n"
                            for p in prices: msg += f"🌾 {p[0]} (📍 {p[1]}): {p[2]}\n"
                            send_whatsapp_message(sender_phone, msg)
                            
                    elif role == "role_buyer":
                        if text == "1":
                            # UPDATED: Search only produce
                            update_session(sender_phone, "buyer_search", "awaiting_search_query")
                            update_session_data(sender_phone, {"search_category": "produce"})
                            send_whatsapp_message(sender_phone, "🔍 What produce are you looking for? (e.g., Rice, Cassava)")
                        elif text == "2":
                            # UPDATED: Search only inputs
                            update_session(sender_phone, "buyer_search", "awaiting_search_query")
                            update_session_data(sender_phone, {"search_category": "input"})
                            send_whatsapp_message(sender_phone, "🚜 What farm inputs are you looking for? (e.g., Fertilizer, Tools)")
                        elif text == "3":
                            orders = get_buyer_orders(sender_phone)
                            if not orders: send_whatsapp_message(sender_phone, "🛒 No recent orders.")
                            else:
                                msg = "🛒 *Recent Orders:*\n\n"
                                for o in orders: msg += f"📦 {o[1]} (Status: {o[2].upper()})\n"
                                send_whatsapp_message(sender_phone, msg)
                        elif text == "4":
                            prices = get_market_prices()
                            msg = "📊 *Today's Market Prices:*\n\n"
                            for p in prices: msg += f"🌾 {p[0]} (📍 {p[1]}): {p[2]}\n"
                            send_whatsapp_message(sender_phone, msg)

                    elif role == "role_input":
                        if text == "1":
                            update_session(sender_phone, "add_input", "awaiting_produce_name")
                            send_whatsapp_message(sender_phone, "Great! 🚜 What is the name of the supply/tool?")
                        elif text == "2":
                            inventory = get_user_inventory(sender_phone)
                            if not inventory: send_whatsapp_message(sender_phone, "📦 Inventory is empty.")
                            else:
                                msg = "📦 *Active Inventory:*\n\n"
                                for item in inventory: msg += f"✔️ {item[0]} - {item[1]}\n"
                                send_whatsapp_message(sender_phone, msg)
                        elif text == "3":
                            orders = get_farmer_orders(sender_phone)
                            if not orders: send_whatsapp_message(sender_phone, "✅ No pending orders.")
                            else:
                                msg = "📋 *Pending Orders:*\n\n"
                                temp_map = {}
                                for idx, o in enumerate(orders, 1):
                                    msg += f"{idx}️⃣ Order #{o[0]} - {o[1]} for {o[2]}\n"
                                    temp_map[str(idx)] = o[0]
                                msg += "\n_Reply with a number to manage an order_"
                                update_session_data(sender_phone, {"manage_map": temp_map})
                                update_session(sender_phone, "manage_order", "awaiting_selection")
                                send_whatsapp_message(sender_phone, msg)
                        elif text == "4":
                            prices = get_market_prices()
                            msg = "📊 *Today's Market Prices:*\n\n"
                            for p in prices: msg += f"🌾 {p[0]} (📍 {p[1]}): {p[2]}\n"
                            send_whatsapp_message(sender_phone, msg)

                    elif role == "role_driver":
                        if text == "1":
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
                        elif text == "2":
                            my_jobs = get_driver_deliveries(sender_phone)
                            if not my_jobs: send_whatsapp_message(sender_phone, "🚚 No active jobs.")
                            else:
                                msg = "🚚 *My Deliveries:*\n\n"
                                temp_map = {}
                                for idx, d in enumerate(my_jobs, 1):
                                    msg += f"{idx}️⃣ Job #{d[0]} - {d[1]}\n🎯 Dropoff: {d[6]}\n\n"
                                    temp_map[str(idx)] = d[0]
                                msg += "_Reply with number to Mark Delivered_"
                                update_session_data(sender_phone, {"active_map": temp_map})
                                update_session(sender_phone, "driver_flow", "awaiting_complete")
                                send_whatsapp_message(sender_phone, msg)

                # --- SEARCH & PURCHASE FLOW ---
                elif flow in ["buyer_search", "farmer_search"]:
                    if step == "awaiting_search_query":
                        # UPDATED: Pulls search category seamlessly for omni-buyers
                        category = get_session_data(sender_phone).get("search_category", "produce") if flow == "buyer_search" else "input"
                        buyer_location = get_user_location(sender_phone)
                        results = search_marketplace(text, category=category, buyer_location=buyer_location)
                        
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
                        
                        if text in results:
                            product_id = results[text]
                            details = get_product_by_id(product_id)
                            if details:
                                p_id, p_name, price, qty, img_id, f_phone, f_name, loc = details
                                qty_text = qty if qty else "Unknown"
                                
                                # THIS IS THE IMAGE FUNCTION: It automatically pushes the product image to the buyer!
                                caption = f"📦 *{p_name}*\n💰 Price: {price}\n⚖️ Available: {qty_text}\n🧑‍🌾 Seller: {f_name} ({loc})\n\n1️⃣ 🛒 Buy Now\n2️⃣ 🔍 Search Again\n\n_Reply 1 or 2_"
                                send_whatsapp_image(sender_phone, img_id, caption)
                                
                                update_session_data(sender_phone, {"temp_buy_id": p_id})
                                update_session(sender_phone, flow, "awaiting_buy_decision")
                        else:
                            send_whatsapp_message(sender_phone, "Invalid number. Please try again or type 'menu'.")
                            
                    elif step == "awaiting_buy_decision":
                        if text == "1":
                            update_session(sender_phone, "buyer_checkout", "awaiting_delivery")
                            send_whatsapp_message(sender_phone, "📦 Almost done!\n\nHow would you like to receive this?\n1️⃣ Need Delivery 🚚\n2️⃣ Self Pickup 🚶\n\n_Reply 1 or 2_")
                        elif text == "2":
                            update_session(sender_phone, flow, "awaiting_search_query")
                            send_whatsapp_message(sender_phone, "🔍 What else are you looking for?")

                # --- CHECKOUT FLOW ---
                elif flow == "buyer_checkout":
                    session_data = get_session_data(sender_phone)
                    if step == "awaiting_delivery":
                        if text == "1": pref = "delivery"
                        elif text == "2": pref = "pickup"
                        else:
                            send_whatsapp_message(sender_phone, "Invalid. Reply 1 for Delivery or 2 for Pickup.")
                            return {"status": "ok"}
                        
                        update_session_data(sender_phone, {"temp_delivery_pref": pref})
                        update_session(sender_phone, "buyer_checkout", "awaiting_payment")
                        send_whatsapp_message(sender_phone, "💳 Payment Method\n\nHow would you like to pay?\n1️⃣ Mobile Money 📱\n2️⃣ Cash on Delivery 💵\n\n_Reply 1 or 2_")
                        
                    elif step == "awaiting_payment":
                        if text == "1": pay = "Mobile Money"
                        elif text == "2": pay = "Cash on Delivery"
                        else:
                            send_whatsapp_message(sender_phone, "Invalid. Reply 1 or 2.")
                            return {"status": "ok"}
                            
                        prod_id = session_data.get("temp_buy_id")
                        deliv_pref = session_data.get("temp_delivery_pref")
                        
                        order = create_order(sender_phone, prod_id, deliv_pref, pay)
                        if order:
                            pref_text = "Delivery Needed 🚚" if deliv_pref == "delivery" else "Self-Pickup 🚶"
                            success_msg = f"✅ Order placed successfully for *{order['product_name']}*!\n\nMethod: {pref_text}\nPayment: *{pay}*\n"
                            
                            if pay == "Mobile Money":
                                success_msg += f"\nPlease send payment to the seller's Mobile Money number: {order['farmer_phone']}\n"
                                
                            success_msg += "\nThe seller has been notified and will contact you shortly."
                            send_whatsapp_message(sender_phone, success_msg)
                            
                            farmer_phone = order['farmer_phone']
                            buyer_link = f"wa.me/{sender_phone}"
                            alert_msg = f"🚨 *NEW ORDER ALERT!* 🚨\n\nA buyer wants to purchase your *{order['product_name']}* ({order['price']}).\n\nMethod: *{pref_text}*\nPayment: *{pay}*\n\nBuyer's Contact: {buyer_link}\n\nPlease check 'View Orders' on your dashboard to accept it."
                            send_whatsapp_message(farmer_phone, alert_msg)
                        else:
                            send_whatsapp_message(sender_phone, "Sorry, there was an issue placing the order.")
                        
                        update_session(sender_phone, "main_menu", "idle")

                # --- SELLER ORDER MANAGEMENT ---
                elif flow == "manage_order":
                    session_data = get_session_data(sender_phone)
                    if step == "awaiting_selection":
                        order_map = session_data.get("manage_map", {})
                        if text in order_map:
                            o_id = order_map[text]
                            order_details = get_order_by_id(o_id)
                            if order_details:
                                _, p_name, b_phone, b_name, status, pref, pay_method = order_details
                                pref_text = "Delivery Needed 🚚" if pref == "delivery" else "Buyer will Pickup 🚶"
                                msg = f"📦 *Manage Order #{o_id}*\n\nItem: {p_name}\nBuyer: {b_name}\nMethod: *{pref_text}*\nPayment: *{pay_method}*\n\n1️⃣ Accept ✅\n2️⃣ Decline ❌\n\n_Reply 1 or 2_"
                                
                                update_session_data(sender_phone, {"target_order": o_id})
                                update_session(sender_phone, "manage_order", "awaiting_action")
                                send_whatsapp_message(sender_phone, msg)
                        else:
                            send_whatsapp_message(sender_phone, "Invalid number. Type 'menu' to exit.")
                            
                    elif step == "awaiting_action":
                        order_id = session_data.get("target_order")
                        order_details = get_order_by_id(order_id)
                        b_phone = order_details[2] if order_details else ""
                        p_name = order_details[1] if order_details else "item"
                        
                        if text == "1":
                            update_order_status(order_id, "ACCEPTED")
                            send_whatsapp_message(sender_phone, f"✅ You have ACCEPTED Order #{order_id}.")
                            send_whatsapp_message(b_phone, f"🔔 *Order Update!*\n\nThe seller has ACCEPTED your order for {p_name}.")
                        elif text == "2":
                            update_order_status(order_id, "DECLINED")
                            send_whatsapp_message(sender_phone, f"❌ You have DECLINED Order #{order_id}.")
                            send_whatsapp_message(b_phone, f"🔔 *Order Update!*\n\nThe seller has DECLINED your order for {p_name}.")
                            
                        update_session(sender_phone, "main_menu", "idle")
                        send_whatsapp_message(sender_phone, "Type 'menu' to return to dashboard.")

                # --- DRIVER FLOW ---
                elif flow == "driver_flow":
                    session_data = get_session_data(sender_phone)
                    if step == "awaiting_accept":
                        job_map = session_data.get("deliv_map", {})
                        if text in job_map:
                            order_id = job_map[text]
                            details = get_delivery_details(order_id)
                            if details:
                                o_id, p_name, f_name, f_loc, f_phone, b_name, b_loc, b_phone = details
                                msg = f"🚚 *Delivery Job #{o_id}*\n\n📦 Item: {p_name}\n📍 Pickup: {f_name} ({f_loc})\n🎯 Dropoff: {b_name} ({b_loc})\n\n1️⃣ Accept Job ✅\n2️⃣ Cancel ❌\n\n_Reply 1 or 2_"
                                update_session_data(sender_phone, {"target_job": o_id})
                                update_session(sender_phone, "driver_flow", "awaiting_confirm_accept")
                                send_whatsapp_message(sender_phone, msg)
                        else:
                            send_whatsapp_message(sender_phone, "Invalid number.")
                            
                    elif step == "awaiting_confirm_accept":
                        order_id = session_data.get("target_job")
                        if text == "1":
                            if assign_driver_to_order(order_id, sender_phone):
                                send_whatsapp_message(sender_phone, f"✅ You have successfully claimed Delivery Job #{order_id}!\n\nCheck 'My Deliveries' on your dashboard for the exact pickup and dropoff contact links.")
                                details = get_delivery_details(order_id)
                                if details:
                                    _, p_name, _, _, f_phone, _, _, b_phone = details
                                    driver_link = f"wa.me/{sender_phone}"
                                    send_whatsapp_message(f_phone, f"🚚 *Driver Assigned!* 🚚\n\nA driver is on their way to pick up the *{p_name}* (Order #{order_id}).\n\nDriver Contact: {driver_link}")
                                    send_whatsapp_message(b_phone, f"🚚 *Order Shipped!* 🚚\n\nYour *{p_name}* (Order #{order_id}) has been picked up by a driver and is on its way!\n\nDriver Contact: {driver_link}")
                            else:
                                send_whatsapp_message(sender_phone, "❌ Sorry, there was an issue accepting this job. It might have been claimed by someone else.")
                        
                        update_session(sender_phone, "main_menu", "idle")
                        send_whatsapp_message(sender_phone, "Type 'menu' to return to dashboard.")
                        
                    elif step == "awaiting_complete":
                        job_map = session_data.get("active_map", {})
                        if text in job_map:
                            order_id = job_map[text]
                            details = get_delivery_details(order_id)
                            if details:
                                o_id, p_name, _, _, f_phone, b_name, _, b_phone = details
                                msg = f"🚚 *Job #{o_id} In Progress*\n\n📦 Item: {p_name}\n🎯 Dropoff: {b_name}\n📞 Pickup: wa.me/{f_phone}\n📞 Dropoff: wa.me/{b_phone}\n\n1️⃣ Mark Delivered ✅\n2️⃣ Cancel ❌\n\n_Reply 1 or 2_"
                                update_session_data(sender_phone, {"target_job": o_id})
                                update_session(sender_phone, "driver_flow", "awaiting_confirm_complete")
                                send_whatsapp_message(sender_phone, msg)
                        else:
                            send_whatsapp_message(sender_phone, "Invalid number.")
                            
                    elif step == "awaiting_confirm_complete":
                        order_id = session_data.get("target_job")
                        if text == "1":
                            update_order_status(order_id, "DELIVERED")
                            send_whatsapp_message(sender_phone, f"✅ Job #{order_id} marked as DELIVERED! Great work.")
                            details = get_delivery_details(order_id)
                            if details:
                                _, p_name, _, _, f_phone, _, _, b_phone = details
                                send_whatsapp_message(f_phone, f"🎉 *Delivery Complete!* 🎉\n\nYour {p_name} (Order #{order_id}) has been successfully delivered to the buyer.")
                                send_whatsapp_message(b_phone, f"🎉 *Package Arrived!* 🎉\n\nYour {p_name} (Order #{order_id}) has been successfully delivered! Thank you for using Agro Market.")
                                
                        update_session(sender_phone, "main_menu", "idle")
                        send_whatsapp_message(sender_phone, "Type 'menu' to return to dashboard.")

    except Exception as e:
        print(f"Error: {e}")
    return {"status": "ok"}
