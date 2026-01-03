
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)
app.secret_key = 'unity_arena_sheets_final_v9'

# --- Google Sheets Connection ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open("UnityArenaDB")
    
    def get_ws(name, headers):
        try: return sheet.worksheet(name)
        except:
            s = sheet.add_worksheet(title=name, rows="1000", cols="10")
            s.append_row(headers)
            return s

    ws_products = get_ws("Products", ["Name", "Category", "BuyPrice", "SellPrice", "Stock", "Limit"])
    ws_txns = get_ws("Transactions", ["ID", "Item", "Category", "Qty", "SellTotal", "CostTotal", "Desc", "Time"])
    ws_expenses = get_ws("Expenses", ["Title", "Amount", "Category", "Time"])
    ws_history = get_ws("StockHistory", ["Item", "Qty", "Time"])
except Exception as e:
    print(f"CRITICAL ERROR: {e}")

# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('user'), request.form.get('pass')
        if u == 'owner' and p == 'owner123':
            session['user'], session['role'] = 'Owner', 'owner'
            return redirect(url_for('index'))
        if u == 'manager' and p == 'manager123':
            session['user'], session['role'] = 'Manager', 'manager'
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    prods = ws_products.get_all_records()
    all_txns = ws_txns.get_all_records()
    today = datetime.now().strftime('%Y-%m-%d')
    today_txns = [t for t in all_txns if t['Time'].startswith(today)][::-1]
    low_stock = [p for p in prods if int(p['Stock']) <= int(p['Limit'])]
    slots = ["6 AM", "7 AM", "8 AM", "9 AM", "10 AM", "11 AM", "12 PM", "1 PM", "2 PM", "3 PM", "4 PM", "5 PM", "6 PM", "7 PM", "8 PM", "9 PM", "10 PM", "11 PM", "12 AM", "1 AM"]
    return render_template('index.html', products=prods, slots=slots, today_txns=today_txns, low_stock=low_stock)

@app.route('/submit_order', methods=['POST'])
def submit_order():
    data = request.json
    order_id = str(uuid.uuid4())[:8]
    all_prods = ws_products.get_all_records()
    
    for item in data['items']:
        cost = 0
        for i, p in enumerate(all_prods):
            if p['Name'] == item['name']:
                if p['Category'] == 'Sale':
                    new_stock = int(p['Stock']) - int(item['qty'])
                    ws_products.update_cell(i+2, 5, new_stock)
                    cost = float(p['BuyPrice']) * int(item['qty'])
                break
        ws_txns.append_row([order_id, item['name'], item['category'], item['qty'], item['price']*item['qty'], cost, data.get('desc'), datetime.now().strftime('%Y-%m-%d %H:%M')])
    return jsonify({"success": True})

@app.route('/undo_txn/<id>', methods=['POST'])
def undo_txn(id):
    rows = ws_txns.get_all_records()
    for i, r in enumerate(rows):
        if str(r['ID']) == str(id):
            if r['Category'] == 'Sale':
                p_rows = ws_products.get_all_records()
                for j, p in enumerate(p_rows):
                    if p['Name'] == r['Item']:
                        ws_products.update_cell(j+2, 5, int(p['Stock']) + int(r['Qty']))
            ws_txns.delete_rows(i+2)
            break
    return redirect(url_for('index'))

@app.route('/admin')
def admin():
    if session.get('role') != 'owner': return "Unauthorized", 403
    prods = ws_products.get_all_records()
    txns = ws_txns.get_all_records()
    exps = ws_expenses.get_all_records()
    hist = ws_history.get_all_records()
    
    rev = sum(float(t['SellTotal']) for t in txns)
    total_exp = sum(float(e['Amount']) for e in exps)
    cogs = sum(float(t['CostTotal']) for t in txns)
    
    chart_data = {'Sale':0, 'Rent':0, 'Booking':0}
    for t in txns: chart_data[t['Category']] = chart_data.get(t['Category'], 0) + float(t['SellTotal'])

    return render_template('admin.html', revenue=rev, expenses_total=total_exp, profit=rev-total_exp-cogs, 
                           products=prods, expenses=exps, stock_history=hist[::-1], chart_data=chart_data, txns=txns[::-1])

@app.route('/product/add', methods=['POST'])
def add_product():
    name, qty = request.form.get('name'), int(request.form.get('stock') or 0)
    all_prods = ws_products.get_all_records()
    found = False
    for i, p in enumerate(all_prods):
        if p['Name'] == name:
            ws_products.update_cell(i+2, 5, int(p['Stock']) + qty)
            ws_products.update_cell(i+2, 3, request.form.get('buy'))
            ws_products.update_cell(i+2, 4, request.form.get('sell'))
            found = True; break
    if not found:
        ws_products.append_row([name, request.form.get('cat'), request.form.get('buy'), request.form.get('sell'), qty, request.form.get('low_limit')])
    ws_history.append_row([name, qty, datetime.now().strftime('%Y-%m-%d %H:%M')])
    return redirect(url_for('admin'))

@app.route('/add_expense', methods=['POST'])
def add_expense():
    ws_expenses.append_row([request.form['title'], request.form['amount'], request.form['cat'], datetime.now().strftime('%Y-%m-%d')])
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
