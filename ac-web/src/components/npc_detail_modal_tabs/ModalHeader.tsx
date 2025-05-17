import React from 'react';

interface ModalHeaderProps {
    npcName: string | undefined;
    onDebug: () => void;
}

const ModalHeader: React.FC<ModalHeaderProps> = ({ npcName, onDebug }) => {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ marginTop: 0, color: '#a6e22e' }}>{npcName || 'NPC'} (Details)</h2>
            <div>
                <button 
                    onClick={onDebug}
                    style={{
                        padding: '5px 10px',
                        backgroundColor: '#444',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '0.9em',
                        marginRight: '8px'
                    }}
                >
                    🔍 Debug
                </button>
            </div>
        </div>
    );
};

export default ModalHeader; 