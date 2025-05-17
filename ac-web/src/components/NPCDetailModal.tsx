import React, { useState } from 'react';
import { useSimStore } from '../store/simStore';
import {
    modalOverlayStyles,
    modalContentStyles,
    tabContainerStyles,
    tabStyles,
    activeTabStyles,
} from './NPCDetailModal.styles';

import ActionsTab from './npc_detail_modal_tabs/ActionsTab';
import MemoryStreamTab from './npc_detail_modal_tabs/MemoryStreamTab';
import ReflectionsTab from './npc_detail_modal_tabs/ReflectionsTab';
import PlanTab from './npc_detail_modal_tabs/PlanTab';
import ModalHeader from './npc_detail_modal_tabs/ModalHeader';

const NPCDetailModal: React.FC = () => {
    const [activeTab, setActiveTab] = useState('actions');
    const { selectedNPCDetails, isNPCDetailModalOpen } = useSimStore(state => state);
    const { closeNPCDetailModal, refreshNPCDetailModal } = useSimStore(state => state.actions);
    const apiUrl = import.meta.env.VITE_API_URL;

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

    if (!isNPCDetailModalOpen) {
        return null;
    }

    return (
        <div style={modalOverlayStyles} onClick={closeNPCDetailModal}>
            <div style={modalContentStyles} onClick={(e) => e.stopPropagation()}> 
                {selectedNPCDetails ? (
                    <>
                        <ModalHeader 
                            npcName={selectedNPCDetails.npc_name}
                            onDebug={handleDebugMemoryTypes}
                        />
                        
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

                        {activeTab === 'actions' && selectedNPCDetails.completed_actions && selectedNPCDetails.queued_actions && (
                            <ActionsTab 
                                completedActions={selectedNPCDetails.completed_actions}
                                queuedActions={selectedNPCDetails.queued_actions}
                            />
                        )}

                        {activeTab === 'reflections' && selectedNPCDetails.reflections && (
                            <ReflectionsTab reflections={selectedNPCDetails.reflections} />
                        )}

                        {activeTab === 'plan' && selectedNPCDetails.current_plan_summary && (
                            <PlanTab currentPlanSummary={selectedNPCDetails.current_plan_summary} />
                        )}

                        {activeTab === 'memories' && selectedNPCDetails.memory_stream && (
                            <MemoryStreamTab memoryStream={selectedNPCDetails.memory_stream} />
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