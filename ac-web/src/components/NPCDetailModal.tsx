import React from 'react';
import { useSimStore } from '../store/simStore';
import type { NPCUIDetailData, ActionInfo } from '../store/simStore';

const modalOverlayStyles: React.CSSProperties = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1000,
};

const modalContentStyles: React.CSSProperties = {
    background: '#2c2c2c',
    color: '#e0e0e0',
    padding: '20px',
    borderRadius: '8px',
    minWidth: '400px',
    maxWidth: '600px',
    maxHeight: '80vh',
    overflowY: 'auto',
    border: '1px solid #444',
    boxShadow: '0 4px 15px rgba(0,0,0,0.2)',
};

const sectionTitleStyles: React.CSSProperties = {
    marginTop: '15px',
    marginBottom: '8px',
    fontSize: '1.1em',
    color: '#76c7c0', // Teal accent
    borderBottom: '1px solid #444',
    paddingBottom: '5px',
};

const listItemStyles: React.CSSProperties = {
    padding: '3px 0',
    fontSize: '0.9em',
};

const NPCDetailModal: React.FC = () => {
    // Use specific selectors for each piece of state
    const isNPCDetailModalOpen = useSimStore((state) => state.isNPCDetailModalOpen);
    const selectedNPCDetails = useSimStore((state) => state.selectedNPCDetails);
    const closeNPCDetailModal = useSimStore((state) => state.actions.closeNPCDetailModal);

    if (!isNPCDetailModalOpen) {
        return null;
    }

    return (
        <div style={modalOverlayStyles} onClick={closeNPCDetailModal}>
            <div style={modalContentStyles} onClick={(e) => e.stopPropagation()}> {/* Prevent click through */}
                {selectedNPCDetails ? (
                    <>
                        <h2 style={{ marginTop: 0, color: '#a6e22e' }}>{selectedNPCDetails.npc_name} (Details)</h2>
                        
                        {selectedNPCDetails.last_completed_action && (
                            <div style={sectionTitleStyles}>Last Completed Action:</div>
                        )}
                        {selectedNPCDetails.last_completed_action && (
                            <div style={listItemStyles}>
                                {selectedNPCDetails.last_completed_action.time} - {selectedNPCDetails.last_completed_action.title}
                            </div>
                        )}

                        <div style={sectionTitleStyles}>Queued Actions ({selectedNPCDetails.queued_actions.length}):</div>
                        {selectedNPCDetails.queued_actions.length > 0 ? (
                            <ul style={{ listStyleType: 'none', paddingLeft: 0 }}>
                                {selectedNPCDetails.queued_actions.map((action, index) => (
                                    <li key={index} style={listItemStyles}>
                                        {action.time} - {action.title}
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p style={listItemStyles}>No actions currently queued.</p>
                        )}

                        {selectedNPCDetails.latest_reflection && (
                            <>
                                <div style={sectionTitleStyles}>Latest Reflection:</div>
                                <p style={{...listItemStyles, whiteSpace: 'pre-wrap'}}>{selectedNPCDetails.latest_reflection}</p>
                            </>
                        )}

                        <div style={sectionTitleStyles}>Current Day's Plan Summary:</div>
                        {selectedNPCDetails.current_plan_summary.length > 0 ? (
                            <ul style={{ listStyleType: 'decimal', paddingLeft: '20px' }}>
                                {selectedNPCDetails.current_plan_summary.map((actionStr, index) => (
                                    <li key={index} style={listItemStyles}>{actionStr}</li>
                                ))}
                            </ul>
                        ) : (
                            <p style={listItemStyles}>No plan summary available for the current day.</p>
                        )}
                        
                        <button 
                            onClick={closeNPCDetailModal} 
                            style={{
                                display: 'block',
                                marginTop: '20px',
                                padding: '8px 15px',
                                backgroundColor: '#555',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer'
                            }}
                        >
                            Close
                        </button>
                    </>
                ) : (
                    <p>Loading NPC details...</p>
                )}
            </div>
        </div>
    );
};

export default NPCDetailModal; 