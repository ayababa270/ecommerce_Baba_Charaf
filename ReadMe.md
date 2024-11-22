Set up the MySQL docker image:  
`docker pull mysql:8.0`
create the MySQL container:  
`docker run --name mysql-container -e MYSQL_ROOT_PASSWORD=rootpassword -e MYSQL_DATABASE=mydatabase -p 3307:3306 -v mysql_data:/var/lib/mysql -d mysql:8.0`  
start it:
`docker start mysql-container`  
run tests:
`pytest -q customers/test_customer.py`