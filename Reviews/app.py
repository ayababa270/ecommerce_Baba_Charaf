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



