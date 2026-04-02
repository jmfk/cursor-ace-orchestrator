from rolf_loop import generate_commit_message, run_cursor_agent


def test_direct_gemini_api():
    print("--- Testing Direct Gemini API (via generate_commit_message) ---")
    # This will trigger the direct API call because GOOGLE_API_KEY is in .env
    msg = generate_commit_message("Test task: Implement user login")
    if msg:
        print(f"✅ Direct Gemini API success. Message: {msg}")
    else:
        print("❌ Direct Gemini API failed.")


def test_cursor_agent_call():
    print("\n--- Testing Cursor Agent Call (via run_cursor_agent) ---")
    # This test assumes cursor-agent is in the PATH and working
    prompt = "Say 'Hello from Cursor Agent' and nothing else."
    result = run_cursor_agent(prompt)
    if result:
        print(f"✅ Cursor Agent success. Output: {result.strip()}")
    else:
        print(
            "❌ Cursor Agent failed (check if 'cursor-agent' is installed and in PATH)."
        )


if __name__ == "__main__":
    # Ensure we are in the right directory to find .env and rolf_loop
    test_direct_gemini_api()
    test_cursor_agent_call()
