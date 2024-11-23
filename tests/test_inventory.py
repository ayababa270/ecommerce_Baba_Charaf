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


