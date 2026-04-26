from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
import os
import json
from dotenv import load_dotenv
import psycopg2
import requests

load_dotenv()

app = FastAPI()

VERIFY_TOKEN = "my_custom_secure_token"
DATABASE_URL = os.getenv("DATABASE_URL")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

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

# --- COMMUNICATION FUNCTIONS ---

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

def send_role_menu(phone_number):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "interactive",
        "interactive": {
            "type": "list", "header": {"type": "text", "text": "Welcome to Agro Market 🌱"},
            "body": {"text": "To get started, please tell us how you want to use the platform."},
            "action": {
                "button": "Choose Role",
                "sections": [{"title": "Select Profile", "rows": [
                    {"id": "role_farmer", "title": "🌾 Farmer (Seller)", "description": "Sell your produce"},
                    {"id": "role_buyer", "title": "🛒 Buyer", "description": "Buy fresh produce"},
                    {"id": "role_input", "title": "🌱 Input Seller", "description": "Sell seeds & tools"},
                    {"id": "role_driver", "title": "🚚 Driver / Rider", "description": "Deliver orders"}
                ]}]
            }
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_main_menu(phone_number, role):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    
    sections = []
    if role == "role_farmer":
        sections = [{"title": "Farmer Dashboard", "rows": [
            {"id": "action_add_produce", "title": "Add Produce", "description": "➕ List new crops for sale"},
            {"id": "action_view_inventory", "title": "My Inventory", "description": "📦 See your active listings"},
            {"id": "action_view_orders", "title": "View Orders", "description": "📋 Check buyer requests"},
            {"id": "action_search_inputs", "title": "Buy Supplies", "description": "🚜 Find seeds, tools & fertilizer"}
        ]}]
    elif role == "role_buyer":
        sections = [{"title": "Buyer Dashboard", "rows": [
            {"id": "action_search_produce", "title": "Search Produce", "description": "🔍 Find crops near you"},
            {"id": "action_my_purchases", "title": "My Orders", "description": "🛒 Track your purchases"}
        ]}]
    elif role == "role_driver":
        sections = [{"title": "Driver Dashboard", "rows": [
            {"id": "action_find_deliveries", "title": "Find Deliveries", "description": "🚚 View ready orders near you"},
            {"id": "action_my_deliveries", "title": "My Deliveries", "description": "📦 Track your active jobs"}
        ]}]
    elif role == "role_input":
        sections = [{"title": "Input Seller Dashboard", "rows": [
            {"id": "action_add_input", "title": "Add Supply", "description": "➕ List seeds, tools, etc."},
            {"id": "action_view_inventory", "title": "My Inventory", "description": "📦 See your active listings"},
            {"id": "action_view_orders", "title": "View Orders", "description": "📋 Check farmer requests"}
        ]}]
    else:
        sections = [{"title": "Main Dashboard", "rows": [{"id": "action_coming_soon", "title": "Coming Soon", "description": "🚧 Under construction"}]}]

    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "interactive",
        "interactive": {
            "type": "list", "header": {"type": "text", "text": "Agro Market Dashboard 📱"},
            "body": {"text": "What would you like to do today?"},
            "action": {"button": "Open Menu", "sections": sections}
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_search_results_menu(phone_number, query, search_results, is_input=False):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    rows = []
    for item in search_results:
        p_id, p_name, price, quantity, image_id, f_phone, f_name, loc = item
        qty_text = quantity if quantity else "Unknown"
        rows.append({"id": f"viewitem_{p_id}", "title": p_name[:24], "description": f"{price} | {qty_text} available | 📍 {loc}"[:72]})

    header_text = f"Search: '{query}' 🚜" if is_input else f"Search: '{query}' 🔍"
    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "interactive",
        "interactive": {
            "type": "list", "header": {"type": "text", "text": header_text},
            "body": {"text": "Here is what we found nearby. Tap an item to view details & photos!"},
            "action": {"button": "View Items", "sections": [{"title": "Available Items", "rows": rows}]}
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_product_details_with_image(phone_number, p_id, p_name, price, quantity, f_name, loc, image_id):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    qty_text = quantity if quantity else "Unknown"
    
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {"type": "image", "image": {"id": image_id}},
            "body": {"text": f"📦 *{p_name}*\n💰 Price: {price}\n⚖️ Available: {qty_text}\n🧑‍🌾 Seller: {f_name} ({loc})\n\nWould you like to order this?"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": f"order_{p_id}", "title": "🛒 Buy Now"}},
                    {"type": "reply", "reply": {"id": "action_search_produce", "title": "🔍 Search Again"}}
                ]
            }
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_delivery_preference_buttons(phone_number, product_id, product_name):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": f"📦 Almost done!\n\nYou are ordering: *{product_name}*\n\nHow would you like to receive this?"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": f"delivery_{product_id}", "title": "🚚 Need Delivery"}},
                    {"type": "reply", "reply": {"id": f"pickup_{product_id}", "title": "🚶 Self Pickup"}}
                ]
            }
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_pending_orders_menu(phone_number, pending_orders):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    rows = []
    for order in pending_orders:
        o_id, p_name, b_name, b_phone, b_loc, pref = order
        pref_text = "🚚 Delivery" if pref == "delivery" else "🚶 Pickup"
        rows.append({"id": f"manage_{o_id}", "title": f"Order #{o_id}", "description": f"{p_name} for {b_name} | {pref_text}"[:72]})

    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "interactive",
        "interactive": {
            "type": "list", "header": {"type": "text", "text": "Pending Orders 📋"},
            "body": {"text": "Select an order to Accept or Decline."},
            "action": {"button": "View Orders", "sections": [{"title": "Action Required", "rows": rows}]}
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_order_action_buttons(phone_number, order_id, product_name, buyer_name, preference):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    pref_text = "Delivery Needed 🚚" if preference == "delivery" else "Buyer will Pickup 🚶"
    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": f"📦 *Manage Order #{order_id}*\n\nItem: {product_name}\nBuyer: {buyer_name}\nMethod: *{pref_text}*\n\nWhat would you like to do?"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": f"accept_{order_id}", "title": "✅ Accept"}},
                    {"type": "reply", "reply": {"id": f"decline_{order_id}", "title": "❌ Decline"}}
                ]
            }
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_available_deliveries_menu(phone_number, deliveries):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    rows = []
    for d in deliveries:
        o_id, p_name, f_name, f_loc, b_name, b_loc = d
        rows.append({"id": f"deliv_{o_id}", "title": f"Job #{o_id}: {p_name}"[:24], "description": f"From: {f_loc} To: {b_loc}"[:72]})

    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "interactive",
        "interactive": {
            "type": "list", "header": {"type": "text", "text": "Available Deliveries 🚚"},
            "body": {"text": "Select a delivery job to view details and accept it."},
            "action": {"button": "View Jobs", "sections": [{"title": "Ready for Pickup", "rows": rows}]}
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_delivery_action_buttons(phone_number, order_id, product_name, f_name, f_loc, b_name, b_loc):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": f"🚚 *Delivery Job #{order_id}*\n\n📦 Item: {product_name}\n📍 Pickup: {f_name} ({f_loc})\n🎯 Dropoff: {b_name} ({b_loc})\n\nDo you want to accept this delivery?"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": f"acceptdeliv_{order_id}", "title": "✅ Accept Job"}}
                ]
            }
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_my_deliveries_menu(phone_number, deliveries):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    rows = []
    for d in deliveries:
        o_id, p_name, f_name, f_loc, f_phone, b_name, b_loc, b_phone = d
        rows.append({"id": f"managejob_{o_id}", "title": f"Job #{o_id}"[:24], "description": f"Deliver to: {b_loc}"[:72]})

    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "interactive",
        "interactive": {
            "type": "list", "header": {"type": "text", "text": "My Active Deliveries 🚚"},
            "body": {"text": "Select a job to view details or mark it as delivered."},
            "action": {"button": "View Active Jobs", "sections": [{"title": "In Transit", "rows": rows}]}
        }
    }
    requests.post(url, headers=headers, json=payload)

def send_job_completion_buttons(phone_number, order_id, product_name, b_name, f_phone, b_phone):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": f"🚚 *Job #{order_id} In Progress*\n\n📦 Item: {product_name}\n🎯 Dropoff: {b_name}\n\n📞 Pickup: wa.me/{f_phone}\n📞 Dropoff: wa.me/{b_phone}\n\nDid you successfully deliver this order?"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": f"delivered_{order_id}", "title": "✅ Mark Delivered"}}
                ]
            }
        }
    }
    requests.post(url, headers=headers, json=payload)

# --- DATABASE FUNCTIONS ---

# UPDATED: We now fetch the nin_status from the database
def get_user_profile(phone_number):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT us.current_flow, us.current_step, u.role, u.nin_status FROM user_sessions us LEFT JOIN users u ON us.phone = u.phone WHERE us.phone = %s", (phone_number,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return {"flow": result[0], "step": result[1], "role": result[2], "nin_status": result[3]} if result else None
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
        cursor.execute("UPDATE user_sessions SET current_flow = %s, current_step = %s WHERE phone = %s", (flow, step, phone_number))
        conn.commit()
        cursor.close()
        conn.close()
    except: pass

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
            FROM products p
            JOIN users u ON p.farmer_phone = u.phone
            WHERE p.product_name ILIKE %s AND p.category = %s
            ORDER BY 
                (u.location ILIKE %s) DESC, 
                p.created_at DESC 
            LIMIT 5
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
        cursor.execute("""
            SELECT p.id, p.product_name, p.price, p.quantity, p.image_id, p.farmer_phone, u.name, u.location
            FROM products p
            JOIN users u ON p.farmer_phone = u.phone
            WHERE p.id = %s
        """, (product_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result
    except: return None

def create_order(buyer_phone, product_id, preference):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT product_name, farmer_phone, price FROM products WHERE id = %s", (product_id,))
        prod = cursor.fetchone()
        if not prod: return None
        prod_name, farmer_phone, price = prod
        cursor.execute("INSERT INTO orders (buyer_phone, farmer_phone, product_id, product_name, status, delivery_preference) VALUES (%s, %s, %s, %s, 'pending', %s)", (buyer_phone, farmer_phone, product_id, prod_name, preference))
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
            SELECT o.id, o.product_name, u.name, u.phone, u.location, o.delivery_preference
            FROM orders o
            JOIN users u ON o.buyer_phone = u.phone
            WHERE o.farmer_phone = %s AND o.status = 'pending'
            ORDER BY o.created_at DESC
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
        cursor.execute("""
            SELECT o.id, o.product_name, o.status, u.name, u.phone
            FROM orders o
            JOIN users u ON o.farmer_phone = u.phone
            WHERE o.buyer_phone = %s
            ORDER BY o.created_at DESC
        """, (buyer_phone,))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def get_order_by_id(order_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.id, o.product_name, o.buyer_phone, u.name, o.status, o.delivery_preference
            FROM orders o
            JOIN users u ON o.buyer_phone = u.phone
            WHERE o.id = %s
        """, (order_id,))
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
            FROM orders o
            JOIN users f ON o.farmer_phone = f.phone
            JOIN users b ON o.buyer_phone = b.phone
            WHERE o.status = 'ACCEPTED' AND o.delivery_preference = 'delivery'
            ORDER BY o.created_at DESC LIMIT 5
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
            FROM orders o
            JOIN users f ON o.farmer_phone = f.phone
            JOIN users b ON o.buyer_phone = b.phone
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
            FROM orders o
            JOIN users f ON o.farmer_phone = f.phone
            JOIN users b ON o.buyer_phone = b.phone
            WHERE o.driver_phone = %s AND o.status = 'IN_TRANSIT'
            ORDER BY o.created_at DESC
        """, (driver_phone,))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except: return []

def update_user_role_and_step(phone_number, role_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (phone, role) VALUES (%s, %s) ON CONFLICT (phone) DO UPDATE SET role = EXCLUDED.role;", (phone_number, role_id))
        cursor.execute("INSERT INTO user_sessions (phone, current_flow, current_step) VALUES (%s, 'registration', 'awaiting_name') ON CONFLICT (phone) DO UPDATE SET current_flow = EXCLUDED.current_flow, current_step = EXCLUDED.current_step;", (phone_number,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

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

def update_user_nin_and_step(phone_number, nin):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET nin_number = %s, nin_status = 'pending' WHERE phone = %s", (nin, phone_number))
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
        cursor.execute("UPDATE user_sessions SET current_flow = 'main_menu', current_step = 'registered' WHERE phone = %s", (phone_number,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except: return False

# NEW: Admin DB Functions
def get_pending_verifications():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        # Buyers don't strictly need NIN verification to buy, so we only flag sellers & drivers
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

# --- MAIN WEBHOOK ---

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
            
            # 1. INTERACTIVE ACTIONS
            if msg_type == "interactive":
                interactive_type = message_data["interactive"]["type"]
                
                if interactive_type == "list_reply":
                    selected_id = message_data["interactive"]["list_reply"]["id"]
                    
                    if selected_id.startswith("role_"):
                        if update_user_role_and_step(sender_phone, selected_id):
                            send_whatsapp_message(sender_phone, f"Awesome! Profile started. Please type your *Full Name*.")
                            return {"status": "ok"}
                    
                    # NEW: THE GATEKEEPER! 🛑
                    # If they try to sell or drive, we check their NIN status first!
                    restricted_actions = ["action_add_produce", "action_add_input", "action_find_deliveries"]
                    if selected_id in restricted_actions and profile and profile.get("nin_status") == "pending":
                        send_whatsapp_message(sender_phone, "⏳ *Account Pending Verification*\n\nYour NIN is currently under review by our admin team to ensure marketplace safety. You will be notified once verified and granted full access to sell or deliver!")
                        return {"status": "ok"}

                    elif selected_id == "action_add_produce":
                        update_session(sender_phone, "add_produce", "awaiting_produce_name")
                        send_whatsapp_message(sender_phone, "Great! 🌾 What is the name of the produce you are selling?")
                    
                    elif selected_id == "action_add_input":
                        update_session(sender_phone, "add_input", "awaiting_produce_name")
                        send_whatsapp_message(sender_phone, "Great! 🚜 What is the name of the supply/tool you are selling?")

                    elif selected_id == "action_view_inventory":
                        inventory = get_user_inventory(sender_phone)
                        if not inventory:
                            send_whatsapp_message(sender_phone, "📦 Your inventory is currently empty. Click 'Add Produce/Supply' to list something!")
                        else:
                            msg = "📦 *Your Active Inventory:*\n\n"
                            for item in inventory:
                                msg += f"✔️ *{item[0]}*\n💰 {item[1]}\n---\n"
                            send_whatsapp_message(sender_phone, msg)

                    elif selected_id == "action_view_orders":
                        pending_orders = get_farmer_orders(sender_phone)
                        if not pending_orders:
                            send_whatsapp_message(sender_phone, "✅ You have no pending orders right now. You're all caught up!")
                        else:
                            send_pending_orders_menu(sender_phone, pending_orders)
                            
                    elif selected_id.startswith("manage_"):
                        order_id = selected_id.split("_")[1]
                        order_details = get_order_by_id(order_id)
                        if order_details:
                            o_id, p_name, b_phone, b_name, status, pref = order_details
                            send_order_action_buttons(sender_phone, o_id, p_name, b_name, pref)

                    elif selected_id == "action_search_produce":
                        update_session(sender_phone, "buyer_search", "awaiting_search_query")
                        send_whatsapp_message(sender_phone, "🔍 What produce are you looking for today? (e.g., Rice, Tomatoes)")
                    
                    elif selected_id == "action_search_inputs":
                        update_session(sender_phone, "farmer_search", "awaiting_search_query")
                        send_whatsapp_message(sender_phone, "🚜 What supplies do you need? (e.g., Tractor, Seeds, Fertilizer)")

                    elif selected_id.startswith("viewitem_"):
                        product_id = selected_id.split("_")[1]
                        details = get_product_by_id(product_id)
                        if details:
                            p_id, p_name, price, qty, img_id, f_phone, f_name, loc = details
                            send_product_details_with_image(sender_phone, p_id, p_name, price, qty, f_name, loc, img_id)

                    elif selected_id == "action_my_purchases":
                        buyer_orders = get_buyer_orders(sender_phone)
                        if not buyer_orders:
                            send_whatsapp_message(sender_phone, "🛒 You haven't placed any orders yet. Click 'Search' to find something!")
                        else:
                            msg = "🛒 *Your Recent Orders:*\n\n"
                            for order in buyer_orders:
                                o_id, p_name, status, f_name, f_phone = order
                                msg += f"📦 *{p_name}* (Order #{o_id})\n⏳ Status: *{status.upper()}*\n🧑‍🌾 Seller: {f_name}\n📞 Contact: wa.me/{f_phone}\n---\n"
                            send_whatsapp_message(sender_phone, msg)
                    
                    elif selected_id == "action_find_deliveries":
                        deliveries = get_available_deliveries()
                        if not deliveries:
                            send_whatsapp_message(sender_phone, "🚫 There are currently no deliveries available in your area. Check back later!")
                        else:
                            send_available_deliveries_menu(sender_phone, deliveries)

                    elif selected_id.startswith("deliv_"):
                        order_id = selected_id.split("_")[1]
                        details = get_delivery_details(order_id)
                        if details:
                            o_id, p_name, f_name, f_loc, f_phone, b_name, b_loc, b_phone = details
                            send_delivery_action_buttons(sender_phone, o_id, p_name, f_name, f_loc, b_name, b_loc)

                    elif selected_id == "action_my_deliveries":
                        my_jobs = get_driver_deliveries(sender_phone)
                        if not my_jobs:
                            send_whatsapp_message(sender_phone, "🚚 You currently have no active deliveries. Click 'Find Deliveries' to get a job!")
                        else:
                            send_my_deliveries_menu(sender_phone, my_jobs)

                    elif selected_id.startswith("managejob_"):
                        order_id = selected_id.split("_")[1]
                        details = get_delivery_details(order_id)
                        if details:
                            o_id, p_name, _, _, f_phone, b_name, _, b_phone = details
                            send_job_completion_buttons(sender_phone, o_id, p_name, b_name, f_phone, b_phone)

                elif interactive_type == "button_reply":
                    selected_id = message_data["interactive"]["button_reply"]["id"]

                    if selected_id.startswith("order_"):
                        product_id = selected_id.split("_")[1]
                        details = get_product_by_id(product_id)
                        if details:
                            p_name = details[1]
                            send_delivery_preference_buttons(sender_phone, product_id, p_name)
                    
                    elif selected_id.startswith("delivery_") or selected_id.startswith("pickup_"):
                        preference_choice, product_id = selected_id.split("_")
                        
                        order_details = create_order(sender_phone, product_id, preference_choice)
                        
                        if order_details:
                            pref_text = "Delivery Needed 🚚" if preference_choice == "delivery" else "Self-Pickup 🚶"
                            send_whatsapp_message(sender_phone, f"✅ Order placed successfully for *{order_details['product_name']}*!\n\nPreference: {pref_text}\n\nThe seller has been notified and will contact you shortly.")
                            
                            farmer_phone = order_details["farmer_phone"]
                            buyer_link = f"wa.me/{sender_phone}"
                            alert_msg = f"🚨 *NEW ORDER ALERT!* 🚨\n\nA buyer wants to purchase your *{order_details['product_name']}* ({order_details['price']}).\n\nMethod: *{pref_text}*\n\nBuyer's Contact: {buyer_link}\n\nPlease check 'View Orders' on your dashboard to accept it."
                            send_whatsapp_message(farmer_phone, alert_msg)
                        else:
                            send_whatsapp_message(sender_phone, "Sorry, there was an issue placing the order.")

                    elif selected_id == "action_search_produce":
                        update_session(sender_phone, "buyer_search", "awaiting_search_query")
                        send_whatsapp_message(sender_phone, "🔍 What produce are you looking for today? (e.g., Rice, Tomatoes)")

                    elif selected_id.startswith("accept_") or selected_id.startswith("decline_"):
                        action, order_id = selected_id.split("_")
                        new_status = "ACCEPTED" if action == "accept" else "DECLINED"
                        update_order_status(order_id, new_status)
                        icon = "✅" if new_status == "ACCEPTED" else "❌"
                        send_whatsapp_message(sender_phone, f"{icon} You have {new_status} Order #{order_id}.")
                        
                        order_details = get_order_by_id(order_id)
                        if order_details:
                            _, p_name, b_phone, _, _, _ = order_details
                            send_whatsapp_message(b_phone, f"🔔 *Order Update!*\n\nThe seller has {new_status} your order for {p_name}.")
                            
                    elif selected_id.startswith("acceptdeliv_"):
                        order_id = selected_id.split("_")[1]
                        success = assign_driver_to_order(order_id, sender_phone)
                        
                        if success:
                            send_whatsapp_message(sender_phone, f"✅ You have successfully claimed Delivery Job #{order_id}!\n\nCheck 'My Deliveries' on your dashboard for the exact pickup and dropoff contact links.")
                            details = get_delivery_details(order_id)
                            if details:
                                _, p_name, _, _, f_phone, _, _, b_phone = details
                                driver_link = f"wa.me/{sender_phone}"
                                send_whatsapp_message(f_phone, f"🚚 *Driver Assigned!* 🚚\n\nA driver is on their way to pick up the *{p_name}* (Order #{order_id}).\n\nDriver Contact: {driver_link}")
                                send_whatsapp_message(b_phone, f"🚚 *Order Shipped!* 🚚\n\nYour *{p_name}* (Order #{order_id}) has been picked up by a driver and is on its way!\n\nDriver Contact: {driver_link}")
                        else:
                            send_whatsapp_message(sender_phone, "❌ Sorry, there was an issue accepting this job. It might have been claimed by someone else.")

                    elif selected_id.startswith("delivered_"):
                        order_id = selected_id.split("_")[1]
                        update_order_status(order_id, "DELIVERED")
                        send_whatsapp_message(sender_phone, f"✅ Job #{order_id} marked as DELIVERED! Great work.")
                        details = get_delivery_details(order_id)
                        if details:
                            _, p_name, _, _, f_phone, _, _, b_phone = details
                            send_whatsapp_message(f_phone, f"🎉 *Delivery Complete!* 🎉\n\nYour {p_name} (Order #{order_id}) has been successfully delivered to the buyer.")
                            send_whatsapp_message(b_phone, f"🎉 *Package Arrived!* 🎉\n\nYour {p_name} (Order #{order_id}) has been successfully delivered! Thank you for using Agro Market.")

            # 2. TEXT ACTIONS
            elif msg_type == "text":
                text = message_data["text"]["body"].strip()
                
                if text.lower() in ["hi", "hello", "menu"]:
                    if profile and profile["step"] == "registered":
                        send_main_menu(sender_phone, profile["role"])
                    else:
                        send_role_menu(sender_phone)

                elif profile and profile["flow"] == "registration":
                    if profile["step"] == "awaiting_name":
                        if update_user_name_and_step(sender_phone, text):
                            send_whatsapp_message(sender_phone, "Thanks! Now please enter your *NIN*.")
                    elif profile["step"] == "awaiting_nin":
                        if update_user_nin_and_step(sender_phone, text):
                            send_whatsapp_message(sender_phone, "NIN Saved. Finally, tell us your *Location*.")
                    elif profile["step"] == "awaiting_location":
                        if update_user_location_and_finish(sender_phone, text):
                            send_whatsapp_message(sender_phone, "Registration Complete! 🎉 Type *'menu'* to start.")

                elif profile and profile["flow"] in ["add_produce", "add_input"]:
                    if profile["step"] == "awaiting_produce_name":
                        update_session_data(sender_phone, {"produce_name": text})
                        update_session(sender_phone, profile["flow"], "awaiting_produce_price")
                        send_whatsapp_message(sender_phone, f"Got it: *{text}*. What is the price? (e.g., 500 per unit)")
                    elif profile["step"] == "awaiting_produce_price":
                        update_session_data(sender_phone, {"produce_price": text})
                        update_session(sender_phone, profile["flow"], "awaiting_produce_quantity")
                        send_whatsapp_message(sender_phone, "Got it. ⚖️ What is the available quantity? (e.g., 50 kg, 20 bags)")
                    elif profile["step"] == "awaiting_produce_quantity":
                        update_session_data(sender_phone, {"produce_quantity": text})
                        update_session(sender_phone, profile["flow"], "awaiting_produce_image")
                        send_whatsapp_message(sender_phone, "Perfect. 📸 Finally, **send a photo** of the item!")

                elif profile and profile["flow"] == "buyer_search":
                    if profile["step"] == "awaiting_search_query":
                        buyer_location = get_user_location(sender_phone)
                        search_results = search_marketplace(text, category='produce', buyer_location=buyer_location)
                        if not search_results:
                            send_whatsapp_message(sender_phone, f"😔 We couldn't find any produce listings for '{text}'.\n\nType *'menu'* to go back.")
                        else:
                            send_search_results_menu(sender_phone, text, search_results, is_input=False)
                        update_session(sender_phone, "main_menu", "registered")

                elif profile and profile["flow"] == "farmer_search":
                    if profile["step"] == "awaiting_search_query":
                        buyer_location = get_user_location(sender_phone)
                        search_results = search_marketplace(text, category='input', buyer_location=buyer_location)
                        if not search_results:
                            send_whatsapp_message(sender_phone, f"😔 We couldn't find any supply listings for '{text}'.\n\nType *'menu'* to go back.")
                        else:
                            send_search_results_menu(sender_phone, text, search_results, is_input=True)
                        update_session(sender_phone, "main_menu", "registered")

            # 3. IMAGE ACTIONS
            elif msg_type == "image":
                if profile and profile["step"] == "awaiting_produce_image":
                    image_id = message_data["image"]["id"]
                    category = 'input' if profile["flow"] == "add_input" else 'produce'
                    save_new_product(sender_phone, image_id, category=category)
                    
                    update_session(sender_phone, "main_menu", "registered")
                    send_whatsapp_message(sender_phone, "Listing Complete! 🎉 Your item is now live. Type 'menu' to see your dashboard.")

    except Exception as e:
        print(f"Error: {e}")
    return {"status": "ok"}

# ========================================================
# NEW: ADMIN WEB DASHBOARD ROUTES
# ========================================================

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard():
    pending_users = get_pending_verifications()
    
    html_content = """
    <html>
        <head>
            <title>Agro Market Admin Panel</title>
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; padding: 40px; }
                h1 { color: #2E7D32; }
                table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
                th, td { padding: 15px; text-align: left; border-bottom: 1px solid #ddd; }
                th { background-color: #2E7D32; color: white; }
                .btn { background-color: #4CAF50; color: white; border: none; padding: 10px 20px; text-align: center; border-radius: 5px; cursor: pointer; font-weight: bold;}
                .btn:hover { background-color: #45a049; }
                .empty { color: #555; font-style: italic; }
            </style>
        </head>
        <body>
            <h1>🛡️ Agro Market Admin Dashboard</h1>
            <p>Review the National Identification Numbers (NIN) of newly registered Sellers and Drivers to ensure a secure marketplace.</p>
            <br>
            <h3>⏳ Pending Verifications</h3>
            <table>
                <tr>
                    <th>Full Name</th>
                    <th>Phone Number</th>
                    <th>Requested Role</th>
                    <th>NIN Number</th>
                    <th>Action</th>
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
                    <td>{name}</td>
                    <td>{phone}</td>
                    <td>{display_role}</td>
                    <td><b>{nin}</b></td>
                    <td>
                        <form action="/admin/verify/{phone}" method="post" style="margin:0;">
                            <button type="submit" class="btn">✅ Approve User</button>
                        </form>
                    </td>
                </tr>
            """
            
    html_content += """
            </table>
        </body>
    </html>
    """
    return html_content

@app.post("/admin/verify/{phone}")
async def verify_user(phone: str):
    if approve_user_nin(phone):
        # Alert the user instantly via WhatsApp that they've been approved!
        send_whatsapp_message(phone, "🎉 *Identity Verified!*\n\nYour NIN has been successfully reviewed by our admin team. You are now a trusted and verified member of Agro Market.\n\nType *'menu'* to access your full dashboard.")
    
    return HTMLResponse("<script>alert('User Successfully Verified! They have been notified via WhatsApp.'); window.location.href='/admin';</script>")