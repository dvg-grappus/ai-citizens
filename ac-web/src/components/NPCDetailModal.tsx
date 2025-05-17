import React, { useState, useMemo } from 'react';
import { useSimStore } from '../store/simStore';
import type { NPCUIDetailData, ActionInfo, ReflectionInfo, MemoryEvent } from '../store/simStore';

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

// New tabbed container styles
const tabContainerStyles: React.CSSProperties = {
    display: 'flex',
    borderBottom: '1px solid #444',
    marginBottom: '15px',
};

const tabStyles: React.CSSProperties = {
    padding: '8px 15px',
    cursor: 'pointer',
    borderBottom: '2px solid transparent',
};

const activeTabStyles: React.CSSProperties = {
    ...tabStyles,
    borderBottom: '2px solid #76c7c0',
    color: '#76c7c0',
};

// Tag styles for memory types
const tagStyles = {
    obs: {
        backgroundColor: '#34495e', // Dark blue/gray for base observation tag
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    social: {
        backgroundColor: '#3498db', // Blue
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    environment: {
        backgroundColor: '#2ecc71', // Green
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    periodic: {
        backgroundColor: '#9b59b6', // Purple
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    dialogue: {
        backgroundColor: '#e67e22', // Orange
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    reflect: {
        backgroundColor: '#e74c3c', // Red
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    plan: {
        backgroundColor: '#f1c40f', // Yellow
        color: 'black',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    other: {
        backgroundColor: '#7f8c8d', // Gray
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    }
};

// Filter toggle button styles
const filterButtonStyles = {
    base: {
        padding: '3px 8px',
        margin: '0 4px 8px 0',
        borderRadius: '4px',
        fontSize: '0.8em',
        cursor: 'pointer',
        border: 'none',
    },
    active: {
        opacity: 1,
        fontWeight: 'bold',
    },
    inactive: {
        opacity: 0.6,
    }
};

const NPCDetailModal: React.FC = () => {
    const [activeTab, setActiveTab] = useState('actions');
    const [activeFilter, setActiveFilter] = useState('all');
    const { selectedNPCDetails, isNPCDetailModalOpen } = useSimStore(state => state);
    const { closeNPCDetailModal, refreshNPCDetailModal } = useSimStore(state => state.actions);
    const apiUrl = import.meta.env.VITE_API_URL;

    // Function to handle manual refresh
    const handleRefresh = () => {
        if (apiUrl && selectedNPCDetails) {
            refreshNPCDetailModal(apiUrl);
        }
    };
    
    // New function to debug memory types
    const handleDebugMemoryTypes = async () => {
        if (apiUrl && selectedNPCDetails) {
            try {
                const response = await fetch(`${apiUrl}/debug_memory_types/${selectedNPCDetails.npc_id}`);
                if (!response.ok) {
                    throw new Error(`Failed to fetch memory types: ${response.status} ${response.statusText}`);
                }
                const debugData = await response.json();
                console.log("DEBUG MEMORY TYPES RESPONSE:", debugData);
                alert(`Memory counts for ${debugData.npc_name}:\n\nReflect: ${debugData.reflect_count}\nPlan: ${debugData.plan_count}\nObservations: ${debugData.obs_count}`);
            } catch (error) {
                console.error("Error debugging memory types:", error);
                alert(`Error debugging memory types: ${error}`);
            }
        }
    };

    // Function to determine memory type from content and type property
    const getMemoryType = (memory: MemoryEvent): string => {
        // Check the type property from the API first
        if (memory.type === 'reflect') return 'reflect';
        if (memory.type === 'plan') return 'plan';
        if (memory.type === 'obs') {
            // Then check content for tags for observation subtypes
            const content = memory.content || '';
            if (content.includes('[Social]')) return 'social';
            if (content.includes('[Environment]')) return 'environment';
            if (content.includes('[Periodic]')) return 'periodic';
            if (content.includes('[Dialogue]')) return 'dialogue';
            return 'other';
        }
        
        // Default to the original type or 'other' if no type is determined
        return memory.type || 'other';
    };

    // Function to clean memory content by removing tags
    const cleanMemoryContent = (content: string): string => {
        return content
            .replace(/\[Social\]/g, '')
            .replace(/\[Environment\]/g, '')
            .replace(/\[Periodic\]/g, '')
            .replace(/\[Dialogue\]/g, '')
            .trim();
    };

    // Filter memory stream based on active filter
    const filteredMemoryStream = useMemo(() => {
        if (!selectedNPCDetails?.memory_stream) return [];
        
        // If 'all' is selected, show everything
        if (activeFilter === 'all') {
            return selectedNPCDetails.memory_stream;
        }
        
        return selectedNPCDetails.memory_stream.filter(memory => {
            const type = getMemoryType(memory);
            return type === activeFilter;
        });
    }, [selectedNPCDetails?.memory_stream, activeFilter]);

    if (!isNPCDetailModalOpen) {
        return null;
    }

    return (
        <div style={modalOverlayStyles} onClick={closeNPCDetailModal}>
            <div style={modalContentStyles} onClick={(e) => e.stopPropagation()}> {/* Prevent click through */}
                {selectedNPCDetails ? (
                    <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <h2 style={{ marginTop: 0, color: '#a6e22e' }}>{selectedNPCDetails.npc_name} (Details)</h2>
                            <div>
                                <button 
                                    onClick={handleDebugMemoryTypes}
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
                                <button 
                                    onClick={handleRefresh}
                                    style={{
                                        padding: '5px 10px',
                                        backgroundColor: '#555',
                                        color: 'white',
                                        border: 'none',
                                        borderRadius: '4px',
                                        cursor: 'pointer',
                                        fontSize: '0.9em'
                                    }}
                                >
                                    🔄 Refresh
                                </button>
                            </div>
                        </div>
                        
                        <div style={tabContainerStyles}>
                            <div 
                                style={activeTab === 'actions' ? activeTabStyles : tabStyles}
                                onClick={() => setActiveTab('actions')}
                            >
                                Actions
                            </div>
                            <div 
                                style={activeTab === 'memories' ? activeTabStyles : tabStyles}
                                onClick={() => setActiveTab('memories')}
                            >
                                Memory Stream
                            </div>
                            <div 
                                style={activeTab === 'reflections' ? activeTabStyles : tabStyles}
                                onClick={() => setActiveTab('reflections')}
                            >
                                Reflections
                            </div>
                            <div 
                                style={activeTab === 'plan' ? activeTabStyles : tabStyles}
                                onClick={() => setActiveTab('plan')}
                            >
                                Plan
                            </div>
                        </div>

                        {activeTab === 'actions' && (
                            <>
                                <div style={sectionTitleStyles}>Recent Completed Actions:</div>
                                {selectedNPCDetails.completed_actions && selectedNPCDetails.completed_actions.length > 0 ? (
                                    <ul style={{ listStyleType: 'none', paddingLeft: 0 }}>
                                        {selectedNPCDetails.completed_actions.map((action, index) => (
                                            <li key={index} style={listItemStyles}>
                                                {action.time} - {action.title}
                                                {action.area_name && (
                                                    <span style={{ color: '#76c7c0' }}> (in {action.area_name})</span>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                ) : (
                                    <p style={listItemStyles}>No completed actions available.</p>
                                )}

                                <div style={sectionTitleStyles}>Queued Actions ({selectedNPCDetails.queued_actions.length}):</div>
                                {selectedNPCDetails.queued_actions.length > 0 ? (
                                    <ul style={{ listStyleType: 'none', paddingLeft: 0 }}>
                                        {selectedNPCDetails.queued_actions.map((action, index) => (
                                            <li key={index} style={listItemStyles}>
                                                {action.time} - {action.title}
                                                {action.area_name && (
                                                    <span style={{ color: '#76c7c0' }}> (in {action.area_name})</span>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                ) : (
                                    <p style={listItemStyles}>No actions currently queued.</p>
                                )}
                            </>
                        )}

                        {activeTab === 'reflections' && (
                            <>
                                <div style={sectionTitleStyles}>Recent Reflections:</div>
                                {selectedNPCDetails.reflections && selectedNPCDetails.reflections.length > 0 ? (
                                    <div>
                                        {selectedNPCDetails.reflections.map((reflection, index) => (
                                            <div key={index} style={{ marginBottom: '15px' }}>
                                                {reflection.time && (
                                                    <div style={{ fontWeight: 'bold', fontSize: '0.8em', color: '#76c7c0', marginBottom: '3px' }}>
                                                        {reflection.time}
                                                    </div>
                                                )}
                                                <div style={{...listItemStyles, whiteSpace: 'pre-wrap'}}>{reflection.content}</div>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <p style={listItemStyles}>No reflections available.</p>
                                )}
                            </>
                        )}

                        {activeTab === 'plan' && (
                            <>
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
                            </>
                        )}

                        {activeTab === 'memories' && (
                            <>
                                <div style={sectionTitleStyles}>Memory Stream (Recent Events):</div>
                                
                                {/* Filter buttons */}
                                <div style={{ marginBottom: '12px' }}>
                                    <button 
                                        onClick={() => setActiveFilter('all')}
                                        style={{
                                            ...filterButtonStyles.base,
                                            backgroundColor: '#555',
                                            color: 'white',
                                            ...(activeFilter === 'all' ? filterButtonStyles.active : filterButtonStyles.inactive)
                                        }}
                                    >
                                        All
                                    </button>
                                    
                                    <button 
                                        onClick={() => setActiveFilter('social')}
                                        style={{
                                            ...filterButtonStyles.base,
                                            ...tagStyles.social,
                                            ...(activeFilter === 'social' ? filterButtonStyles.active : filterButtonStyles.inactive)
                                        }}
                                    >
                                        Social
                                    </button>
                                    
                                    <button 
                                        onClick={() => setActiveFilter('environment')}
                                        style={{
                                            ...filterButtonStyles.base,
                                            ...tagStyles.environment,
                                            ...(activeFilter === 'environment' ? filterButtonStyles.active : filterButtonStyles.inactive)
                                        }}
                                    >
                                        Environment
                                    </button>
                                    
                                    <button 
                                        onClick={() => setActiveFilter('periodic')}
                                        style={{
                                            ...filterButtonStyles.base,
                                            ...tagStyles.periodic,
                                            ...(activeFilter === 'periodic' ? filterButtonStyles.active : filterButtonStyles.inactive)
                                        }}
                                    >
                                        Periodic
                                    </button>
                                    
                                    <button 
                                        onClick={() => setActiveFilter('dialogue')}
                                        style={{
                                            ...filterButtonStyles.base,
                                            ...tagStyles.dialogue,
                                            ...(activeFilter === 'dialogue' ? filterButtonStyles.active : filterButtonStyles.inactive)
                                        }}
                                    >
                                        Dialogue
                                    </button>
                                    
                                    <button 
                                        onClick={() => setActiveFilter('reflect')}
                                        style={{
                                            ...filterButtonStyles.base,
                                            ...tagStyles.reflect,
                                            ...(activeFilter === 'reflect' ? filterButtonStyles.active : filterButtonStyles.inactive)
                                        }}
                                    >
                                        Reflect
                                    </button>
                                    
                                    <button 
                                        onClick={() => setActiveFilter('plan')}
                                        style={{
                                            ...filterButtonStyles.base,
                                            ...tagStyles.plan,
                                            ...(activeFilter === 'plan' ? filterButtonStyles.active : filterButtonStyles.inactive)
                                        }}
                                    >
                                        Plan
                                    </button>
                                    
                                    <button 
                                        onClick={() => setActiveFilter('other')}
                                        style={{
                                            ...filterButtonStyles.base,
                                            ...tagStyles.other,
                                            ...(activeFilter === 'other' ? filterButtonStyles.active : filterButtonStyles.inactive)
                                        }}
                                    >
                                        Other
                                    </button>
                                </div>
                                
                                {filteredMemoryStream.length > 0 ? (
                                    <div>
                                        {filteredMemoryStream.map((memory, index) => {
                                            const memoryType = getMemoryType(memory);
                                            const cleanContent = cleanMemoryContent(memory.content);
                                            
                                            return (
                                                <div key={index} style={{ marginBottom: '12px', borderBottom: index < filteredMemoryStream.length - 1 ? '1px solid #444' : 'none', paddingBottom: '8px' }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '3px' }}>
                                                        <div style={{ fontWeight: 'bold', fontSize: '0.8em', color: '#76c7c0' }}>
                                                            {memory.time || 'Unknown time'}
                                                        </div>
                                                        <div>
                                                            {memoryType === 'reflect' || memoryType === 'plan' ? (
                                                                // For reflect and plan, just show the single type tag
                                                                <span style={tagStyles[memoryType]}>
                                                                    {memoryType.charAt(0).toUpperCase() + memoryType.slice(1)}
                                                                </span>
                                                            ) : (
                                                                // For observation-based types, show both obs and category tags
                                                                <>
                                                                    <span style={tagStyles.obs}>obs</span>
                                                                    <span style={tagStyles[memoryType as keyof typeof tagStyles]}>
                                                                        {memoryType.charAt(0).toUpperCase() + memoryType.slice(1)}
                                                                    </span>
                                                                </>
                                                            )}
                                                        </div>
                                                    </div>
                                                    <div style={{...listItemStyles, whiteSpace: 'pre-wrap'}}>{cleanContent}</div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                ) : (
                                    <p style={listItemStyles}>No memory events available or all types filtered out.</p>
                                )}
                            </>
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
                    <div>
                        <h3 style={{ color: '#ff6b6b' }}>NPC Details Not Available</h3>
                        <p>Could not load details for this NPC. The NPC may no longer exist in the database.</p>
                        <p>This can happen if the database was recently reseeded.</p>
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
                    </div>
                )}
            </div>
        </div>
    );
};

export default NPCDetailModal; 