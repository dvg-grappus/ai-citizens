import React, { useState, useRef, useEffect } from 'react';
import { useSimStore } from '../store/simStore';

const ChatBox: React.FC = () => {
    const [message, setMessage] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);
    const { pushLog } = useSimStore(state => state.actions);
    const apiUrl = import.meta.env.VITE_API_URL;

    // Style definitions
    const containerStyle: React.CSSProperties = {
        position: 'fixed',
        bottom: 0,
        left: 0,
        width: '100%',
        padding: '10px',
        backgroundColor: 'rgba(30, 30, 30, 0.95)',
        borderTop: '1px solid #444',
        boxShadow: '0 -2px 10px rgba(0, 0, 0, 0.2)',
        display: 'flex',
        alignItems: 'center',
        zIndex: 1000,
    };

    const inputStyle: React.CSSProperties = {
        flex: 1,
        backgroundColor: '#333',
        border: 'none',
        color: '#fff',
        padding: '10px 15px',
        borderRadius: '4px',
        fontSize: '14px',
        outline: 'none',
    };

    const buttonStyle: React.CSSProperties = {
        backgroundColor: '#4c8bf5',
        color: 'white',
        border: 'none',
        borderRadius: '4px',
        padding: '10px 15px',
        marginLeft: '10px',
        fontSize: '14px',
        cursor: 'pointer',
        transition: 'background-color 0.2s',
    };

    const enhanceCheckboxStyle: React.CSSProperties = {
        display: 'flex',
        alignItems: 'center',
        color: '#aaa',
        fontSize: '12px',
        marginLeft: '15px',
    };

    // State for enhance toggle
    const [enhance, setEnhance] = useState(true);

    // Auto focus input on mount
    useEffect(() => {
        if (inputRef.current) {
            inputRef.current.focus();
        }
    }, []);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        
        if (!message.trim() || !apiUrl) return;
        
        setIsLoading(true);
        pushLog(`🔄 Processing: "${message}"`);
        
        try {
            const response = await fetch(`${apiUrl}/trigger_user_event`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, enhance }),
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Failed to send event: ${response.status} - ${errorText}`);
            }

            const result = await response.json();
            console.log('Event created:', result);
            
            // Clear the input after successful submission
            setMessage('');
            
        } catch (error) {
            console.error('Error creating event:', error);
            pushLog(`❌ Error creating event: ${error}`);
        } finally {
            setIsLoading(false);
            // Re-focus the input
            if (inputRef.current) {
                inputRef.current.focus();
            }
        }
    };

    return (
        <form onSubmit={handleSubmit} style={containerStyle}>
            <input
                ref={inputRef}
                type="text"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Create an environmental event..."
                style={inputStyle}
                disabled={isLoading}
            />
            <div style={enhanceCheckboxStyle}>
                <input
                    type="checkbox"
                    id="enhance"
                    checked={enhance}
                    onChange={(e) => setEnhance(e.target.checked)}
                />
                <label htmlFor="enhance" style={{ marginLeft: '5px' }}>Enhance with AI</label>
            </div>
            <button 
                type="submit" 
                style={{
                    ...buttonStyle,
                    backgroundColor: isLoading ? '#666' : '#4c8bf5',
                }}
                disabled={isLoading}
            >
                {isLoading ? 'Sending...' : 'Send'}
            </button>
        </form>
    );
};

export default ChatBox; 