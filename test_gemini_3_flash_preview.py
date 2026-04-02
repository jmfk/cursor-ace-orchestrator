import os
import google.generativeai as genai
from pathlib import Path
from dotenv import load_dotenv

def test_gemini_3_flash_preview():
    """
    Test script for gemini-3-flash-preview model.
    """
    # Load environment variables from .env if it exists
    load_dotenv()

    # Get API key from environment or fallback to ~/.ace/credentials
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        cred_file = Path.home() / ".ace" / "credentials"
        if cred_file.exists():
            for line in cred_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("GOOGLE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        print("❌ Error: GOOGLE_API_KEY not found in environment or ~/.ace/credentials")
        return

    # Configure the SDK
    genai.configure(api_key=api_key)

    model_name = "gemini-3-flash-preview"
    print(f"--- Testing Model: {model_name} ---")

    try:
        # Initialize the model
        model = genai.GenerativeModel(model_name)
        
        # Simple test prompt
        prompt = "Explain what 'gemini-3-flash-preview' is in one sentence."
        
        print(f"Prompt: {prompt}")
        print("Generating response...")
        
        response = model.generate_content(prompt)
        
        if response and response.text:
            print(f"✅ Success! Response:\n{response.text}")
        else:
            print("⚠️ Received an empty response from the model.")
            
    except Exception as e:
        print(f"❌ Error during model call: {e}")
        if "404" in str(e) or "not found" in str(e).lower():
            print(f"Note: The model '{model_name}' might not be available yet or the name is incorrect.")

if __name__ == "__main__":
    test_gemini_3_flash_preview()
