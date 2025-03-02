import yaml
import streamlit as st
from yaml.loader import SafeLoader

def load_credentials():
    with open('./credentials.yaml', encoding="utf-8") as file:
        credentials = yaml.load(file, Loader=SafeLoader) or {'credentials': {'usernames': {}}}
        return credentials

def save_credentials(credentials):
    with open('./credentials.yaml', 'w', encoding="utf-8") as file:
        yaml.dump(credentials, file)

def add_user(user_name, hashed_password, email):
    credentials = load_credentials()
    if 'credentials' not in credentials:
        credentials = {'credentials': {'usernames': {}}}
    if 'usernames' not in credentials['credentials']:
        credentials['credentials']['usernames'] = {}

    if user_name in credentials['credentials']['usernames']:
        st.error(f"Username '{user_name}' already exists. Please choose a different username.")
        return False

    credentials['credentials']['usernames'][user_name] = {
        'name': user_name, # You can store name separately if needed, otherwise username is name
        'password': hashed_password,
        'email': email
    }
    save_credentials(credentials)
    return True

def delete_user(user_name):
    credentials = load_credentials()
    if 'credentials' in credentials and 'usernames' in credentials['credentials'] and user_name in credentials['credentials']['usernames']:
        del credentials['credentials']['usernames'][user_name]
        save_credentials(credentials)
        return True
    else:
        st.error(f"User '{user_name}' not found.")
        return False
