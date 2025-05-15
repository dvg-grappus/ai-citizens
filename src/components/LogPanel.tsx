import React, { useEffect, useRef } from 'react';
import { useSimStore } from '../store/simStore';

const LogPanel: React.FC = () => {
    const logMessages = useSimStore((state) => state.log);
    const logContainerRef = useRef<HTMLDivElement>(null);

    const styles: React.CSSProperties = {
        position: 'fixed',
        bottom: '8px',
        right: '8px',
        width: '200px',
        height: '300px',
        backgroundColor: 'rgba(0,0,0,0.7)',
        border: '1px solid #333',
        color: '#fff',
        fontFamily: 'monospace',
        fontSize: '10px',
        overflowY: 'scroll',
        padding: '5px',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column-reverse', // To show newest at bottom and auto-scroll effectively
    };

    // Auto-scroll to the bottom (which is the top when using column-reverse)
    useEffect(() => {
        if (logContainerRef.current) {
            logContainerRef.current.scrollTop = 0; // Scroll to top (bottom for user)
        }
    }, [logMessages]);

    return (
        <div style={styles} ref={logContainerRef}>
            {[...logMessages].reverse().map((msg, index) => ( // Reverse for newest at visual bottom
                <div key={index} style={{ whiteSpace: 'pre-wrap', marginBottom: '3px' }}>
                    {msg}
                </div>
            ))}
        </div>
    );
};

export default LogPanel; 