from flask import Flask, request, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
import os
import requests
from datetime import datetime
from functools import wraps
import jwt

app = Flask(__name__)

# Set up database
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'SQLALCHEMY_DATABASE_URI',
    'mysql+pymysql://root:rootpassword@localhost:3307/mydatabase'  # Default for local testing
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Secret key for JWT (should match with customer service)
SECRET_KEY = "b'|\xe7\xbfU3`\xc4\xec\xa7\xa9zf:}\xb5\xc7\xb9\x139^3@Dv'"

db = SQLAlchemy(app)
ma = Marshmallow(app)

# Review Model
class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_username = db.Column(db.String(50), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    is_moderated = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=True)  # True by default
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, customer_username, product_name, rating, comment):
        self.customer_username = customer_username
        self.product_name = product_name
        self.rating = rating
        self.comment = comment

class ReviewSchema(ma.Schema):
    class Meta:
        fields = ("id", "customer_username", "product_name", "rating", "comment", "is_moderated", "is_approved", "timestamp")

review_schema = ReviewSchema()
reviews_schema = ReviewSchema(many=True)


# Custom error handler for 405 errors
@app.errorhandler(405)
def forbidden_error(error):
    response = {
        "error": "Forbidden",
        "message": "No token provided. Please log in first."
    }
    return jsonify(response), 405
    
# Custom error handler for 406 errors
@app.errorhandler(406)
def forbidden_error(error):
    response = {
        "error": "Forbidden",
        "message": "Requires Admin. Please log in first."
    }
    return jsonify(response), 406



# Function to verify JWT token
def token_required(f):
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

# Function to check if user is admin (for simplicity, let's assume admin usernames are stored in a list)
ADMIN_USERS = ['admin']

def admin_required(f):
    @wraps(f)
    def decorator(username, *args, **kwargs):
        if username not in ADMIN_USERS:
            abort(406)
        return f(username, *args, **kwargs)
    return decorator

# Endpoint 1: Submit Review
@app.route('/reviews', methods=['POST'])
@token_required
def submit_review(customer_username):
    data = request.json
    product_name = data.get('product_name')
    rating = data.get('rating')
    comment = data.get('comment')

    if not product_name or rating is None:
        return jsonify({'error': 'Missing required fields'}), 400

    # Validate rating
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({'error': 'Rating must be an integer between 1 and 5'}), 400

    # Check if product exists
    try:
        response = requests.get(f'http://inventory:5001/goods/{product_name}')
        if response.status_code == 404:
            return jsonify({'error': 'Product not found'}), 404
    except Exception as e:
        return jsonify({'error': 'Failed to verify product'}), 500

    # Create and save review
    new_review = Review(customer_username, product_name, rating, comment)
    try:
        db.session.add(new_review)
        db.session.commit()
        return jsonify({'message': 'Review submitted successfully'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500





# Endpoint 2: Update Review
@app.route('/reviews/<int:review_id>', methods=['PUT'])
@token_required
def update_review(customer_username, review_id):
    data = request.json
    rating = data.get('rating')
    comment = data.get('comment')

    review = Review.query.get(review_id)
    if not review:
        return jsonify({'error': 'Review not found'}), 404

    if review.customer_username != customer_username:
        return jsonify({'error': 'You can only update your own reviews'}), 403

    if rating is not None:
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            return jsonify({'error': 'Rating must be an integer between 1 and 5'}), 400
        review.rating = rating

    if comment is not None:
        review.comment = comment

    # Mark review as unmoderated if updated
    review.is_moderated = False

    try:
        db.session.commit()
        return jsonify({'message': 'Review updated successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Endpoint 3: Delete Review
@app.route('/reviews/<int:review_id>', methods=['DELETE'])
@token_required
def delete_review(customer_username, review_id):
    review = Review.query.get(review_id)
    if not review:
        return jsonify({'error': 'Review not found'}), 404

    if review.customer_username != customer_username and customer_username not in ADMIN_USERS:
        return jsonify({'error': 'You can only delete your own reviews'}), 403

    try:
        db.session.delete(review)
        db.session.commit()
        return jsonify({'message': 'Review deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Endpoint 4: Get Product Reviews
@app.route('/reviews/product/<string:product_name>', methods=['GET'])
def get_product_reviews(product_name):
    reviews = Review.query.filter_by(product_name=product_name, is_approved=True).all()
    return jsonify(reviews_schema.dump(reviews)), 200

# Endpoint 5: Get Customer Reviews
@app.route('/reviews/customer/<string:customer_username>', methods=['GET'])
def get_customer_reviews(customer_username):
    reviews = Review.query.filter_by(customer_username=customer_username).all()
    return jsonify(reviews_schema.dump(reviews)), 200

# Endpoint 6: Moderate Review
@app.route('/reviews/<int:review_id>/moderate', methods=['POST'])
@token_required
@admin_required
def moderate_review(admin_username, review_id):
    data = request.json
    is_approved = data.get('is_approved')

    if is_approved is None:
        return jsonify({'error': 'Missing required field: is_approved'}), 400

    review = Review.query.get(review_id)
    if not review:
        return jsonify({'error': 'Review not found'}), 404

    review.is_moderated = True
    review.is_approved = bool(is_approved)

    try:
        db.session.commit()
        return jsonify({'message': 'Review moderated successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Endpoint 7: Get Review Details
@app.route('/reviews/<int:review_id>', methods=['GET'])
def get_review_details(review_id):
    review = Review.query.get(review_id)
    if not review:
        return jsonify({'error': 'Review not found'}), 404
    return jsonify(review_schema.dump(review)), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5001)
