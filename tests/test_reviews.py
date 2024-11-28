import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from flask import json
import jwt
import datetime

from reviews.app import app, db, SECRET_KEY, Review

@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Use an in-memory SQLite database for testing
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()  # Fresh DB for each test
        yield client

def create_token(username):
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

def test_submit_review(client):
    # Create a test user token
    username = 'testuser'
    token = create_token(username)

    # Mock the requests.get call to the inventory service
    with patch('reviews.app.requests.get') as mock_get:
        # Mock response for product verification
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'name': 'Laptop',
            'category': 'electronics',
            'price_per_item': 1000.0,
            'description': 'High-end laptop',
            'count_in_stock': 5
        }
        mock_get.return_value = mock_response

        # Data for submitting a review
        review_data = {
            'product_name': 'Laptop',
            'rating': 5,
            'comment': 'Excellent product!'
        }

        # Make the POST request to submit a review
        response = client.post('/reviews',
                               data=json.dumps(review_data),
                               content_type='application/json',
                               headers={'Authorization': token})
        
        assert response.status_code == 201
        data = response.get_json()
        assert data['message'] == 'Review submitted successfully'

        # Verify that the review is in the database
        with app.app_context():
            review = Review.query.filter_by(customer_username=username, product_name='Laptop').first()
            assert review is not None
            assert review.rating == 5
            assert review.comment == 'Excellent product!'
            assert review.is_moderated == False
            assert review.is_approved == True

def test_submit_review_missing_fields(client):
    # Create a test user token
    username = 'testuser'
    token = create_token(username)

    # Data with missing 'product_name'
    review_data = {
        'rating': 4,
        'comment': 'Good product!'
    }

    # Make the POST request to submit a review
    response = client.post('/reviews',
                           data=json.dumps(review_data),
                           content_type='application/json',
                           headers={'Authorization': token})
    
    assert response.status_code == 400
    data = response.get_json()
    assert data['error'] == 'Missing required fields'

def test_submit_review_invalid_rating(client):
    # Create a test user token
    username = 'testuser'
    token = create_token(username)

    # Data with invalid 'rating'
    review_data = {
        'product_name': 'Laptop',
        'rating': 6,  # Invalid rating
        'comment': 'Too good!'
    }

    # Make the POST request to submit a review
    response = client.post('/reviews',
                           data=json.dumps(review_data),
                           content_type='application/json',
                           headers={'Authorization': token})
    
    assert response.status_code == 400
    data = response.get_json()
    assert data['error'] == 'Rating must be an integer between 1 and 5'

def test_submit_review_product_not_found(client):
    # Create a test user token
    username = 'testuser'
    token = create_token(username)

    # Mock the requests.get call to the inventory service to simulate product not found
    with patch('reviews.app.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {'error': 'Product not found'}
        mock_get.return_value = mock_response

        # Data for submitting a review
        review_data = {
            'product_name': 'NonexistentProduct',
            'rating': 4,
            'comment': 'Cannot find this product!'
        }

        # Make the POST request to submit a review
        response = client.post('/reviews',
                               data=json.dumps(review_data),
                               content_type='application/json',
                               headers={'Authorization': token})
        
        assert response.status_code == 404
        data = response.get_json()
        assert data['error'] == 'Product not found'

def test_update_review(client):
    # Create a test user token
    username = 'testuser'
    token = create_token(username)

    # Insert a review into the database
    with app.app_context():
        review = Review(customer_username=username, product_name='Laptop', rating=5, comment='Great!')
        db.session.add(review)
        db.session.commit()
        review_id = review.id

    # Data to update the review
    update_data = {
        'rating': 4,
        'comment': 'Good product!'
    }

    # Make the PUT request to update the review
    response = client.put(f'/reviews/{review_id}',
                          data=json.dumps(update_data),
                          content_type='application/json',
                          headers={'Authorization': token})
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['message'] == 'Review updated successfully'

    # Verify that the review is updated in the database
    with app.app_context():
        updated_review = Review.query.get(review_id)
        assert updated_review.rating == 4
        assert updated_review.comment == 'Good product!'
        assert updated_review.is_moderated == False

def test_update_review_not_owner(client):
    # Create tokens for two users
    owner_username = 'owneruser'
    other_username = 'otheruser'
    owner_token = create_token(owner_username)
    other_token = create_token(other_username)

    # Insert a review into the database by owner
    with app.app_context():
        review = Review(customer_username=owner_username, product_name='Laptop', rating=5, comment='Great!')
        db.session.add(review)
        db.session.commit()
        review_id = review.id

    # Data to update the review
    update_data = {
        'rating': 3,
        'comment': 'Average product.'
    }

    # Attempt to update the review by another user
    response = client.put(f'/reviews/{review_id}',
                          data=json.dumps(update_data),
                          content_type='application/json',
                          headers={'Authorization': other_token})
    
    assert response.status_code == 403
    data = response.get_json()
    assert data['error'] == 'You can only update your own reviews'

def test_delete_review_by_owner(client):
    # Create a test user token
    username = 'testuser'
    token = create_token(username)

    # Insert a review into the database
    with app.app_context():
        review = Review(customer_username=username, product_name='Laptop', rating=5, comment='Excellent!')
        db.session.add(review)
        db.session.commit()
        review_id = review.id

    # Make the DELETE request to delete the review
    response = client.delete(f'/reviews/{review_id}',
                             headers={'Authorization': token})
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['message'] == 'Review deleted successfully'

    # Verify that the review is deleted from the database
    with app.app_context():
        deleted_review = Review.query.get(review_id)
        assert deleted_review is None

def test_delete_review_by_admin(client):
    # Create an admin token
    admin_username = 'johndoe112'
    admin_token = create_token(admin_username)

    # Insert a review into the database by another user
    with app.app_context():
        review = Review(customer_username='testuser', product_name='Laptop', rating=5, comment='Excellent!')
        db.session.add(review)
        db.session.commit()
        review_id = review.id

    # Make the DELETE request to delete the review as admin
    response = client.delete(f'/reviews/{review_id}',
                             headers={'Authorization': admin_token})
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['message'] == 'Review deleted successfully'

    # Verify that the review is deleted from the database
    with app.app_context():
        deleted_review = Review.query.get(review_id)
        assert deleted_review is None

def test_delete_review_not_owner_nor_admin(client):
    # Create tokens for two users
    owner_username = 'owneruser'
    other_username = 'otheruser'
    owner_token = create_token(owner_username)
    other_token = create_token(other_username)

    # Insert a review into the database by owner
    with app.app_context():
        review = Review(customer_username=owner_username, product_name='Laptop', rating=5, comment='Great!')
        db.session.add(review)
        db.session.commit()
        review_id = review.id

    # Attempt to delete the review by another user who is not admin
    response = client.delete(f'/reviews/{review_id}',
                             headers={'Authorization': other_token})
    
    assert response.status_code == 403
    data = response.get_json()
    assert data['error'] == 'You can only delete your own reviews'

def test_get_product_reviews(client):
    # Insert approved and unapproved reviews into the database
    with app.app_context():
        review1 = Review(customer_username='user1', product_name='Laptop', rating=5, comment='Excellent!')
        review2 = Review(customer_username='user2', product_name='Laptop', rating=4, comment='Very good!')
        review3 = Review(customer_username='user3', product_name='Laptop', rating=3, comment='Average.')
        review3.is_approved = False  # Unapproved review
        db.session.add_all([review1, review2, review3])
        db.session.commit()

    # Make the GET request to retrieve product reviews
    response = client.get('/reviews/product/Laptop')
    
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2  # Only approved reviews should be returned
    for review in data:
        assert review['product_name'] == 'Laptop'
        assert review['is_approved'] == True

def test_get_customer_reviews(client):
    # Insert reviews into the database
    with app.app_context():
        review1 = Review(customer_username='testuser', product_name='Laptop', rating=5, comment='Excellent!')
        review2 = Review(customer_username='testuser', product_name='Phone', rating=4, comment='Good!')
        review3 = Review(customer_username='anotheruser', product_name='Tablet', rating=3, comment='Average.')
        db.session.add_all([review1, review2, review3])
        db.session.commit()

    # Make the GET request to retrieve customer reviews
    response = client.get('/reviews/customer/testuser')
    
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2
    for review in data:
        assert review['customer_username'] == 'testuser'

def test_moderate_review_as_admin(client):
    # Create an admin token
    admin_username = 'johndoe112'
    admin_token = create_token(admin_username)

    # Insert a review into the database
    with app.app_context():
        review = Review(customer_username='testuser', product_name='Laptop', rating=1, comment='Bad product.')
        db.session.add(review)
        db.session.commit()
        review_id = review.id

    # Data to moderate the review
    moderate_data = {
        'is_approved': False
    }

    # Make the POST request to moderate the review
    response = client.post(f'/reviews/{review_id}/moderate',
                           data=json.dumps(moderate_data),
                           content_type='application/json',
                           headers={'Authorization': admin_token})
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['message'] == 'Review moderated successfully'

    # Verify that the review is moderated in the database
    with app.app_context():
        moderated_review = Review.query.get(review_id)
        assert moderated_review.is_moderated == True
        assert moderated_review.is_approved == False

def test_moderate_review_as_non_admin(client):
    # Create a non-admin user token
    username = 'testuser'
    token = create_token(username)

    # Insert a review into the database
    with app.app_context():
        review = Review(customer_username=username, product_name='Laptop', rating=1, comment='Bad product.')
        db.session.add(review)
        db.session.commit()
        review_id = review.id

    # Data to moderate the review
    moderate_data = {
        'is_approved': False
    }

    # Attempt to moderate the review as a non-admin user
    response = client.post(f'/reviews/{review_id}/moderate',
                           data=json.dumps(moderate_data),
                           content_type='application/json',
                           headers={'Authorization': token})
    
    assert response.status_code == 406
    data = response.get_json()
    assert data['error'] == 'Forbidden'
    assert data['message'] == 'Requires Admin. Please log in first.'

def test_get_review_details(client):
    # Insert a review into the database
    with app.app_context():
        review = Review(customer_username='testuser', product_name='Laptop', rating=5, comment='Excellent!')
        db.session.add(review)
        db.session.commit()
        review_id = review.id

    # Make the GET request to retrieve review details
    response = client.get(f'/reviews/{review_id}')
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == review_id
    assert data['customer_username'] == 'testuser'
    assert data['product_name'] == 'Laptop'
    assert data['rating'] == 5
    assert data['comment'] == 'Excellent!'
    assert data['is_moderated'] == False
    assert data['is_approved'] == True

def test_get_review_details_not_found(client):
    # Make the GET request for a non-existent review
    response = client.get('/reviews/999')
    
    assert response.status_code == 404
    data = response.get_json()
    assert data['error'] == 'Review not found'
