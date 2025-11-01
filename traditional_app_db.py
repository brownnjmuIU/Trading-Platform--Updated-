from flask import Flask, render_template, request, jsonify, session
from datetime import datetime
import psycopg
from psycopg.rows import dict_row
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-traditional-production')

# Database connection
def get_db_connection():
    conn = psycopg.connect(
        os.environ.get('DATABASE_URL'),
        row_factory=dict_row
    )
    return conn

# Initialize database tables
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id SERIAL PRIMARY KEY,
            session_id VARCHAR(255) UNIQUE NOT NULL,
            platform_type VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            initial_cash DECIMAL(12, 2) DEFAULT 100000.00,
            current_cash DECIMAL(12, 2) DEFAULT 100000.00
        )
    ''')
    
    # Trades table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            trade_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(user_id),
            session_id VARCHAR(255) NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            action VARCHAR(10) NOT NULL,
            shares INTEGER NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            total_cost DECIMAL(12, 2) NOT NULL,
            order_type VARCHAR(20),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Portfolio table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS portfolio (
            portfolio_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(user_id),
            session_id VARCHAR(255) NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            shares INTEGER NOT NULL,
            avg_price DECIMAL(10, 2) NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, symbol)
        )
    ''')
    
    # Clickstream table for behavioral tracking
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clickstream (
            click_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(user_id),
            session_id VARCHAR(255) NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            event_data JSONB,
            page_url VARCHAR(255),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Orders table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(user_id),
            session_id VARCHAR(255) NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            side VARCHAR(10) NOT NULL,
            shares INTEGER NOT NULL,
            order_type VARCHAR(20) NOT NULL,
            limit_price DECIMAL(10, 2),
            status VARCHAR(20) DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    cur.close()
    conn.close()

# Initialize session and user
def init_user():
    if 'session_id' not in session:
        session['session_id'] = os.urandom(16).hex()
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO users (session_id, platform_type, initial_cash, current_cash)
            VALUES (%s, %s, %s, %s)
            RETURNING user_id
        ''', (session['session_id'], 'traditional', 100000.00, 100000.00))
        
        user = cur.fetchone()
        session['user_id'] = user['user_id']
        
        conn.commit()
        cur.close()
        conn.close()

# Log clickstream event
def log_event(event_type, event_data=None):
    if 'session_id' not in session:
        return
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO clickstream (user_id, session_id, event_type, event_data, page_url)
        VALUES (%s, %s, %s, %s, %s)
    ''', (
        session.get('user_id'),
        session['session_id'],
        event_type,
        json.dumps(event_data) if event_data else None,
        request.url
    ))
    
    conn.commit()
    cur.close()
    conn.close()

@app.route('/')
def index():
    init_user()
    log_event('page_view', {'page': 'home'})
    
    session_id = session['session_id']
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get user's current cash
    cur.execute('SELECT current_cash FROM users WHERE session_id = %s', (session_id,))
    user = cur.fetchone()
    current_cash = float(user['current_cash']) if user else 100000.00
    
    # Get portfolio
    cur.execute('''
        SELECT symbol, shares, avg_price 
        FROM portfolio 
        WHERE session_id = %s
    ''', (session_id,))
    portfolio_data = cur.fetchall()
    
    # Calculate portfolio value
    portfolio_value = current_cash
    positions = []
    market_data = get_market_data()
    
    for item in portfolio_data:
        stock = next((s for s in market_data if s['symbol'] == item['symbol']), None)
        if stock:
            market_value = item['shares'] * stock['last']
            cost_basis = item['shares'] * float(item['avg_price'])
            gain_loss = market_value - cost_basis
            gain_loss_percent = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0
            
            portfolio_value += market_value
            
            positions.append({
                'symbol': item['symbol'],
                'shares': item['shares'],
                'avg_cost': float(item['avg_price']),
                'current_price': stock['last'],
                'market_value': market_value,
                'gain_loss': gain_loss,
                'gain_loss_percent': gain_loss_percent
            })
    
    account_summary = {
        'total_value': portfolio_value,
        'cash_balance': current_cash,
        'buying_power': current_cash * 2,
        'today_change': portfolio_value - 100000.00,
        'today_change_percent': ((portfolio_value - 100000.00) / 100000.00 * 100)
    }
    
    # Get orders
    cur.execute('''
        SELECT order_id, symbol, side, shares, order_type, limit_price, status, created_at as timestamp
        FROM orders
        WHERE session_id = %s AND status = 'PENDING'
        ORDER BY created_at DESC
    ''', (session_id,))
    orders = cur.fetchall()
    
    # Get trade history
    cur.execute('''
        SELECT symbol, action as side, shares, price, total_cost as total, timestamp
        FROM trades
        WHERE session_id = %s
        ORDER BY timestamp DESC
        LIMIT 20
    ''', (session_id,))
    history = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # Format data for template
    formatted_orders = []
    for order in orders:
        formatted_orders.append({
            'id': order['order_id'],
            'symbol': order['symbol'],
            'side': order['side'],
            'shares': order['shares'],
            'order_type': order['order_type'],
            'limit_price': float(order['limit_price']) if order['limit_price'] else None,
            'status': order['status'],
            'timestamp': order['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        })
    
    formatted_history = []
    for trade in history:
        formatted_history.append({
            'symbol': trade['symbol'],
            'side': trade['side'],
            'shares': trade['shares'],
            'price': float(trade['price']),
            'total': float(trade['total']),
            'timestamp': trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        })
    
    return render_template('traditional.html',
                         account_summary=account_summary,
                         positions=positions,
                         market_data=market_data,
                         orders=formatted_orders,
                         history=formatted_history)

@app.route('/trade', methods=['POST'])
def trade():
    init_user()
    
    data = request.json
    symbol = data.get('symbol', '').upper()
    shares = int(data.get('shares', 0))
    action = data.get('action')
    order_type = data.get('order_type', 'market')
    limit_price = float(data.get('limit_price', 0)) if data.get('limit_price') else None
    
    log_event('trade_attempt', {
        'symbol': symbol,
        'shares': shares,
        'action': action,
        'order_type': order_type
    })
    
    if not symbol or shares <= 0:
        return jsonify({'success': False, 'message': 'Invalid order parameters'})
    
    stock = next((s for s in get_market_data() if s['symbol'] == symbol), None)
    if not stock:
        return jsonify({'success': False, 'message': 'Symbol not found'})
    
    session_id = session['session_id']
    
    # For market orders, execute immediately
    if order_type == 'market':
        price = stock['last']
        total_cost = shares * price
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT current_cash FROM users WHERE session_id = %s', (session_id,))
        user = cur.fetchone()
        current_cash = float(user['current_cash'])
        
        if action == 'buy':
            if total_cost > current_cash:
                cur.close()
                conn.close()
                return jsonify({'success': False, 'message': 'Insufficient funds'})
            
            # Update cash
            new_cash = current_cash - total_cost
            cur.execute('UPDATE users SET current_cash = %s WHERE session_id = %s', (new_cash, session_id))
            
            # Update portfolio
            cur.execute('SELECT shares, avg_price FROM portfolio WHERE session_id = %s AND symbol = %s', (session_id, symbol))
            existing = cur.fetchone()
            
            if existing:
                old_shares = existing['shares']
                old_avg = float(existing['avg_price'])
                new_shares = old_shares + shares
                new_avg = ((old_shares * old_avg) + (shares * price)) / new_shares
                
                cur.execute('''
                    UPDATE portfolio 
                    SET shares = %s, avg_price = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = %s AND symbol = %s
                ''', (new_shares, new_avg, session_id, symbol))
            else:
                cur.execute('''
                    INSERT INTO portfolio (user_id, session_id, symbol, shares, avg_price)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (session['user_id'], session_id, symbol, shares, price))
            
            # Record trade
            cur.execute('''
                    INSERT INTO trades (user_id, session_id, symbol, action, shares, price, total_cost)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (session['user_id'], session_id, symbol, 'BUY', shares, price, total_cost))
            
            conn.commit()
            cur.close()
            conn.close()
            
            log_event('trade_completed', {
                'symbol': symbol,
                'shares': shares,
                'action': 'buy',
                'price': price,
                'total': total_cost
            })
            
            return jsonify({
                'success': True,
                'message': f'Order filled: Bought {shares} shares of {symbol} at ${price:.2f}',
                'cash': new_cash
            })
        
        elif action == 'sell':
            cur.execute('SELECT shares FROM portfolio WHERE session_id = %s AND symbol = %s', (session_id, symbol))
            portfolio_item = cur.fetchone()
            
            if not portfolio_item or portfolio_item['shares'] < shares:
                cur.close()
                conn.close()
                return jsonify({'success': False, 'message': 'Insufficient shares'})
            
            # Update cash
            new_cash = current_cash + total_cost
            cur.execute('UPDATE users SET current_cash = %s WHERE session_id = %s', (new_cash, session_id))
            
            # Update portfolio
            new_shares = portfolio_item['shares'] - shares
            if new_shares == 0:
                cur.execute('DELETE FROM portfolio WHERE session_id = %s AND symbol = %s', (session_id, symbol))
            else:
                cur.execute('''
                    UPDATE portfolio 
                    SET shares = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = %s AND symbol = %s
                ''', (new_shares, session_id, symbol))
            
            # Record trade
            cur.execute('''
                INSERT INTO trades (user_id, session_id, symbol, action, shares, price, total_cost)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (session['user_id'], session_id, symbol, 'SELL', shares, price, total_cost))
            
            conn.commit()
            cur.close()
            conn.close()
            
            log_event('trade_completed', {
                'symbol': symbol,
                'shares': shares,
                'action': 'sell',
                'price': price,
                'total': total_cost
            })
            
            return jsonify({
                'success': True,
                'message': f'Order filled: Sold {shares} shares of {symbol} at ${price:.2f}',
                'cash': new_cash
            })
    
    # For limit orders, add to orders table
    else:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO orders (user_id, session_id, symbol, side, shares, order_type, limit_price, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (session['user_id'], session_id, symbol, action.upper(), shares, order_type, limit_price, 'PENDING'))
        
        conn.commit()
        cur.close()
        conn.close()
        
        log_event('order_placed', {
            'symbol': symbol,
            'shares': shares,
            'action': action,
            'order_type': order_type,
            'limit_price': limit_price
        })
        
        return jsonify({
            'success': True,
            'message': f'{order_type.capitalize()} order placed for {shares} shares of {symbol}'
        })

@app.route('/cancel_order', methods=['POST'])
def cancel_order():
    order_id = request.json.get('order_id')
    session_id = session.get('session_id')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE orders 
        SET status = 'CANCELLED' 
        WHERE order_id = %s AND session_id = %s
    ''', (order_id, session_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    log_event('order_cancelled', {'order_id': order_id})
    
    return jsonify({'success': True, 'message': 'Order cancelled'})

@app.route('/reset', methods=['POST'])
def reset():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'success': False, 'message': 'No session found'})
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('UPDATE users SET current_cash = 100000.00 WHERE session_id = %s', (session_id,))
    cur.execute('DELETE FROM portfolio WHERE session_id = %s', (session_id,))
    cur.execute('UPDATE orders SET status = %s WHERE session_id = %s', ('CANCELLED', session_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    log_event('account_reset')
    
    return jsonify({'success': True, 'message': 'Account reset successfully'})

def get_market_data():
    return [
        {'symbol': 'AAPL', 'name': 'Apple Inc.', 'bid': 178.22, 'ask': 178.24, 'last': 178.23, 'change': 1.89, 'change_percent': 1.07, 'volume': '87.2M'},
        {'symbol': 'MSFT', 'name': 'Microsoft Corporation', 'bid': 378.55, 'ask': 378.57, 'last': 378.56, 'change': -2.34, 'change_percent': -0.61, 'volume': '45.8M'},
        {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'bid': 142.14, 'ask': 142.16, 'last': 142.15, 'change': 0.78, 'change_percent': 0.55, 'volume': '32.1M'},
        {'symbol': 'TSLA', 'name': 'Tesla Inc.', 'bid': 242.83, 'ask': 242.85, 'last': 242.84, 'change': 5.67, 'change_percent': 2.39, 'volume': '145.3M'},
        {'symbol': 'NVDA', 'name': 'NVIDIA Corp', 'bid': 478.10, 'ask': 478.14, 'last': 478.12, 'change': -3.24, 'change_percent': -0.67, 'volume': '98M'},
        {'symbol': 'GME', 'name': 'GameStop Corp', 'bid': 18.43, 'ask': 18.47, 'last': 18.45, 'change': 2.34, 'change_percent': 14.53, 'volume': '234M'}
    ]

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5001)))