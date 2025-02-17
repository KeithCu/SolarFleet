import streamlit_authenticator as stauth
import argparse

def generate_password_hash(password):
    """
    Generates a bcrypt hash of the given password using streamlit-authenticator.

    Args:
        password (str): The password to hash.

    Returns:
        str: The bcrypt hashed password.
    """
    hasher = stauth.Hasher([password]) # Hasher still expects a list for constructor, but hash() takes single password
    hashed_password = hasher.hash(password) # Use hash() method, pass password directly
    return hashed_password

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate a bcrypt hash for a password.')
    parser.add_argument('password', type=str, help='The password to hash.')
    args = parser.parse_args()

    password_to_hash = args.password
    hashed_password = generate_password_hash(password_to_hash)

    print("Hashed password:")
    print(hashed_password)
    print("\nCopy and paste the above hashed password into your credentials.yaml file.")