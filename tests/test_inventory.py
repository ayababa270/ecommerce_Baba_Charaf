from flask import json
from ..inventory.app import app, db
import pytest

@pytest.fixture
def client(good1):
    app.config['TESTING'] = True
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()  # Fresh DB for each test
        response = client.post(
            '/add_good',
            data=json.dumps(good1),
            content_type='application/json',
        )
        yield client
    
@pytest.fixture
def good1():
    good = {
        "name": "Smartphone",
        "category": "electronics",
        "price_per_item": 299.99,
        "description": "A high-end smartphone with great features.",
        "count_in_stock": 50
    }
    return good

@pytest.fixture
def good2():
    good = {
        "name": "Apple",
        "category": "food",
        "price_per_item": 0.99,
        "description": "Red Granny Smith Apple",
        "count_in_stock": 519
    }
    return good

def test_add_good(client, good2):
    response = client.post(
            '/add_good',
            data=json.dumps(good2),
            content_type='application/json',
        )
    assert response.status_code == 201

    data = response.json
    assert data["name"] == good2["name"]
    assert data["category"] == good2["category"]
    assert data["price_per_item"] == good2["price_per_item"]
    assert data["description"] == good2["description"]
    assert data["count_in_stock"] == good2["count_in_stock"]

    good2["category"] = "no"

    response = client.post(
            '/add_good',
            data=json.dumps(good2),
            content_type='application/json',
        )
    
    assert response.status_code == 400

def test_delete_good(client):
    response = client.delete(
            '/delete_good/1',
        )
    assert response.status_code == 200
    assert response.json["product_id"] == 1

    response = client.delete(
            '/delete_good/2',
        )
    
    assert response.status_code == 404

def test_update_good(client, good1):
    update_data = {
        "name": "Updated Apple",
        "price_per_item": 1.25,
    }
    response = client.put(
        f'/update_good/1',
        data=json.dumps(update_data),
        content_type='application/json',
    )
    assert response.status_code == 200
    data = response.json
    assert data["message"] == "Product updated successfully"
    assert data["product"]["name"] == update_data["name"]
    assert data["product"]["category"] == good1["category"]
    assert data["product"]["price_per_item"] == update_data["price_per_item"]
    assert data["product"]["description"] == good1["description"]
    assert data["product"]["count_in_stock"] == good1["count_in_stock"]

    # Attempt to update a non-existent product
    response = client.put(
        '/update_good/9999',
        data=json.dumps(update_data),
        content_type='application/json',
    )
    assert response.status_code == 404
    assert response.json["error"] == "Product not found"

    # Attempt to update with no valid fields
    invalid_update_data = {
        "invalid_field": "Invalid value"
    }
    response = client.put(
        f'/update_good/1',
        data=json.dumps(invalid_update_data),
        content_type='application/json',
    )
    assert response.status_code == 400


def test_get_all_goods(client, good2):
    response = client.post(
            '/add_good',
            data=json.dumps(good2),
            content_type='application/json',
        )
    assert response.status_code == 201

    response = client.get('/goods')
    assert response.status_code == 200

    data = response.json
    assert isinstance(data, list)
    assert len(data) == 2  
    assert data[0]["name"] == "Smartphone"
    assert data[1]["name"] == "Apple"

def test_get_good_by_name(client, good1):

    response = client.get(f'/goods/{good1["name"]}')
    assert response.status_code == 200

    data = response.json
    assert data["name"] == good1["name"]
    assert data["category"] == good1["category"]
    assert data["price_per_item"] == good1["price_per_item"]
    assert data["description"] == good1["description"]
    assert data["count_in_stock"] == good1["count_in_stock"]

    # Fetch a non-existent good
    response = client.get('/goods/non_existent_good')
    assert response.status_code == 404
    assert response.json["error"] == "Good not found"

def test_decrease_stock(client, good1):
    # Decrease stock successfully
    response = client.post(f'/decrease_stock/{good1["name"]}')
    assert response.status_code == 200

    data = response.json
    assert data["message"] == "Stock decreased"
    assert data["new_count"] == good1["count_in_stock"] - 1

    # Attempt to decrease stock for a non-existent good
    response = client.post('/decrease_stock/non_existent_good')
    assert response.status_code == 404
    assert response.json["error"] == "Good not found"

    # Attempt to decrease stock with no stock available
    # Simulate stock depletion
    for _ in range(good1["count_in_stock"]):
        client.post(f'/decrease_stock/{good1["name"]}')
    
    response = client.post(f'/decrease_stock/{good1["name"]}')
    assert response.status_code == 400
    assert response.json["error"] == "No stock available"