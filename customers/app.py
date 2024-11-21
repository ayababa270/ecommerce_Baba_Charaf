from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from datetime import datetime

app = Flask(__name__)

# Set the URI for the database connection
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:rootpassword@localhost:3307/mydatabase'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Disable modification tracking for performance
app.config['SQLALCHEMY_ECHO'] = True


# Initialize SQLAlchemy
db = SQLAlchemy(app)
ma = Marshmallow(app)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    username = db.Column(db.String(50), unique = True)
    password = db.Column(db.String(128))
    age = db.Column(db.Integer)
    address = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    marital_status = db.Column(db.String(10))

class CustomerSchema(ma.Schema): 
    class Meta: 
        fields = ("id", "first_name", "last_name", "username", "password",
                  "age", "address", "gender", "marital_status") 
        model = Customer 

customer_schema = CustomerSchema() 


@app.route("/create_customer", methods = ["POST"])
def create_customer():
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
        customer = get_customer_by_username(data['username'])
        return jsonify(customer[0].json), 201
    except Exception as e:
        db.session.rollback()  # Rollback in case of error
        return jsonify({"error": str(e)}), 500
    

@app.route("/get_customer_by_username/<username>", methods=["GET"])
def get_customer_by_username(username):
    # Query the customer by the provided username
    customer = Customer.query.filter_by(username=username).first()

    # If customer is not found, return an error message
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404

    # Return the customer data as a JSON response
    return jsonify(customer_schema.dump(customer)), 200



if __name__ == '__main__':
    # Create tables if they don't exist

    with app.app_context():
        
        db.create_all()
    app.run(debug=True)
