import React, { useState } from 'react';

const ControlsPanel: React.FC = () => {
    const [isPaused, setIsPaused] = useState(false);
    const apiUrl = import.meta.env.VITE_API_URL;

    const handlePauseToggle = () => {
        setIsPaused(!isPaused);
        console.log(isPaused ? 'Resuming simulation (placeholder)' : 'Pausing simulation (placeholder)');
    };

    const handleManualTick = async () => {
        if (!apiUrl) {
            console.error('API URL not defined for manual tick');
            return;
        }
        try {
            const response = await fetch(`${apiUrl}/tick`, { method: 'POST' });
            if (!response.ok) {
                throw new Error(`Failed to send tick: ${response.status}`);
            }
            const result = await response.json();
            console.log('Manual tick sent:', result);
        } catch (error) {
            console.error('Error sending manual tick:', error);
        }
    };

    const handleSetSpeed = (speed: number) => {
        console.log(`Set speed to ${speed}x (placeholder)`);
    };

    const styles: React.CSSProperties = {
        position: 'fixed',
        top: '8px',
        left: '8px',
        backgroundColor: 'rgba(50,50,50,0.8)',
        padding: '5px',
        borderRadius: '3px',
        zIndex: 1000,
        display: 'flex',
        gap: '5px'
    };

    const buttonStyles: React.CSSProperties = {
        padding: '3px 6px',
        fontSize: '10px',
        cursor: 'pointer'
    };

    return (
        <div style={styles}>
            <button style={buttonStyles} onClick={handlePauseToggle}>
                {isPaused ? 'Resume' : 'Pause'}
            </button>
            <button style={buttonStyles} onClick={handleManualTick} disabled={!isPaused}>
                Step Tick
            </button>
            <button style={buttonStyles} onClick={() => handleSetSpeed(1)}>
                x1 Speed
            </button>
            <button style={buttonStyles} onClick={() => handleSetSpeed(2)}>
                x2 Speed
            </button>
        </div>
    );
};

export default ControlsPanel;
