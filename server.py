from flask import Flask, request, jsonify
from flask_cors import CORS
from fuzzywuzzy import process, fuzz
import json
import os
import traceback
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash  # For password hashing

app = Flask(__name__)
CORS(app)
MONGO_URI = os.getenv("MONGO_URI")
# MongoDB Connection
client = MongoClient(MONGO_URI)
db = client["chatbotDB"]
collection = db["user_queries"]
users_collection = db["users"]  # Collection for user data

# Load JSON files
json_path = r"C:\Users\Administrator\Desktop\mindmatrix\bca_data.json"
generic_responses_path = r"C:\Users\Administrator\Desktop\mindmatrix\generic_responses.json"

# Ensure JSON files exist before loading
if not os.path.exists(json_path):
    raise FileNotFoundError(f"Missing JSON file: {json_path}")
if not os.path.exists(generic_responses_path):
    raise FileNotFoundError(f"Missing JSON file: {generic_responses_path}")

with open(json_path, "r", encoding="utf-8") as file:
    json_data = json.load(file)

with open(generic_responses_path, "r", encoding="utf-8") as file:
    generic_responses = json.load(file)

# Flatten generic responses
flat_responses = {}
for category, responses in generic_responses.items():
    flat_responses.update(responses)

# Extract subjects from JSON
json_subjects = list(json_data["subjects"].keys())

# Track last mentioned subject
last_subject = None  

@app.route('/signup', methods=['POST'])
def signup():
    try:
        username = request.json.get('username')
        email = request.json.get('email')
        password = request.json.get('password')

        # Check if user already exists
        if users_collection.find_one({"$or": [{"username": username}, {"email": email}]}):
            return jsonify({"message": "Username or email already exists"}), 400

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Create new user
        users_collection.insert_one({
            "username": username,
            "email": email,
            "password": hashed_password
        })

        return jsonify({"message": "User  created successfully"}), 201

    except Exception as e:
        print("Error:", traceback.format_exc())
        return jsonify({"message": "Server error"}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        username = request.json.get('username')
        password = request.json.get('password')

        # Find user
        user = users_collection.find_one({"username": username})
        if not user or not check_password_hash(user['password'], password):
            return jsonify({"message": "Invalid credentials"}), 401

        return jsonify({"message": "Login successful"}), 200

    except Exception as e:
        print("Error:", traceback.format_exc())
        return jsonify({"message": "Server error"}), 500

@app.route('/get_response', methods=['POST'])
def get_response():
    global last_subject
    try:
        user_message = request.json.get('message', '').lower()
        print(f"Received: {user_message}")

        # Store user query in MongoDB
        collection.insert_one({"user_message": user_message})

        # Check for generic responses
        best_match, score = process.extractOne(user_message, flat_responses.keys(), scorer=fuzz.partial_ratio)
        if score > 80:
            bot_response = flat_responses[best_match]
            collection.insert_one({"user_message": user_message, "bot_response": bot_response})  # Store bot response
            return jsonify({"response": bot_response})

        # Extract subject from message
        matched_subject, subject_score = process.extractOne(user_message, json_subjects, scorer=fuzz.token_set_ratio)

        # Extract keyword (books, topics, PYQs)
        keyword_match, key_score = process.extractOne(
            user_message, 
            ["books", "topics", "pyqs", "previous", "questions", "past year"], 
            scorer=fuzz.partial_ratio
        )

        # Update last_subject properly
        if matched_subject and subject_score > 50:
            last_subject = matched_subject  # Update last subject
        
        # If both subject & keyword are found, return correct response immediately
        if matched_subject and subject_score > 50 and keyword_match and key_score > 60:
            subject_data = json_data["subjects"].get(matched_subject, {})
            if keyword_match in ["books"]:
                bot_response = f"📚 Books for {matched_subject}:\n" + "\n".join(subject_data.get("books", ["No books available"]))
            elif keyword_match in ["topics"]:
                bot_response = f"🔑 Topics for {matched_subject}:\n" + "\n".join(subject_data.get("important_topics", ["No topics available"]))
            elif keyword_match in ["pyqs", "previous", "questions", "past year"]:
                bot_response = f"📝 PYQs for {matched_subject}:\n" + "\n".join(subject_data.get("pyqs", ["No PYQs available"]))

            collection.insert_one({"user_message": user_message, "bot_response": bot_response})  # Store bot response
            return jsonify({"response": bot_response})

        # If only subject is detected, ask what info they need
        if matched_subject and subject_score > 50:
            bot_response = f"Ask about books, topics, or PYQs for {matched_subject}."
            collection.insert_one({"user_message": user_message, "bot_response": bot_response})  # Store bot response
            return jsonify({"response": bot_response})

        # If keyword is detected but no subject, use last_subject
        if keyword_match and key_score > 60 and last_subject:
            subject_data = json_data["subjects"].get(last_subject, {})
            if keyword_match in ["books"]:
                bot_response = f"📚 Books for {last_subject}:\n" + "\n".join(subject_data.get("books", ["No books available"]))
            elif keyword_match in ["topics"]:
                bot_response = f"🔑 Topics for {last_subject}:\n" + "\n".join(subject_data.get("important_topics", ["No topics available"]))
            elif keyword_match in ["pyqs", "previous", "questions", "past year"]:
                bot_response = f"📝 PYQs for {last_subject}:\n" + "\n".join(subject_data.get("pyqs", ["No PYQs available"]))

            collection.insert_one({"user_message": user_message, "bot_response": bot_response})  # Store bot response
            return jsonify({"response": bot_response})

        bot_response = "⚠️ Oops! I couldn't find that subject. 🔍 Try asking again! 😊"
        collection.insert_one({"user_message": user_message, "bot_response": bot_response})  # Store bot response
        return jsonify({"response": bot_response})

    except Exception as e:
        print("Error:", traceback.format_exc())  
        bot_response = f"⚠️ Error occurred: {str(e)}"
        collection.insert_one({"user_message": user_message, "bot_response": bot_response})  # Store error in DB
        return jsonify({"response": bot_response})
    
if __name__ == '__main__':
    app.run(debug=True, port=5000)