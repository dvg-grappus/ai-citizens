import React from 'react';
import CanvasStage from './components/CanvasStage';
import ClockOverlay from './components/ClockOverlay';
import ControlsPanel from './components/ControlsPanel';
import LogPanel from './components/LogPanel';
import ChatBox from './components/ChatBox';
import { useWS } from './hooks/useWS';
import NPCDetailModal from './components/NPCDetailModal';
import './App.css'; // Ensure this file is present and cleared or has minimal styles

function App() {
  useWS(); // Initialize WebSocket connection

  const appStyles: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'row',
    height: '100vh',
    width: '100vw',
    overflow: 'hidden', // Prevent scrollbars from main layout
    backgroundColor: '#121212', // Overall page background
    paddingBottom: '60px', // Add padding at bottom to accommodate the ChatBox height
  };

  const canvasContainerStyles: React.CSSProperties = {
    flexGrow: 1, // Canvas takes remaining space
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    padding: '10px', // Some padding around canvas
    overflow: 'auto', // In case canvas is larger than container
  };

  return (
    <div style={appStyles}>
      <div style={canvasContainerStyles}>
        <CanvasStage /> 
      </div>
      <LogPanel /> {/* LogPanel will define its own width and take full height */}
      <ClockOverlay />
      <ControlsPanel />
      <NPCDetailModal />
      <ChatBox /> {/* New ChatBox component */}
      <div style={{ position: 'fixed', bottom: '70px', left: '5px', color: 'cyan', fontSize: '12px', zIndex: 2000, background: 'black', padding: '2px' }}>
        AC UI - Rev.Clean
      </div>
    </div>
  );
}

export default App;
