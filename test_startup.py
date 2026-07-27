import sys
sys.path.insert(0, 'src')

from agent_hub.main import app
import uvicorn

print("Starting AgentHub on http://127.0.0.1:17860")
print("Press Ctrl+C to stop")

uvicorn.run(app, host="127.0.0.1", port=17860, log_level="info")
