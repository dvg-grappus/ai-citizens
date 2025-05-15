import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css'; // Standard Vite CSS import. Ensure it exists.
import './App.css';   // Ensure this exists and is cleared or has minimal global styles.

const rootElement = document.getElementById('root');

if (rootElement) {
  console.log("main.tsx: Found root element, rendering App... CORRECTED VERSION"); // Debug log
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
} else {
  console.error("main.tsx: Failed to find the root element. Check your index.html file in ac-web.");
} 