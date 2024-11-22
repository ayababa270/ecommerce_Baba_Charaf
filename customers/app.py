from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from datetime import datetime
from flask import abort, jsonify, request, Blueprint, make_response, current_app
from functools import wraps
import jwt
import datetime

app = Flask(__name__)

# Set the URI for the database connection
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:rootpassword@localhost:3307/mydatabase'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Disable modification tracking for performance
app.config['SQLALCHEMY_ECHO'] = True


# Initialize SQLAlchemy
db = SQLAlchemy(app)
ma = Marshmallow(app)

class Customer(db.Model):
    """
    This class represents a model for a customer entity in the database

    :param id: The ID of the customer. Automatically generated by MySQL.
    :type id: int
    :param first_name: The first name of the customer.
    :type first_name: str
    :param last_name: The last name of the customer.
    :type last_name: str
    :param username: The unique username of the customer.
    :type username: str
    :param password: The hashed password of the customer.
    :type password: str
    :param age: The age of the customer.
    :type age: int
    :param address: The address of the customer.
    :type address: str
    :param gender: The gender of the customer. Example values: 'Male', 'Female', etc.
    :type gender: str
    :param marital_status: The marital status of the customer. Example values: 'Single', 'Married', etc.
    :type marital_status: str
    """
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    username = db.Column(db.String(50), unique = True)
    password = db.Column(db.String(128))
    age = db.Column(db.Integer)
    address = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    marital_status = db.Column(db.String(10))
    wallet = db.Column(db.Float)
    def __init__(self, first_name, last_name, username, password, age, 
                 address, gender, marital_status):
        """
        Initialize a new customer instance.

        :param id: The ID of the customer (optional, if provided for existing customer).
        :param first_name: The first name of the customer.
        :param last_name: The last name of the customer.
        :param username: The username of the customer.
        :param password: The password of the customer.
        :param age: The age of the customer.
        :param address: The address of the customer.
        :param gender: The gender of the customer.
        :param marital_status: The marital status of the customer.
        :param wallet: The wallet balance of the customer.
        """
        super(Customer, self).__init__(username=username, first_name = first_name, last_name = last_name, password = password,age = age, address = address, gender = gender,marital_status= marital_status)
        self.wallet = 0

class CustomerSchema(ma.Schema): 
    """
    This schema represents a serialization/deserialization schema for the Customer model.
    :cvar Meta: A nested class containing metadata for the schema.
    """
    class Meta: 
        """
        Metadata for the CustomerSchema class.

        :cvar fields: A tuple specifying the fields to include in the schema.
        :vartype fields: tuple
        :cvar model: The model that this schema is based on.
        :vartype model: type
        """
        fields = ("id", "first_name", "last_name", "username", "password",
                  "age", "address", "gender", "marital_status", "wallet") 
        model = Customer 

customer_schema = CustomerSchema()
customers_schema = CustomerSchema(many=True)

@app.route("/create_customer", methods = ["POST"])
def create_customer():
    """
    Creates a new customer from the information in the request body. Inserts it into the customer table.
    :return: A tuple containing a JSON response and an HTTP status code.
        - If any required field is missing: JSON error message and status code 400.
        - If 'age' is not an integer: JSON error message and status code 400.
        - If the customer is created successfully: JSON with customer attributes and status code 201.
        - If a database error occurs: JSON error message and status code 500.
    :rtype: tuple[dict, int]
    """
    data = request.json

    if not all(field in data for field in ['first_name', 'last_name', 'username', 'password', 'age', 'address', 'gender', 'marital_status']):
        return jsonify({"error": "Missing required fields"}), 400
    
    if not isinstance(data['age'], int):
        return jsonify({"error": "bad age"}), 400

    new_customer = Customer(
        first_name=data['first_name'],
        last_name=data['last_name'],
        username=data['username'],
        password=data['password'],
        age=data['age'],  
        address=data['address'],
        gender=data['gender'],
        marital_status=data['marital_status']
    )

    try:
        # Add the customer to the session and commit
        db.session.add(new_customer)
        db.session.commit()

        # Return success response with customer info (or just a success message)
        c = get_customer_by_username(data['username'])
        return jsonify(c[0].json), 201
    except Exception as e:
        db.session.rollback()  # Rollback in case of error
        return jsonify({"error": str(e)}), 500
    

@app.route("/get_customer_by_username/<username>", methods=["GET"])
def get_customer_by_username(username):
    """
    Retrieves a customer by their username.

    :param username: The username of the customer to retrieve.
    :type username: str
    :return: A tuple containing a JSON response and an HTTP status code.
        - If the customer is not found: JSON error message and status code 404.
        - If the customer is found: JSON with customer attributes and status code 200.
    :rtype: tuple[dict, int]
    """

    c = Customer.query.filter_by(username=username).first()

    if c is None:
        return jsonify({"error": "Customer not found"}), 404
    
    return jsonify(customer_schema.dump(c)), 200



SECRET_KEY = "b'|\xe7\xbfU3`\xc4\xec\xa7\xa9zf:}\xb5\xc7\xb9\x139^3@Dv'"

def create_token(username): 
    """
    Generates a JWT token for the specified username.

    :param username: The username for which the token is generated.
    :type username: str
    :return: A JWT token as a string.
    :rtype: str
    """
    payload = { 
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=2), 
        'iat': datetime.datetime.utcnow(), 
        'sub': username
    } 
    return jwt.encode( 
        payload, 
        SECRET_KEY, 
        algorithm='HS256' 
    ) 

def token_required(f):
    """
    A decorator function that checks if a valid JWT token is provided in the request cookies.
    If the token is missing or invalid, it aborts the request with a 403 status code.

    :param f: The original function to be wrapped.
    :type f: function
    :return: The wrapped function with the username as a parameter if the token is valid.
    :rtype: function
    """
    @wraps(f)
    def decorator(*args, **kwargs):
        token = request.cookies.get('jwt-token')
        if not token:
            abort(403)
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            username = data['sub']
        except:
            abort(403)
        return f(username, token, *args, **kwargs)
    return decorator

@app.route("/login", methods = ["POST"])
def login():
    """
    Authenticates a user by validating the username and password. If authentication is successful,
    a JWT token is created and sent back in a cookie.

    :return: A response with a success message and the JWT token set as a cookie if authentication is successful.
    :rtype: Response
    :raises: 403 Forbidden if authentication fails due to incorrect credentials.
    """
    username = request.json['username']
    password = request.json['password']
    c = Customer.query.filter_by(username=username).first()
    if c.password == password:
        token = create_token(username)
        resp = make_response({"message": "authentication successful"})
        resp.set_cookie('jwt-token', token, 
                            httponly=True, #to prevent javascript from accessing cookie
                            secure=True,    # Only send cookie over HTTPS
                            samesite='Lax' 
                            )

        return resp 
    
    abort(403)

@app.route("/delete_customer", methods = ["DELETE"])
@token_required
def delete_customer(username, token):
    """
    The logged in user only may delete his account (token required)
    Deletes a customer from the database based on the provided username. The request must be authenticated with a valid JWT token.
    
    :param username: The username of the customer to be deleted, extracted from the JWT token.
    :type username: str
    :param token: The JWT token used for authentication (passed by the decorator).
    :type token: str
    :return: A response indicating the success or failure of the deletion.
    :rtype: Response
    :raises: 404 Not Found if the customer does not exist.
    :raises: 500 Internal Server Error if there is an issue during the deletion process.
    """
    customer = Customer.query.filter_by(username=username).first()
    
    # If customer not found, return 404 error
    if not customer:
        return jsonify({"error": "Customer not found"}), 404
    
    try:
        db.session.delete(customer)
        db.session.commit()
        
        # Return a success message
        return jsonify({"message": "Customer deleted successfully"}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/update_customer_information", methods=["PUT"])
@token_required
def update_customer_information(username, token):
    """
    The logged in user only may update his info
    Updates the customer information. The request can contain one or more fields to update (e.g., first_name, last_name, etc.).
    Only the provided fields will be updated, and the rest will remain unchanged.

    :param username: The username of the customer whose information is to be updated, extracted from the JWT token.
    :type username: str
    :param token: The JWT token used for authentication (passed by the decorator).
    :type token: str
    :return: A response indicating the success or failure of the update operation.
    :rtype: Response
    :raises: 404 Not Found if the customer does not exist.
    :raises: 400 Bad Request if no valid fields are provided for update.
    :raises: 500 Internal Server Error if there is an issue during the update process.
    """
    data = request.json  
    # Prevent updating wallet value
    if 'wallet' in data:
        abort(403)
    # Validate if at least one valid field is provided
    valid_fields = ['first_name', 'last_name', 'username', 'password', 'age', 'address', 'gender', 'marital_status']
    if not any(field in data for field in valid_fields):
        return jsonify({"error": "No valid fields provided for update"}), 400
    
    # Find the customer by username
    customer = Customer.query.filter_by(username=username).first()
    
    # If customer not found, return 404 error
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    # Update the customer information with the provided fields
    for field, value in data.items():
        if hasattr(customer, field):  # Check if the field exists on the customer model
            setattr(customer, field, value)

    try:
        db.session.commit()
        return jsonify( customer_schema.dump(customer)), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/get_all_customers", methods=["GET"])
def get_all_customers():
    """
    Fetches all customers from the database.

    :return: A JSON response containing all customers.
    :rtype: Response
    :raises: 500 Internal Server Error if there is an issue retrieving customer data.
    """
    try:
        customers = Customer.query.all()

        if not customers:
            return jsonify({"message": "No customers found"}), 200
        return jsonify(customers_schema.dump(customers)), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/charge_wallet", methods=["POST"])
@token_required
def charge_wallet(username, token):
    """
    Only the logged in customer may charge his account
    Charge a customer's wallet by adding a specified amount in dollars.
    
    :param username: The username of the customer.
    :param token: The JWT token for authentication.
    :return: A success message with updated wallet balance, or an error message.
    :rtype: dict
    """
    data = request.json
    
    amount = data.get("amount")
    if not amount or amount <= 0:
        return jsonify({"error": "Invalid or missing amount"}), 400
    
    customer = Customer.query.filter_by(username=username).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404
    
    customer.wallet += amount
    
    try:
        db.session.commit()
        return jsonify({
            "message": "Wallet charged successfully",
            "new_balance": customer.wallet
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/deduct_wallet", methods=["POST"])
@token_required
def deduct_wallet(username, token):
    """
    Only the logged in user may cause money to be deducted from his account
    Deduct money from a customer's wallet.
    :param username: The username of the customer.
    :param token: The JWT token for authentication.
    :return: A success message with updated wallet balance, or an error message.
    :rtype: dict
    """
    data = request.json
    
    amount = data.get("amount")
    if not amount or amount <= 0:
        return jsonify({"error": "Invalid or missing amount"}), 400
    
    customer = Customer.query.filter_by(username=username).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404
    
    if customer.wallet < amount:
        return jsonify({"error": "Insufficient funds"}), 400
    
    customer.wallet -= amount
    
    try:

        db.session.commit()
        return jsonify({
            "message": "Money deducted successfully",
            "new_balance": customer.wallet
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
