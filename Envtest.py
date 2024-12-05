from dotenv import load_dotenv
import os

# Load Key.env
load_dotenv()  # Adjust filename if needed

# Check if the key is loaded
api_key = os.getenv('GLHF_API_KEY')
if api_key:
    print(f"GLHF_API_KEY successfully loaded: {api_key}")
else:
    print("GLHF_API_KEY not found!")