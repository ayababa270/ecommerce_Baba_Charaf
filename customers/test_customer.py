from flask import json
from app import app, db
import pytest

@pytest.fixture
def client(customer2):
    app.config['TESTING'] = True
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()  # Fresh DB for each test
        response = client.post(
            '/create_customer',
            data=json.dumps(customer2),
            content_type='application/json',
        )
        yield client

@pytest.fixture
def customer1():
    user = {
            "first_name": "Walter",
            "last_name": "White",
            "username": "walt12",
            "password": "12345",
            "age": 50,
            "address": "308 Negra Arroyo Lane, Albuquerque, NM",
            "gender": "male",
            "marital_status": "married"
        }
    return user

@pytest.fixture
def customer2():
    user = {
            "first_name": "Gale",
            "last_name": "Boetticer",
            "username": "gale12",
            "password": "123456",
            "age": 40,
            "address": "6353 Juan Tabo Blvd NE, Apt 6, Albuquerque, New Mexico 87111",
            "gender": "male",
            "marital_status": "single"
        }
    return user


def test_create_customer(client, customer1, customer2):
    response = client.post(
        '/create_customer',
        data=json.dumps(customer1),
        content_type='application/json',
    )
    data = json.loads(response.get_data(as_text=True)) 
    assert response.status_code == 201
    assert 'id' in data  
    assert data['first_name'] == 'Walter'
    assert data['last_name'] == 'White'
    assert data['username'] == 'walt12'
    assert data['password'] == '12345'
    assert data['age'] == 50
    assert data['address'] == '308 Negra Arroyo Lane, Albuquerque, NM'
    assert data['gender'] == 'male'
    assert data['marital_status'] == 'married'

    response = client.post(
        '/create_customer',
        data=json.dumps(customer2),
        content_type='application/json',
    )
    data = json.loads(response.get_data(as_text=True)) 

    assert response.status_code == 500 #Already exists


def test_get_customer_by_username(client, customer2):
    response = app.test_client().get('/get_customer_by_username/gale12')
    data = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert isinstance(data, dict)

    assert 'id' in data  
    assert data['first_name'] == 'Gale'
    assert data['last_name'] == 'Boetticer'
    assert data['username'] == 'gale12'
    assert data['password'] == '123456'  
    assert data['age'] == 40
    assert data['address'] == '6353 Juan Tabo Blvd NE, Apt 6, Albuquerque, New Mexico 87111'
    assert data['gender'] == 'male'
    assert data['marital_status'] == 'single'

    response = app.test_client().get('/get_customer_by_username/nicole')
    data = json.loads(response.get_data(as_text=True))

    assert response.status_code == 404

def test_login(client, customer2):
    username = customer2['username']
    password = customer2['password']

    res = client.post(
        '/login',
        data=json.dumps({"username": username, "password": password}),
        content_type='application/json',
    )
    assert res.status_code == 200

    res = client.post(
        '/login',
        data=json.dumps({"username": username, "password": "wrong"}),
        content_type='application/json',
    )
    
    assert res.status_code == 403

def test_delete_customer(client, customer2):
    username = customer2['username']
    password = customer2['password']

    res = client.post(
        '/login',
        data=json.dumps({"username": username, "password": password}),
        content_type='application/json',
    )

    token = res.headers.get('jwt-token')

    res2 = client.delete(
        '/delete_customer', 
        environ_base={'HTTP_COOKIE': f'jwt-token={token}'}  
    )

    assert res2.status_code == 200

    res2 = client.delete(
        '/delete_customer', 
        environ_base={'HTTP_COOKIE': f'jwt-token={token}'}  
    )

    assert res2.status_code == 404

def test_update_customer_information(client, customer2):
    username = customer2['username']
    password = customer2['password']

    res = client.post(
        '/login',
        data=json.dumps({"username": username, "password": password}),
        content_type='application/json',
    )

    token = res.headers.get('jwt-token')

    updated_data = {
        "age": 81,
        "address": "New Address"
    }

    res2 = client.put(
        '/update_customer_information',  # Replace with the actual endpoint for updating customer info
        data=json.dumps(updated_data),
        content_type='application/json',
        environ_base={'HTTP_COOKIE': f'jwt-token={token}'} 
    )
    data = res2.json
    assert res2.status_code == 200  
    assert data['first_name'] == 'Gale'
    assert data['last_name'] == 'Boetticer'
    assert data['username'] == 'gale12'
    assert data['password'] == '123456'  
    assert data['gender'] == 'male'
    assert data['marital_status'] == 'single'
    assert res2.json['age'] == updated_data['age']  
    assert res2.json['address'] == updated_data['address']  


def test_get_all_customers(client, customer1, customer2):
    response = client.post(
        '/create_customer',
        data=json.dumps(customer1),
        content_type='application/json',
    )
    response = client.get("/get_all_customers")

    assert response.status_code == 200

    c1 = response.json[0]
    c2 = response.json[1]
    assert c1['first_name'] == "Gale"
    assert c2['first_name'] == "Walter"

    assert c1['last_name'] == "Boetticer"  
    assert c2['last_name'] == "White"
    assert c1['age'] == 40  
    assert c2['age'] == 50  

    assert c1['address'] == "6353 Juan Tabo Blvd NE, Apt 6, Albuquerque, New Mexico 87111"
    assert c2['address'] == "308 Negra Arroyo Lane, Albuquerque, NM"

    assert len(response.json) == 2  

def test_charge_wallet(client, customer2):
    username = customer2['username']
    password = customer2['password']

    res = client.post(
        '/login',
        data=json.dumps({"username": username, "password": password}),
        content_type='application/json',
    )

    token = res.headers.get('jwt-token')

    res = client.post(
        '/charge_wallet',
        data=json.dumps({'amount': 20}),
        content_type='application/json',
    )
    res = client.post(
        '/charge_wallet',
        data=json.dumps({'amount': 70}),
        content_type='application/json',
    )
    assert res.status_code == 200
    assert res.json['new_balance'] == 90

def test_deduct_wallet(client, customer2):
    username = customer2['username']
    password = customer2['password']

    res = client.post(
        '/login',
        data=json.dumps({"username": username, "password": password}),
        content_type='application/json',
    )

    token = res.headers.get('jwt-token')

    res = client.post(
        '/charge_wallet',
        data=json.dumps({'amount': 20}),
        content_type='application/json',
    )
    res = client.post(
        '/deduct_wallet',
        data=json.dumps({'amount': 5}),
        content_type='application/json',
    )

    assert res.status_code == 200
    assert res.json['new_balance'] == 15

    res = client.post(
        '/deduct_wallet',
        data=json.dumps({'amount': 100}),
        content_type='application/json',
    )
    assert res.status_code == 400

    res = client.post(
        '/deduct_wallet',
        data=json.dumps({'amount': -100}),
        content_type='application/json',
    )
    assert res.status_code == 400