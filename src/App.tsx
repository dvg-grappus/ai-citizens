import React from 'react';
import CanvasStage from './components/CanvasStage';
import ClockOverlay from './components/ClockOverlay';
import ControlsPanel from './components/ControlsPanel';
import LogPanel from './components/LogPanel';
import { useWS } from './hooks/useWS';
import './App.css'; // Ensure this file is present and cleared

function App() {
  console.log("Rendering App component - CORRECTED VERSION"); // Debug log
  useWS(); // Initialize WebSocket connection

  return (
    <>
      <ControlsPanel />
      <CanvasStage />
      <ClockOverlay />
      <LogPanel />
      <div style={{ position: 'fixed', bottom: '5px', left: '5px', color: 'lime', fontSize: '12px', zIndex: 2000, background: 'black', padding: '2px' }}>
        Artificial Citizens UI - Active
      </div>
    </>
  );
}

export default App; 