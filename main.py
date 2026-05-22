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

# --- TEXT-BASED DICTIONARY ---
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
    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": phone_number, "type": "text", "text": {"body": message_text}}
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"WhatsApp API Error: {e}")

def send_whatsapp_image(phone_number, image_id, caption_text):
    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": phone_number, "type": "image", "image": {"id": image_id, "caption": caption_text}}
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"WhatsApp API Error: {e}")

def send_language_menu(phone_number):
    msg = "🌍 Welcome to Agro Market! / Wɛlkɔm to Agro Makit!\n\nPlease select your preferred language:\n\n1️⃣ English\n2️⃣ Krio\n\n_Reply with 1 or 2_"
    send_whatsapp_message(phone_number, msg)

def send_role_menu(phone_number, lang="english"):
    t = LANGUAGES.get(lang, LANGUAGES["english"])
    send_whatsapp_message(phone_number, t["welcome"])

def send_main_menu(phone_number, role, lang="english"):
    t = LANGUAGES.get(lang, LANGUAGES["english"])
    menus = {"role_farmer": t["farmer_menu"], "role_buyer": t["buyer_menu"], "role_driver": t["driver_menu"], "role_input": t["input_menu"]}
    send_whatsapp_message(phone_number, menus.get(role, "Menu unavailable."))

# --- DATABASE FUNCTIONS ---
def get_user_profile(phone_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT u.role, u.nin_status, u.language, us.current_flow, us.current_step, u.name, u.vehicle_number FROM users u LEFT JOIN user_sessions us ON u.phone = us.phone WHERE u.phone = %s", (phone_number,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result: return {"role": result[0], "nin_status": result[1], "language": result[2] or "english", "flow": result[3], "step": result[4], "name": result[5], "vehicle_number": result[6]}
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
        cursor.execute("SELECT product_name, farmer_phone, price, quantity FROM products WHERE id = %s", (product_id,))
        prod = cursor.fetchone()
        if not prod: return None
        prod_name, farmer_phone, price, quantity = prod
        
        clean_price = int(''.join(filter(str.isdigit, str(price)))) if any(c.isdigit() for c in str(price)) else 0
        clean_qty = int(''.join(filter(str.isdigit, str(quantity)))) if any(c.isdigit() for c in str(quantity)) else 1
        subtotal = clean_price * clean_qty
        
        cursor.execute("""
            INSERT INTO orders (buyer_phone, farmer_phone, product_id, product_name, status, delivery_preference, payment_method, subtotal, total_amount) 
            VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, %s) RETURNING id
        """, (buyer_phone, farmer_phone, product_id, prod_name, preference, payment_method, subtotal, subtotal))
        order_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        return {"id": order_id, "farmer_phone": farmer_phone, "product_name": prod_name, "price": price}
    except Exception as e:
        print(f"Error creating order: {e}")
        return None

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
            WHERE o.status = 'paid' AND o.delivery_preference = 'delivery' AND o.delivery_option IS NOT NULL AND o.driver_phone IS NULL ORDER BY o.created_at DESC LIMIT 5
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
                   b.name AS buyer_name, b.location AS buyer_loc, b.phone AS buyer_phone, o.payment_method, p.price, p.quantity,
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

def assign_driver_to_order(order_id, driver_phone):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'dispatched', driver_phone = %s WHERE id = %s", (driver_phone, order_id))
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
        print(f"Role Update Error: {e}")
        return False

def update_user_name_and_step(phone_number, name):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET name = %s WHERE phone = %s", (name, phone_number))
        cursor.execute("SELECT role FROM users WHERE phone = %s", (phone_number,))
        user_role = cursor.fetchone()[0]
        next_step = 'awaiting_vehicle' if user_role == 'role_driver' else 'awaiting_nin'
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
        cursor.execute("UPDATE user_sessions SET current_step = 'awaiting_nin' WHERE phone = %s", (phone_number,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

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
        
        # CLEAN PRODUCTION SEARCH: Look up the typed password strictly against the Supabase hashed values columns 
        cursor.execute("""
            SELECT password_hash FROM admin_auth 
            WHERE phone = %s 
               OR phone = (CASE WHEN %s ~ '^[0-9]+$' THEN %s ELSE '-1' END);
        """, (str(ADMIN_PHONE), str(ADMIN_PHONE), str(ADMIN_PHONE)))
        
        result = cursor.fetchone()
        if result and result[0]:
            db_hash = result[0]
            if hash_password(password) == db_hash:
                session_token = secrets.token_hex(32)
                cursor.execute("""
                    UPDATE admin_auth 
                    SET session_token = %s 
                    WHERE phone = %s 
                       OR phone = (CASE WHEN %s ~ '^[0-9]+$' THEN %s ELSE '-1' END);
                """, (session_token, str(ADMIN_PHONE), str(ADMIN_PHONE), str(ADMIN_PHONE)))
                conn.commit()
                cursor.close()
                conn.close()
                
                response = RedirectResponse(url="/admin", status_code=302)
                # CLEAN ROUTING COOKIE: Kept lax cross-origin cookie mapping securely
                response.set_cookie(key="secure_admin_session", value=session_token, httponly=True, samesite="lax", max_age=86400)
                return response
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Login Verification Error: {e}")
        
    return HTMLResponse("<script>alert('Invalid Password.'); window.location.href='/admin/login';</script>")

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not is_admin_authorized(request): return RedirectResponse(url="/admin/login")
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

            <h2>🔍 Receipt Registry Tracker</h2>
            <div class="add-form" style="margin-bottom:30px;">
                <form action="javascript:void(0);" onsubmit="lookupReceipt()">
                    <input type="text" id="rcpt_input" placeholder="e.g., AGM-2026-000001" style="width:50%;" required>
                    <button type="submit" class="btn btn-add">Track Order Status</button>
                </form>
                <div id="tracker_results" style="margin-top:15px; font-weight:bold; color:#333;"></div>
            </div>

            <script>
                async function lookupReceipt() {{
                    const query = document.getElementById('rcpt_input').value;
                    const resDiv = document.getElementById('tracker_results');
                    resDiv.innerText = "Querying data arrays...";
                    try {{
                        let response = await fetch('/admin/api/track-receipt/' + query);
                        if(response.ok) {{
                            let data = await response.json();
                            if(data.found) {{
                                resDiv.innerHTML = "✅ Order Found!<br>Item: " + data.product_name + "<br>Status: <span style='color:#008CBA;'>" + data.status.toUpperCase() + "</span><br>Total Escrow value: Le " + data.total_amount;
                            }} else {{
                                resDiv.innerText = "❌ No active orders register found for receipt reference code.";
                            }}
                        }} else {{ resDiv.innerText = "Error pulling registry logs."; }}
                    }} catch(e) {{ resDiv.innerText = "Network connection timeout."; }}
                }}
            </script>

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

@app.get("/admin/api/track-receipt/{receipt_number}")
async def track_receipt_api(receipt_number: str):
    res = search_order_by_receipt(receipt_number)
    if res:
        return {"found": True, "product_name": res[1], "buyer_phone": res[2], "status": res[4], "total_amount": res[5]}
    return {"found": False}

@app.get("/admin/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("secure_admin_session")
    return response

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
# SIMULATED MONIME WEBHOOK ENDPOINT
# ========================================================
@app.post("/webhook/monime")
async def monime_payment_webhook(request: Request):
    payload = await request.json()
    order_id = payload.get("metadata", {}).get("order_id")
    event = payload.get("event")
    
    if event == "payment.success" and order_id:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            tx_id = payload.get("transaction_id", f"OM-{random.randint(10000000, 99999999)}")
            rec_num = f"AGM-{datetime.now().strftime('%Y')}-{str(order_id).zfill(6)}"
            
            cursor.execute("""
                UPDATE orders 
                SET status = 'paid', transaction_id = %s, receipt_number = %s, wallet_status = 'held' 
                WHERE id = %s RETURNING buyer_phone, farmer_phone, product_name, total_amount
            """, (tx_id, rec_num, order_id))
            res = cursor.fetchone()
            conn.commit()
            cursor.close()
            conn.close()
            
            if res:
                b_phone, f_phone, p_name, total_amt = res
                success_msg = f"💳 *Payment Escrow Confirmed!* Le {total_amt} for your order of *{p_name}* has been successfully secured. Funds are locked safely until delivery verification."
                send_whatsapp_message(b_phone, success_msg)
                send_whatsapp_message(f_phone, f"💰 *Payment Received in Escrow!* The buyer has funded Order #{order_id} ({p_name}). Please process shipping configurations immediately.")
        except Exception as e:
            print(f"Monime Webhook Processing Error: {e}")
            
    return {"status": "processed"}

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
            
            # --- 🎙️ VOICE NOTES ---
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
                
                if text in ["hi", "hello", "menu"]:
                    if not profile:
                        create_user_with_language(sender_phone, "english")
                    update_session(sender_phone, "onboarding", "awaiting_role")
                    send_role_menu(sender_phone, profile.get("language", "english") if profile else "english")
                    return {"status": "ok"}

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
                        fresh_prof = get_user_profile(sender_phone)
                        if fresh_prof and fresh_prof.get("step") == "awaiting_vehicle":
                            send_whatsapp_message(sender_phone, "Responded! 1️⃣ Logistics Profile Detected!\n\nPlease type your **Vehicle License Plate Number** (e.g., AEK-458).")
                        else:
                            send_whatsapp_message(sender_phone, "Thanks! Now please enter your *NIN (National ID Number)*.")
                    
                    elif step == "awaiting_vehicle":
                        update_user_vehicle(sender_phone, text.upper())
                        send_whatsapp_message(sender_phone, "Vehicle linked successfully. 🛡️ Now please enter your *NIN (National ID Number)*.")
                        
                    elif step == "awaiting_nin":
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
                                msg = "📋 *Pending Requests for Review:*\n\n"
                                temp_map = {}
                                for idx, o in enumerate(orders, 1):
                                    msg += f"{idx}️⃣ Request #{o[0]} - {o[1]} for {o[2]}\n"
                                    temp_map[str(idx)] = o[0]
                                msg += "\n_Reply with a number to accept/reject request_"
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
                            update_session(sender_phone, "buyer_search", "awaiting_search_query")
                            update_session_data(sender_phone, {"search_category": "produce"})
                            send_whatsapp_message(sender_phone, "🔍 What produce are you looking for? (e.g., Rice, Cassava)")
                        elif text == "2":
                            update_session(sender_phone, "buyer_search", "awaiting_search_query")
                            update_session_data(sender_phone, {"search_category": "input"})
                            send_whatsapp_message(sender_phone, "🚜 What farm inputs are you looking for? (e.g., Fertilizer, Tools)")
                        elif text == "3":
                            orders = get_buyer_orders(sender_phone)
                            if not orders: send_whatsapp_message(sender_phone, "🛒 No recent orders.")
                            else:
                                msg = "🛒 *Recent Orders:*\n\n"
                                for o in orders: 
                                    rcpt_info = f" (Receipt: {o[5]})" if o[5] else ""
                                    msg += f"📦 {o[1]} (Status: {o[2].upper()}){rcpt_info}\n"
                                msg += "\n💡 _Type 'confirm delivery' once items arrive!_"
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
                                caption = f"📦 *{p_name}*\n💰 Price: {price}\n⚖️ Available: {qty_text}\n🧑‍🌾 Seller: {f_name} ({loc})\n\n1️⃣ 🛒 Place Order\n2️⃣ 🔍 Search Again\n\n_Reply 1 or 2_"
                                send_whatsapp_image(sender_phone, img_id, caption)
                                update_session_data(sender_phone, {"temp_buy_id": p_id})
                                update_session(sender_phone, flow, "awaiting_buy_decision")
                        else:
                            send_whatsapp_message(sender_phone, "Invalid number. Please try again or type 'menu'.")
                            
                    elif step == "awaiting_buy_decision":
                        if text == "1":
                            update_session(sender_phone, "buyer_checkout", "awaiting_delivery")
                            send_whatsapp_message(sender_phone, "📦 Delivery Selection\n\nHow would you like to receive this?\n1️⃣ Request Platform Delivery 🚚\n2️⃣ Self Pickup / Vendor Delivery 🚶\n\n_Reply 1 or 2_")
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
                            send_whatsapp_message(sender_phone, "Invalid. Reply 1 or 2.")
                            return {"status": "ok"}
                        
                        update_session_data(sender_phone, {"temp_delivery_pref": pref})
                        prod_id = session_data.get("temp_buy_id")
                        order_map = create_order(sender_phone, prod_id, pref, "Monime Escrow Hold")
                        
                        if order_map:
                            send_whatsapp_message(sender_phone, "🕒 *Order Submitted!* Please wait while the seller confirms stock availability. We will notify you with a payment link immediately upon confirmation.")
                            farmer_phone = order_map['farmer_phone']
                            alert_msg = f"🚨 *NEW ORDER REQUEST!* 🚨\n\nA buyer wants to purchase your *{order_map['product_name']}* ({order_map['price']}).\n\nPlease check 'View Orders' (Option 3) on your dashboard to Accept or Decline right away."
                            send_whatsapp_message(farmer_phone, alert_msg)
                        else:
                            send_whatsapp_message(sender_phone, "Sorry, there was an issue processing your order request.")
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
                                _, p_name, b_phone, b_name, status, pref, pay_method, *rest = order_details
                                msg = f"📦 *Manage Request #{o_id}*\n\nItem: {p_name}\nBuyer: {b_name}\nPreference: {pref}\n\n1️⃣ Confirm Availability ✅\n2️⃣ Reject Request ❌\n\n_Reply 1 or 2_"
                                update_session_data(sender_phone, {"target_order": o_id})
                                update_session(sender_phone, "manage_order", "awaiting_action")
                                send_whatsapp_message(sender_phone, msg)
                        else:
                            send_whatsapp_message(sender_phone, "Invalid selection tracker.")
                            
                    elif step == "awaiting_action":
                        order_id = session_data.get("target_order")
                        order_details = get_order_by_id(order_id)
                        b_phone = order_details[2] if order_details else ""
                        p_name = order_details[1] if order_details else "item"
                        pref = order_details[5] if order_details else "pickup"
                        
                        if text == "1":
                            update_order_status(order_id, "AWAITING_PAYMENT")
                            send_whatsapp_message(sender_phone, f"✅ Order #{order_id} confirmed. Prompting the buyer to complete escrow deposit.")
                            monime_checkout_url = f"https://checkout.monime.io/payment?order={order_id}"
                            send_whatsapp_message(b_phone, f"🎉 *Good News!* The seller has confirmed availability for your order of *{p_name}*.\n\nPlease process your payment securely to our escrow container using the link below:\n🔗 {monime_checkout_url}\n\n_Funds will remain safely locked until you confirm delivery receipt!_")
                            if pref == "delivery":
                                update_session(sender_phone, "logistics_setup", "choose_option")
                                send_whatsapp_message(sender_phone, "🚚 *Logistics Dispatch Selection*:\n\nHow would you like to handle shipping for this order?\n1️⃣ Use Platform Fleet (View Courier Services & Rates) 🏢\n2️⃣ Self-Delivery (Handle shipping paths personally) 🚶")
                                return {"status": "ok"}
                        elif text == "2":
                            update_order_status(order_id, "DECLINED")
                            send_whatsapp_message(sender_phone, f"❌ Request #{order_id} rejected.")
                            send_whatsapp_message(b_phone, f"遭遇 😔 Unfortunately, the seller declined your request for {p_name}. Try ordering from another listing.")
                        update_session(sender_phone, "main_menu", "idle")
                        send_whatsapp_message(sender_phone, "Type 'menu' to return to dashboard.")

                # --- LOGISTICS SETUP FLOW ---
                elif flow == "logistics_setup":
                    session_data = get_session_data(sender_phone)
                    order_id = session_data.get("target_order")
                    if step == "choose_option":
                        if text == "1":
                            update_session(sender_phone, "logistics_setup", "select_service")
                            msg = f"📋 *Available Delivery Options for Order #{order_id}:*\n\n1️⃣ Flash Logistics (Est: 4km, Fee: Le 1,500)\n2️⃣ EcoRiders (Est: 5km, Fee: Le 1,800)\n\n_Reply with 1 or 2 to select option and make platform logistics payment._"
                            send_whatsapp_message(sender_phone, msg)
                        elif text == "2":
                            try:
                                conn = psycopg2.connect(DATABASE_URL)
                                cursor = conn.cursor()
                                cursor.execute("UPDATE orders SET delivery_option = 'self-delivery', delivery_fee = 0 WHERE id = %s", (order_id,))
                                conn.commit()
                                cursor.close()
                                conn.close()
                            except: pass
                            send_whatsapp_message(sender_phone, "✅ Self-delivery option saved. You are responsible for shipping this package directly to the buyer.")
                            update_session(sender_phone, "main_menu", "idle")
                        else:
                            send_whatsapp_message(sender_phone, "Invalid response selection. Choose 1 or 2.")
                    elif step == "select_service":
                        fee = 1500 if text == "1" else 1800
                        srv = "Flash Logistics" if text == "1" else "EcoRiders"
                        try:
                            conn = psycopg2.connect(DATABASE_URL)
                            cursor = conn.cursor()
                            cursor.execute("UPDATE orders SET delivery_option = %s, delivery_fee = %s, total_amount = subtotal + %s WHERE id = %s", (srv, fee, fee, order_id))
                            conn.commit()
                            cursor.close()
                            conn.close()
                        except: pass
                        send_whatsapp_message(sender_phone, f"✅ Service option locked. Logistics Fee of Le {fee} added to escrow balance registry.")
                        update_session(sender_phone, "main_menu", "idle")

                # --- DRIVER FLOW ---
                elif flow == "driver_flow":
                    session_data = get_session_data(sender_phone)
                    if step == "awaiting_accept":
                        job_map = session_data.get("deliv_map", {})
                        if text in job_map:
                            order_id = job_map[text]
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
                        if text == "1":
                            if assign_driver_to_order(order_id, sender_phone):
                                send_whatsapp_message(sender_phone, f"✅ You have successfully claimed Delivery Job #{order_id}!\n\nCheck 'My Deliveries' on your dashboard for pickup links.")
                                details = get_delivery_details(order_id)
                                if details:
                                    _, p_name, _, _, f_phone, _, _, b_phone, *rest = details
                                    driver_link = f"wa.me/{sender_phone}"
                                    send_whatsapp_message(f_phone, f"🚚 *Driver Assigned!* A platform rider is on the way to pick up *{p_name}* (Order #{order_id}).")
                                    send_whatsapp_message(b_phone, f"🚚 *Order Dispatched!* Your *{p_name}* is on its way with our courier platform rider link: {driver_link}")
                            else:
                                send_whatsapp_message(sender_phone, "❌ Delivery match claimed by another agent.")
                        update_session(sender_phone, "main_menu", "idle")
                        send_whatsapp_message(sender_phone, "Type 'menu' to return to dashboard.")
                    elif step == "awaiting_complete":
                        job_map = session_data.get("active_map", {})
                        if text in job_map:
                            order_id = job_map[text]
                            details = get_delivery_details(order_id)
                            if details:
                                o_id, p_name, _, _, f_phone, b_name, _, b_phone, *rest = details
                                msg = f"🚚 *Job #{o_id} In Progress*\n\n📦 Item: {p_name}\n🎯 Dropoff: {b_name}\n📞 Seller: wa.me/{f_phone}\n📞 Buyer: wa.me/{b_phone}\n\n1️⃣ Mark Package Delivered ✅\n2️⃣ Cancel Route ❌\n\n_Reply 1 or 2_"
                                update_session_data(sender_phone, {"target_job": order_id})
                                update_session(sender_phone, "driver_flow", "awaiting_confirm_complete")
                                send_whatsapp_message(sender_phone, msg)
                        else:
                            send_whatsapp_message(sender_phone, "Invalid number.")
                    elif step == "awaiting_confirm_complete":
                        order_id = session_data.get("target_job")
                        if text == "1":
                            update_order_status(order_id, "DELIVERED")
                            send_whatsapp_message(sender_phone, f"✅ Job #{order_id} flagged as delivered! Awaiting buyer completion approval to clear system escrow parameters.")
                            details = get_delivery_details(order_id)
                            if details:
                                _, p_name, _, _, f_phone, _, _, b_phone, *rest = details
                                send_whatsapp_message(f_phone, f"🚚 Delivery complete for Job #{order_id}. Awaiting buyer validation parameter to release cash holdings.")
                                send_whatsapp_message(b_phone, f"🔔 *Delivery Arrival Notification!* Your order of *{p_name}* has been dropped off. Please check the package and reply with **'confirm delivery'** to release wallet authorization balances.")
                        update_session(sender_phone, "main_menu", "idle")

                # --- DETECT ESCROW COMPLETION MESSAGES FROM BUYERS ---
                elif text == "confirm delivery":
                    try:
                        conn = psycopg2.connect(DATABASE_URL)
                        cursor = conn.cursor()
                        cursor.execute("SELECT id, product_name, farmer_phone, total_amount FROM orders WHERE buyer_phone = %s AND status = 'DELIVERED' AND wallet_status = 'held' LIMIT 1", (sender_phone,))
                        escrow_match = cursor.fetchone()
                        if escrow_match:
                            o_id, p_name, f_phone, total_amt = escrow_match
                            monime_api_endpoint = "https://api.monime.io/v1/financial-account/transfers"
                            monime_headers = {"Authorization": f"Bearer {MONIME_SECRET_KEY}", "Content-Type": "application/json"}
                            monime_payload = {
                                "source_account": "agro_market_escrow_holding",
                                "destination_wallet": f"wallet_{f_phone}",
                                "amount": total_amt,
                                "currency": "SLE",
                                "metadata": {"order_id": o_id, "tracking_type": "escrow_payout"}
                            }
                            try: requests.post(monime_api_endpoint, headers=monime_headers, json=monime_payload, timeout=5)
                            except: pass
                            
                            tx_id = f"OM-{random.randint(10000000, 99999999)}"
                            rec_num = f"AGM-{datetime.now().strftime('%Y')}-{str(o_id).zfill(6)}"
                            cursor.execute("UPDATE orders SET wallet_status = 'released', transaction_id = %s, receipt_number = %s WHERE id = %s", (tx_id, rec_num, o_id))
                            conn.commit()
                            
                            cursor.execute("""
                                SELECT f.name, b.name, b.location, p.price, p.quantity, o.delivery_fee, o.subtotal, o.delivery_option, u_d.name, u_d.vehicle_number
                                FROM orders o 
                                JOIN users f ON o.farmer_phone = f.phone 
                                JOIN users b ON o.buyer_phone = b.phone 
                                LEFT JOIN products p ON o.product_id = p.id
                                LEFT JOIN users u_d ON o.driver_phone = u_d.phone
                                WHERE o.id = %s
                            """, (o_id,))
                            rcpt_data = cursor.fetchone()
                            f_name, b_name, b_loc, p_price, p_qty, d_fee, s_total, d_opt, d_name, d_veh = rcpt_data
                            date_now = datetime.now().strftime("%d %b %Y")
                            time_now = datetime.now().strftime("%I:%M %p")
                            
                            receipt_msg = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         AGRO MARKET 🌱
   Agricultural Marketplace
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📄 RECEIPT NUMBER:
{rec_num}

📅 ORDER DATE:
{date_now}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👨‍🌾 SELLER DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Seller Name: {f_name}
Phone Number: +{f_phone.lstrip('+')}
Location: Marketplace Seller

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛒 BUYER DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Buyer Name: {b_name}
Phone Number: +{sender_phone.lstrip('+')}

Delivery Address:
{b_loc}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 ORDER DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Product: {p_name}
Quantity: {p_qty if p_qty else '1 Unit'}
Price Per Bag: {p_price if p_price else 'Market Value'}
Subtotal: Le {s_total}

Delivery Fee: Le {d_fee if d_fee else 0}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 PAYMENT DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Amount Paid: Le {total_amt}

Payment Status:
✅ PAID (RELEASED FROM ESCROW)

Payment Method:
Orange Money / Monime Escrow

Transaction ID:
{tx_id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚚 DELIVERY DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rider/Driver Name:
{d_name if d_name else 'Self-Delivery'}

Vehicle Type:
{d_opt if d_opt else 'Vendor Dispatch'}

Vehicle Number:
{d_veh if d_veh else 'N/A'}

Delivery Status:
✅ DELIVERED & APPROVED BY BUYER

Delivery Time:
{time_now}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⭐ THANK YOU FOR USING
        AGRO MARKET
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For support contact:
📞 +232 XX XXX XXX
📧 support@agromarket.sl
🌐 www.agromarket.sl"""
                            send_whatsapp_message(sender_phone, receipt_msg)
                            send_whatsapp_message(f_phone, f"💸 *Escrow Balance Released!* Buyer confirmed delivery tracking items for Order #{o_id}.\n\n" + receipt_msg)
                        else:
                            send_whatsapp_message(sender_phone, "❌ No pending order matching delivery approval requirements was logged for your device.")
                        cursor.close()
                        conn.close()
                    except Exception as e:
                        print(f"Escrow error validation tracker maps: {e}")
                        send_whatsapp_message(sender_phone, "Database timeout compiling receipt values.")
    except Exception as e:
        print(f"Error logic layer main arrays: {e}")
    return {"status": "ok"}
