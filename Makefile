# Target to run each script individually
customer:
	flask --app customers/app run --port 5000

customer-test:
	pytest -q tests/test_customer.py 

inventory-test: 
	pytest -q tests/test_inventory.py

sales-test:
	pytest -q tests/test_sales.py
	
inventory:
	flask --app inventory/app run --port 5001


# Phony targets to avoid conflicts with file names
.PHONY: customer inventory inventory-test customer-test run-all
