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
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column-reverse', // Keeps newest at bottom visually
    };

    const messageStyles: React.CSSProperties = {
        whiteSpace: 'pre-wrap',
        marginBottom: '4px',
        paddingBottom: '2px',
        borderBottom: '1px solid #2a2a2a' // Separator for messages
    };

    // Auto-scroll to the bottom (which is the top when using column-reverse)
    useEffect(() => {
        if (logContainerRef.current) {
            logContainerRef.current.scrollTop = 0; 
        }
    }, [logMessages]);

    return (
        <div style={panelStyles} ref={logContainerRef}>
            {/* Add a placeholder if log is empty, or just render empty */}
            {[...logMessages].reverse().map((msg, index) => ( 
                <div key={index} style={messageStyles}>
                    {msg}
                </div>
            ))}
        </div>
    );
};

export default LogPanel;
