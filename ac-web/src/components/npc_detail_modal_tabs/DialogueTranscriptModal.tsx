import React, { useState, useEffect } from 'react';
import { modalOverlayStyles, modalContentStyles, sectionTitleStyles, listItemStyles } from '../NPCDetailModal.styles';
// import { useSimStore } from '../../store/simStore'; // To get API URL - REMOVED

interface DialogueTurn {
    speaker_name: string;
    text: string;
    sim_min_of_turn: number;
    timestamp_str: string;
}

interface DialogueTranscriptModalProps {
    isOpen: boolean;
    onClose: () => void;
    dialogueId: string | null;
    // apiUrl: string; // Optional: Pass if available, otherwise use default
}

// Define a default API base URL (adjust if your backend runs elsewhere)
const DEFAULT_API_BASE_URL = 'http://localhost:8000'; 

const DialogueTranscriptModal: React.FC<DialogueTranscriptModalProps> = ({ isOpen, onClose, dialogueId }) => {
    const [transcript, setTranscript] = useState<DialogueTurn[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // const apiUrlFromStore = useSimStore(state => state.apiUrl); // Get API URL from Zustand store - REMOVED
    const apiUrl = DEFAULT_API_BASE_URL; // Use the default or prop

    useEffect(() => {
        if (isOpen && dialogueId && apiUrl) {
            const fetchTranscript = async () => {
                setIsLoading(true);
                setError(null);
                try {
                    const response = await fetch(`${apiUrl}/api/v1/dialogues/${dialogueId}/transcript`);
                    if (!response.ok) {
                        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
                        throw new Error(`Failed to fetch transcript: ${response.status} ${errorData.detail || response.statusText}`);
                    }
                    const data = await response.json();
                    setTranscript(data.turns || []);
                } catch (err: any) {
                    setError(err.message || 'An unknown error occurred');
                    setTranscript([]);
                }
                setIsLoading(false);
            };
            fetchTranscript();
        }
    }, [isOpen, dialogueId, apiUrl]);

    if (!isOpen || !dialogueId) {
        return null;
    }

    return (
        <div style={modalOverlayStyles} onClick={onClose}>
            <div style={{...modalContentStyles, minWidth: '500px', maxWidth: '700px'}} onClick={(e) => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h2 style={{...sectionTitleStyles, marginTop: 0, borderBottom: 'none'}}>Dialogue Transcript</h2>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#e0e0e0', fontSize: '1.5em', cursor: 'pointer' }}>&times;</button>
                </div>
                
                {isLoading && <p style={listItemStyles}>Loading transcript...</p>}
                {error && <p style={{...listItemStyles, color: '#e74c3c'}}>Error: {error}</p>}
                
                {!isLoading && !error && transcript.length === 0 && (
                    <p style={listItemStyles}>No turns found for this dialogue.</p>
                )}

                {!isLoading && !error && transcript.length > 0 && (
                    <div style={{ maxHeight: '60vh', overflowY: 'auto', marginTop: '10px' }}>
                        {transcript.map((turn, index) => (
                            <div key={index} style={{ marginBottom: '10px', paddingBottom: '8px', borderBottom: index < transcript.length - 1 ? '1px solid #444' : 'none' }}>
                                <div style={{ fontSize: '0.8em', color: '#76c7c0', marginBottom: '3px' }}>
                                    {turn.timestamp_str} - <strong>{turn.speaker_name}</strong>
                                </div>
                                <div style={listItemStyles}>{turn.text}</div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default DialogueTranscriptModal; 