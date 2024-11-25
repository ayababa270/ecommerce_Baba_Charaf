from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
import os
import requests
from datetime import datetime
from functools import wraps
import jwt


app = Flask(__name__)


app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'SQLALCHEMY_DATABASE_URI',
    'mysql+pymysql://root:rootpassword@localhost:3307/mydatabase'  # Default for local testing
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Secret key for JWT (should match with customer service)
SECRET_KEY = "b'|\xe7\xbfU3`\xc4\xec\xa7\xa9zf:}\xb5\xc7\xb9\x139^3@Dv'"


db = SQLAlchemy(app)
ma = Marshmallow(app)


# Purchase model
class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_username = db.Column(db.String(50))
    good_name = db.Column(db.String(100))
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    price = db.Column(db.Float)

    def __init__(self, customer_username, good_name, price):
        self.customer_username = customer_username
        self.good_name = good_name
        self.price = price
        

class PurchaseSchema(ma.Schema):
    class Meta:
        fields = ("id", "customer_username", "good_name", "purchase_date", "price")
        
        
purchase_schema = PurchaseSchema()
purchases_schema = PurchaseSchema(many=True)

# Function to verify JWT token
def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        token = request.cookies.get('jwt-token') or request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Authentication token required'}), 403
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            username = data['sub']
        except Exception as e:
            return jsonify({'error': 'Invalid token'}), 403
        return f(username, *args, **kwargs)
    return decorator
    
    
    
# Endpoint 1: Display available goods
@app.route('/goods', methods=['GET'])
def display_goods():
    # Call inventory service to get list of goods
    try:
        response = requests.get('http://inventory:5000/goods')
        goods = response.json()
        # Extract good name and price
        goods_list = [{'name': good['name'], 'price_per_item': good['price_per_item']} for good in goods]
        return jsonify(goods_list), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
        
# Endpoint 2: Get goods details
@app.route('/goods/<string:good_name>', methods=['GET'])
def get_good_details(good_name):
    # Call inventory service to get good details
    try:
        response = requests.get(f'http://inventory:5000/goods/{good_name}')
        if response.status_code == 404:
            return jsonify({'error': 'Good not found'}), 404
        good = response.json()
        return jsonify(good), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
# Endpoint 3: Sale
@app.route('/sale', methods=['POST'])
@token_required
def make_sale(customer_username):
    data = request.json
    good_name = data.get('good_name')

    if not good_name:
        return jsonify({'error': 'Missing required fields'}), 400

    token = request.cookies.get('jwt-token') or request.headers.get('Authorization')

    try:
        # Check if good is available
        response = requests.get(f'http://inventory:5000/goods/{good_name}')
        if response.status_code == 404:
            return jsonify({'error': 'Good not found'}), 404
        good = response.json()
        if good['count_in_stock'] <= 0:
            return jsonify({'error': 'Good is out of stock'}), 400

        # Check if customer has enough money
        response = requests.get(f'http://customers:5000/get_customer_by_username/{customer_username}', cookies={'jwt-token': token})
        if response.status_code == 404:
            return jsonify({'error': 'Customer not found'}), 404
        customer = response.json()
        if customer['wallet'] < good['price_per_item']:
            return jsonify({'error': 'Insufficient funds'}), 400

        # Deduct money from customer wallet
        deduct_data = {'amount': good['price_per_item']}
        response = requests.post(f'http://customers:5000/deduct_wallet', json=deduct_data, cookies={'jwt-token': token})
        if response.status_code != 200:
            return jsonify({'error': 'Failed to deduct money from wallet'}), response.status_code

        # Decrease count of the purchased good
        response = requests.post(f'http://inventory:5000/decrease_stock/{good_name}')
        if response.status_code != 200:
            return jsonify({'error': 'Failed to update good stock'}), response.status_code

        # Save the purchase
        new_purchase = Purchase(customer_username, good_name, good['price_per_item'])
        db.session.add(new_purchase)
        db.session.commit()

        return jsonify({'message': 'Purchase successful'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
        

# Endpoint 4: Get purchase history for a customer
@app.route('/purchase_history', methods=['GET'])
@token_required
def get_purchase_history(customer_username):
    purchases = Purchase.query.filter_by(customer_username=customer_username).all()
    return jsonify(purchases_schema.dump(purchases)), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)


