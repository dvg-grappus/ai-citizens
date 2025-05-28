import React, { useState } from 'react';
import CanvasStage from './components/CanvasStage';
import ClockOverlay from './components/ClockOverlay';
import ControlsPanel from './components/ControlsPanel';
import LogPanel from './components/LogPanel';
import ChatBox from './components/ChatBox';
import { useWS } from './hooks/useWS';
import NPCDetailModal from './components/NPCDetailModal';
import PromptWallet from './components/PromptWallet';

function App() {
  useWS(); // Initialize WebSocket connection
  const [isPromptDrawerOpen, setIsPromptDrawerOpen] = useState(false);

  const openPromptDrawer = () => setIsPromptDrawerOpen(true);
  const closePromptDrawer = () => setIsPromptDrawerOpen(false);

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

  // Small button positioned next to ControlsPanel
  const promptWalletButtonStyles: React.CSSProperties = {
    position: 'fixed',
    top: '8px',
    left: '470px', // Increased from 410px to avoid overlap
    backgroundColor: 'rgba(59, 130, 246, 0.8)', // Blue with transparency to match panel style
    color: 'white',
    padding: '3px 8px',
    fontSize: '10px',
    borderRadius: '3px',
    border: 'none',
    cursor: 'pointer',
    zIndex: 1000,
    transition: 'background-color 0.2s ease',
  };

  return (
    <div style={appStyles}>
      <div style={canvasContainerStyles}>
        <CanvasStage /> 
      </div>
      <LogPanel /> {/* LogPanel will define its own width and take full height */}
      <ClockOverlay />
      <ControlsPanel 
        onOpenPromptWallet={openPromptDrawer}
      />
      <NPCDetailModal />
      <ChatBox /> {/* New ChatBox component */}
      <div style={{ position: 'fixed', bottom: '70px', left: '5px', color: 'cyan', fontSize: '12px', zIndex: 2000, background: 'black', padding: '2px' }}>
        AC UI - Rev.Clean
      </div>
      <PromptWallet 
        isDrawerOpen={isPromptDrawerOpen} 
        onCloseDrawer={closePromptDrawer} 
      />
    </div>
  );
}

export default App;
