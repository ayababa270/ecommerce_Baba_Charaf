from flask import Flask, request, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
import os
import requests
from datetime import datetime
from functools import wraps
import jwt
from pybreaker import CircuitBreaker, CircuitBreakerError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

# Set up database
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'SQLALCHEMY_DATABASE_URI',
    'mysql+pymysql://root:rootpassword@localhost:3307/mydatabase'  # Default for local testing
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

limiter = Limiter(
    get_remote_address,  # Uses client's IP address for rate-limiting
    app=app,
    default_limits=["200 per day", "50 per hour"],  # Global rate limits
)

# Secret key for JWT (should match with customer service)
SECRET_KEY = "b'|\xe7\xbfU3`\xc4\xec\xa7\xa9zf:}\xb5\xc7\xb9\x139^3@Dv'"

db = SQLAlchemy(app)
ma = Marshmallow(app)

# Purchase model
class Purchase(db.Model):
    """
    Represents a purchase made by a customer.

    :param id: Unique identifier for the purchase.
    :type id: int
    :param customer_username: Username of the customer who made the purchase.
    :type customer_username: str
    :param good_name: Name of the good purchased.
    :type good_name: str
    :param purchase_date: Date and time when the purchase was made.
    :type purchase_date: datetime
    :param price: Price of the good at the time of purchase.
    :type price: float
    """

    id = db.Column(db.Integer, primary_key=True)
    customer_username = db.Column(db.String(50))
    good_name = db.Column(db.String(100))
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    price = db.Column(db.Float)

    def __init__(self, customer_username, good_name, price):
        """
        Initializes a new Purchase instance.

        :param customer_username: Username of the customer.
        :type customer_username: str
        :param good_name: Name of the good.
        :type good_name: str
        :param price: Price of the good.
        :type price: float
        """
        self.customer_username = customer_username
        self.good_name = good_name
        self.price = price

class PurchaseSchema(ma.Schema):
    """
    Schema for serializing and deserializing Purchase instances.

    :cvar Meta: Meta information for the schema.
    """
    class Meta:
        """
        Meta information for PurchaseSchema.

        :cvar fields: Fields to include in the serialized output.
        :vartype fields: tuple
        """
        fields = ("id", "customer_username", "good_name", "purchase_date", "price")
        
    @validates('customer_username')
    def validate_customer_username(self, value):
        if not value or len(value) < 5:
            raise ValidationError("Customer username must be at least 5 characters long.")

    @validates('good_name')
    def validate_good_name(self, value):
        if not value or len(value) < 2:
            raise ValidationError("Good name must be at least 2 characters long.")

    @validates('price')
    def validate_price(self, value):
        if value is None or value <= 0:
            raise ValidationError("Price must be a positive number.")

purchase_schema = PurchaseSchema()
purchases_schema = PurchaseSchema(many=True)

# Custom error handler for 405 errors
@app.errorhandler(405)
def forbidden_error(error):
    """
    Custom error handler for 405 Method Not Allowed errors.

    :param error: The error object.
    :type error: Exception
    :return: JSON response with error details.
    :rtype: flask.Response
    """
    response = {
        "error": "Forbidden",
        "message": "No token provided. Please log in first."
    }
    return jsonify(response), 405

# Function to verify JWT token
def token_required(f):
    """
    Decorator to ensure that a valid JWT token is provided.

    :param f: The decorated function.
    :type f: function
    :return: The wrapped function.
    :rtype: function
    """
    @wraps(f)
    def decorator(*args, **kwargs):
        token = request.cookies.get('jwt-token') or request.headers.get('Authorization')
        if not token:
            abort(405)
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            username = data['sub']
        except Exception as e:
            return jsonify({'error': 'Invalid token'}), 403
        return f(username, *args, **kwargs)
    return decorator

# Initialize Circuit Breakers for external services
inventory_circuit_breaker = CircuitBreaker(
    fail_max=5,          # Number of consecutive failures before opening the circuit
    reset_timeout=60,    # Time in seconds before attempting to reset the circuit
    name='inventory_service'  # Optional: Name for the circuit breaker
)

customers_circuit_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name='customers_service'
)

# Endpoint 1: Display available goods
@app.route('/goods', methods=['GET'])
@limiter.limit("100 per minute")
def display_goods():
    """
    Retrieve and display a list of available goods.

    This endpoint calls the inventory service to get a list of goods that are in stock.

    :return: A JSON response containing a list of goods with their names and prices.
    :rtype: flask.Response
    :raises 500: If there is an error communicating with the inventory service.
    """
    try:
        response = inventory_circuit_breaker.call(requests.get, 'http://inventory:5001/goods')
        goods = response.json()
        # Extract good name and price
        goods_list = [
            {'name': good['name'], 'price_per_item': good['price_per_item']}
            for good in goods if good.get('count_in_stock') >= 1
        ]
        return jsonify(goods_list), 200
    except CircuitBreakerError:
        return jsonify({'error': 'Inventory service temporarily unavailable'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint 2: Get goods details
@app.route('/goods/<string:good_name>', methods=['GET'])
@limiter.limit("100 per minute")
def get_good_details(good_name):
    """
    Retrieve detailed information about a specific good.

    This endpoint calls the inventory service to get detailed information about a specific good.

    :param good_name: Name of the good to retrieve details for.
    :type good_name: str
    :return: A JSON response containing the good's details.
    :rtype: flask.Response
    :raises 404: If the good is not found in the inventory.
    :raises 500: If there is an error communicating with the inventory service.
    """
    try:
        response = inventory_circuit_breaker.call(requests.get, f'http://inventory:5001/goods/{good_name}')
        if response.status_code == 404:
            return jsonify({'error': 'Good not found'}), 404
        good = response.json()
        return jsonify(good), 200
    except CircuitBreakerError:
        return jsonify({'error': 'Inventory service temporarily unavailable'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint 3: Sale
@app.route('/sale', methods=['POST'])
@token_required
@limiter.limit("100 per minute")
def make_sale(customer_username):
    """
    Process a sale transaction for a customer.

    This endpoint allows a logged-in customer to purchase a good. It performs the following actions:
    - Checks if the good is available in inventory.
    - Verifies the customer has sufficient funds.
    - Deducts the purchase price from the customer's wallet.
    - Decreases the stock count of the purchased good.
    - Records the purchase in the database.

    :param customer_username: Username of the customer making the purchase (extracted from JWT token).
    :type customer_username: str
    :return: JSON response indicating success or failure of the purchase.
    :rtype: flask.Response
    :raises 400: If required fields are missing or if funds are insufficient.
    :raises 404: If the good or customer is not found.
    :raises 503: If external services are temporarily unavailable.
    :raises 500: If there is an internal server error during the transaction.
    """
    data = request.json
    good_name = data.get('name')

    if not good_name:
        return jsonify({'error': 'Missing required fields'}), 400

    token = request.cookies.get('jwt-token') or request.headers.get('Authorization')

    try:
        # Check if good is available
        try:
            response = inventory_circuit_breaker.call(requests.get, f'http://inventory:5001/goods/{good_name}')
        except CircuitBreakerError:
            return jsonify({'error': 'Inventory service temporarily unavailable'}), 503

        if response.status_code == 404:
            return jsonify({'error': 'Good not found'}), 404
        good = response.json()
        if good['count_in_stock'] <= 0:
            return jsonify({'error': 'Good is out of stock'}), 400

        # Check if customer has enough money
        try:
            response = customers_circuit_breaker.call(
                requests.get,
                f'http://customers:5001/get_customer_by_username/{customer_username}',
                cookies={'jwt-token': token}
            )
        except CircuitBreakerError:
            return jsonify({'error': 'Customer service temporarily unavailable'}), 503

        if response.status_code == 404:
            return jsonify({'error': 'Customer not found'}), 404
        customer = response.json()
        if customer['wallet'] < good['price_per_item']:
            return jsonify({'error': 'Insufficient funds'}), 400

        # Deduct money from customer wallet
        deduct_data = {'amount': good['price_per_item']}
        try:
            response = customers_circuit_breaker.call(
                requests.post,
                f'http://customers:5001/deduct_wallet',
                json=deduct_data,
                cookies={'jwt-token': token}
            )
        except CircuitBreakerError:
            return jsonify({'error': 'Customer service temporarily unavailable'}), 503

        if response.status_code != 200:
            return jsonify({'error': 'Failed to deduct money from wallet'}), response.status_code

        # Decrease count of the purchased good
        try:
            response = inventory_circuit_breaker.call(
                requests.post,
                f'http://inventory:5001/decrease_stock/{good_name}'
            )
        except CircuitBreakerError:
            return jsonify({'error': 'Inventory service temporarily unavailable'}), 503

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
@limiter.limit("100 per minute")
@token_required
def get_purchase_history(customer_username):
    """
    Retrieve the purchase history for a specific customer.

    This endpoint fetches all purchases made by a particular customer.

    :param customer_username: Username of the customer whose purchase history is to be retrieved.
    :type customer_username: str
    :return: JSON response containing a list of purchases.
    :rtype: flask.Response
    :raises 500: If there is an error retrieving purchase history from the database.
    """
    try:
        purchases = Purchase.query.filter_by(customer_username=customer_username).all()
        return jsonify(purchases_schema.dump(purchases)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5001)
