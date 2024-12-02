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

# Review Model
class Review(db.Model):
    """
    Represents a review left by a customer for a product.

    :param id: Unique identifier for the review.
    :type id: int
    :param customer_username: Username of the customer who wrote the review.
    :type customer_username: str
    :param product_name: Name of the product being reviewed.
    :type product_name: str
    :param rating: Rating given to the product, between 1 and 5.
    :type rating: int
    :param comment: Optional comment provided by the customer.
    :type comment: str
    :param is_moderated: Indicates if the review has been moderated.
    :type is_moderated: bool
    :param is_approved: Indicates if the review has been approved.
    :type is_approved: bool
    :param timestamp: Date and time when the review was created.
    :type timestamp: datetime
    """

    id = db.Column(db.Integer, primary_key=True)
    customer_username = db.Column(db.String(50), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    is_moderated = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=True)  # True by default
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, customer_username, product_name, rating, comment):
        """
        Initializes a Review instance.

        :param customer_username: Username of the customer.
        :type customer_username: str
        :param product_name: Name of the product.
        :type product_name: str
        :param rating: Rating given to the product (1-5).
        :type rating: int
        :param comment: Optional comment.
        :type comment: str
        """
        self.customer_username = customer_username
        self.product_name = product_name
        self.rating = rating
        self.comment = comment

class ReviewSchema(ma.Schema):
    """
    Schema for serializing and deserializing Review instances.

    :cvar Meta: Meta information for the schema.
    """
    class Meta:
        """
        Meta information for ReviewSchema.

        :cvar fields: Fields to include in the serialized output.
        :vartype fields: tuple
        """
        fields = ("id", "customer_username", "product_name", "rating", "comment", "is_moderated", "is_approved", "timestamp")
        
    @validates('customer_username')
    def validate_customer_username(self, value):
        if not value or len(value) < 5:
            raise ValidationError("Customer username must be at least 5 characters long.")

    @validates('product_name')
    def validate_product_name(self, value):
        if not value or len(value) < 2:
            raise ValidationError("Product name must be at least 2 characters long.")

    @validates('rating')
    def validate_rating(self, value):
        if not isinstance(value, int) or value < 1 or value > 5:
            raise ValidationError("Rating must be an integer between 1 and 5.")

    @validates('comment')
    def validate_comment(self, value):
        if value and len(value) > 500:
            raise ValidationError("Comment cannot be more than 500 characters.")

    @validates('is_moderated')
    def validate_is_moderated(self, value):
        if not isinstance(value, bool):
            raise ValidationError("is_moderated must be a boolean.")

    @validates('is_approved')
    def validate_is_approved(self, value):
        if not isinstance(value, bool):
            raise ValidationError("is_approved must be a boolean.")

review_schema = ReviewSchema()
reviews_schema = ReviewSchema(many=True)

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

# Custom error handler for 406 errors
@app.errorhandler(406)
def admin_required_error(error):
    """
    Custom error handler for 406 Not Acceptable errors (Admin required).

    :param error: The error object.
    :type error: Exception
    :return: JSON response with error details.
    :rtype: flask.Response
    """
    response = {
        "error": "Forbidden",
        "message": "Requires Admin. Please log in first."
    }
    return jsonify(response), 406

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

# Function to check if user is admin (for simplicity, let's assume admin usernames are stored in a list)
ADMIN_USERS = ['johndoe112']

def admin_required(f):
    """
    Decorator to ensure that the user is an admin.

    :param f: The decorated function.
    :type f: function
    :return: The wrapped function.
    :rtype: function
    """
    @wraps(f)
    def decorator(username, *args, **kwargs):
        if username not in ADMIN_USERS:
            abort(406)
        return f(username, *args, **kwargs)
    return decorator

# Initialize Circuit Breaker for the Inventory Service
inventory_circuit_breaker = CircuitBreaker(
    fail_max=5,          # Number of consecutive failures before opening the circuit
    reset_timeout=60,    # Time in seconds before attempting to reset the circuit
    name='inventory_service'  # Optional: Name for the circuit breaker
)

# Optional: Add Logging Listener for Circuit Breaker State Changes
import logging
from pybreaker import CircuitBreakerListener, CircuitBreakerState

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LoggingListener(CircuitBreakerListener):
    def state_change(self, cb, old_state, new_state):
        logger.info(f'Circuit breaker "{cb.name}" state changed from {old_state} to {new_state}')

# Re-initialize Circuit Breaker with Listener
inventory_circuit_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name='inventory_service',
    listeners=[LoggingListener()]
)

# Endpoint 1: Submit Review
@app.route('/reviews', methods=['POST'])
@token_required
@limiter.limit("100 per minute")
def submit_review(customer_username):
    """
    Submit a new review for a product.

    This endpoint allows a logged-in customer to submit a review for a product they have purchased.

    :param customer_username: Username of the customer submitting the review.
    :type customer_username: str
    :return: JSON response indicating success or failure.
    :rtype: flask.Response
    """
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
        response = inventory_circuit_breaker.call(requests.get, f'http://inventory:5001/goods/{product_name}')
        if response.status_code == 404:
            return jsonify({'error': 'Product not found'}), 404
    except CircuitBreakerError:
        return jsonify({'error': 'Inventory service temporarily unavailable'}), 503
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
@limiter.limit("100 per minute")
def update_review(customer_username, review_id):
    """
    Update an existing review.

    Allows a customer to update their own review. Only the rating and comment can be updated.

    :param customer_username: Username of the customer attempting the update.
    :type customer_username: str
    :param review_id: ID of the review to update.
    :type review_id: int
    :return: JSON response indicating success or failure.
    :rtype: flask.Response
    """
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
@limiter.limit("100 per minute")
def delete_review(customer_username, review_id):
    """
    Delete a review.

    Allows a customer to delete their own review or an admin to delete any review.

    :param customer_username: Username of the customer attempting the deletion.
    :type customer_username: str
    :param review_id: ID of the review to delete.
    :type review_id: int
    :return: JSON response indicating success or failure.
    :rtype: flask.Response
    """
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
@limiter.limit("100 per minute")
def get_product_reviews(product_name):
    """
    Get all approved reviews for a product.

    Retrieves all reviews for a specific product that have been approved by an admin.

    :param product_name: Name of the product.
    :type product_name: str
    :return: JSON list of reviews.
    :rtype: flask.Response
    """
    reviews = Review.query.filter_by(product_name=product_name, is_approved=True).all()
    return jsonify(reviews_schema.dump(reviews)), 200

# Endpoint 5: Get Customer Reviews
@app.route('/reviews/customer/<string:customer_username>', methods=['GET'])
@limiter.limit("100 per minute")
def get_customer_reviews(customer_username):
    """
    Get all reviews written by a customer.

    Retrieves all reviews submitted by a specific customer.

    :param customer_username: Username of the customer.
    :type customer_username: str
    :return: JSON list of reviews.
    :rtype: flask.Response
    """
    reviews = Review.query.filter_by(customer_username=customer_username).all()
    return jsonify(reviews_schema.dump(reviews)), 200

# Endpoint 6: Moderate Review
@app.route('/reviews/<int:review_id>/moderate', methods=['POST'])
@token_required
@admin_required
@limiter.limit("100 per minute")
def moderate_review(admin_username, review_id):
    """
    Moderate a review (admin only).

    Allows an admin to approve or reject a review.

    :param admin_username: Username of the admin performing moderation.
    :type admin_username: str
    :param review_id: ID of the review to moderate.
    :type review_id: int
    :return: JSON response indicating success or failure.
    :rtype: flask.Response
    """
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
@limiter.limit("100 per minute")
def get_review_details(review_id):
    """
    Get details of a specific review.

    Retrieves all information about a specific review, regardless of its approval status.

    :param review_id: ID of the review.
    :type review_id: int
    :return: JSON object with review details.
    :rtype: flask.Response
    """
    review = Review.query.get(review_id)
    if not review:
        return jsonify({'error': 'Review not found'}), 404
    return jsonify(review_schema.dump(review)), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5001)
