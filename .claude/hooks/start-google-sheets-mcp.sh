#!/bin/bash
# Start Google Sheets + Google Slides/Drive MCP servers if not already running

export PATH="/Users/reidgilbertson/.nvm/versions/node/v22.17.1/bin:$PATH"

# --- Google Sheets MCP (port 3000) ---
SHEETS_PORT=3000
if ! curl -s -o /dev/null -w "%{http_code}" http://localhost:$SHEETS_PORT/mcp 2>/dev/null | grep -q "404\|200\|405"; then
  export GOOGLE_CLIENT_ID='YOUR_CLIENT_ID.apps.googleusercontent.com'
  export GOOGLE_CLIENT_SECRET='GOCSPX-YOUR_SECRET'
  export MCP_TRANSPORT=http
  export PORT=$SHEETS_PORT

  nohup npx --registry https://registry.npmjs.org -y google-sheets-mcp > /tmp/google-sheets-mcp.log 2>&1 &

  for i in {1..10}; do
    sleep 1
    if curl -s -o /dev/null http://localhost:$SHEETS_PORT/mcp 2>/dev/null; then
      break
    fi
  done
fi

# --- Google Slides/Drive MCP (port 3100) ---
SLIDES_PORT=3100
if ! curl -s -o /dev/null -w "%{http_code}" http://localhost:$SLIDES_PORT/mcp 2>/dev/null | grep -q "400\|200\|405"; then
  export GOOGLE_DRIVE_OAUTH_CREDENTIALS='/Users/reidgilbertson/Downloads/client_secret_YOUR_CLIENT_ID.apps.googleusercontent.com.json'
  export MCP_TRANSPORT=http

  nohup npx --registry https://registry.npmjs.org -y @piotr-agier/google-drive-mcp start --port $SLIDES_PORT > /tmp/google-slides-mcp.log 2>&1 &

  for i in {1..10}; do
    sleep 1
    if curl -s -o /dev/null http://localhost:$SLIDES_PORT/mcp 2>/dev/null; then
      break
    fi
  done
fi

# Verify at least one is up
if curl -s -o /dev/null http://localhost:$SHEETS_PORT/mcp 2>/dev/null || curl -s -o /dev/null http://localhost:$SLIDES_PORT/mcp 2>/dev/null; then
  exit 0
fi

echo "Google MCP servers failed to start. Check /tmp/google-sheets-mcp.log and /tmp/google-slides-mcp.log" >&2
exit 2
