import React, { useEffect, useRef } from 'react';
import { useSimStore } from '../store/simStore';

const LogPanel: React.FC = () => {
    const logMessages = useSimStore((state) => state.log);
    const logContainerRef = useRef<HTMLDivElement>(null);

    const panelStyles: React.CSSProperties = {
        width: '300px', // Fixed width for the log panel
        height: '100vh', // Full viewport height
        backgroundColor: '#1e1e1e',
        borderLeft: '1px solid #333',
        color: '#ccc',
        fontFamily: 'monospace',
        fontSize: '11px',
        overflowY: 'auto', // Changed to auto for scrollbar only when needed
        padding: '10px',
        paddingBottom: '70px', // Add padding to prevent overlap with the ChatBox
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column-reverse', // Use column-reverse to show newest at bottom
    };

    const messageStyles: React.CSSProperties = {
        whiteSpace: 'pre-wrap',
        marginBottom: '4px',
        paddingBottom: '2px',
        borderBottom: '1px solid #2a2a2a' // Separator for messages
    };

    // Auto-scroll to keep newest messages visible
    useEffect(() => {
        if (logContainerRef.current) {
            logContainerRef.current.scrollTop = 0; // In column-reverse, 0 is the end (newest)
        }
    }, [logMessages]);

    return (
        <div style={panelStyles} ref={logContainerRef}>
            {/* No need to reverse the array - the store already has newest first */}
            {logMessages.map((msg, index) => ( 
                <div key={index} style={messageStyles}>
                    {msg}
                </div>
            ))}
        </div>
    );
};

export default LogPanel;
