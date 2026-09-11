# Frontend (Vite + React)

This frontend uses Vite for development/build and keeps the existing Jest test path via `react-scripts` for now.

## Available Scripts

In the project directory, you can run:

### `npm start` / `npm run dev`

Runs the app in the development mode.\
Open [http://localhost:3000](http://localhost:3000) to view it in the browser.

The page will reload if you make edits.\
You will also see any lint errors in the console.

### `npm test`

Launches the test runner in the interactive watch mode.\
See the section about [running tests](https://facebook.github.io/create-react-app/docs/running-tests) for more information.

### `npm run build`

Builds the app for production to the `dist` folder.\
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.\
Your app is ready to be deployed!

See the section about [deployment](https://facebook.github.io/create-react-app/docs/deployment) for more information.

### `npm run preview`

Serves the production build locally for verification.

## ATT&CK Coverage configuration

The Coverage page embeds the MITRE ATT&CK Navigator and loads a live coverage layer JSON from the backend.

### Backend base URL

Set either `VITE_API_URL` (preferred) or `REACT_APP_API_URL` (legacy fallback) to the base URL of your backend (for example, your reverse proxy origin `https://localhost` or `http://localhost`; use `http://localhost:8000` only when running Django directly). The Coverage page builds the layer URL as:

```
${VITE_API_URL}/api/coverage/layer.json
```

When neither variable is set, the app defaults to same-origin (`window.location.origin`).

### Authentication for the layer JSON

The Coverage page requests a short-lived coverage token from:

```
${VITE_API_URL}/api/coverage/token
```

Then it loads the layer JSON with that scoped token:

```
${VITE_API_URL}/api/coverage/layer.json?token=SHORT_LIVED_COVERAGE_TOKEN
```

The token endpoint accepts session-authenticated users and Bearer JWT credentials.

### Debugging

- Use the “Open raw JSON” button on the Coverage page to view the generated layer JSON in a new tab.
- If the embedded Navigator shows an error, paste the layer URL directly in the browser and ensure you receive JSON (not 403/404 or HTML).

## ATT&CK Navigator setup

The app now embeds the hosted Navigator at `https://mitre-attack.github.io/attack-navigator/enterprise/`. If you need a local instance in the future, see Docs/ATTACK_NAVIGATOR_SETUP.md (kept for fallback) for Angular and Docker run instructions.
