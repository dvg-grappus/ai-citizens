import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css'; // Standard Vite CSS. Should exist from scaffolding.
import './App.css';   // Custom App CSS. We cleared this earlier.

const rootElement = document.getElementById('root');

if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    // <React.StrictMode> // Temporarily commented out
    <App />
    // </React.StrictMode> // Temporarily commented out
  );
} else {
  console.error("main.tsx: CRITICAL - Failed to find the root element. Check ac-web/index.html.");
}
