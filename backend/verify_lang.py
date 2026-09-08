import urllib.request
import json

def test_language(lang_label, user_text):
    url = "http://localhost:8000/api/ai/chat"
    payload = {
        "business_id": "biz-clinic-01",
        "workflow_id": "wf-clinic-01",
        "caller_name": "Test User",
        "caller_phone": "+91 98765 43210",
        "language": "auto",
        "messages": [
            {"role": "assistant", "content": "Hello! You have reached Apex Health Clinic."},
            {"role": "user", "content": user_text}
        ]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            print(f"=== {lang_label} Test ===")
            print(f"Input: '{user_text}'")
            print(f"Detected Language: {res_data['data']['language']}")
            print(f"Urgency: {res_data['data']['urgency']}")
            print(f"Executed Tools: {[t['tool'] for t in res_data['data']['executed_tools']]}")
            print(f"AI Assistant Reply: {res_data['data']['assistant_reply']}\n")
    except Exception as e:
        print(f"Error testing {lang_label}: {e}")

if __name__ == "__main__":
    test_language("ENGLISH", "I want to schedule a doctor appointment for tomorrow at 4 PM.")
    test_language("HINDI", "Mujhe kal shaam 4 baje doctor appointment chahiye.")
    test_language("KANNADA", "Naale sanje 4 gantege Doctor appointment book madi.")
