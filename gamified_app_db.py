from flask import Flask, render_template, request, jsonify, session
from datetime import datetime
import psycopg
from psycopg.rows import dict_row
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production-please')

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
    
    # Clickstream table for detailed behavioral tracking
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
    
    conn.commit()
    cur.close()
    conn.close()

# Initialize session and user
def init_user():
    if 'session_id' not in session:
        session['session_id'] = os.urandom(16).hex()
        
        # Create user in database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO users (session_id, platform_type, initial_cash, current_cash)
            VALUES (%s, %s, %s, %s)
            RETURNING user_id
        ''', (session['session_id'], 'gamified', 100000.00, 100000.00))
        
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
    
    # Get user's current cash
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT current_cash FROM users WHERE session_id = %s', (session_id,))
    user = cur.fetchone()
    current_cash = float(user['current_cash']) if user else 100000.00
    
    # Get portfolio from database
    cur.execute('''
        SELECT symbol, shares, avg_price 
        FROM portfolio 
        WHERE session_id = %s
    ''', (session_id,))
    portfolio_data = cur.fetchall()
    
    # Calculate portfolio value
    portfolio_value = current_cash
    portfolio_items = []
    trending_stocks = get_trending_stocks()
    
    for item in portfolio_data:
        stock = next((s for s in trending_stocks if s['symbol'] == item['symbol']), None)
        if stock:
            current_value = item['shares'] * stock['price']
            cost_basis = item['shares'] * float(item['avg_price'])
            gain_loss = current_value - cost_basis
            gain_loss_percent = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0
            
            portfolio_value += current_value
            
            portfolio_items.append({
                'symbol': item['symbol'],
                'shares': item['shares'],
                'avg_price': float(item['avg_price']),
                'current_price': stock['price'],
                'current_value': current_value,
                'gain_loss': gain_loss,
                'gain_loss_percent': gain_loss_percent
            })
    
    # Get trade history
    cur.execute('''
        SELECT symbol, action, shares, price, total_cost, timestamp
        FROM trades
        WHERE session_id = %s
        ORDER BY timestamp DESC
        LIMIT 10
    ''', (session_id,))
    trade_history = cur.fetchall()
    
    cur.close()
    conn.close()
    
    user_stats = {
        'rank': 47,
        'total_users': 12453,
        'streak': 12,
        'badges': 8,
        'portfolio_value': portfolio_value,
        'cash': current_cash,
        'daily_change': portfolio_value - 100000.00,
        'daily_change_percent': ((portfolio_value - 100000.00) / 100000.00 * 100),
        'level': 'Gold Trader',
        'xp': 8450,
        'next_level_xp': 10000
    }
    
    leaderboard = [
        {'rank': 1, 'name': 'TradeMaster_99', 'returns': 147.3, 'streak': 45, 'badge': '🏆'},
        {'rank': 2, 'name': 'BullMarket_King', 'returns': 132.8, 'streak': 38, 'badge': '🥈'},
        {'rank': 3, 'name': 'DiamondHands_Pro', 'returns': 128.5, 'streak': 31, 'badge': '🥉'},
        {'rank': 4, 'name': 'MoonShot_Trader', 'returns': 119.2, 'streak': 28, 'badge': '⭐'},
        {'rank': 5, 'name': 'StockWhiz_AI', 'returns': 115.7, 'streak': 25, 'badge': '⭐'},
        {'rank': 6, 'name': 'RocketTrader_X', 'returns': 108.3, 'streak': 22, 'badge': '⭐'},
        {'rank': 47, 'name': 'You', 'returns': ((portfolio_value - 100000) / 100000 * 100), 'streak': 12, 'badge': '🔥', 'is_user': True}
    ]
    
    achievements = get_achievements()
    
    # Format trade history
    formatted_history = []
    for trade in trade_history:
        formatted_history.append({
            'symbol': trade['symbol'],
            'action': trade['action'],
            'shares': trade['shares'],
            'price': float(trade['price']),
            'total': float(trade['total_cost']),
            'timestamp': trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        })
    
    return render_template('gamified.html',
                         user_stats=user_stats,
                         leaderboard=leaderboard,
                         trending_stocks=trending_stocks,
                         achievements=achievements,
                         portfolio=portfolio_items,
                         trade_history=formatted_history)

@app.route('/trade', methods=['POST'])
def trade():
    init_user()
    
    data = request.json
    symbol = data.get('symbol')
    shares = int(data.get('shares', 0))
    action = data.get('action')
    
    log_event('trade_attempt', {
        'symbol': symbol,
        'shares': shares,
        'action': action
    })
    
    if shares <= 0:
        return jsonify({'success': False, 'message': 'Invalid number of shares'})
    
    stock = next((s for s in get_trending_stocks() if s['symbol'] == symbol), None)
    if not stock:
        return jsonify({'success': False, 'message': 'Stock not found'})
    
    price = stock['price']
    total_cost = shares * price
    session_id = session['session_id']
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get current cash
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
            'message': f'Successfully bought {shares} shares of {symbol}!',
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
            'message': f'Successfully sold {shares} shares of {symbol}!',
            'cash': new_cash
        })
    
    cur.close()
    conn.close()
    return jsonify({'success': False, 'message': 'Invalid action'})

@app.route('/reset', methods=['POST'])
def reset():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'success': False, 'message': 'No session found'})
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Reset cash
    cur.execute('UPDATE users SET current_cash = 100000.00 WHERE session_id = %s', (session_id,))
    
    # Clear portfolio
    cur.execute('DELETE FROM portfolio WHERE session_id = %s', (session_id,))
    
    # Keep trade history for research purposes
    
    conn.commit()
    cur.close()
    conn.close()
    
    log_event('portfolio_reset')
    
    return jsonify({'success': True, 'message': 'Portfolio reset successfully!'})

def get_trending_stocks():
    return [
        {'symbol': 'TSLA', 'name': 'Tesla Inc', 'price': 242.84, 'change': 5.67, 'percent': 2.39, 'volume': '145M', 'trending': 'up', 'popularity': 94},
        {'symbol': 'NVDA', 'name': 'NVIDIA Corp', 'price': 478.12, 'change': -3.24, 'percent': -0.67, 'volume': '98M', 'trending': 'up', 'popularity': 91},
        {'symbol': 'AAPL', 'name': 'Apple Inc', 'price': 178.23, 'change': 1.89, 'percent': 1.07, 'volume': '87M', 'trending': 'up', 'popularity': 88},
        {'symbol': 'GME', 'name': 'GameStop', 'price': 18.45, 'change': 2.34, 'percent': 14.53, 'volume': '234M', 'trending': 'hot', 'popularity': 96}
    ]

def get_achievements():
    return [
        {'name': 'First Trade', 'icon': '🎯', 'unlocked': True},
        {'name': '10 Day Streak', 'icon': '🔥', 'unlocked': True},
        {'name': 'Green Week', 'icon': '💚', 'unlocked': True},
        {'name': '$100K Portfolio', 'icon': '💎', 'unlocked': True},
        {'name': 'Top 100', 'icon': '🏆', 'unlocked': False},
        {'name': 'Day Trader', 'icon': '⚡', 'unlocked': False}
    ]

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))