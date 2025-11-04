# Tank Operations Frontend

This Vite + React application provides the web experience for the Tank Operations stack.

## Getting Started

`
cd visual_controller/frontend
npm install
npm run dev
`

Set the following environment variables when running locally or deploying:

- VITE_API_BASE_URL – e.g. http://api.nene.02labs.me
- VITE_WS_BASE_URL – e.g. wss://ws.nene.02labs.me
- VITE_DEFAULT_TANK_ID – optional default tank identifier (defaults to 	ank_001).

Deploy the built site to 
ene.02labs.me, keeping the FastAPI backend reachable at pi.nene.02labs.me and the websocket service at ws.nene.02labs.me.
