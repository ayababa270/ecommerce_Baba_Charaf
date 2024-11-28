from flask import json
from ..Sales.app import app, db, SECRET_KEY, Purchase
import pytest
import jwt
import datetime
from unittest.mock import patch, MagicMock

@pytest.fixture
def client():
    app.config['TESTING'] = True
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

def test_display_goods(client):
    # Mock the requests.get call to the inventory service
    with patch('sales.app.requests.get') as mock_get:
        # Set up the mock response data
        mock_goods = [
            {
                'name': 'Apple',
                'category': 'food',
                'price_per_item': 1.0,
                'description': 'Fresh apple',
                'count_in_stock': 10
            },
            {
                'name': 'Laptop',
                'category': 'electronics',
                'price_per_item': 1000.0,
                'description': 'High-end laptop',
                'count_in_stock': 0
            },
            {
                'name': 'T-Shirt',
                'category': 'clothes',
                'price_per_item': 20.0,
                'description': 'Cotton T-Shirt',
                'count_in_stock': 5
            },
        ]

        # Configure the mock to return a response with our mock_goods
        mock_response = MagicMock()
        mock_response.json.return_value = mock_goods
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # Call the endpoint
        response = client.get('/goods')
        data = response.get_json()
        assert response.status_code == 200
        # The endpoint filters out goods with count_in_stock >= 1
        # and returns only name and price_per_item
        expected_goods_list = [
            {'name': 'Apple', 'price_per_item': 1.0},
            {'name': 'T-Shirt', 'price_per_item': 20.0},
        ]
        assert data == expected_goods_list

def test_get_good_details(client):
    with patch('sales.app.requests.get') as mock_get:
        # Set up the mock response data
        mock_good = {
            'name': 'Apple',
            'category': 'food',
            'price_per_item': 1.0,
            'description': 'Fresh apple',
            'count_in_stock': 10
        }

        # Configure the mock to return a response with our mock_good
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_good
        mock_get.return_value = mock_response

        # Call the endpoint
        response = client.get('/goods/Apple')
        data = response.get_json()
        assert response.status_code == 200
        assert data == mock_good

        # Test for good not found
        mock_response.status_code = 404
        mock_response.json.return_value = {'error': 'Good not found'}
        mock_get.return_value = mock_response

        response = client.get('/goods/NonexistentGood')
        data = response.get_json()
        assert response.status_code == 404
        assert data == {'error': 'Good not found'}

def test_make_sale(client):
    # Create a test user token
    username = 'testuser'
    token = create_token(username)

    # Set up the data for the good and customer
    good_name = 'Apple'
    good = {
        'name': 'Apple',
        'category': 'food',
        'price_per_item': 1.0,
        'description': 'Fresh apple',
        'count_in_stock': 10
    }

    customer = {
        'id': 1,
        'first_name': 'Test',
        'last_name': 'User',
        'username': username,
        'password': 'password',
        'age': 30,
        'address': '123 Test Street',
        'gender': 'other',
        'marital_status': 'single',
        'wallet': 5.0
    }

    # Mock the requests
    with patch('sales.app.requests.get') as mock_get, patch('sales.app.requests.post') as mock_post:
        # Mock requests.get to inventory service for good details
        mock_response_good = MagicMock()
        mock_response_good.status_code = 200
        mock_response_good.json.return_value = good

        # Mock requests.get to customers service for customer details
        mock_response_customer = MagicMock()
        mock_response_customer.status_code = 200
        mock_response_customer.json.return_value = customer

        def side_effect_get(url, *args, **kwargs):
            if url == f'http://inventory:5001/goods/{good_name}':
                return mock_response_good
            elif url == f'http://customers:5001/get_customer_by_username/{username}':
                return mock_response_customer
            else:
                raise ValueError('Unmocked url in get: ' + url)

        mock_get.side_effect = side_effect_get

        # Mock requests.post to customers service to deduct wallet
        mock_response_deduct = MagicMock()
        mock_response_deduct.status_code = 200
        mock_response_deduct.json.return_value = {'message': 'Money deducted successfully', 'new_balance': customer['wallet'] - good['price_per_item']}

        # Mock requests.post to inventory service to decrease stock
        mock_response_decrease_stock = MagicMock()
        mock_response_decrease_stock.status_code = 200
        mock_response_decrease_stock.json.return_value = {'message': 'Stock decreased', 'new_count': good['count_in_stock'] - 1}

        def side_effect_post(url, *args, **kwargs):
            if url == f'http://customers:5001/deduct_wallet':
                return mock_response_deduct
            elif url == f'http://inventory:5001/decrease_stock/{good_name}':
                return mock_response_decrease_stock
            else:
                raise ValueError('Unmocked url in post: ' + url)

        mock_post.side_effect = side_effect_post

        # Make the request to /sale
        response = client.post('/sale',
                               data=json.dumps({'name': good_name}),
                               content_type='application/json',
                               headers={'Authorization': token})

        data = response.get_json()
        assert response.status_code == 200
        assert data['message'] == 'Purchase successful'

        # Verify that the purchase was saved in the database
        with app.app_context():
            purchase = Purchase.query.filter_by(customer_username=username, good_name=good_name).first()
            assert purchase is not None
            assert purchase.price == good['price_per_item']

def test_get_purchase_history(client):
    # Create a test user token
    username = 'testuser'
    token = create_token(username)

    # Insert some purchases into the database
    with app.app_context():
        purchase1 = Purchase(customer_username=username, good_name='Apple', price=1.0)
        purchase2 = Purchase(customer_username=username, good_name='Banana', price=0.5)
        db.session.add(purchase1)
        db.session.add(purchase2)
        db.session.commit()

    # Make the request to /purchase_history
    response = client.get('/purchase_history',
                          headers={'Authorization': token})

    data = response.get_json()
    assert response.status_code == 200
    assert len(data) == 2
    assert data[0]['customer_username'] == username
    assert data[1]['customer_username'] == username
    assert data[0]['good_name'] in ['Apple', 'Banana']
    assert data[1]['good_name'] in ['Apple', 'Banana']

def test_make_sale_insufficient_funds(client):
    # Create a test user token
    username = 'testuser'
    token = create_token(username)

    # Set up the data for the good and customer
    good_name = 'Laptop'
    good = {
        'name': 'Laptop',
        'category': 'electronics',
        'price_per_item': 1000.0,
        'description': 'High-end laptop',
        'count_in_stock': 5
    }

    customer = {
        'id': 1,
        'first_name': 'Test',
        'last_name': 'User',
        'username': username,
        'password': 'password',
        'age': 30,
        'address': '123 Test Street',
        'gender': 'other',
        'marital_status': 'single',
        'wallet': 100.0  # Not enough for laptop
    }

    # Mock the requests
    with patch('sales.app.requests.get') as mock_get, patch('sales.app.requests.post') as mock_post:
        # Mock requests.get to inventory service for good details
        mock_response_good = MagicMock()
        mock_response_good.status_code = 200
        mock_response_good.json.return_value = good

        # Mock requests.get to customers service for customer details
        mock_response_customer = MagicMock()
        mock_response_customer.status_code = 200
        mock_response_customer.json.return_value = customer

        def side_effect_get(url, *args, **kwargs):
            if url == f'http://inventory:5001/goods/{good_name}':
                return mock_response_good
            elif url == f'http://customers:5001/get_customer_by_username/{username}':
                return mock_response_customer
            else:
                raise ValueError('Unmocked url in get: ' + url)

        mock_get.side_effect = side_effect_get

        # Make the request to /sale
        response = client.post('/sale',
                               data=json.dumps({'name': good_name}),
                               content_type='application/json',
                               headers={'Authorization': token})

        data = response.get_json()
        assert response.status_code == 400
        assert data['error'] == 'Insufficient funds'

def test_make_sale_good_out_of_stock(client):
    # Create a test user token
    username = 'testuser'
    token = create_token(username)

    # Set up the data for the good and customer
    good_name = 'Laptop'
    good = {
        'name': 'Laptop',
        'category': 'electronics',
        'price_per_item': 1000.0,
        'description': 'High-end laptop',
        'count_in_stock': 0  # Out of stock
    }

    customer = {
        'id': 1,
        'first_name': 'Test',
        'last_name': 'User',
        'username': username,
        'password': 'password',
        'age': 30,
        'address': '123 Test Street',
        'gender': 'other',
        'marital_status': 'single',
        'wallet': 2000.0  # Enough money
    }

    # Mock the requests
    with patch('sales.app.requests.get') as mock_get, patch('sales.app.requests.post') as mock_post:
        # Mock requests.get to inventory service for good details
        mock_response_good = MagicMock()
        mock_response_good.status_code = 200
        mock_response_good.json.return_value = good

        # Mock requests.get to customers service for customer details
        mock_response_customer = MagicMock()
        mock_response_customer.status_code = 200
        mock_response_customer.json.return_value = customer

        def side_effect_get(url, *args, **kwargs):
            if url == f'http://inventory:5001/goods/{good_name}':
                return mock_response_good
            elif url == f'http://customers:5001/get_customer_by_username/{username}':
                return mock_response_customer
            else:
                raise ValueError('Unmocked url in get: ' + url)

        mock_get.side_effect = side_effect_get

        # Make the request to /sale
        response = client.post('/sale',
                               data=json.dumps({'name': good_name}),
                               content_type='application/json',
                               headers={'Authorization': token})

        data = response.get_json()
        assert response.status_code == 400
        assert data['error'] == 'Good is out of stock'
